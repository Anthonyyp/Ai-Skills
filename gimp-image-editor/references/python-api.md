# The GIMP 3 Python API

GIMP 3 exposes libgimp through GObject Introspection. There is no `gimpfu`
module any more — `from gimpfu import *` and `pdb.gimp_image_new(...)` are 2.10
idioms that fail outright.

## Preamble

`gimp_cli.py run` already does this for you; write it yourself only when
invoking `gimp-console` directly.

```python
import gi
gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gimp, Gegl, Gio, GLib
Gegl.init(None)
```

## Calling PDB procedures

Two routes, and you need both.

**1. Direct methods**, where a binding exists:

```python
image = Gimp.Image.new(800, 600, Gimp.ImageBaseType.RGB)
layer = Gimp.Layer.new(image, "bg", 800, 600,
                       Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL)
image.insert_layer(layer, None, 0)
layer.scale(400, 300, False)
```

The naming rule that predicts most of the API:

> `gimp_<class>_<verb>(obj, ...)` becomes `obj.<verb>(...)`.

So `gimp-drawable-edit-gradient-fill` is **`drawable.edit_gradient_fill(...)`**
— *not* `Gimp.drawable_edit_gradient_fill(...)`, which does not exist. Only
genuinely free functions stay module-level: `Gimp.context_*`, `Gimp.file_*`,
`Gimp.version()`, `Gimp.displays_flush()`. There is no `Gimp.Context` class at
all; context is ~120 `Gimp.context_*` functions.

**2. The PDB**, for procedures with no binding, or when you want to pass
arguments by name:

```python
proc = Gimp.get_pdb().lookup_procedure("file-pdf-export")
cfg = proc.create_config()
cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
cfg.set_property("image", image)
cfg.set_property("file", Gio.File.new_for_path(path))
cfg.set_property("layers-as-pages", True)
result = proc.run(cfg)
if result.index(0) != Gimp.PDBStatusType.SUCCESS:
    raise RuntimeError(result.index(1))
```

`gimp_helpers.pdb_run()` wraps that whole dance:

```python
pdb_run("file-pdf-export", run_mode=Gimp.RunMode.NONINTERACTIVE,
        image=image, file=gfile(path), options=None, layers_as_pages=True, ...)
```

**Property names use hyphens.** `pdb_run` converts underscores, so
`layers_as_pages=True` works.

**Look up the signature, don't guess:**

```bash
python scripts/gimp_cli.py args file-pdf-export
```

## Return values and status

`proc.run(cfg)` returns a `GimpValueArray`. It has **no `len()`** — use
`.length()` and `.index(i)`. Index 0 is always the status; real return values
start at index 1. `pdb_run` strips the status and unwraps a single value.

**`Gimp.PDBStatusType.SUCCESS == 3`, not 0.** The enum is
`EXECUTION_ERROR=0, CALLING_ERROR=1, PASS_THROUGH=2, SUCCESS=3, CANCEL=4`, so
`if status:` and `if status == 0:` are both exactly backwards. Always compare
against the enum member.

Two more silent-failure traps:

- **A failing PDB call does not raise.** It prints `GIMP-Error: ...` to stderr
  and returns a non-SUCCESS status you have to check.
- **Boolean-returning methods return `False` rather than raising.**
  `layer.scale()` on a layer that hasn't been inserted into an image returns
  `False`, logs a `GIMP-Error`, and your script carries on with an unscaled
  layer. Check the return value or use the helpers.

Some properties can't be set with `set_property` at all: `GimpCoreObjectArray`
needs `cfg.set_core_object_array("drawables", [layer])`, and colour arrays need
`set_color_array`. Introspection shows the property either way.

## Images and layers

```python
image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(p))
layers = image.get_layers()            # top to bottom; a LIST, not one layer
image.insert_layer(layer, None, 0)     # (layer, parent-group-or-None, position)
image.remove_layer(layer)
image.flatten()                        # returns the resulting layer
image.duplicate()
image.delete()                         # free it; batch scripts leak otherwise
```

`gimp-image-get-active-layer` is **gone**. GIMP 3 supports multiple selected
layers: `image.get_selected_layers()` / `image.set_selected_layers([...])`.
Most scripts should just index `get_layers()`.

### Order of operations that bites

```python
layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, gfile(p))
image.insert_layer(layer, None, 0)     # MUST come first
layer.scale(400, 300, False)           # else: "cannot be used because it has
layer.set_offsets(20, 20)              #        not been added to an image"
```

The failure prints as a `GIMP-Error` on stderr and the script keeps going with
an unscaled layer — a silent wrong result, not a crash. `place()` gets this
right.

## Colour

`Gegl.Color`, not the old `(r, g, b)` tuples:

```python
c = Gegl.Color.new("#e8a33d")
c = Gegl.Color.new("red")
r, g, b, a = c.get_rgba()              # floats 0.0-1.0
c.set_rgba(0.9, 0.6, 0.2, 1.0)
```

**Strings and `set_rgba()` are different colour spaces.** `Gegl.Color.new()`
parses sRGB and stores it linearised, while `set_rgba()` writes linear-light
values straight through:

```python
Gegl.Color.new("#808080").get_rgba()   # -> 0.2159 ...  (sRGB, linearised)
c.set_rgba(0.5, 0.5, 0.5, 1.0)         # -> 0.5     ...  (linear-light)
```

So `"#808080"` and `set_rgba(.5,.5,.5,1)` are **not** the same colour. Prefer
hex strings unless you specifically want linear values.

`gimp_helpers.color()` accepts a hex string, a name, a tuple, or a
`Gegl.Color`; its tuple path is `set_rgba`, so tuples are linear.

## Selections and fills

```python
image.select_rectangle(Gimp.ChannelOps.REPLACE, x, y, w, h)
image.select_ellipse(Gimp.ChannelOps.REPLACE, x, y, w, h)
Gimp.Selection.invert(image)
Gimp.Selection.feather(image, 4.0)
Gimp.Selection.none(image)             # ALWAYS clean up

Gimp.context_set_foreground(color("#ff0000"))
Gimp.context_set_background(color("#000000"))
layer.edit_fill(Gimp.FillType.FOREGROUND)
layer.edit_clear()
```

A leftover selection silently constrains every subsequent operation. When a
later step mysteriously affects only part of the image, this is why.

## GEGL filters

```python
filt = Gimp.DrawableFilter.new(drawable, "gegl:gaussian-blur", "")
cfg = filt.get_config()
cfg.set_property("std-dev-x", 4.0)
cfg.set_property("std-dev-y", 4.0)
filt.update()
drawable.merge_filter(filt)            # destructive: bake it in
```

`new()` only builds the filter — it must then be **either** merged **or**
appended; these are two alternative terminal operations, and `merge_filter()`
does *not* require `append_filter()` first.

- **`merge_filter()`** applies it destructively and invalidates the filter
  object — don't reuse it. It merges *below* any existing non-destructive
  effects.
- **`append_filter()`** adds a live, re-editable, non-destructive effect (new
  in GIMP 3). It appears in the Layers dock and **survives an XCF round trip**.
  `get_filters()` returns the stack topmost-first; `merge_filters()` (plural,
  no argument) bakes the whole stack.
- **After `append_filter()`, every later config change needs `update()`.** The
  config is not synced back to the core automatically — `set_opacity`,
  `set_blend_mode` and `set_aux_input` all defer too. Before `merge_filter()`
  it isn't strictly required, but GIMP's own bundled `foggify.py` calls it
  anyway; do the same.
- `append_new_filter()` / `merge_new_filter()` are varargs and therefore
  **absent from Python by design**. Script-Fu does get them.
- `gimp_helpers.apply_gegl(drawable, op, **props)` is the destructive path.

### Two operation namespaces

`Gegl.list_operations()` is **not** the set of usable filters:

| Source | Count (3.2.4) | Contents |
|---|---|---|
| `Gegl.list_operations()` | 258 | `gegl:*` and `svg:*` |
| `Gimp.DrawableFilter.operation_get_available()` | 182 | filter-usable set, **plus ~51 `gimp:*` ops GEGL cannot see** |

GIMP registers its `gimp:*` ops in the core process, so a plug-in's GEGL never
enumerates them — but they are perfectly valid filters. `gimp_cli.py gegl`
lists the union and marks which are filter-usable.

Prefer `gimp:*` when you want the GIMP UI's behaviour: those ops carry extra
`gimp-clip` / `gimp-region` / `gimp-mode` / `gimp-opacity` properties and
**respect the current selection by default**. The `gegl:` op of the same name
often differs materially:

| Want | Use | Because |
|---|---|---|
| UI-equivalent levels | `gimp:levels` | `gegl:levels` has **no gamma** |
| UI-equivalent brightness/contrast | `gimp:brightness-contrast` | additive ±1; the `gegl:` one is multiplicative, contrast default 1.0 |
| Posterize | `gimp:posterize` | different default (3 vs 8) and range |

**Operation names are not guessable.** `gegl:dropshadow` is one word;
`gegl:drop-shadow`, `gegl:hue-saturation` and `gegl:desaturate` do not exist.
`gegl:gaussian-blur` has **no `radius`** — it's `std-dev-x`/`std-dev-y`, and
GIMP 2's `plug-in-gauss` radius was roughly `std_dev * 2`, so don't port
numbers across verbatim. Always look it up:

```bash
python scripts/gimp_cli.py gegl shadow
python scripts/gimp_cli.py geglargs gegl:dropshadow
```

A few op categories don't work as drawable filters at all: geometry ops
(`gegl:crop`, `gegl:scale-ratio`) are pointless because a filter renders into
the drawable's fixed extent — use `Layer.scale()` / `Image.crop()`. Source ops
(`gegl:color`, `gegl:plasma`, `gegl:text`) have no input pad and replace rather
than filter. GIMP also refuses sink ops, `gegl:nop`, and `gegl:gegl` outright.

## Text

```python
font = Gimp.Font.get_by_name("Sans-serif Bold")     # "Family Style"
layer = Gimp.TextLayer.new(image, "Hello", font, 48, Gimp.Unit.pixel())
image.insert_layer(layer, None, 0)
layer.set_color(color("#ffffff"))
layer.set_offsets(40, 40)
```

`Gimp.Font.get_by_name` returns `None` for an unknown font and `TextLayer.new`
then fails unhelpfully. `gimp_helpers.text_layer()` raises a clear error
instead. Enumerate what exists:

```bash
python scripts/gimp_cli.py eval "print([f.get_name() for f in Gimp.fonts_get_list('')])"
```

The portable generics are `Sans-serif`, `Serif`, `Monospace`, each with
` Bold` / ` Italic` / ` Bold Italic`. Bare `Sans` is **not** a font.

Text layers stay editable in XCF and can export as real text to PDF
(`convert-text-layers=False`).

## Loading and saving

```python
Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, gfile(path))         # -> Image
Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, gfile(path))  # -> Layer
Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gfile(path), None)  # XCF
```

**Save vs export**: `Gimp.file_save` is for `.xcf`. Everything else goes
through a `file-<fmt>-export` procedure so you can pass format options.
`gimp_helpers.export()` picks the right one and auto-flattens for formats
without alpha. See `formats.md`.

The `options` parameter (a `GimpExportOptions`) can be `None` — GIMP then uses
defaults. Only build one when you need to control the colour-profile /
metadata export policy.

## Errors

PDB failures come back as a status, **not** an exception:

```python
result = proc.run(cfg)
status = result.index(0)               # Gimp.PDBStatusType
```

`SUCCESS`, `EXECUTION_ERROR`, `CALLING_ERROR`, `PASS_THROUGH`, `CANCEL`.
Ignoring the status is how scripts "succeed" while doing nothing — `pdb_run`
raises instead.

## Authoritative sources

When introspection isn't enough:

- **API reference** — <https://developer.gimp.org/api/3.0/libgimp/>
  (`class.Image.html`, `method.Drawable.edit_gradient_fill.html`,
  `enum.PDBStatusType.html`, …)
- **Python signatures**, the most practical lookup —
  <https://lazka.github.io/pgi-docs/#Gimp-3.0> and
  <https://lazka.github.io/pgi-docs/#Gegl-0.4>
  (⚠️ it types `Image.select_*`'s first argument as `Gimp.SelectionMode`; the C
  header says `GimpChannelOps` — `ADD=0, SUBTRACT=1, REPLACE=2, INTERSECT=3`)
- **Porting guide** — <https://developer.gimp.org/resource/gimp3-plug-in-porting-guide/>
  plus `/classes/`, `/pdb-calls/`, `/removed_functions/`. GIMP labels these
  "likely incomplete", and some examples are 2.99-era and no longer run.
- **GEGL operations** — <https://gegl.org/operations/> (per-op pages carry the
  UI ranges that Python introspection cannot reach). The API index at
  `gegl.org/api/` is a dead link; use <https://developer.gimp.org/api/gegl/>.
- **Best worked examples: GIMP's own bundled Python plug-ins**, on disk at
  `<GIMP>/lib/gimp/3.0/plug-ins/*/*.py` — `foggify.py` (layers, masks,
  DrawableFilter, context), `file-openraster.py` (load/export procedures),
  `python-eval.py` (the batch interpreter itself).

There is also a bundled `gegl` CLI that introspects operations without starting
GIMP at all:

```bash
"<GIMP>/bin/gegl.exe" --list-all
"<GIMP>/bin/gegl.exe" --info gegl:unsharp-mask
```

## Housekeeping

Call `image.delete()` on images you're done with. Batch loops that skip it
accumulate images and you'll see `stray image seems to have been left around`
and GeglBuffer leak warnings at exit. They're usually harmless but they mask
real problems, and memory does grow over a long batch.
