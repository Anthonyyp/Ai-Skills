#!/usr/bin/env python3
"""Make the delivery encodes from a QA-passed master.

  python deliver.py EDIT.mp4                        # -> EDIT-share.mp4, EDIT-phone.mp4
  python deliver.py EDIT.mp4 --only share           # one of them
  python deliver.py EDIT.mp4 --width 1600           # override the share width

The master is delivered as-is (source resolution). The two derived files are for the ways a
long recording actually travels:

  share   1280x800-ish, 15 fps, 32 kbps mono   ~0.5-0.7 MB/min   a link, a Drive folder, Slack
  phone   1152x720-ish, 10 fps, 24 kbps mono   ~0.35-0.5 MB/min  watched on a phone, sent by text

Widths are targets; the height follows the source aspect and both are rounded to even numbers
(h264 needs them). Audio is mono at speech rates - it's half the file otherwise. The fps drop is
the big saving for a screen recording: nothing on a slide moves 30 times a second.

Each output is verified after encoding: duration within a second of the master, one video and
one audio stream, +faststart. Prints one line per file with the size.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

PROFILES = {
    "share": dict(width=1280, fps=15, abr="32k", crf=26),
    "phone": dict(width=1152, fps=10, abr="24k", crf=28),
}


def die(msg):
    sys.exit(f"ERROR: {msg}")


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,width,height",
                        "-of", "json", str(path)], capture_output=True, text=True)
    if r.returncode:
        die(f"ffprobe failed on {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def even(n):
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("master")
    ap.add_argument("--only", choices=sorted(PROFILES), help="make just this one")
    ap.add_argument("--width", type=int, help="override the share width (phone scales with it)")
    ap.add_argument("--out-dir", help="where to write (default: beside the master)")
    a = ap.parse_args()

    src = Path(a.master)
    if not src.exists():
        die(f"{src} not found")
    info = probe(src)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not v:
        die("no video stream in the master")
    sw, sh = int(v["width"]), int(v["height"])
    sdur = float(info["format"]["duration"])
    out_dir = Path(a.out_dir) if a.out_dir else src.parent

    names = [a.only] if a.only else list(PROFILES)
    for name in names:
        p = dict(PROFILES[name])
        if a.width:
            p["width"] = a.width if name == "share" else int(a.width * 0.9)
        w = min(even(p["width"]), even(sw))          # never upscale
        h = even(sh * w / sw)
        out = out_dir / f"{src.stem}-{name}{src.suffix}"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-i", str(src),
               "-vf", f"scale={w}:{h}:flags=lanczos,fps={p['fps']}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", str(p["crf"]),
               "-pix_fmt", "yuv420p", "-profile:v", "high",
               "-c:a", "aac", "-ac", "1", "-b:a", p["abr"],
               "-map_chapters", "-1", "-movflags", "+faststart", "-y", str(out)]
        print(f"{name:6}  {w}x{h} {p['fps']} fps {p['abr']} mono  ->  {out.name}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode:
            die(f"ffmpeg failed on {name}")

        # verify: same length, one of each stream, faststart honoured (moov before mdat)
        oi = probe(out)
        odur = float(oi["format"]["duration"])
        kinds = sorted(s["codec_type"] for s in oi["streams"])
        if abs(odur - sdur) > 1.0:
            die(f"{out.name}: duration {odur:.2f} vs master {sdur:.2f}")
        if kinds != ["audio", "video"]:
            die(f"{out.name}: streams {kinds}, expected one audio + one video")
        head = out.open("rb").read(64 * 1024)
        if head.find(b"moov") < 0 or (head.find(b"mdat") >= 0 and head.find(b"mdat") < head.find(b"moov")):
            die(f"{out.name}: moov atom not at the front (faststart failed)")
        mb = int(oi["format"]["size"]) / 1e6
        print(f"        ok  {odur/60:.1f} min  {mb:.1f} MB  ({mb/(odur/60):.2f} MB/min)", flush=True)


if __name__ == "__main__":
    main()
