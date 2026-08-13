"""Turn a SOLID-background image into a transparent PNG.

    python scripts/gimp_cli.py run examples/chroma_key.py -- <src> <dst> [key]

NOT a background remover. This keys one flat colour; it has no notion of what
the subject is. Point it at a photo of a person in a room and it will eat
whatever happens to match the sampled corner - quietly, and with exit code 0.
For real subject cut-outs use a segmentation tool (rembg or similar).

`key` is a colour spec ('#00FF00', 'white'). Omit it and the corner pixel is
sampled instead, which is what you want for AI-generated art: image models
drift a few points off whatever background colour you asked for, so a
hard-coded key leaves a halo.

Uses gegl:color-to-alpha rather than fuzzy-select-and-delete because it also
un-premultiplies antialiased edge pixels - that is what stops a coloured
fringe appearing once the cut-out sits on a different background.
"""

import os

from gimp_helpers import *  # noqa: F401,F403

if len(ARGS) < 2:  # noqa: F821
    raise SystemExit(__doc__)

src, dst = ARGS[0], ARGS[1]  # noqa: F821
key = ARGS[2] if len(ARGS) > 2 else None  # noqa: F821

image = load_image(src)
layer = image.get_layers()[0]
layer.add_alpha()

if key is None:
    sampled = layer.get_pixel(2, 2)
    rgba = sampled.get_rgba()
    log("sampled key from corner pixel: #%02X%02X%02X"
        % tuple(int(round(c * 255)) for c in rgba[:3]))
    key_color = sampled
else:
    key_color = color(key)

apply_gegl(layer, "gegl:color-to-alpha",
           color=key_color,
           transparency_threshold=0.15,   # within this of the key -> clear
           opacity_threshold=0.85)        # beyond this -> untouched

if os.path.splitext(dst)[1].lower() not in (".png", ".webp", ".xcf", ".tif", ".tiff"):
    log("WARNING: %s may not support alpha; transparency could be lost" % dst)

export(image, dst, flatten=False)
log("%s -> %s" % (os.path.basename(src), dst))
image.delete()
