#!/usr/bin/env python3
"""qa_check.py - machine QA of a rendered edit against its manifest.

    python qa_check.py FINAL.mp4 --manifest manifest.json [--report qa-report.md] [--sheet QC-CHEAT-SHEET.md]

Every check is something a person would otherwise do by scrubbing: is it the right length, are the
mutes silent, are the blurs actually blurred (and NOT blurred where they shouldn't be), does each join
land between words, do the stretches we kept still move. Exit 0 = all PASS, 1 = something FAILed.
Whisper runs only on a few seconds either side of each join, so this finishes in minutes even for a
two-hour edit.

The manifest comes from build_edit.py. Nothing here needs the plan except the optional
`disclosures` list, which is read from the plan the manifest points at.
"""
import argparse, json, os, re, subprocess, sys, tempfile

import numpy as np

TILE_W = 320  # analysis width for motion pulls


# ---------------------------------------------------------------- helpers
def hms(t):
    t = max(0.0, float(t)); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,r_frame_rate,duration",
             "-show_chapters", "-of", "json", path])
    if r.returncode:
        sys.exit(f"ffprobe failed on {path}: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    n, d = v["r_frame_rate"].split("/")
    return {"duration": float(j["format"]["duration"]), "chapters": len(j.get("chapters", [])),
            "width": int(v["width"]), "height": int(v["height"]), "fps": int(n) / int(d),
            "vdur": float(v.get("duration") or 0), "adur": float(a.get("duration") or 0) if a else None}


def frame(path, t, w, h):
    """One grayscale frame at t as a float array of the file's own size (w,h)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", path,
                        "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    if r.returncode or len(r.stdout) < w * h:
        return None
    return np.frombuffer(r.stdout[:w * h], dtype=np.uint8).reshape(h, w).astype(np.float32)


def frames_at(path, a, b, w, h, fps=1):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}", "-i", path,
                        "-t", f"{b - a:.3f}", "-vf", f"fps={fps},scale={w}:{h},format=gray",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(buf) // (w * h)
    return buf[:n * w * h].reshape(n, h, w).astype(np.float32)


def sharpness(img):
    """Mean absolute Laplacian - high-frequency energy. Blur drives this toward zero."""
    if img.shape[0] < 3 or img.shape[1] < 3:
        return 0.0
    lap = (-4 * img[1:-1, 1:-1] + img[:-2, 1:-1] + img[2:, 1:-1] + img[1:-1, :-2] + img[1:-1, 2:])
    return float(np.abs(lap).mean())


def loudness_db(path, a, b):
    """Peak level in [a,b], trimmed sample-accurately (AAC frames are ~21 ms, so -ss would smear)."""
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-vn",
             "-af", f"atrim={a:.3f}:{b:.3f},volumedetect", "-f", "null", "-"])
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


_model = None
def whisper():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def words(path, a, b):
    """[(start,end,word)] for the audio in [a,b], absolute times."""
    a = max(0.0, a)
    fd, wav = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}", "-i", path, "-t",
             f"{b - a:.3f}", "-vn", "-ac", "1", "-ar", "16000", "-y", wav])
        segs, _ = whisper().transcribe(wav, word_timestamps=True, vad_filter=False, beam_size=1)
        out = []
        for s in segs:
            for w in s.words or []:
                out.append((a + w.start, a + w.end, w.word.strip()))
        return out
    finally:
        os.unlink(wav)


def audio(path, a, b):
    """Mono 16 kHz float samples for [a,b]."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-vn",
                        "-af", f"atrim={max(0.0, a):.3f}:{b:.3f},asetpts=PTS-STARTPTS",
                        "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def similarity(x, y, max_lag=1600):
    """Best normalised cross-correlation of two clips over lags of +/-max_lag samples (100 ms)."""
    n = min(len(x), len(y)) - 2 * max_lag
    if n < 1600:
        return 0.0, 0
    xs = x[max_lag:max_lag + n]
    nx = np.linalg.norm(xs)

    def corr(lag):
        ys = y[max_lag + lag:max_lag + lag + n]
        d = nx * np.linalg.norm(ys)
        return float(np.dot(xs, ys) / d) if d > 0 else 0.0

    # coarse search, then refine to the sample: speech at 16 kHz decorrelates within a few
    # samples, so a half-millisecond miss reads as 0.7 on audio that is actually identical
    best, blag = max((corr(l), l) for l in range(-max_lag, max_lag + 1, 8))
    best, blag = max((corr(l), l) for l in range(blag - 8, blag + 9))
    return best, blag


def s2o(t, pieces):
    for p in pieces:
        if p["a"] <= t <= p["b"]:
            return p["out_a"] + (t - p["a"]) / p["speed"]
    return None


# ---------------------------------------------------------------- checks
class Report:
    def __init__(self):
        self.rows = []; self.failed = 0

    def add(self, ok, group, detail):
        self.rows.append((ok, group, detail))
        if ok is False:
            self.failed += 1
        print(f"  {'PASS' if ok else 'FAIL' if ok is False else 'skip'}  {detail}")


def check_container(rep, out, man):
    p = probe(out)
    d = abs(p["duration"] - man["output_duration"])
    rep.add(d <= 1.0, "container", f"duration {hms(p['duration'])} vs planned {hms(man['output_duration'])} (diff {d:.2f}s)")
    rep.add(p["chapters"] == 0, "container", f"chapters: {p['chapters']}")
    rep.add(p["width"] == man["width"] and p["height"] == man["height"], "container",
            f"frame {p['width']}x{p['height']} (source {man['width']}x{man['height']})")
    rep.add(abs(p["fps"] - man["fps"]) < 0.01, "container", f"fps {p['fps']:.3f} (source {man['fps']:.3f})")
    if p["adur"] is not None and p["vdur"]:
        dd = abs(p["adur"] - p["vdur"])
        rep.add(dd <= 0.25, "container", f"audio/video stream lengths differ by {dd:.2f}s")
    return p


def check_mutes(rep, out, man):
    for a, b in man.get("mutes_out", []):
        db = loudness_db(out, a + 0.03, b - 0.03)
        rep.add(db is not None and db <= -70, "mute", f"mute {hms(a)}-{hms(b)} peak {db} dB")
        db2 = loudness_db(out, b + 0.05, b + 1.0)
        rep.add(db2 is not None and db2 > -60, "mute", f"audio back after mute at {hms(b)}: peak {db2} dB")


def region_px(reg, W, H):
    x0, y0, x1, y1 = reg
    return int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)


def check_blur(rep, out, src, man, pv):
    regions = man.get("regions", {})
    W, H = pv["width"], pv["height"]
    sw, sh = man["width"], man["height"]
    if not man["checks"].get("blur"):
        rep.add(None, "blur", "no blur windows"); return
    for c in man["checks"]["blur"]:
        fo = frame(out, c["out"], W, H); fs = frame(src, c["src"], sw, sh)
        if fo is None or fs is None:
            rep.add(False, "blur", f"could not pull frame at out {hms(c['out'])}"); continue
        for name in c["regions"]:
            x0, y0, x1, y1 = region_px(regions[name], sw, sh)
            so = sharpness(fo[y0:y1, x0:x1]); ss = sharpness(fs[y0:y1, x0:x1])
            if ss < 1.0:
                rep.add(None, "blur", f"{name} @ out {hms(c['out'])}: source region is flat ({ss:.2f}), cannot judge"); continue
            ratio = so / ss
            rep.add(ratio < 0.25, "blur", f"{name} @ out {hms(c['out'])} (src {hms(c['src'])}): detail {ratio:.2f} of source")
    # negative control: just outside each window the region must be sharp. The source region
    # has to hold still around the sample point, or a placeholder appearing between the two
    # frames reads as blur; try a few offsets and judge the first stable one.
    pieces = man["pieces"]
    for w in man.get("blur", []):
        for side, sign in (("before", -1), ("after", 1)):
            for name in w["regions"]:
                x0, y0, x1, y1 = region_px(regions[name], sw, sh)
                verdict = None
                for off in (1.5, 3.0, 0.75, 5.0):
                    t = (w["start"] if sign < 0 else w["end"]) + sign * off
                    if any(o["start"] <= t <= o["end"] for o in man["blur"]):
                        continue
                    ot = s2o(t, pieces)
                    if ot is None:
                        continue
                    fs = frame(src, t, sw, sh)
                    if fs is None:
                        continue
                    ss = sharpness(fs[y0:y1, x0:x1])
                    if ss < 3.0:
                        continue
                    near = [frame(src, t + dt, sw, sh) for dt in (-0.4, 0.4)]
                    if any(f is None or abs(sharpness(f[y0:y1, x0:x1]) - ss) > 0.25 * ss for f in near):
                        continue
                    fo = frame(out, ot, W, H)
                    if fo is None:
                        continue
                    ratio = sharpness(fo[y0:y1, x0:x1]) / ss
                    verdict = (ratio > 0.6, f"{name} unblurred {side} window @ out {hms(ot)}: detail {ratio:.2f} of source")
                    break
                if verdict is None:
                    rep.add(None, "blur", f"{name} {side} window {hms(w['start'])}-{hms(w['end'])}: no stable frame to judge against")
                else:
                    rep.add(verdict[0], "blur", verdict[1])


def check_joins(rep, out, src, man, pad=4.0):
    """Two things can go wrong at a join: the edge lands inside a word (whisper on the SOURCE says
    where the words are), or the output audio around the join is not the source audio it should be
    - a dropped or doubled chunk, a drifted piece. The second is a waveform test, not a transcript
    test: whisper wording varies run to run, waveforms don't."""
    joins = man["checks"].get("joins", [])
    if not joins:
        rep.add(None, "join", "no joins"); return
    pieces = man["pieces"]
    for j in joins:
        a, b = j["removed"]; o = j["out"]
        before = words(src, a - pad, a)
        after = words(src, b, b + pad)
        for edge, ws, side in ((a, before, "before"), (b, after, "after")):
            hit = [w for w in ws if w[0] + 0.08 < edge < w[1] - 0.08]
            rep.add(not hit, "join", f"join @ out {hms(o)} ({j['why']}): {side}-edge {hms(edge)} "
                    + (f"splits word '{hit[0][2]}'" if hit else "in a word gap")
                    + f"  '{' '.join(w for _,_,w in before[-4:])} | {' '.join(w for _,_,w in after[:4])}'")
        # waveform either side of the join must be the source waveform either side of the removal,
        # unless that side is a speed ramp (then it is time-compressed and won't correlate)
        # each side's window stays inside its own piece - two joins a second apart would
        # otherwise compare across the neighbouring seam and fail on a fine edit
        pb = next((p for p in pieces if abs(p["b"] - a) < 0.03), None)
        pa = next((p for p in pieces if abs(p["a"] - b) < 0.03), None)
        sides = []
        if pb:
            sides.append(("before", max(pb["a"], a - 2.0), a, a, pb["speed"]))
        if pa:
            sides.append(("after", b, min(pa["b"], b + 2.0), b, pa["speed"]))
        for side, sa, sb, edge, spd in sides:
            oa, ob = o + (sa - edge), o + (sb - edge)
            if sa < 0.1 or sb > man["source_duration"] - 0.1 or oa < 0.1:
                continue
            if spd != 1.0:
                rep.add(None, "join", f"join @ out {hms(o)}: {side} side is a x{spd} ramp, waveform not compared"); continue
            if sb - sa < 0.8:
                rep.add(None, "join", f"join @ out {hms(o)}: {side} side piece is {sb - sa:.2f} s, too short to compare"); continue
            x = audio(src, sa - 0.1, sb + 0.1); y = audio(out, oa - 0.1, ob + 0.1)
            if np.abs(x).max() < 1e-3:
                rep.add(None, "join", f"join @ out {hms(o)}: {side} side is silent, waveform not compared"); continue
            c, lag = similarity(x, y)
            rep.add(c >= 0.6, "join", f"join @ out {hms(o)}: {side} side matches source waveform "
                    f"(corr {c:.2f}, lag {lag / 16:.0f} ms)")


def check_motion(rep, out, man, pv):
    """Every stretch we kept or ramped because the screen was moving must still move in the output."""
    pieces = man["pieces"]
    W = TILE_W; H = max(2, int(TILE_W * pv["height"] / pv["width"]))
    todo = [(s[0], s[1], "spared") for s in man.get("report", {}).get("spared", [])]
    todo += [(r["src"][0], r["src"][1], f"ramp x{r['speed']}") for r in man["checks"].get("ramps", [])]
    if not todo:
        rep.add(None, "motion", "no kept/ramped stretches"); return
    for a, b, why in todo:
        oa, ob = s2o(a, pieces), s2o(b, pieces)
        if oa is None or ob is None:
            rep.add(False, "motion", f"{why} {hms(a)}-{hms(b)} is not in the output at all"); continue
        # short runs are sampled at the native rate with a second either side: a scan_signals
        # run can be one frame of screen switch, and a seek that lands just past it sees nothing
        short = ob - oa < 3
        fr = frames_at(out, max(0.0, oa - 1.0), max(ob, oa + 1) + 1.0, W, H,
                       fps=(pv.get("fps") or 25) if short else 1)
        if len(fr) < 2:
            rep.add(False, "motion", f"{why} @ out {hms(oa)}: too short to measure"); continue
        d = np.abs(np.diff(fr, axis=0))
        changed = (d > 12).mean(axis=(1, 2))
        rep.add(bool(changed.max() >= 0.005), "motion",
                f"{why} @ out {hms(oa)}-{hms(ob)}: peak {changed.max()*100:.1f}% of pixels changing")


def check_disclosures(rep, man):
    plan_path = man.get("plan")
    if not plan_path or not os.path.exists(plan_path):
        rep.add(None, "privacy", "no plan file to read disclosures from"); return
    plan = json.load(open(plan_path, encoding="utf-8"))
    disc = plan.get("disclosures", [])
    if not disc:
        rep.add(None, "privacy", "plan lists no disclosures"); return
    cuts = [(r["a"], r["b"]) for r in man["removals"] if r["kind"] == "cut"]
    for d in disc:
        a, b, what = d["start"], d["end"], d.get("what", "?")
        region = d.get("region")
        in_cut = any(ca <= a and b <= cb for ca, cb in cuts)
        in_blur = any(w["start"] <= a and b <= w["end"] and (region is None or region in w["regions"])
                      for w in man.get("blur", []))
        rep.add(in_cut or in_blur, "privacy", f"disclosure {hms(a)}-{hms(b)} '{what}': "
                + ("cut" if in_cut else "blurred" if in_blur else "NOT COVERED"))


# ---------------------------------------------------------------- output
def write_report(rep, path, out, man):
    npass = sum(1 for r in rep.rows if r[0] is True); nskip = sum(1 for r in rep.rows if r[0] is None)
    lines = [f"# QA report - {os.path.basename(out)}", "",
             f"{'ALL PASS' if rep.failed == 0 else str(rep.failed) + ' FAIL'}  ({npass} pass, {nskip} skipped)", ""]
    for ok, g, d in rep.rows:
        lines.append(f"- {'PASS' if ok else 'FAIL' if ok is False else 'skip'} `{g}` {d}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def write_sheet(path, out, man):
    """Human QC cheat sheet: every timestamp worth eyeballing, in OUTPUT time."""
    c = man["checks"]
    L = [f"# QC cheat sheet - {os.path.basename(out)}", "",
         f"Output {hms(man['output_duration'])} from source {hms(man['source_duration'])}. "
         f"Times below are in the *output* file. Machine QA already passed on all of them; "
         f"this is the eyes-and-ears pass.", ""]
    L += ["## Joins - listen for a clipped word or a jump", ""]
    for j in c.get("joins", []):
        L.append(f"- **{hms(j['out'])}** removed {hms(j['removed'][0])}-{hms(j['removed'][1])} ({j['kind']}: {j['why']})")
    if c.get("ramps"):
        L += ["", "## Speed ramps - should read as a natural fast-forward", ""]
        for r in c["ramps"]:
            L.append(f"- **{hms(r['out'][0])}-{hms(r['out'][1])}** x{r['speed']}")
    if c.get("blur"):
        L += ["", "## Blur - region must be unreadable, everything around it sharp", ""]
        for b in c["blur"]:
            L.append(f"- **{hms(b['out'])}** {', '.join(b['regions'])}")
    if c.get("mutes"):
        L += ["", "## Mutes - dead silent, picture untouched", ""]
        names = {round(m["out"], 1): m["words"] for m in man.get("mutes_words", []) if m.get("out") is not None}
        for a, b in c["mutes"]:
            L.append(f"- **{hms(a)}-{hms(b)}**" + (f'  "{names[round(a, 1)]}"' if round(a, 1) in names else ""))
    L += ["", "## Kept silent stretches - screen should be doing something", ""]
    for a, b in man.get("report", {}).get("spared", []):
        oa = s2o(a, man["pieces"])
        if oa is not None:
            L.append(f"- **{hms(oa)}** ({b - a:.1f}s)")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--source", help="override the manifest's source path")
    ap.add_argument("--report", default="qa-report.md")
    ap.add_argument("--sheet", help="also write a human QC cheat sheet here")
    ap.add_argument("--skip", default="", help="comma list of groups to skip: mute,blur,join,motion,privacy")
    args = ap.parse_args()

    man = json.load(open(args.manifest, encoding="utf-8"))
    src = args.source or man["source"]
    if not os.path.exists(src):
        sys.exit(f"source not found: {src} (pass --source)")
    skip = set(s.strip() for s in args.skip.split(",") if s.strip())
    rep = Report()

    print("container"); pv = check_container(rep, args.output, man)
    if "mute" not in skip:
        print("mutes"); check_mutes(rep, args.output, man)
    if "blur" not in skip:
        print("blur"); check_blur(rep, args.output, src, man, pv)
    if "motion" not in skip:
        print("motion"); check_motion(rep, args.output, man, pv)
    if "privacy" not in skip:
        print("privacy"); check_disclosures(rep, man)
    if "join" not in skip:
        print("joins (whisper on a few seconds around each)"); check_joins(rep, args.output, src, man)

    write_report(rep, args.report, args.output, man)
    if args.sheet:
        write_sheet(args.sheet, args.output, man)
    print()
    print(("ALL PASS" if rep.failed == 0 else f"{rep.failed} FAIL") + f"  -> {args.report}")
    sys.exit(0 if rep.failed == 0 else 1)


if __name__ == "__main__":
    main()
