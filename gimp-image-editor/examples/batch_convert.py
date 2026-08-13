"""Batch convert / resize a folder of images in ONE GIMP invocation.

    python scripts/gimp_cli.py run examples/batch_convert.py -- \
        <src-folder> <dst-folder> [--ext png] [--max 1024] [--quality 0.85]

GIMP costs ~3-4s to start (measured warm; the first run after install is much
slower while it builds its font cache). Loop INSIDE the script rather than
launching GIMP once per file - over a few hundred files that is the difference
between minutes and an hour.

Honest note: for plain resize/convert with no layer or text work,
ImageMagick (`magick mogrify -resize 1024x1024 -format webp *.png`) is faster
and simpler. Reach for GIMP when you need layers, XCF/PSD, text layout, or
GEGL ops in the same pass.
"""

import glob
import os

from gimp_helpers import *  # noqa: F401,F403

INPUT_EXTS = ("png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "xcf", "psd")


def parse(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    opts = {"src": argv[0], "dst": argv[1],
            "ext": "png", "max": None, "quality": None}
    rest = argv[2:]
    for i, token in enumerate(rest):
        if token == "--ext":
            opts["ext"] = rest[i + 1].lstrip(".")
        elif token == "--max":
            opts["max"] = int(rest[i + 1])
        elif token == "--quality":
            opts["quality"] = float(rest[i + 1])
    return opts


opts = parse(ARGS)  # noqa: F821
os.makedirs(opts["dst"], exist_ok=True)

sources = []
for ext in INPUT_EXTS:
    sources.extend(glob.glob(os.path.join(opts["src"], "*." + ext)))
    sources.extend(glob.glob(os.path.join(opts["src"], "*." + ext.upper())))
sources = sorted(set(sources))

if not sources:
    raise SystemExit("no images found in %s" % opts["src"])

log("%d file(s) -> .%s in %s" % (len(sources), opts["ext"], opts["dst"]))

export_opts = {}
if opts["quality"] is not None and opts["ext"] in ("jpg", "jpeg", "webp"):
    export_opts["quality"] = opts["quality"]

ok = 0
for src in sources:
    stem = os.path.splitext(os.path.basename(src))[0]
    dst = os.path.join(opts["dst"], "%s.%s" % (stem, opts["ext"]))
    try:
        image = load_image(src)
        before = (image.get_width(), image.get_height())
        if opts["max"]:
            fit_within(image, opts["max"], opts["max"])
        export(image, dst, **export_opts)
        log("  %-28s %dx%d -> %dx%d  %d bytes"
            % (os.path.basename(src), before[0], before[1],
               image.get_width(), image.get_height(), os.path.getsize(dst)))
        image.delete()
        ok += 1
    except Exception as exc:
        # One bad file shouldn't abandon the other 200.
        log("  SKIP %s: %s" % (os.path.basename(src), exc))

log("converted %d/%d" % (ok, len(sources)))
if ok == 0:
    raise SystemExit("every file failed")
