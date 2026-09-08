#!/usr/bin/env python3
"""Find every moment a screen region shows a given kind of content, across the whole runtime.

The problem it solves: you spotted the client's channel list in the left rail at 1:11:45 and
1:14:40 from the contact sheets, but a sheet is one frame per 30 s and the rail also flashed up
for two seconds at 1:19:02 and 1:36:30. Blur windows built from spot-checks miss those. This
scores the region on EVERY frame at --step seconds against examples you already identified,
and prints the windows where it matches - ready to paste into the plan's "blur" list.

  python find_regions.py in.mp4 --region 0.004,0.085,0.192,0.99 \\
      --positive 4305,4340,4480 --negative 100,2600,5000 --out rail-windows.json

  --region     x0,y0,x1,y1 as fractions of the frame (same numbers as the plan's "regions")
  --positive   times (s) where the region shows the thing you want to find
  --negative   times (s) where it shows anything else that appears in that place
  --step       seconds between samples (default 2)
  --pad        seconds added either side of each window (default 1)
  --gap        merge windows closer than this (default 4 s)

How it decides: each sample is reduced to a small signature (mean colour, contrast, edge density,
and a 6x3 grid of brightness - the layout) of the region, and classified by which example it is nearest to, positive or negative. It
prints the margin (negative distance minus positive distance) for every window and flags the ones
that were close, so you can check those frames with contact_sheet.py --times rather than trust
them. Give it at least three examples of each; more negatives of the *confusable* screens
(the same app on a different page) matter more than more positives.

Output: windows as [start, end] in source seconds, JSON, plus a table on stdout.
"""
import argparse
import json
import subprocess
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("ERROR: pip install numpy")

W = 320   # analysis width; the region is cropped from a frame this wide


def die(msg):
    sys.exit(f"ERROR: {msg}")


def probe(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", src],
                       capture_output=True, text=True)
    if r.returncode:
        die(r.stderr.strip())
    j = json.loads(r.stdout)
    return int(j["streams"][0]["width"]), int(j["streams"][0]["height"]), float(j["format"]["duration"])


GRID = (6, 3)   # rows x cols of the layout fingerprint


def signature(reg):
    """reg: HxWx3 uint8. Colour + texture + a coarse layout fingerprint of the region."""
    f = reg.astype(np.float32)
    mean = f.mean(axis=(0, 1)) / 255.0                          # 3: overall colour
    gray = f.mean(axis=2)
    spread = gray.std() / 128.0                                  # 1: contrast
    dx = np.abs(np.diff(gray, axis=1)).mean() / 32.0             # 1: horizontal edge density
    dy = np.abs(np.diff(gray, axis=0)).mean() / 32.0             # 1: vertical edge density
    bmr = (f[..., 2] - f[..., 0]).mean() / 128.0                 # 1: blue minus red (UI tints)
    # layout: mean gray of a GRID of cells - a sidebar with icons looks different from a nav
    # column with text even when both are dark, and this is what tells them apart
    rows = np.array_split(gray, GRID[0], axis=0)
    cells = [c.mean() / 255.0 for r in rows for c in np.array_split(r, GRID[1], axis=1)]
    return np.array([*mean, spread, dx, dy, bmr, *cells], dtype=np.float32)


def frames(src, step, h):
    """Yield (t, HxWx3) for every sample, decoding once at analysis size."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
           "-vf", f"fps=1/{step},scale={W}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=W * h * 3 * 8)
    n = W * h * 3
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield i * step, np.frombuffer(buf, np.uint8).reshape(h, W, 3)
        i += 1
    p.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--region", required=True, help="x0,y0,x1,y1 fractions")
    ap.add_argument("--positive", required=True, help="comma-separated seconds")
    ap.add_argument("--negative", required=True, help="comma-separated seconds")
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--pad", type=float, default=1.0)
    ap.add_argument("--gap", type=float, default=4.0)
    ap.add_argument("--out", help="write windows as JSON here")
    a = ap.parse_args()

    x0, y0, x1, y1 = (float(v) for v in a.region.split(","))
    pos = [float(v) for v in a.positive.split(",")]
    neg = [float(v) for v in a.negative.split(",")]
    if len(pos) < 2 or len(neg) < 2:
        die("give at least two --positive and two --negative example times (three or more is better)")

    sw, sh, dur = probe(a.video)
    h = int(round(sh * W / sw)) // 2 * 2
    rx0, rx1 = int(x0 * W), max(int(x0 * W) + 2, int(x1 * W))
    ry0, ry1 = int(y0 * h), max(int(y0 * h) + 2, int(y1 * h))

    # one decode pass: collect signatures for every sample
    print(f"scanning {dur/60:.1f} min at one sample per {a.step:g} s ...", flush=True)
    times, sigs = [], []
    for t, fr in frames(a.video, a.step, h):
        times.append(t)
        sigs.append(signature(fr[ry0:ry1, rx0:rx1]))
    times = np.array(times)
    sigs = np.stack(sigs)

    def nearest(t):
        return int(np.argmin(np.abs(times - t)))

    P = sigs[[nearest(t) for t in pos]]
    N = sigs[[nearest(t) for t in neg]]

    def dist_to(examples):
        # distance from every sample to its NEAREST example - not a centroid, because the
        # negatives are usually several different screens (slides, another app, a blank page)
        return np.min(np.linalg.norm(sigs[:, None, :] - examples[None, :, :], axis=2), axis=1)

    # the smallest positive-to-negative example distance is the scale everything is judged on
    sep = float(np.min(np.linalg.norm(P[:, None, :] - N[None, :, :], axis=2)))
    if sep < 0.05:
        die(f"a positive and a negative example look the same in that region (gap {sep:.3f}); "
            f"the region may be wrong, or one of the example times is")
    # sanity: the positives are one kind of screen, so each should be nearer another positive
    # than any negative. (Negatives are several kinds, so the same test would misfire on them.)
    for i, (t, s) in enumerate(zip(pos, P)):
        same = np.delete(np.linalg.norm(P - s, axis=1), i)
        if same.size and np.min(np.linalg.norm(N - s, axis=1)) < same.min():
            print(f"  warning: positive example at {t:.0f}s looks more like a negative; "
                  f"check that time on a contact sheet", flush=True)

    dp = dist_to(P)
    dn = dist_to(N)
    hit = dp < dn

    # merge consecutive hits into windows
    windows = []
    for t, is_hit, a_, b_ in zip(times, hit, dp, dn):
        if not is_hit:
            continue
        if windows and t - windows[-1]["end"] <= a.gap:
            windows[-1]["end"] = t
            windows[-1]["margin"] = min(windows[-1]["margin"], float(b_ - a_))
        else:
            windows.append({"start": float(t), "end": float(t), "margin": float(b_ - a_)})
    for w in windows:
        w["start"] = max(0.0, w["start"] - a.pad)
        w["end"] = min(dur, w["end"] + a.step + a.pad)

    print(f"\nexample gap {sep:.3f}; {int(hit.sum())} of {len(times)} samples matched; "
          f"{len(windows)} window(s):\n")
    print(f"{'start':>10} {'end':>10} {'len':>6}  margin")
    for w in windows:
        flag = "  <- close, check the frames" if w["margin"] < 0.6 * sep else ""
        print(f"{w['start']:>10.1f} {w['end']:>10.1f} {w['end']-w['start']:>6.1f}  {w['margin']:.3f}{flag}")
    print(f"\ncovered {sum(w['end']-w['start'] for w in windows)/60:.1f} min in total")

    if a.out:
        with open(a.out, "w") as f:
            json.dump([[round(w["start"], 1), round(w["end"], 1)] for w in windows], f)
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
