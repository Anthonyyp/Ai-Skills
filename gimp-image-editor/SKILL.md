---
name: gimp-image-editor
description: Control GIMP headlessly via its Script-Fu and Python batch CLI. Use for layered compositing, XCF/PSD, text layers, layer masks, GEGL filters, chroma keying, watermarking, batch export, and layer-preserving PDF/EPS/PSD output. Triggers on GIMP, .xcf, .psd, layers, "composite these", "make this transparent", "add a watermark", or batch image work where layers or precise text matter.
---

# GIMP Image Editor

GIMP ships `gimp-console`, a no-GUI binary that runs Script-Fu (Scheme) or
Python batch scripts. This skill wraps it so scripted image work is reliable
instead of a series of silent hangs.

## First: should this be GIMP at all?

GIMP costs ~3-4s of startup per invocation and its API is large and version-
sensitive. It earns that cost when the work is *editor* work; it does not when
the work is *conversion* work.

| Use GIMP | Use something else |
|---|---|
| Layers, layer masks, blend modes, opacity | Plain resize / crop / format convert → **ImageMagick** (`magick`) |
| `.xcf`, `.psd` read or write | Strip metadata, quick optimise → **ImageMagick** / `oxipng` |
| Text layers with real font layout | Video / animated formats → **ffmpeg** (see the `ffmpeg` skill) |
| GEGL filters, chroma key, colour-to-alpha | Purely programmatic pixel math → **Pillow** / **numpy** |
| Layer-preserving PDF/PSD export | Simple thumbnails over 1000s of files → **ImageMagick** |

If the task is "resize this folder to 800px webp", say so and use ImageMagick.
Reach for GIMP when layers, text, masks, or GEGL are genuinely involved.

### What this cannot do

**"Remove the background" only works when the background is a flat colour.**
`examples/chroma_key.py` keys a solid field; it has no idea what the subject
is. On a photograph — a person against a room, a product on a textured
surface — it will destroy the image while appearing to succeed. GIMP has no
scripted subject segmentation. Say so and suggest a segmentation tool
(`rembg`, a hosted API, or GIMP's interactive Foreground Select by hand)
rather than keying and hoping.

Similarly out of scope: content-aware fill/inpainting, upscaling beyond plain
resampling, OCR, and face/object detection.

## Running it

Everything goes through `scripts/gimp_cli.py` (host Python 3.8+, any platform).
It finds the GIMP binary, supplies the flags that batch mode requires, and —
importantly — turns a failing script into a **non-zero exit code**, which raw
`gimp-console` does not do.

```bash
python scripts/gimp_cli.py doctor                    # what's installed, which formats
python scripts/gimp_cli.py run myscript.py -- a b c  # run a script (args land in ARGS)
python scripts/gimp_cli.py eval "print(Gimp.version())"
python scripts/gimp_cli.py scm script.scm            # Script-Fu instead of Python
```

Run `doctor` first in a new environment. If GIMP isn't found, set
`GIMP_CONSOLE` to the binary.

## Discover the API — do not guess it

**The GIMP 2.10 → 3.x API changed enough that most examples online are wrong.**
`file-png-save` became `file-png-export`, `plug-in-autocrop` became
`gimp-image-autocrop`, `gimpfu` is gone entirely. Rather than trusting recall,
look up the real signature on the machine you're on:

```bash
python scripts/gimp_cli.py pdb text            # 1030 procedures, filtered
python scripts/gimp_cli.py args file-jpeg-export   # exact params, types, defaults
python scripts/gimp_cli.py gegl blur           # 309 filter ops, filtered
python scripts/gimp_cli.py geglargs gegl:unsharp-mask
```

`args` prints every parameter with its type, default, and enum values. Use it
before calling any procedure you haven't called before — it is faster than
debugging a wrong guess, and it is correct for the installed version.

## Writing scripts

Scripts run *inside* GIMP. `from gimp_helpers import *` gives you the wrappers;
`Gimp`, `Gegl`, `Gio` and an `ARGS` list are already in scope.

```python
from gimp_helpers import *

image, bg = new_image(1200, 630, "#0E6B6B")
place(image, "logo.png", "logo", width=300, x=60, y=60)
text_layer(image, "Release 2.0", font="Sans-serif Bold", size=72,
           fill="#F5EBDC", x=60, y=420)
apply_gegl(bg, "gegl:noise-rgb", independent=True, red=0.02)

export(image, "card.png")            # picks file-png-export
export(image, "card.jpg", quality=0.9)   # auto-flattens: JPEG has no alpha
save_xcf(image, "card.xcf")          # layered master
log(describe(image))
```

Key helpers: `new_image` `place` `text_layer` `apply_gegl` `export`
`export_each_layer` `save_xcf` `load_image` `fit_within` `scale_to_width`
`autocrop` `flattened` `describe` `pdb_run` `color`.

`pdb_run("proc-name", **kwargs)` calls any of the 1030 PDB procedures with
named arguments and raises on failure — use it for anything the helpers don't
wrap. Underscores become hyphens, so `layers_as_pages=True` sets
`layers-as-pages`.

## Batch work: one invocation, not one per file

Startup dominates. Loop **inside** one script:

```bash
python scripts/gimp_cli.py run examples/batch_convert.py -- src/ out/ --ext webp --max 1024
```

Not `for f in *.png; do gimp-console ...; done` — that multiplies startup by
the file count. `--fast` (adds `-d -f`) shaves startup further but disables
fonts, brushes, gradients and patterns, so never use it with `text_layer` or
gradient fills.

## References

Read these as needed — they are not preloaded.

| File | Contents |
|---|---|
| `references/invocation.md` | Every batch flag, per-OS binary locations, what hangs and why |
| `references/python-api.md` | GIMP 3 GI API patterns: images, layers, selections, filters, text, export |
| `references/script-fu.md` | Script-Fu / TinyScheme when Scheme is wanted or required |
| `references/recipes.md` | Task cookbook: watermark, chroma key, thumbnails, contact sheet, masks, PSD/PDF |
| `references/migration.md` | 2.10 → 3.x renames and removals; how to fix stale examples found online |
| `references/formats.md` | Import/export formats, per-format options, which preserve layers |

`examples/` holds runnable scripts; `tests/selftest.py` verifies the whole
helper surface against the local GIMP (`python scripts/gimp_cli.py run
tests/selftest.py`) and is the fastest way to check a new machine or a new
GIMP version.

## Gotchas that will otherwise cost an hour

- **`--batch-interpreter` is mandatory in GIMP 3.** Without it every `-b`
  aborts. `gimp_cli.py` supplies it.
- **Without `--quit`, a failed batch command hangs forever** waiting at an
  interactive prompt. `gimp_cli.py` supplies it.
- **A failed PDB call still exits 0** from raw `gimp-console` — it only prints
  `GIMP-Error:` and returns a status you must check. Only an uncaught Python
  exception is fatal (exit 64). `gimp_cli.py` normalises this to exit 1.
- **`Gimp.PDBStatusType.SUCCESS == 3`, not 0.** Compare against the enum;
  `if status:` is exactly backwards.
- **`layer.scale()` returns `False` rather than raising** if the layer isn't
  inserted into an image yet — the script carries on with an unscaled layer.
  Insert first, then scale. `place()` does this correctly.
- **`quality` means different things per format**: JPEG wants 0.0–1.0, WebP
  wants 0.0–100.0. `quality=0.85` on WebP is a legal 0.85% and ruins the file.
  `export()` normalises it; raw `pdb_run` does not.
- **`Gegl.list_operations()` is not the list of usable filters** — GIMP's ~51
  `gimp:*` ops are invisible to it but perfectly valid, and often the ones you
  want (`gimp:levels` has gamma, `gegl:levels` doesn't). Use `gimp_cli.py gegl`.
- **Methods, not module functions**: `gimp_<class>_<verb>(obj, …)` maps to
  `obj.<verb>(…)`. `Gimp.drawable_edit_gradient_fill()` does not exist;
  `drawable.edit_gradient_fill()` does.
- **Fonts are `"Family Style"`** — `"Sans-serif Bold"`, not `"Sans"` or a bare
  `"Arial"`. The portable generics are `Sans-serif`, `Serif`, `Monospace`.
- **GIMP is a native binary**: on Windows give it Windows paths, not MSYS/Git-
  Bash `/c/...` or `/tmp/...` paths.
- **EPS/PostScript cannot hold layers** — exporting one always flattens. For a
  layer-preserving page format use `file-pdf-export` with
  `layers-as-pages=True`, or PSD/XCF.
- **GEGL op names are not guessable**: it's `gegl:dropshadow`, not
  `gegl:drop-shadow`. Check with `gimp_cli.py gegl <pattern>`.
