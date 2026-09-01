#!/usr/bin/env python3
"""Extract frames from a video and tile them into timestamped contact sheets.

The point is that a vision-capable agent can then LOOK at the video, with exact
timestamps, without any cloud video model.

  # survey a whole recording, one frame per 30s
  python contact_sheet.py in.mp4 --interval 30 --out sheets/

  # zoom in on a stretch
  python contact_sheet.py in.mp4 --start 4200 --end 4500 --interval 5 --out sheets/

  # check specific moments (e.g. verifying a render)
  python contact_sheet.py out.mp4 --times 120,240,360 --out check/

Each tile is labelled with its timestamp, so anything you spot can be acted on
directly. Sheets are capped at --per-sheet tiles so they stay readable.
"""
import argparse
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("ERROR: pip install pillow")


def hms(t):
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def duration(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffprobe failed on {src}")
    return float(r.stdout.strip())


def grab(src, t, path, width):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(t),
                    "-i", str(src), "-frames:v", "1", "-update", "1",
                    "-vf", f"scale={width}:-1", "-q:v", "4", "-y", str(path)],
                   capture_output=True)
    return path.exists()


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(tiles, out, cols, tile_w, label_h=22):
    """tiles: list of (timestamp, image path). Returns the sheet path."""
    if not tiles:
        return None
    first = Image.open(tiles[0][1])
    tile_h = int(tile_w * first.height / first.width)
    rows = (len(tiles) + cols - 1) // cols
    gap, pad = 8, 12
    W = pad * 2 + cols * tile_w + (cols - 1) * gap
    H = pad * 2 + rows * (tile_h + label_h + gap)
    sheet = Image.new("RGB", (W, H), (238, 238, 238))
    d = ImageDraw.Draw(sheet)
    f = font(max(12, tile_w // 34))
    for i, (t, p) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + gap)
        y = pad + r * (tile_h + label_h + gap)
        sheet.paste(Image.open(p).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS),
                    (x, y + label_h))
        d.text((x, y + 2), hms(t), font=f, fill=(0, 0, 0))
    sheet.save(out, quality=85)
    return out


def main():
    p = argparse.ArgumentParser(description="Video -> timestamped contact sheets.")
    p.add_argument("input")
    p.add_argument("--out", default="sheets", help="output directory")
    p.add_argument("--interval", type=float, default=30.0, help="seconds between frames")
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--times", default=None,
                   help="explicit comma-separated seconds; overrides interval/start/end")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--tile-width", type=int, default=560)
    p.add_argument("--per-sheet", type=int, default=24, help="max tiles per sheet")
    p.add_argument("--keep-frames", action="store_true")
    args = p.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"ERROR: not found: {src}")
    out = Path(args.out).expanduser().resolve()
    (out / "_frames").mkdir(parents=True, exist_ok=True)

    if args.times:
        times = [float(x) for x in args.times.replace(" ", "").split(",") if x]
    else:
        end = args.end if args.end is not None else duration(src)
        times, t = [], args.start
        while t < end:
            times.append(round(t, 2))
            t += args.interval
    if not times:
        sys.exit("ERROR: no timestamps to grab")

    print(f"grabbing {len(times)} frames from {src.name}", flush=True)
    tiles = []
    for i, t in enumerate(times):
        fp = out / "_frames" / f"f{i:05d}.jpg"
        if grab(src, t, fp, args.tile_width):
            tiles.append((t, fp))
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(times)}", flush=True)

    made = []
    for n, i in enumerate(range(0, len(tiles), args.per_sheet), start=1):
        chunk = tiles[i:i + args.per_sheet]
        path = out / (f"sheet-{n:02d}.jpg" if len(tiles) > args.per_sheet else "sheet.jpg")
        build(chunk, path, args.cols, args.tile_width)
        made.append((path, chunk[0][0], chunk[-1][0]))

    if not args.keep_frames:
        for _, fp in tiles:
            fp.unlink(missing_ok=True)
        try:
            (out / "_frames").rmdir()
        except OSError:
            pass

    print()
    for path, a, b in made:
        print(f"  {path.name}   {hms(a)} - {hms(b)}")
    print(f"\n{len(tiles)} frames across {len(made)} sheet(s) -> {out}")


if __name__ == "__main__":
    main()
