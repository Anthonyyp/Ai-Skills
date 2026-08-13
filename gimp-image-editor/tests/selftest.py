"""Self-test for the GIMP skill. Run it with:

    python scripts/gimp_cli.py run tests/selftest.py -- <output-folder>

Exercises every helper against the real GIMP on this machine, so a version
difference shows up here rather than halfway through someone's task.
"""

import os
import sys

from gimp_helpers import *  # noqa: F401,F403

OUT = ARGS[0] if ARGS else os.path.join(os.path.dirname(__file__), "_selftest_out")  # noqa: F821
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


print("GIMP %s" % Gimp.version())  # noqa: F821
print("output -> %s\n" % OUT)

state = {}


# --- construction ---------------------------------------------------------

def t_new_image():
    image, layer = new_image(640, 400, "#123456")
    state["image"] = image
    assert image.get_width() == 640
    assert len(image.get_layers()) == 1


def t_new_layer():
    layer = new_layer(state["image"], "overlay")
    assert layer.get_name() == "overlay"
    state["overlay"] = layer


def t_gegl_fill():
    # paint something so later ops have pixels to chew on
    Gimp.context_set_foreground(color("#e8a33d"))  # noqa: F821
    state["image"].select_ellipse(Gimp.ChannelOps.REPLACE, 80, 60, 300, 220)  # noqa: F821
    state["overlay"].edit_fill(Gimp.FillType.FOREGROUND)  # noqa: F821
    Gimp.Selection.none(state["image"])  # noqa: F821


def t_text_layer():
    layer = text_layer(state["image"], "Skill test", font="Arial Bold",
                       size=54, fill="#f5ebdc", x=40, y=300, name="caption")
    assert layer.get_width() > 0
    state["text"] = layer


def t_apply_gegl_blur():
    apply_gegl(state["overlay"], "gegl:gaussian-blur", std_dev_x=4.0, std_dev_y=4.0)


def t_apply_gegl_shadow():
    apply_gegl(state["overlay"], "gegl:dropshadow", x=8.0, y=8.0,
               radius=6.0, opacity=0.6, color="#000000")


def t_apply_gimp_namespace_op():
    # gimp:* ops are invisible to Gegl.list_operations() but ARE valid
    # drawable filters. Validating against the GEGL list alone rejects them.
    apply_gegl(state["overlay"], "gimp:brightness-contrast", brightness=0.1)


def t_export_quality_scales_per_format():
    # JPEG wants 0.0-1.0, WebP wants 0.0-100.0. A single fraction must mean
    # the same visual quality in both, or webp silently exports at ~1%.
    image, layer = new_image(240, 240, "#3388cc")
    # Needs real detail: a flat colour compresses to the same size at every
    # quality setting, so the test would pass vacuously.
    apply_gegl(layer, "gegl:noise-rgb", red=0.4, green=0.4, blue=0.4,
               independent=True)
    hi = os.path.join(OUT, "q_high.webp")
    lo = os.path.join(OUT, "q_low.webp")
    export(image, hi, quality=0.95)
    export(image, lo, quality=0.05)
    image.delete()
    assert os.path.getsize(hi) > os.path.getsize(lo), (
        "quality=0.95 (%d bytes) should exceed quality=0.05 (%d bytes)"
        % (os.path.getsize(hi), os.path.getsize(lo)))


def t_apply_gegl_bad_op():
    try:
        apply_gegl(state["overlay"], "gegl:not-a-real-op")
    except RuntimeError as exc:
        assert "no such filter operation" in str(exc), exc
        return
    raise AssertionError("expected a RuntimeError for a bogus op")


def t_apply_gegl_bad_prop():
    try:
        apply_gegl(state["overlay"], "gegl:gaussian-blur", nonsense=1.0)
    except RuntimeError as exc:
        assert "has no property" in str(exc)
        return
    raise AssertionError("expected a RuntimeError for a bogus property")


# --- output ---------------------------------------------------------------

def t_describe():
    text = describe(state["image"])
    assert "3 layer(s)" in text, text
    print("\n".join("        " + l for l in text.splitlines()))


def t_save_xcf():
    path = save_xcf(state["image"], os.path.join(OUT, "test.xcf"))
    assert os.path.getsize(path) > 0


def t_export_png():
    path = export(state["image"], os.path.join(OUT, "test.png"), compression=9)
    assert os.path.getsize(path) > 0


def t_export_jpeg():
    # multi-layer + no-alpha format: must be flattened automatically
    path = export(state["image"], os.path.join(OUT, "test.jpg"), quality=0.85)
    assert os.path.getsize(path) > 0


def t_export_webp():
    path = export(state["image"], os.path.join(OUT, "test.webp"))
    assert os.path.getsize(path) > 0


def t_export_unknown_ext():
    try:
        export(state["image"], os.path.join(OUT, "test.zzz"))
    except RuntimeError as exc:
        assert "no exporter" in str(exc)
        return
    raise AssertionError("expected a RuntimeError for an unknown extension")


def t_export_each_layer():
    paths = export_each_layer(state["image"], os.path.join(OUT, "layers"))
    assert len(paths) == 3, paths
    for p in paths:
        assert os.path.getsize(p) > 0


def t_pdf_layers_as_pages():
    pdb_run("file-pdf-export", run_mode=Gimp.RunMode.NONINTERACTIVE,  # noqa: F821
            image=state["image"], file=gfile(os.path.join(OUT, "test.pdf")),
            options=None, vectorize=False, ignore_hidden=False,
            apply_masks=True, layers_as_pages=True, reverse_order=False,
            root_layers_only=True, convert_text_layers=False,
            fill_background_color=False)
    assert os.path.getsize(os.path.join(OUT, "test.pdf")) > 0


def t_reload_pdf_pages():
    image = load_image(os.path.join(OUT, "test.pdf"))
    assert len(image.get_layers()) == 3, len(image.get_layers())
    image.delete()


# --- geometry -------------------------------------------------------------

def t_load_and_fit():
    image = load_image(os.path.join(OUT, "test.png"))
    fit_within(image, 200, 200)
    assert image.get_width() <= 200 and image.get_height() <= 200
    export(image, os.path.join(OUT, "thumb.png"))
    image.delete()


def t_scale_to_width():
    image = load_image(os.path.join(OUT, "test.png"))
    scale_to_width(image, 320)
    assert image.get_width() == 320
    image.delete()


def t_autocrop():
    image, layer = new_image(400, 400, None)
    Gimp.context_set_foreground(color("#ff0000"))  # noqa: F821
    image.select_rectangle(Gimp.ChannelOps.REPLACE, 100, 120, 80, 60)  # noqa: F821
    layer.edit_fill(Gimp.FillType.FOREGROUND)  # noqa: F821
    Gimp.Selection.none(image)  # noqa: F821
    autocrop(image)
    assert (image.get_width(), image.get_height()) == (80, 60), \
        (image.get_width(), image.get_height())
    image.delete()


# --- error surfaces -------------------------------------------------------

def t_pdb_bad_proc():
    try:
        pdb_run("gimp-does-not-exist")
    except RuntimeError as exc:
        assert "no such PDB procedure" in str(exc)
        return
    raise AssertionError("expected a RuntimeError")


def t_pdb_bad_param():
    try:
        pdb_run("gimp-image-flatten", nope=1)
    except RuntimeError as exc:
        assert "has no parameter" in str(exc)
        return
    raise AssertionError("expected a RuntimeError")


def t_bad_font():
    try:
        text_layer(state["image"], "x", font="No Such Font Bold")
    except RuntimeError as exc:
        assert "font not found" in str(exc)
        return
    raise AssertionError("expected a RuntimeError")


for label, fn in [
    ("new_image", t_new_image),
    ("new_layer", t_new_layer),
    ("fill via selection", t_gegl_fill),
    ("text_layer", t_text_layer),
    ("apply_gegl gaussian-blur", t_apply_gegl_blur),
    ("apply_gegl dropshadow", t_apply_gegl_shadow),
    ("apply_gegl accepts gimp: namespace op", t_apply_gimp_namespace_op),
    ("export quality scales per format", t_export_quality_scales_per_format),
    ("apply_gegl rejects bad op", t_apply_gegl_bad_op),
    ("apply_gegl rejects bad prop", t_apply_gegl_bad_prop),
    ("describe", t_describe),
    ("save_xcf", t_save_xcf),
    ("export png", t_export_png),
    ("export jpeg (auto-flatten)", t_export_jpeg),
    ("export webp", t_export_webp),
    ("export rejects unknown ext", t_export_unknown_ext),
    ("export_each_layer", t_export_each_layer),
    ("pdf layers-as-pages", t_pdf_layers_as_pages),
    ("reload pdf pages as layers", t_reload_pdf_pages),
    ("load + fit_within", t_load_and_fit),
    ("scale_to_width", t_scale_to_width),
    ("autocrop", t_autocrop),
    ("pdb_run rejects bad proc", t_pdb_bad_proc),
    ("pdb_run rejects bad param", t_pdb_bad_param),
    ("text_layer rejects bad font", t_bad_font),
]:
    check(label, fn)

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    for label, exc in failed:
        print("  FAILED: %s -> %s" % (label, exc))
    sys.exit(1)
