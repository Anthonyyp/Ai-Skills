#!/usr/bin/env python3
"""Measure the two signals an edit is built on: where nobody is talking, and where the screen is
moving anyway.

  python scan_signals.py in.mp4 --out signals.json

Silence comes from ffmpeg's silencedetect. Motion is a frame difference sampled once per second,
but only inside silences long enough to be trimmed - that keeps the scan to minutes, not the
whole runtime. A silence with motion in it is a "stretch": the picture is doing something while
the audio isn't, and the edit must decide what to do with it rather than trim it as dead air.

Output (signals.json):
  duration, width, height, fps
  silence    [[start, end], ...]                      every silence >= --min-silence
  motion     [[start, end, mean, peak], ...]          motion runs inside those silences
  stretches  [{id, start, end, silence, seconds, changed_seconds, mean, peak}, ...]

build_edit.py reads this and treats motion as content: dead air = silence minus motion.

Thresholds (tune per source, defaults suit screen recordings):
  --pixel-delta 12   a pixel "changed" if its grey value moved more than this (0-255)
  --area 0.02        a second "moved" if more than this fraction of pixels changed
A blinking cursor or a small spinner stays under 2%; a click that changes a pane, a scroll, or a
playing video is well over it.
"""
import argparse
import json
import re
import subprocess
import sys

import numpy as np

SCAN_W, SCAN_H = 160, 100


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return (float(j["format"]["duration"]), int(s["width"]), int(s["height"]),
            round(float(num) / float(den), 3))


def silences(path, noise_db, min_len):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
           "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"]
    log = subprocess.run(cmd, capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    spans = list(zip(starts, ends))
    if len(starts) == len(ends) + 1:          # silence runs to the end of the file
        spans.append((starts[-1], None))
    return spans


def frames(path, start, length):
    """Grey frames at 1 fps, downscaled, as an (n, H, W) uint8 array."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats",
           "-ss", f"{start:.3f}", "-i", path, "-t", f"{length:.3f}",
           "-vf", f"fps=1,scale={SCAN_W}:{SCAN_H},format=gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (SCAN_W * SCAN_H)
    return np.frombuffer(raw[: n * SCAN_W * SCAN_H], dtype=np.uint8).reshape(n, SCAN_H, SCAN_W)


def motion_runs(scores, start, area, gap=1):
    """Group seconds whose changed-fraction >= area into runs, bridging gaps of `gap` seconds."""
    runs, cur = [], None
    for i, sc in enumerate(scores):
        t = start + i          # score i = change between frame i-1 and frame i
        if sc >= area:
            if cur and t - cur["last"] <= gap + 1:
                cur["last"] = t
                cur["vals"].append(sc)
            else:
                if cur:
                    runs.append(cur)
                cur = {"first": t, "last": t, "vals": [sc]}
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        # the change at second t happened between t-1 and t; start the run a second early
        a = max(start, r["first"] - 1.0)
        b = r["last"] + 0.5
        out.append((round(a, 2), round(b, 2), round(float(np.mean(r["vals"])), 4),
                    round(float(np.max(r["vals"])), 4), len(r["vals"])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="signals.json")
    ap.add_argument("--noise", type=float, default=-32.0, help="silencedetect noise floor, dB")
    ap.add_argument("--detect", type=float, default=2.0, help="silencedetect minimum length, s")
    ap.add_argument("--min-silence", type=float, default=3.0,
                    help="only silences at least this long are trimmable, so only they are scanned")
    ap.add_argument("--pixel-delta", type=int, default=12)
    ap.add_argument("--area", type=float, default=0.02)
    args = ap.parse_args()

    dur, W, H, fps = probe(args.input)
    print(f"source   {args.input}  {dur:.2f}s  {W}x{H}  {fps}fps", file=sys.stderr)

    sil = [(a, b if b is not None else dur) for a, b in silences(args.input, args.noise, args.detect)]
    long = [(a, b) for a, b in sil if b - a >= args.min_silence]
    total_long = sum(b - a for a, b in long)
    print(f"silence  {len(sil)} spans, {len(long)} >= {args.min_silence}s "
          f"({total_long/60:.1f} min to scan)", file=sys.stderr)

    motion, stretches = [], []
    for i, (a, b) in enumerate(long, 1):
        fr = frames(args.input, a, b - a)
        if len(fr) < 2:
            continue
        d = np.abs(fr[1:].astype(np.int16) - fr[:-1].astype(np.int16))
        scores = (d > args.pixel_delta).mean(axis=(1, 2))      # fraction changed, per second
        runs = motion_runs(list(scores), a + 1, args.area)
        for ra, rb, mean, peak, n in runs:
            ra, rb = max(a, ra), min(b, rb)
            motion.append([ra, rb, mean, peak])
            stretches.append({
                "id": f"S{len(stretches)+1:03d}",
                "start": ra, "end": rb, "silence": [round(a, 2), round(b, 2)],
                "seconds": round(rb - ra, 2), "changed_seconds": n,
                "mean": mean, "peak": peak,
            })
        flag = f"  motion x{len(runs)}" if runs else ""
        print(f"  [{i}/{len(long)}] {a:8.1f}-{b:8.1f} ({b-a:5.1f}s){flag}", file=sys.stderr)

    out = {
        "source": args.input, "duration": round(dur, 3), "width": W, "height": H, "fps": fps,
        "params": {"noise_db": args.noise, "detect": args.detect, "min_silence": args.min_silence,
                   "pixel_delta": args.pixel_delta, "area": args.area},
        "silence": [[round(a, 2), round(b, 2)] for a, b in sil],
        "motion": motion,
        "stretches": stretches,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    moving = sum(s["seconds"] for s in stretches)
    print(f"\nstretches {len(stretches)} silent-but-moving, {moving:.0f}s total - "
          f"these need a decision, not a trim", file=sys.stderr)
    print(f"dead      ~{total_long - moving:.0f}s of silence with a still screen", file=sys.stderr)
    print(f"wrote    {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
