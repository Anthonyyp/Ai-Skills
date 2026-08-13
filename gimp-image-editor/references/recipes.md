# Recipes

Every snippet here is extracted from `tests/test_recipes.py`, which runs
against a real GIMP. If something stops working, run that test — it will say
which recipe broke.

All examples assume a script run via `gimp_cli.py run`, so `Gimp`, `Gegl`,
`Gio`, `ARGS` and `from gimp_helpers import *` are in scope.

## Watermark (text)

```python
image = load_image(src)
mark = text_layer(image, "© EXAMPLE", font="Sans-serif Bold", size=36,
                  fill="#ffffff", name="watermark")
mark.set_opacity(45.0)
mark.set_offsets(image.get_width()  - mark.get_width()  - 24,
                 image.get_height() - mark.get_height() - 24)
export(image, dst)
```

Position after creating the layer — you need its measured width/height to
place it relative to an edge.

## Watermark (image/logo)

```python
logo = place(image, "logo.png", "logo", width=160, x=24, y=24)
logo.set_opacity(60.0)
```

## Thumbnail

```python
image = load_image(src)
fit_within(image, 200, 200)          # never upscales unless allow_upscale=True
export(image, dst, quality=0.82)     # quality is 0.0-1.0, not 0-100
```

For a whole folder use `examples/batch_convert.py` — one GIMP process, not one
per file.

## Contact sheet

```python
cols, cell, pad = 4, 220, 12
rows = (len(paths) + cols - 1) // cols
sheet, _ = new_image(cols * (cell + pad) + pad, rows * (cell + pad) + pad, "#1b1b1b")
for i, path in enumerate(paths):
    place(sheet, path, "tile%d" % i,
          width=cell,
          x=pad + (i % cols) * (cell + pad),
          y=pad + (i // cols) * (cell + pad))
export(sheet, "contact_sheet.png")
```

## Layer mask (gradient fade)

```python
mask = layer.create_mask(Gimp.AddMaskType.WHITE)
layer.add_mask(mask)
Gimp.context_set_foreground(color("#ffffff"))   # white = opaque
Gimp.context_set_background(color("#000000"))   # black = transparent
Gimp.context_set_gradient(Gimp.Gradient.get_by_name("FG to BG (RGB)"))
mask.edit_gradient_fill(Gimp.GradientType.LINEAR, 0.0,
                        False, 3, 0.2, False,
                        0.0, 0.0, float(image.get_width()), 0.0)
```

`Gimp.AddMaskType` options: `WHITE` (all visible), `BLACK` (all hidden),
`ALPHA`, `ALPHA_TRANSFER`, `SELECTION`, `COPY`, `CHANNEL`.

The method is on the drawable — `mask.edit_gradient_fill(...)`, following the
`gimp_<class>_<verb>(obj, …)` → `obj.<verb>(…)` rule. There is no
`Gimp.drawable_edit_gradient_fill(...)` module function, which is a common
wrong guess. `pdb_run("gimp-drawable-edit-gradient-fill", drawable=mask, ...)`
also works and lets you pass the arguments by name.

## Drop shadow on a cut-out

```python
apply_gegl(layer, "gegl:dropshadow", x=10.0, y=10.0, radius=8.0,
           opacity=0.55, color="#000000")
export(image, dst, flatten=False)     # keep alpha
```

It's `gegl:dropshadow` — **not** `gegl:drop-shadow`. The filter grows the layer
beyond the canvas to fit the shadow, which is expected.

## Colour and tone

```python
pdb_run("gimp-drawable-brightness-contrast", drawable=layer,
        brightness=0.15, contrast=0.25)          # both -1.0 .. 1.0
pdb_run("gimp-drawable-desaturate", drawable=layer,
        desaturate_mode=Gimp.DesaturateMode.LUMINANCE)
pdb_run("gimp-drawable-levels-stretch", drawable=layer)   # auto-levels
apply_gegl(layer, "gegl:saturation", scale=1.6)
apply_gegl(layer, "gegl:unsharp-mask", std_dev=3.0, scale=0.8)
```

Also available: `gimp-drawable-levels`, `gimp-drawable-curves-spline`,
`gimp-drawable-curves-explicit`, `gimp-drawable-hue-saturation`.

## Blend modes

```python
top.set_mode(Gimp.LayerMode.OVERLAY)
top.set_opacity(55.0)
```

`Gimp.LayerMode` includes `NORMAL MULTIPLY SCREEN OVERLAY DIFFERENCE ADDITION
SUBTRACT DARKEN_ONLY LIGHTEN_ONLY HSL_COLOR SOFTLIGHT HARDLIGHT` and more.
List them: `gimp_cli.py eval "print([v for v in dir(Gimp.LayerMode) if v.isupper()])"`.

## Circular crop

```python
layer.add_alpha()
size = min(image.get_width(), image.get_height())
image.select_ellipse(Gimp.ChannelOps.REPLACE,
                     (image.get_width() - size) / 2,
                     (image.get_height() - size) / 2, size, size)
Gimp.Selection.invert(image)
layer.edit_clear()
Gimp.Selection.none(image)
export(image, dst, flatten=False)
```

Soften the edge by calling `Gimp.Selection.feather(image, 4.0)` before
inverting. **Always** `Gimp.Selection.none()` when done — a leftover selection
silently constrains every later operation, which is a classic bug.

## Transforms

```python
pdb_run("gimp-image-rotate", image=image, rotate_type=Gimp.RotationType.DEGREES90)
pdb_run("gimp-image-flip", image=image, flip_type=Gimp.OrientationType.HORIZONTAL)
```

Arbitrary angles and per-layer transforms: `gimp-item-transform-rotate`,
`gimp-item-transform-flip`, `gimp-item-transform-scale`.

## Canvas border / padding

```python
pad = 40
image.resize(image.get_width() + pad * 2, image.get_height() + pad * 2, pad, pad)
image.flatten()          # fills the new area with the background colour
```

`image.resize(w, h, offx, offy)` changes the canvas; `image.scale(w, h)`
resamples the content. Easy to confuse.

## Animated GIF from layers

```python
for i, spec in enumerate(colors):
    frame = new_layer(image, "frame %d (100ms)" % i, position=0)
    ...
image.convert_indexed(Gimp.ConvertDitherType.NONE,
                      Gimp.ConvertPaletteType.WEB, 255, False, True, "")
pdb_run("file-gif-export", run_mode=Gimp.RunMode.NONINTERACTIVE,
        image=image, file=gfile(dst), options=None,
        as_animation=True, loop=True, default_delay=100, default_dispose=1)
```

GIF **must** be indexed first. Per-frame timing goes in the layer name as
`(100ms)` — a GIMP convention, not a parameter.

For real video work use ffmpeg, not GIMP.

## PSD round trip

```python
export(image, "layers.psd", flatten=False)
back = load_image("layers.psd")
assert len(back.get_layers()) >= 3
```

## Layer-preserving PDF, and splitting it back out

```python
pdb_run("file-pdf-export", run_mode=Gimp.RunMode.NONINTERACTIVE,
        image=image, file=gfile("out.pdf"), options=None,
        vectorize=False, ignore_hidden=False, apply_masks=True,
        layers_as_pages=True, reverse_order=False, root_layers_only=True,
        convert_text_layers=False, fill_background_color=False)

back = load_image("out.pdf")          # one layer per page
export_each_layer(back, "separated/")
```

Page names don't survive the round trip (pages come back as `1`, `2`, …), so
record the original stack yourself if you need the names.

## Chroma key / background removal

See `examples/chroma_key.py`. The short version:

```python
layer.add_alpha()
key = layer.get_pixel(2, 2)          # sample, don't assume
apply_gegl(layer, "gegl:color-to-alpha", color=key,
           transparency_threshold=0.15, opacity_threshold=0.85)
```

Sampling matters for AI-generated art: image models drift a few points off
whatever background colour you requested, so a hard-coded `#FF00FF` leaves a
visible halo.

## Reading information without changing anything

```python
image = load_image(src)
print(describe(image))                       # size, layers, offsets, modes
px = image.get_layers()[0].get_pixel(5, 5)   # Gegl.Color
r, g, b, a = px.get_rgba()
```

For a quick one-off, skip the script file entirely:

```bash
python scripts/gimp_cli.py eval "
from gimp_helpers import *
print(describe(load_image(r'C:\path\file.psd')))"
```

If you only need width/height, don't start GIMP at all — use Pillow, or
`magick identify`. GIMP's 3-4s startup is not worth it for metadata.
