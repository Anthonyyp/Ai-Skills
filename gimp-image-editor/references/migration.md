# GIMP 2.10 → 3.x: fixing examples found online

Most GIMP scripting material on the web is 2.10-era and **will not run** on
GIMP 3. When you find a promising snippet, translate it before trusting it.

The table below was produced by checking each 2.10 name against the live PDB of
GIMP 3.2.4 — everything in the "gone" column genuinely does not exist.

## Verify before you debug

```bash
python scripts/gimp_cli.py pdb <fragment>     # does any such procedure exist?
python scripts/gimp_cli.py args <name>        # what are its real parameters?
```

That is faster than reasoning about why a snippet fails.

## Confirmed removed, with replacements

### File output: `-save` → `-export`

| GIMP 2.10 (gone) | GIMP 3 |
|---|---|
| `file-png-save` | `file-png-export` |
| `file-jpeg-save` | `file-jpeg-export` |
| `file-tiff-save` | `file-tiff-export` |
| `file-psd-save` | `file-psd-export` |
| `file-gif-save` | `file-gif-export` |
| `file-webp-save` | `file-webp-export` |
| `file-pdf-save`, `file-pdf-save-multi` | `file-pdf-export`, `file-pdf-export-multi` |

The **signature changed too**, not just the name. 2.10 took
`(run-mode, image, drawable, filename, raw-filename, ...)`. GIMP 3 takes
`(run-mode, image, file, options, ...)` — a `GFile` rather than two strings,
an `options` argument, and no drawable. Renaming alone is not enough.

`.xcf` is the exception: it is still `Gimp.file_save` / `gimp-xcf-save`,
because XCF is saved, not exported.

### Active layer → selected layers

| Gone | Replacement |
|---|---|
| `gimp-image-get-active-layer` | `gimp-image-get-selected-layers` (returns a **list**) |
| `gimp-image-set-active-layer` | `gimp-image-set-selected-layers` |
| `gimp-image-get-active-drawable` | `gimp-image-get-selected-drawables` |

GIMP 3 supports operating on several layers at once, so the singular "active"
concept was replaced by a selection list. In batch scripts you usually want
`image.get_layers()[0]` and no notion of "active" at all.

### Layer insertion

| Gone | Replacement |
|---|---|
| `gimp-image-add-layer` | `gimp-image-insert-layer(image, layer, parent, position)` |

The extra `parent` argument is for layer groups; pass `None`.

### Item vs drawable naming

| Gone | Replacement |
|---|---|
| `gimp-drawable-set-name` | `gimp-item-set-name` |
| `gimp-drawable-get-name` | `gimp-item-get-name` |
| `gimp-drawable-transform-scale` | `gimp-item-transform-scale` |

Anything common to layers, channels and paths moved to `gimp-item-*`.

### Colour adjustment moved onto the drawable

| Gone | Replacement |
|---|---|
| `gimp-brightness-contrast` | `gimp-drawable-brightness-contrast` |
| `gimp-levels` | `gimp-drawable-levels` |
| `gimp-desaturate` | `gimp-drawable-desaturate` |
| `gimp-hue-saturation` | `gimp-drawable-hue-saturation` |

### Vectors → paths

| Gone | Replacement |
|---|---|
| `gimp-vectors-new` | `gimp-path-new` |
| `gimp-image-get-vectors` | `gimp-image-get-paths` |

The whole `gimp-vectors-*` family is now `gimp-path-*`.

### Filter plug-ins → GEGL operations

| Gone | Replacement |
|---|---|
| `plug-in-gauss` | `gegl:gaussian-blur` |
| `plug-in-unsharp-mask` | `gegl:unsharp-mask` |
| `plug-in-drop-shadow` | `gegl:dropshadow` |
| `plug-in-colortoalpha` | `gegl:color-to-alpha` |
| `plug-in-autocrop` | `gimp-image-autocrop` |
| `plug-in-autocrop-layer` | `gimp-image-autocrop-selected-layers` |

Most 2.10 `plug-in-*` filters are GEGL ops now, applied through
`Gimp.DrawableFilter` (see `python-api.md`) rather than a PDB call. Note the
autocrop pair went to `gimp-image-*`, not to GEGL.

`plug-in-script-fu-eval` still exists — it is the batch interpreter.

## Python: `gimpfu` is gone entirely

```python
# 2.10 - does not work in GIMP 3
from gimpfu import *
img = pdb.gimp_image_new(w, h, RGB)
pdb.gimp_image_add_layer(img, layer, 0)
pdb.file_png_save(img, layer, path, path, 0,9,1,1,1,1,1)
register(...)
main()
```

```python
# GIMP 3
import gi
gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gegl, Gio
img = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
img.insert_layer(layer, None, 0)
pdb_run("file-png-export", run_mode=Gimp.RunMode.NONINTERACTIVE,
        image=img, file=gfile(path), options=None, compression=9)
```

Changes to expect:
- No `pdb.foo_bar()` attribute access — look the procedure up, or use a method.
- Constants are namespaced enums: `RGB` → `Gimp.ImageBaseType.RGB`,
  `NORMAL_MODE` → `Gimp.LayerMode.NORMAL`, `RUN-NONINTERACTIVE` →
  `Gimp.RunMode.NONINTERACTIVE`.
- Colours are `Gegl.Color`, not `(r, g, b)` tuples.
- Paths are `Gio.File`, not strings.
- Plug-in registration is a `Gimp.PlugIn` subclass, not `register()`/`main()`.

## Script-Fu changes

The language is unchanged (still TinyScheme, still `car` to unwrap returns),
but the PDB renames above apply identically. A 2.10 `.scm` typically needs only
the procedure names and their argument lists updated.

## Batch invocation changes

- `--batch-interpreter` is **required** in 3.x. 2.10 defaults to Script-Fu when
  it's omitted, so a 2.10 script that relied on that default breaks on 3.x with
  *"No batch interpreter specified"*.
- Otherwise `-i`, `-b`, `--quit`, `-d`, `-f` behave the same.
