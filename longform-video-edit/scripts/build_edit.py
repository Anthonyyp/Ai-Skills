#!/usr/bin/env python3
"""Turn an edit plan into an ffmpeg filter graph, and tell you what to verify.

  python build_edit.py plan.json --filter filter.txt

plan.json:
{
  "duration": 6089.77,
  "cuts":  [[0, 723.2, "banter and setup"], [1584, 1623, "fumbling"]],
  "silence": [[812.4, 818.1], ...],          optional, from silencedetect
  "min_silence": 3.0,                         trim gaps >= this...
  "leave_silence": 1.0,                       ...down to this
  "regions": { "rail": [0.004,0.085,0.192,0.99] },   fractions x0,y0,x1,y1
  "blur":  [ {"start": 4302, "end": 4356, "regions": ["rail"]} ],
  "mute":  [[3148.96, 3149.54]],
  "width": 2560, "height": 1600
}

Emits the filter graph (blur overlays, then select/setpts for the cuts), the
output duration, the mute spans remapped to output time, and the timestamps to
sample when verifying the render.

Ordering matters and is handled here: blur is applied BEFORE select, so its
enable expressions use source time; everything after uses output time.
"""
import argparse
import json
import sys
from pathlib import Path


def hms(t):
    h, rem = divmod(float(t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}"


def merged_removals(plan):
    cuts = [(float(a), float(b)) for a, b, *_ in plan.get("cuts", [])]
    lo = float(plan.get("min_silence", 3.0))
    leave = float(plan.get("leave_silence", 1.0))
    dead = []
    for a, b in plan.get("silence", []):
        a, b = float(a), float(b)
        if b - a >= lo:
            pad = leave / 2.0
            a2, b2 = a + pad, b - pad
            if b2 > a2 and not any(not (b2 <= c0 or a2 >= c1) for c0, c1 in cuts):
                dead.append((a2, b2))
    out = []
    for a, b in sorted(cuts + dead):
        if out and a <= out[-1][1] + 0.05:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def keep_list(plan):
    dur = float(plan["duration"])
    keep, pos = [], 0.0
    for a, b in merged_removals(plan):
        if a - pos > 0.4:
            keep.append((round(pos, 2), round(a, 2)))
        pos = max(pos, b)
    if dur - pos > 0.4:
        keep.append((round(pos, 2), round(dur, 2)))
    return keep


def s2o(t, keep):
    acc = 0.0
    for a, b in keep:
        if t < a:
            return None
        if t < b:
            return acc + (t - a)
        acc += b - a
    return None


def even(v):
    return int(v) // 2 * 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--filter", default="filter.txt")
    ap.add_argument("--blur-strength", type=int, default=26)
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    W, H = int(plan.get("width", 1920)), int(plan.get("height", 1080))
    keep = keep_list(plan)
    if not keep:
        sys.exit("ERROR: cuts remove the entire video")
    total = sum(b - a for a, b in keep)

    # group blur windows by region
    wins = {}
    for w in plan.get("blur", []):
        for r in w["regions"]:
            wins.setdefault(r, []).append((float(w["start"]), float(w["end"])))
    for r in wins:
        if r not in plan.get("regions", {}):
            sys.exit(f"ERROR: blur window references undefined region '{r}'")

    used = list(wins)
    parts = []
    cur = "[0:v]"
    if used:
        parts.append("[0:v]split=" + str(len(used) + 1)
                     + "".join(f"[s{i}]" for i in range(len(used) + 1)))
        cur = "[s0]"
        for i, r in enumerate(used):
            x0, y0, x1, y1 = plan["regions"][r]
            x, y = even(x0 * W), even(y0 * H)
            w, h = even(x1 * W - x), even(y1 * H - y)
            en = "+".join(f"between(t,{a},{b})" for a, b in wins[r])
            parts.append(f"[s{i+1}]crop={w}:{h}:{x}:{y},avgblur={args.blur_strength}[b{i}]")
            parts.append(f"{cur}[b{i}]overlay={x}:{y}:enable='{en}'[v{i}]")
            cur = f"[v{i}]"
    sel = "+".join(f"between(t,{a},{b})" for a, b in keep)
    parts.append(f"{cur}select='{sel}',setpts=N/FRAME_RATE/TB[vout]")
    parts.append(f"[0:a]aselect='{sel}',asetpts=N/SR/TB[aout]")
    Path(args.filter).write_text(";".join(parts), encoding="utf-8")

    print(f"source   {hms(plan['duration'])}")
    print(f"output   {hms(total)}   ({len(keep)} keep segments, "
          f"{len(merged_removals(plan))} removals)")
    print(f"filter   {args.filter}  ({len(used)} blur region(s))\n")
    print("render:")
    print(f'  ffmpeg -i INPUT -/filter_complex {args.filter} -map "[vout]" -map "[aout]" \\')
    print("    -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 128k \\")
    print("    -map_chapters -1 -movflags +faststart -y EDIT.mp4")
    print("  (swap libx264 for h264_qsv / h264_nvenc if you have hardware encoding)\n")

    mutes = []
    for a, b in plan.get("mute", []):
        oa, ob = s2o(float(a), keep), s2o(float(b), keep)
        if oa is None or ob is None:
            print(f"  note: mute at {hms(a)} falls inside a cut - it is already gone")
        else:
            mutes.append((round(oa, 2), round(ob, 2)))
    if mutes:
        expr = "+".join(f"between(t,{a},{b})" for a, b in mutes)
        print("mute pass (video copied, seconds to run):")
        print(f'  ffmpeg -i EDIT.mp4 -af "volume=0:enable=\'{expr}\'" -c:v copy \\')
        print("    -c:a aac -b:a 128k -map_chapters -1 -y FINAL.mp4\n")

    checks = []
    for w in plan.get("blur", []):
        mid = (float(w["start"]) + float(w["end"])) / 2
        for frac in (0.25, 0.5, 0.75):
            t = float(w["start"]) + (float(w["end"]) - float(w["start"])) * frac
            o = s2o(t, keep)
            if o is not None:
                checks.append(round(o, 1))
    for a, b, *why in plan.get("cuts", []):
        o = s2o(float(b) + 0.5, keep)
        if o is not None:
            checks.append(round(o, 1))
    checks = sorted(set(checks))
    if checks:
        print(f"verify the render - {len(checks)} timestamps (blur windows x3, plus each join):")
        print("  python contact_sheet.py FINAL.mp4 --times "
              + ",".join(str(c) for c in checks) + " --out verify/")


if __name__ == "__main__":
    main()
