#!/usr/bin/env python3
"""Turn an edit plan plus measured signals into an ffmpeg filter graph, a render command, and a
manifest the QA step can check the render against.

  python build_edit.py plan.json --signals signals.json --filter filter.txt --manifest manifest.json
  python build_edit.py plan.json --signals signals.json --render EDIT.mp4      # and run it

plan.json:
{
  "source": "in.mp4",
  "cuts":      [[0, 723.2, "banter and setup"], [1584, 1623, "fumbling"]],
  "stretches": [ {"id": "S025", "action": "cap", "seconds": 3, "why": "tab flick, then waiting"},
                 {"id": "S009", "action": "cut", "why": "spinner only"},
                 {"range": [5217.9, 5226.4], "action": "cap", "seconds": 4, "why": "..."} ],
  "min_silence": 3.0,        trim dead air at least this long...
  "leave_silence": 1.0,      ...down to this
  "max_speed": 8,            fastest a capped stretch may run
  "regions": { "rail": [0.004, 0.085, 0.192, 0.99] },      fractions x0,y0,x1,y1
  "blur":  [ {"start": 4302, "end": 4356, "regions": ["rail"]} ],
  "mute":  [[3148.96, 3149.54]],       SOURCE seconds, word start -> word end from the words file
  "flag_words": "fuck|shit|...",       optional: regex over the words file; default is a profanity
                                       list. Every hit must be cut or muted or listed in "allow"
  "allow": ["damn", 4624.65],          optional: a word (every occurrence) or a start time to leave
  "disclosures": [ {"start": 4305, "end": 4420, "what": "client names", "region": "rail"} ],
                             optional: from the visual pass; each must be cut or blurred or the build dies
  "words": "in.words.tsv"    optional: word timings (local-transcription --words TSV, or JSON
                             [[start, end, "word"], ...]) - cut edges snap to word gaps
}

How dead air is derived - the part that used to be a hand-pasted list:
  signals.json (from scan_signals.py) holds every silence and every motion run inside it.
  Content = speech + motion. A silence is trimmed only where the screen was still. Motion inside a
  silence is a STRETCH and is kept in full unless the plan says otherwise:
    keep  (default)  leave it exactly as recorded
    cap N            speed-ramp it so it lasts N seconds - every frame of action survives, faster
    cut              it was a spinner / idle screen; treat the silence as still
  Nothing is protected by being listed; it is protected by having been measured.

The graph is trim+concat rather than select, so ramped pieces are first-class. Every edit point
is snapped to the frame grid and video is trimmed by frame index, so the video and audio of each
piece are the same length and the output matches the manifest to the sample. Pieces are split at
blur-window edges and the crop/blur/overlay chain runs only inside the pieces that need it.

Refuses to build on a conflict (a stretch inside a cut, an unknown blur region, a cap longer than
the stretch, a listed disclosure that is neither cut nor blurred, a flagged word that is neither cut
nor muted, a mute window that covers no word - the classic sign of output times pasted in as source
times) and prints what it spared and what each mute silences, so the decision is visible.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_FLAG_WORDS = r"fuck|shit|bitch|asshole|ass|cunt|bastard|goddamn|dick|prick|cock|wanker"


def hms(t):
    h, rem = divmod(float(t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def die(msg):
    sys.exit(f"ERROR: {msg}")


def overlaps(a, b, c, d):
    return not (b <= c or a >= d)


# ---------------------------------------------------------------- plan resolution

def load_words(plan, base):
    w = plan.get("words")
    if not w:
        return None
    p = Path(w) if Path(w).is_absolute() else base / w
    text = p.read_text(encoding="utf-8")
    out = []
    if p.suffix.lower() in (".tsv", ".txt"):
        # local-transcription's --words output: start<TAB>end<TAB>word
        for line in text.splitlines():
            parts = line.split("	")
            if len(parts) >= 2:
                try:
                    out.append((float(parts[0]), float(parts[1]), parts[2].strip() if len(parts) > 2 else ""))
                except ValueError:
                    continue  # header or comment line
    else:
        for item in json.loads(text):
            if isinstance(item, dict):
                out.append((float(item["start"]), float(item["end"]), str(item.get("word", ""))))
            else:
                out.append((float(item[0]), float(item[1]), str(item[2]) if len(item) > 2 else ""))
    return sorted(out)


def snap(t, words, window):
    """Move t to the nearest gap between words within +-window. Returns (t', moved)."""
    if not words:
        return t, False
    best, best_d = None, window
    for i in range(len(words) - 1):
        gap_a, gap_b = words[i][1], words[i + 1][0]
        if gap_b - gap_a < 0.15:
            continue
        if gap_a <= t <= gap_b:
            return t, False                       # already in a gap
        mid = (gap_a + gap_b) / 2
        d = abs(mid - t)
        if d < best_d:
            best, best_d = mid, d
    return (round(best, 2), True) if best is not None else (t, False)


def resolve_stretches(plan, signals):
    by_id = {s["id"]: s for s in signals.get("stretches", [])}
    decided = {}                                   # (start,end) -> decision
    for d in plan.get("stretches", []):
        if "id" in d:
            if d["id"] not in by_id:
                die(f"stretch {d['id']} is not in signals.json")
            s = by_id[d["id"]]
            rng = (s["start"], s["end"])
        else:
            rng = (float(d["range"][0]), float(d["range"][1]))
        act = d.get("action", "keep")
        if act not in ("keep", "cap", "cut"):
            die(f"stretch {rng}: unknown action '{act}'")
        if act == "cap":
            secs = float(d.get("seconds", 0))
            if secs <= 0:
                die(f"stretch {rng}: cap needs 'seconds'")
            if secs >= rng[1] - rng[0]:
                die(f"stretch {rng}: cap of {secs}s is not shorter than the stretch "
                    f"({rng[1]-rng[0]:.1f}s) - use keep")
        decided[rng] = dict(d, range=rng, action=act)
    return decided


def build_timeline(plan, signals, words):
    """Return ordered pieces [{a, b, speed}], removals [{a, b, why, kind}], report."""
    dur = float(signals["duration"])
    lo = float(plan.get("min_silence", signals.get("params", {}).get("min_silence", 3.0)))
    leave = float(plan.get("leave_silence", 1.0))
    max_speed = float(plan.get("max_speed", 8))
    snap_win = float(plan.get("snap_window", 0.75))

    # structural cuts, edges snapped to word gaps
    cuts, snapped = [], []
    for a, b, *why in plan.get("cuts", []):
        a, b = float(a), float(b)
        a2, ma = snap(a, words, snap_win)
        b2, mb = snap(b, words, snap_win)
        if ma or mb:
            snapped.append((a, b, a2, b2))
        cuts.append({"a": a2, "b": b2, "why": (why[0] if why else ""), "kind": "cut"})
    cuts.sort(key=lambda c: c["a"])

    # stretches: decisions
    decided = resolve_stretches(plan, signals)
    motion = []                                    # runs that count as content
    ramps = []                                     # (a, b, speed, why)
    junk = []                                      # runs demoted to still
    for run in signals.get("motion", []):
        ra, rb = float(run[0]), float(run[1])
        d = decided.get((ra, rb))
        if d is None:
            d = next((v for k, v in decided.items()
                      if "range" in v and k[0] <= ra and rb <= k[1]), None)
        act = d["action"] if d else "keep"
        if act == "cut":
            junk.append((ra, rb, d.get("why", "")))
        else:
            motion.append((ra, rb))
    for rng, d in decided.items():
        if d["action"] == "cap":
            a, b = rng
            speed = (b - a) / float(d["seconds"])
            if speed > max_speed:
                # too much compression for a ramp: run at max_speed and drop the tail
                keep_len = float(d["seconds"]) * max_speed
                ramps.append((a, a + keep_len, max_speed, d.get("why", "")))
                junk.append((a + keep_len, b, f"tail beyond {max_speed}x cap"))
            else:
                ramps.append((a, b, round(speed, 3), d.get("why", "")))
    # conflicts: a measured motion run inside a structural cut is simply swallowed (the cut is a
    # content decision and outranks a measurement), but an explicit keep/cap that contradicts a
    # cut is two opposite statements about the same footage and is refused.
    swallowed_motion = [(a, b) for a, b in motion
                        if any(overlaps(a, b, c["a"], c["b"]) for c in cuts)]
    motion = [(a, b) for a, b in motion if (a, b) not in swallowed_motion]
    for rng, d in decided.items():
        if d["action"] in ("keep", "cap"):
            for c in cuts:
                if overlaps(rng[0], rng[1], c["a"], c["b"]):
                    die(f"stretch {hms(rng[0])}-{hms(rng[1])} is marked '{d['action']}' but lies "
                        f"inside cut '{c['why']}' ({hms(c['a'])}-{hms(c['b'])}). "
                        f"One of them is wrong.")

    # dead air = silence minus content (motion), then trimmed to leave_silence
    junk_spans = [(a, b) for a, b, _ in junk]
    dead, spared = [], []
    for sa, sb in signals.get("silence", []):
        sa, sb = float(sa), float(sb)
        if sb - sa < lo:
            continue
        pieces = [(sa, sb)]
        for ma, mb in motion:
            if any(overlaps(ma, mb, ja, jb) for ja, jb in junk_spans):
                continue
            nxt = []
            for pa, pb in pieces:
                if not overlaps(ma, mb, pa, pb):
                    nxt.append((pa, pb))
                    continue
                spared.append((ma, mb))
                if pa < ma:
                    nxt.append((pa, ma))
                if mb < pb:
                    nxt.append((mb, pb))
            pieces = nxt
        for pa, pb in pieces:
            if pb - pa >= lo:
                pad = leave / 2
                if pb - pad > pa + pad:
                    dead.append({"a": round(pa + pad, 2), "b": round(pb - pad, 2),
                                 "why": "dead air", "kind": "silence"})
    spared = sorted(set(spared))

    # a ramped region is never also trimmed as dead air
    ramp_spans = [(a, b) for a, b, *_ in ramps]
    dead = [d for d in dead if not any(overlaps(d["a"], d["b"], a, b) for a, b in ramp_spans)]

    # every edit point lands on a frame boundary. The video trim can only cut on frames and the
    # audio trim cuts on samples; concat pads each segment to the longer of the two, so an edge
    # between frames grows the output by up to a frame per join - 30 joins at 25 fps drifted the
    # manifest 170 ms by the end. Snapping first makes both streams the same length exactly.
    fps = float(signals.get("fps") or 25)

    def fq(t):
        return round(round(t * fps) / fps, 4)

    for d in dead:
        d["a"], d["b"] = fq(d["a"]), fq(d["b"])
    for c in cuts:
        c["a"], c["b"] = fq(c["a"]), fq(c["b"])
    ramps = [(fq(a), fq(b), sp, why) for a, b, sp, why in ramps]

    # merge removals: cuts + dead (silence inside a cut is swallowed)
    removals = []
    for r in sorted(cuts + dead, key=lambda r: r["a"]):
        if removals and r["a"] <= removals[-1]["b"] + 0.05:
            if r["b"] > removals[-1]["b"]:
                removals[-1]["b"] = r["b"]
            if r["kind"] == "cut":
                removals[-1]["why"] = r["why"]
                removals[-1]["kind"] = "cut"
        else:
            removals.append(dict(r))

    # pieces: walk the timeline, splitting kept spans at ramp boundaries
    pieces, pos = [], 0.0
    bounds = [(r["a"], r["b"]) for r in removals]
    for a, b in bounds + [(dur, dur)]:
        if a - pos > 0.4:
            seg = [(pos, a)]
            for ra, rb, sp, why in sorted(ramps):
                nxt = []
                for s in seg:
                    if len(s) != 2:
                        nxt.append(s)
                        continue
                    x, y = s
                    if not overlaps(ra, rb, x, y):
                        nxt.append((x, y))
                        continue
                    if x < ra:
                        nxt.append((x, ra))
                    nxt.append((max(x, ra), min(y, rb), sp, why))
                    if rb < y:
                        nxt.append((rb, y))
                seg = nxt
            for s in seg:
                if len(s) == 2:
                    pieces.append({"a": fq(s[0]), "b": fq(s[1]), "speed": 1.0})
                else:
                    pieces.append({"a": fq(s[0]), "b": fq(s[1]), "speed": s[2], "why": s[3]})
        pos = max(pos, b)
    pieces = [p for p in pieces if p["b"] - p["a"] > 1.5 / fps]

    # split pieces at blur-window edges and tag each with the regions active inside it, so the
    # blur chain runs only on frames that get blurred. Running it over the whole source with
    # enable= costs a frame copy per region per frame (the overlay makes the shared frame
    # writable even when disabled) - about a quarter of the render time per region, every time.
    edges = set()
    for w in plan.get("blur", []):
        w["start"], w["end"] = fq(float(w["start"])), fq(float(w["end"]))
        edges.update((w["start"], w["end"]))
    out = []
    for p in pieces:
        cuts_at = sorted(e for e in edges if p["a"] + 1.5 / fps < e < p["b"] - 1.5 / fps)
        lo = p["a"]
        for e in cuts_at + [p["b"]]:
            q = dict(p, a=lo, b=e)
            mid = (lo + e) / 2
            regs = []
            for w in plan.get("blur", []):
                if w["start"] <= mid < w["end"]:
                    regs += [r for r in w["regions"] if r not in regs]
            q["blur"] = regs
            out.append(q)
            lo = e
    pieces = out

    # output times
    t = 0.0
    for p in pieces:
        p["out_a"] = round(t, 3)
        t += (p["b"] - p["a"]) / p["speed"]
        p["out_b"] = round(t, 3)

    report = {"snapped": snapped, "spared": spared, "junk": junk, "ramps": ramps,
              "swallowed_motion": swallowed_motion,
              "dead_count": len(dead), "dead_seconds": sum(d["b"] - d["a"] for d in dead),
              "cut_seconds": sum(c["b"] - c["a"] for c in cuts)}
    return pieces, removals, report


def s2o(t, pieces):
    for p in pieces:
        if t < p["a"]:
            return None
        if t < p["b"]:
            return p["out_a"] + (t - p["a"]) / p["speed"]
    return None


# ---------------------------------------------------------------- filter graph

def even(v):
    return int(v) // 2 * 2


def build_graph(plan, signals, pieces, blur_strength):
    W, H = int(signals["width"]), int(signals["height"])
    fps = signals.get("fps", 25)
    regions = plan.get("regions", {})
    for w in plan.get("blur", []):
        for r in w["regions"]:
            if r not in regions:
                die(f"blur window references undefined region '{r}'")
    used = sorted({r for p in pieces for r in p.get("blur", [])})
    n = len(pieces)
    # constant frame rate from t=0 first, so frame N sits at exactly N/fps and the per-piece
    # trims can select by frame index - the edges build_timeline snapped to
    parts = [f"[0:v]fps={fps}:start_time=0,split={n}" + "".join(f"[p{i}]" for i in range(n)),
             f"[0:a]asplit={n}" + "".join(f"[q{i}]" for i in range(n))]
    for i, p in enumerate(pieces):
        a, b, sp = p["a"], p["b"], p["speed"]
        fa, fb = int(round(a * fps)), int(round(b * fps))
        v = f"[p{i}]trim=start_frame={fa}:end_frame={fb},setpts=PTS-STARTPTS"
        regs = p.get("blur", [])
        if regs:
            # blur is per piece: trim first, then crop/blur/overlay only the frames in the window
            v += f",split={len(regs) + 1}" + "".join(f"[t{i}_{j}]" for j in range(len(regs) + 1))
            parts.append(v)
            cur = f"[t{i}_0]"
            for j, r in enumerate(regs, 1):
                x0, y0, x1, y1 = regions[r]
                x, y = even(x0 * W), even(y0 * H)
                w, h = even(x1 * W - x), even(y1 * H - y)
                parts.append(f"[t{i}_{j}]crop={w}:{h}:{x}:{y},avgblur={blur_strength}[b{i}_{j}]")
                parts.append(f"{cur}[b{i}_{j}]overlay={x}:{y}[o{i}_{j}]")
                cur = f"[o{i}_{j}]"
            v = f"{cur}setpts=PTS"
        au = f"[q{i}]atrim={a}:{b},asetpts=PTS-STARTPTS"
        if sp != 1.0:
            v += f"/{sp}"
            au += f",atempo={sp}"
        parts.append(v + f"[v{i}o]")
        parts.append(au + f"[a{i}o]")
    parts.append("".join(f"[v{i}o][a{i}o]" for i in range(n))
                 + f"concat=n={n}:v=1:a=1[vc][ac]")
    parts.append(f"[vc]fps={fps}[vout]")
    parts.append("[ac]anull[aout]")
    return ";".join(parts), used


def pick_encoder(choice):
    """Find a hardware H.264 encoder that actually works, by test-encoding a few frames.
    The -encoders list only says what ffmpeg was built with; nvenc is listed on machines with
    no NVIDIA card and fails at open time."""
    if choice != "auto":
        return choice
    for name in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                                "-i", "color=c=black:s=256x144:d=0.2", "-c:v", name,
                                "-f", "null", "-"], capture_output=True, timeout=30)
        except FileNotFoundError:
            die("ffmpeg not on PATH")
        except subprocess.TimeoutExpired:
            continue
        if r.returncode == 0:
            return name
    return "libx264"


def encoder_args(enc):
    if enc == "libx264":
        return ["-c:v", "libx264", "-crf", "20", "-preset", "medium"]
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "23"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp",
                "-qp_i", "22", "-qp_p", "24"]
    return ["-c:v", enc]


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--signals", help="signals.json from scan_signals.py (default: plan['signals'])")
    ap.add_argument("--filter", default="filter.txt")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--blur-strength", type=int, default=26)
    ap.add_argument("--encoder", default="auto",
                    help="auto | libx264 | h264_nvenc | h264_qsv | h264_amf")
    ap.add_argument("--render", metavar="OUT.mp4", help="run the render (and the mute pass) now")
    args = ap.parse_args()

    plan_path = Path(args.plan)
    base = plan_path.parent
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sig_path = args.signals or plan.get("signals")
    if not sig_path:
        die("no signals.json - run scan_signals.py first and pass --signals")
    sig_path = Path(sig_path) if Path(sig_path).is_absolute() else base / sig_path
    signals = json.loads(sig_path.read_text(encoding="utf-8"))
    source = plan.get("source") or signals.get("source")
    words = load_words(plan, base)

    pieces, removals, rep = build_timeline(plan, signals, words)
    if not pieces:
        die("cuts remove the entire video")
    total = pieces[-1]["out_b"]

    # every disclosure the visual pass found must be inside a cut, or inside a blur window that
    # covers its region - catch it here, before an hour-long render, not in QA after it
    cut_spans = [(r["a"], r["b"]) for r in removals if r["kind"] == "cut"]
    for d in plan.get("disclosures", []):
        a, b, what, region = float(d["start"]), float(d["end"]), d.get("what", "?"), d.get("region")
        in_cut = any(ca <= a and b <= cb for ca, cb in cut_spans)
        in_blur = any(float(w["start"]) <= a and b <= float(w["end"])
                      and (region is None or region in w["regions"]) for w in plan.get("blur", []))
        if not (in_cut or in_blur):
            die(f"disclosure {hms(a)}-{hms(b)} '{what}' is neither cut nor blurred"
                + (f" (needs region '{region}')" if region else "") + " - add a cut or a blur window")

    graph, used = build_graph(plan, signals, pieces, args.blur_strength)
    Path(args.filter).write_text(graph, encoding="utf-8")

    # mutes, remapped
    mutes, swallowed = [], []
    for a, b in plan.get("mute", []):
        oa, ob = s2o(float(a), pieces), s2o(float(b), pieces)
        if oa is None or ob is None:
            swallowed.append((float(a), float(b)))
        else:
            mutes.append((round(oa, 2), round(ob, 2)))

    # words: every mute must land on words, and every flagged word must be cut, muted or allowed.
    # Both checks exist because of one real render that muted "tested this" and "can't wait" -
    # output times from an earlier cut pasted into the plan as source times - and passed QA,
    # because QA only measures the windows it is told about.
    muted_words = []
    if words:
        for a, b in plan.get("mute", []):
            a, b = float(a), float(b)
            hit = [w for w in words if overlaps(a, b, w[0], w[1])]
            text = " ".join(w[2] for w in hit).strip() or "?"
            muted_words.append((a, b, text))
            if not hit:
                die(f"mute {hms(a)}-{hms(b)} covers no word in {plan.get('words')} - mute times are "
                    "SOURCE seconds, word start to word end (output times from a previous cut?)")
        import re
        flag_re = re.compile(plan.get("flag_words") or DEFAULT_FLAG_WORDS, re.I)
        allow = plan.get("allow", [])
        allow_words = {str(x).lower() for x in allow if not isinstance(x, (int, float))}
        allow_times = [float(x) for x in allow if isinstance(x, (int, float))]
        uncovered = []
        for wa, wb, text in words:
            core = text.strip().strip(".,!?;:\"'").lower()
            if not core or not flag_re.search(core):
                continue
            if core in allow_words or any(abs(wa - t) < 0.5 for t in allow_times):
                continue
            if any(ca <= wa and wb <= cb for ca, cb in cut_spans):
                continue
            if any(float(a) - 0.05 <= wa and wb <= float(b) + 0.05 for a, b in plan.get("mute", [])):
                continue
            uncovered.append((wa, wb, text))
        if uncovered:
            lines = "\n".join(f'  [{wa:.2f}, {wb:.2f}]   "{t}"  at {hms(wa)}' for wa, wb, t in uncovered)
            die(f"{len(uncovered)} flagged word(s) neither cut nor muted - add each to \"mute\" "
                f"or to \"allow\":\n{lines}")

    # verify points: blur windows x3, each join, each ramp
    checks = {"blur": [], "joins": [], "ramps": [], "mutes": mutes}
    for w in plan.get("blur", []):
        for frac in (0.25, 0.5, 0.75):
            t = float(w["start"]) + (float(w["end"]) - float(w["start"])) * frac
            o = s2o(t, pieces)
            if o is not None:
                checks["blur"].append({"out": round(o, 2), "src": round(t, 2),
                                       "regions": w["regions"]})
    for r in removals:
        o = s2o(r["b"], pieces)
        if o is not None:
            checks["joins"].append({"out": round(o, 3), "removed": [r["a"], r["b"]],
                                    "why": r["why"], "kind": r["kind"]})
    for p in pieces:
        if p["speed"] != 1.0:
            checks["ramps"].append({"out": [p["out_a"], p["out_b"]], "src": [p["a"], p["b"]],
                                    "speed": p["speed"]})

    enc = pick_encoder(args.encoder)
    render = (["ffmpeg", "-hide_banner", "-i", source, "-/filter_complex", args.filter,
               "-map", "[vout]", "-map", "[aout]"] + encoder_args(enc)
              + ["-c:a", "aac", "-b:a", "128k", "-map_chapters", "-1",
                 "-movflags", "+faststart", "-y"])
    mute_cmd = None
    if mutes:
        # AAC frames are ~21 ms; pad each window so the frame boundaries fall inside the mute
        expr = "+".join(f"between(t,{max(0.0, a - 0.05):.3f},{b + 0.05:.3f})" for a, b in mutes)
        mute_cmd = ["ffmpeg", "-hide_banner", "-i", "EDIT.mp4", "-af",
                    f"volume=0:enable='{expr}'", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-map_chapters", "-1", "-y"]

    manifest = {
        "source": source, "signals": str(sig_path), "plan": str(plan_path),
        "source_duration": signals["duration"], "output_duration": round(total, 3),
        "width": signals["width"], "height": signals["height"], "fps": signals.get("fps"),
        "pieces": pieces, "removals": removals, "mutes_out": mutes, "mutes_swallowed": swallowed,
        "mutes_words": [{"src": [a, b], "out": s2o(a, pieces), "words": t} for a, b, t in muted_words],
        "checks": checks, "blur_regions_used": used, "regions": plan.get("regions", {}),
        "blur": plan.get("blur", []), "report": rep, "encoder": enc,
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    # ---- report
    print(f"source    {hms(signals['duration'])}")
    print(f"output    {hms(total)}   {len(pieces)} pieces, {len(removals)} removals")
    print(f"cuts      {rep['cut_seconds']/60:.1f} min structural")
    print(f"dead air  {rep['dead_count']} trims, {rep['dead_seconds']/60:.1f} min removed")
    print(f"spared    {len(rep['spared'])} silent-but-moving stretches kept "
          f"({sum(b-a for a,b in rep['spared']):.0f}s) - screen was doing something")
    for a, b, sp, why in rep["ramps"]:
        print(f"ramped    {hms(a)}-{hms(b)} at {sp}x  {why}")
    if rep["swallowed_motion"]:
        print(f"inside cuts {len(rep['swallowed_motion'])} motion runs fell inside structural cuts "
              f"and went with them")
    for a, b, why in rep["junk"]:
        print(f"demoted   {hms(a)}-{hms(b)} treated as still  {why}")
    for a, b, a2, b2 in rep["snapped"]:
        print(f"snapped   cut {hms(a)}-{hms(b)} -> {hms(a2)}-{hms(b2)} (word gaps)")
    for a, b, text in muted_words:
        gone = any(abs(a - sa) < 1e-6 for sa, sb in swallowed)
        print(f"mute      {hms(a)} \"{text}\"" + ("  (inside a cut - already gone)" if gone else ""))
    print(f"filter    {args.filter}  ({len(used)} blur region(s), encoder {enc})")
    print(f"manifest  {args.manifest}\n")
    print("render:\n  " + " ".join(f'"{x}"' if " " in x else x for x in render) + " EDIT.mp4")
    if mute_cmd:
        print("mute pass (video copied, seconds):\n  " + " ".join(mute_cmd) + " FINAL.mp4")
    print(f"\nthen:  python qa_check.py FINAL.mp4 --manifest {args.manifest}")

    if args.render:
        out = Path(args.render)
        edit = out if not mute_cmd else out.with_name(out.stem + "-unmuted" + out.suffix)
        print(f"\nrendering -> {edit}")
        subprocess.run(render + [str(edit)], check=True)
        if mute_cmd:
            mute_cmd[3] = str(edit)
            print(f"muting -> {out}")
            subprocess.run(mute_cmd + [str(out)], check=True)
        print("done")


if __name__ == "__main__":
    main()
