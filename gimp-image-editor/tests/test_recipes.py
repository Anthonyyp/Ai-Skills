"""Verifies every recipe in references/recipes.md actually runs.

    python scripts/gimp_cli.py run tests/test_recipes.py -- <output-folder>

The cookbook is generated from code that passes here, so a recipe in the docs
is never merely plausible.
"""

import os
import sys

from gimp_helpers import *  # noqa: F401,F403

OUT = ARGS[0] if ARGS else os.path.join(os.path.dirname(__file__), "_recipes_out")  # noqa: F821
os.makedirs(OUT, exist_ok=True)

passed, failed = [], []


def check(label, fn):
    try:
        fn()
        passed.append(label)
        print("  PASS  %s" % label)
    except Exception as exc:
        failed.append((label, exc))
        print("  FAIL  %s -> %s: %s" % (label, type(exc).__name__, exc))


def sample(w=480, h=320, fill="#2f6f9f"):
    """A throwaway image with something in it."""
    image, layer = new_image(w, h, fill)
    Gimp.context_set_foreground(color("#e8a33d"))  # noqa: F821
    image.select_ellipse(Gimp.ChannelOps.REPLACE, w * 0.15, h * 0.15, w * 0.5, h * 0.5)  # noqa: F821
    layer.edit_fill(Gimp.FillType.FOREGROUND)  # noqa: F821
    Gimp.Selection.none(image)  # noqa: F821
    return image, layer


# --- 1. text watermark ----------------------------------------------------

def r_watermark_text():
    image, _ = sample(800, 500)
    mark = text_layer(image, "© EXAMPLE", font="Sans-serif Bold", size=36,
                      fill="#ffffff", name="watermark")
    mark.set_opacity(45.0)
    mark.set_offsets(image.get_width() - mark.get_width() - 24,
                     image.get_height() - mark.get_height() - 24)
    export(image, os.path.join(OUT, "watermark_text.png"))
    image.delete()


# --- 2. image watermark ---------------------------------------------------

def r_watermark_image():
    image, _ = sample(800, 500)
    logo = place(image, os.path.join(OUT, "watermark_text.png"), "logo",
                 width=160, x=24, y=24)
    logo.set_opacity(60.0)
    export(image, os.path.join(OUT, "watermark_image.png"))
    image.delete()


# --- 3. thumbnail ---------------------------------------------------------

def r_thumbnail():
    image = load_image(os.path.join(OUT, "watermark_text.png"))
    fit_within(image, 200, 200)
    assert image.get_width() <= 200 and image.get_height() <= 200
    export(image, os.path.join(OUT, "thumb.jpg"), quality=0.82)
    image.delete()


# --- 4. contact sheet -----------------------------------------------------

def r_contact_sheet():
    tiles = [os.path.join(OUT, "watermark_text.png"),
             os.path.join(OUT, "watermark_image.png"),
             os.path.join(OUT, "thumb.jpg")]
    cols, cell, pad = 2, 220, 12
    rows = (len(tiles) + cols - 1) // cols
    sheet, _ = new_image(cols * (cell + pad) + pad,
                         rows * (cell + pad) + pad, "#1b1b1b")
    for i, path in enumerate(tiles):
        x = pad + (i % cols) * (cell + pad)
        y = pad + (i // cols) * (cell + pad)
        place(sheet, path, "tile%d" % i, width=cell, x=x, y=y)
    export(sheet, os.path.join(OUT, "contact_sheet.png"))
    sheet.delete()


# --- 5. layer mask, gradient fade ----------------------------------------

def r_layer_mask_fade():
    image, bg = sample(600, 400, "#102030")
    top = place(image, os.path.join(OUT, "watermark_text.png"), "top", width=600)
    mask = top.create_mask(Gimp.AddMaskType.WHITE)  # noqa: F821
    top.add_mask(mask)
    Gimp.context_set_foreground(color("#ffffff"))  # noqa: F821
    Gimp.context_set_background(color("#000000"))  # noqa: F821
    Gimp.context_set_gradient(Gimp.Gradient.get_by_name("FG to BG (RGB)"))  # noqa: F821
    # Method form: gimp_<class>_<verb>(obj, ...) -> obj.<verb>(...).
    # Gimp.drawable_edit_gradient_fill(...) does NOT exist.
    mask.edit_gradient_fill(Gimp.GradientType.LINEAR, 0.0,  # noqa: F821
                            False, 3, 0.2, False,
                            0.0, 0.0, float(image.get_width()), 0.0)
    export(image, os.path.join(OUT, "mask_fade.png"))
    image.delete()


# --- 6. drop shadow on a transparent cut-out -----------------------------

def r_drop_shadow():
    image = Gimp.Image.new(400, 400, Gimp.ImageBaseType.RGB)  # noqa: F821
    layer = new_layer(image, "shape")
    Gimp.context_set_foreground(color("#e8a33d"))  # noqa: F821
    image.select_ellipse(Gimp.ChannelOps.REPLACE, 100, 100, 200, 200)  # noqa: F821
    layer.edit_fill(Gimp.FillType.FOREGROUND)  # noqa: F821
    Gimp.Selection.none(image)  # noqa: F821
    apply_gegl(layer, "gegl:dropshadow", x=10.0, y=10.0, radius=8.0,
               opacity=0.55, color="#000000")
    export(image, os.path.join(OUT, "drop_shadow.png"), flatten=False)
    image.delete()


# --- 7. colour and tone ---------------------------------------------------

def r_brightness_contrast():
    image, layer = sample()
    pdb_run("gimp-drawable-brightness-contrast", drawable=layer,
            brightness=0.15, contrast=0.25)
    export(image, os.path.join(OUT, "bright.png"))
    image.delete()


def r_desaturate():
    image, layer = sample()
    pdb_run("gimp-drawable-desaturate", drawable=layer,
            desaturate_mode=Gimp.DesaturateMode.LUMINANCE)  # noqa: F821
    export(image, os.path.join(OUT, "desaturated.png"))
    image.delete()


def r_levels_stretch():
    image, layer = sample()
    pdb_run("gimp-drawable-levels-stretch", drawable=layer)
    export(image, os.path.join(OUT, "levels.png"))
    image.delete()


def r_gegl_color_ops():
    image, layer = sample()
    apply_gegl(layer, "gegl:saturation", scale=1.6)
    apply_gegl(layer, "gegl:unsharp-mask", std_dev=3.0, scale=0.8)
    export(image, os.path.join(OUT, "punchy.png"))
    image.delete()


# --- 8. blend modes -------------------------------------------------------

def r_blend_mode():
    image, bg = sample(500, 350, "#334455")
    top = new_layer(image, "tint")
    Gimp.context_set_background(color("#ff8800"))  # noqa: F821
    top.edit_fill(Gimp.FillType.BACKGROUND)  # noqa: F821
    top.set_mode(Gimp.LayerMode.OVERLAY)  # noqa: F821
    top.set_opacity(55.0)
    export(image, os.path.join(OUT, "blend_overlay.png"))
    image.delete()


# --- 9. circular crop -----------------------------------------------------

def r_circular_crop():
    image = load_image(os.path.join(OUT, "watermark_text.png"))
    layer = image.get_layers()[0]
    layer.add_alpha()
    size = min(image.get_width(), image.get_height())
    image.select_ellipse(Gimp.ChannelOps.REPLACE,  # noqa: F821
                         (image.get_width() - size) / 2,
                         (image.get_height() - size) / 2, size, size)
    Gimp.Selection.invert(image)  # noqa: F821
    layer.edit_clear()
    Gimp.Selection.none(image)  # noqa: F821
    export(image, os.path.join(OUT, "circle.png"), flatten=False)
    image.delete()


# --- 10. transforms -------------------------------------------------------

def r_rotate_flip():
    image = load_image(os.path.join(OUT, "watermark_text.png"))
    pdb_run("gimp-image-rotate", image=image, rotate_type=Gimp.RotationType.DEGREES90)  # noqa: F821
    pdb_run("gimp-image-flip", image=image, flip_type=Gimp.OrientationType.HORIZONTAL)  # noqa: F821
    export(image, os.path.join(OUT, "rotated.png"))
    image.delete()


# --- 11. canvas border ----------------------------------------------------

def r_canvas_border():
    image = load_image(os.path.join(OUT, "watermark_text.png"))
    pad = 40
    w, h = image.get_width(), image.get_height()
    image.resize(w + pad * 2, h + pad * 2, pad, pad)
    image.flatten()
    export(image, os.path.join(OUT, "bordered.png"))
    image.delete()


# --- 12. animated gif from layers ----------------------------------------

def r_animated_gif():
    image, _ = new_image(200, 200, "#000000")
    for i, spec in enumerate(("#ff0000", "#00ff00", "#0000ff")):
        frame = new_layer(image, "frame %d (100ms)" % i, position=0)
        Gimp.context_set_background(color(spec))  # noqa: F821
        frame.edit_fill(Gimp.FillType.BACKGROUND)  # noqa: F821
    image.convert_indexed(Gimp.ConvertDitherType.NONE,  # noqa: F821
                          Gimp.ConvertPaletteType.WEB, 255, False, True, "")
    pdb_run("file-gif-export", run_mode=Gimp.RunMode.NONINTERACTIVE,  # noqa: F821
            image=image, file=gfile(os.path.join(OUT, "anim.gif")),
            options=None, as_animation=True, loop=True, default_delay=100,
            default_dispose=1)
    assert os.path.getsize(os.path.join(OUT, "anim.gif")) > 0
    image.delete()


# --- 13. psd round trip ---------------------------------------------------

def r_psd_roundtrip():
    image, _ = sample(320, 240)
    new_layer(image, "extra")
    text_layer(image, "PSD", size=40, fill="#ffffff", x=20, y=20)
    path = os.path.join(OUT, "layers.psd")
    export(image, path, flatten=False)
    image.delete()
    back = load_image(path)
    assert len(back.get_layers()) >= 3, len(back.get_layers())
    back.delete()


# --- 14. read information without changing anything ----------------------

def r_read_info():
    image = load_image(os.path.join(OUT, "watermark_text.png"))
    layer = image.get_layers()[0]
    px = layer.get_pixel(5, 5)
    rgba = px.get_rgba()
    info = describe(image)
    assert "x" in info
    print("        corner pixel #%02X%02X%02X"
          % tuple(int(round(c * 255)) for c in rgba[:3]))
    image.delete()


for label, fn in [
    ("text watermark", r_watermark_text),
    ("image watermark", r_watermark_image),
    ("thumbnail", r_thumbnail),
    ("contact sheet", r_contact_sheet),
    ("layer mask gradient fade", r_layer_mask_fade),
    ("drop shadow", r_drop_shadow),
    ("brightness/contrast", r_brightness_contrast),
    ("desaturate", r_desaturate),
    ("levels stretch", r_levels_stretch),
    ("gegl saturation + unsharp", r_gegl_color_ops),
    ("blend mode overlay", r_blend_mode),
    ("circular crop", r_circular_crop),
    ("rotate + flip", r_rotate_flip),
    ("canvas border", r_canvas_border),
    ("animated gif", r_animated_gif),
    ("psd round trip", r_psd_roundtrip),
    ("read info", r_read_info),
]:
    check(label, fn)

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    for label, exc in failed:
        print("  FAILED: %s -> %s" % (label, exc))
    sys.exit(1)
