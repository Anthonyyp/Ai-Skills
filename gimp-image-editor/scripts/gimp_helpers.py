"""gimp_helpers.py - small utility layer over the GIMP 3 GI API.

Runs INSIDE GIMP. Scripts launched via `gimp_cli.py run` can just:

    from gimp_helpers import *

gimp_cli.py puts this file's directory on sys.path for you.

Everything here is a thin, obvious wrapper. The point is not to hide the GIMP
API - it is to remove the boilerplate that is easy to get wrong (PDB status
checking, export-vs-save, insert-before-scale, GeglColor coercion).
"""

import os

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gimp, Gegl, Gio  # noqa: E402

__all__ = [
    "pdb_run", "color", "gfile", "log",
    "load_image", "load_layer", "new_image", "new_layer",
    "save_xcf", "export", "export_each_layer",
    "place", "text_layer", "apply_gegl",
    "fit_within", "scale_to_width", "autocrop", "flattened",
    "describe", "EXPORT_PROC",
]


# --------------------------------------------------------------------------
# basics
# --------------------------------------------------------------------------

def log(msg):
    """Print progress. Goes to stdout, which gimp_cli.py passes through."""
    print("[gimp] %s" % msg, flush=True)


def gfile(path):
    return Gio.File.new_for_path(os.path.abspath(path))


def color(spec):
    """Gegl.Color from '#rrggbb', 'red', or an (r,g,b[,a]) 0-1 tuple.

    CAUTION: strings and tuples are not the same colour space. Gegl parses
    '#808080' as sRGB and stores it linearised (get_rgba() -> 0.216), while
    set_rgba() writes linear-light values directly (0.5 stays 0.5). Prefer hex
    strings unless you specifically want linear values.
    """
    if isinstance(spec, Gegl.Color):
        return spec
    if isinstance(spec, (tuple, list)):
        c = Gegl.Color.new("black")
        rgba = list(spec) + [1.0] * (4 - len(spec))
        c.set_rgba(*rgba)
        return c
    return Gegl.Color.new(spec)


def pdb_run(name, **kwargs):
    """Call a PDB procedure by name with keyword args. Raises on failure.

    Underscores in kwargs become hyphens, so you can write image_type=...
    for the 'image-type' property. Discover parameters with:
        python gimp_cli.py args <name>
    """
    proc = Gimp.get_pdb().lookup_procedure(name)
    if proc is None:
        raise RuntimeError(
            "no such PDB procedure: %s\n"
            "  (list them with: python gimp_cli.py pdb <pattern>)" % name)
    cfg = proc.create_config()
    for key, value in kwargs.items():
        prop = key.replace("_", "-")
        spec = cfg.find_property(prop)
        if spec is None:
            raise RuntimeError(
                "%s has no parameter %r\n"
                "  (see: python gimp_cli.py args %s)" % (name, prop, name))
        # Let callers pass '#ff0000' where a GeglColor is wanted.
        if spec.value_type.name == "GeglColor" and not isinstance(value, Gegl.Color):
            value = color(value)
        cfg.set_property(prop, value)
    result = proc.run(cfg)
    status = result.index(0)
    if status != Gimp.PDBStatusType.SUCCESS:
        detail = result.index(1) if result.length() > 1 else ""
        raise RuntimeError("%s failed: %s %s" % (name, status.value_nick, detail))
    # index 0 is status; hand back the rest, unwrapped when it's a single value
    values = [result.index(i) for i in range(1, result.length())]
    if not values:
        return None
    return values[0] if len(values) == 1 else values


# --------------------------------------------------------------------------
# images and layers
# --------------------------------------------------------------------------

def load_image(path):
    """Open any format GIMP can import. Returns a Gimp.Image."""
    return Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, gfile(path))


def load_layer(image, path, name=None):
    """Load a file as a new layer in `image`. NOT yet inserted."""
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, gfile(path))
    if name:
        layer.set_name(name)
    return layer


def new_image(width, height, fill=None):
    """New RGB image. `fill` is a colour spec, or None for transparent."""
    image = Gimp.Image.new(width, height, Gimp.ImageBaseType.RGB)
    layer = new_layer(image, "background", width, height)
    if fill is not None:
        Gimp.context_set_background(color(fill))
        layer.edit_fill(Gimp.FillType.BACKGROUND)
    return image, layer


def new_layer(image, name, width=None, height=None, position=0, opacity=100.0):
    layer = Gimp.Layer.new(
        image, name,
        width or image.get_width(), height or image.get_height(),
        Gimp.ImageType.RGBA_IMAGE, opacity, Gimp.LayerMode.NORMAL)
    image.insert_layer(layer, None, position)
    return layer


def place(image, path, name=None, width=None, height=None, x=0, y=0, position=0):
    """Load an image file as a positioned, optionally scaled layer.

    Scaling happens AFTER insertion - Gimp.Layer.scale() fails on an item that
    does not yet belong to an image, and the failure is easy to miss because
    it only shows up as a GIMP-Error on stderr.
    """
    layer = load_layer(image, path, name)
    image.insert_layer(layer, None, position)
    if width or height:
        ratio = layer.get_height() / layer.get_width()
        if width and not height:
            height = int(round(width * ratio))
        elif height and not width:
            width = int(round(height / ratio))
        layer.scale(int(width), int(height), False)
    layer.set_offsets(int(x), int(y))
    return layer


def text_layer(image, text, font="Sans-serif Bold", size=48, fill="#000000",
               x=0, y=0, position=0, name=None):
    """Render text as a real (still editable) text layer.

    The default is deliberately the generic family, which exists on every
    platform. 'Arial Bold' does not exist on a stock Linux box.
    """
    font_obj = Gimp.Font.get_by_name(font)
    if font_obj is None:
        raise RuntimeError(
            "font not found: %r\n"
            "  GIMP 3 wants 'Family Style', e.g. 'Sans-serif Bold'. A bare "
            "family ('Arial') or a wrong alias ('Sans') resolves to nothing;\n"
            "  the portable generics are 'Sans-serif', 'Serif', 'Monospace' "
            "(+ ' Bold' / ' Italic' / ' Bold Italic').\n"
            "  List what this machine has with:\n"
            "    python gimp_cli.py eval "
            "\"print([f.get_name() for f in Gimp.fonts_get_list('')])\""
            % font)
    layer = Gimp.TextLayer.new(image, text, font_obj, size, Gimp.Unit.pixel())
    image.insert_layer(layer, None, position)
    layer.set_color(color(fill))
    if name:
        layer.set_name(name)
    layer.set_offsets(int(x), int(y))
    return layer


def filter_operations():
    """Every operation usable as a drawable filter.

    NOT the same set as Gegl.list_operations(). GIMP registers ~51 `gimp:*`
    ops (gimp:levels, gimp:brightness-contrast, the legacy blend modes...) in
    its core process, where a plug-in's GEGL cannot see them. Validating
    against the GEGL list alone wrongly rejects all of them.
    """
    ops = set(Gegl.list_operations())
    try:
        ops |= set(Gimp.DrawableFilter.operation_get_available())
    except Exception:
        pass
    return ops


def apply_gegl(drawable, operation, **props):
    """Apply an operation destructively to a drawable.

    Takes `gegl:*` ops and also GIMP's own `gimp:*` ops. The `gimp:` variants
    match the GIMP UI's semantics and honour the current selection by default;
    the `gegl:` ones often differ (e.g. gegl:brightness-contrast is
    multiplicative and has no gamma, gimp:brightness-contrast is additive).

    Discover operations and their properties with:
        python gimp_cli.py gegl <pattern>
        python gimp_cli.py geglargs <operation>
    """
    if operation not in filter_operations():
        raise RuntimeError(
            "no such filter operation: %s\n"
            "  (list them with: python gimp_cli.py gegl <pattern>)" % operation)
    filt = Gimp.DrawableFilter.new(drawable, operation, "")
    cfg = filt.get_config()
    for key, value in props.items():
        prop = key.replace("_", "-")
        spec = cfg.find_property(prop)
        if spec is None:
            raise RuntimeError(
                "%s has no property %r\n"
                "  (see: python gimp_cli.py geglargs %s)" % (operation, prop, operation))
        if spec.value_type.name == "GeglColor" and not isinstance(value, Gegl.Color):
            value = color(value)
        cfg.set_property(prop, value)
    filt.update()
    drawable.merge_filter(filt)
    return drawable


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def scale_to_width(image, width):
    height = int(round(image.get_height() * width / image.get_width()))
    image.scale(width, height)
    return image


def fit_within(image, max_width, max_height, allow_upscale=False):
    """Scale so the whole image fits in the box, preserving aspect ratio."""
    w, h = image.get_width(), image.get_height()
    factor = min(max_width / w, max_height / h)
    if factor >= 1.0 and not allow_upscale:
        return image
    image.scale(max(1, int(round(w * factor))), max(1, int(round(h * factor))))
    return image


def autocrop(image, drawable=None):
    """Trim uniform/transparent borders.

    GIMP 2.10's `plug-in-autocrop` is gone in 3.x; this is `gimp-image-autocrop`.
    `drawable` decides what counts as border - pass None to use the whole image.
    """
    pdb_run("gimp-image-autocrop", image=image, drawable=drawable)
    return image


class flattened(object):
    """Context manager giving a flattened *copy*, leaving the original alone.

        with flattened(image) as flat:
            export(flat, "out.jpg", quality=0.9)
    """

    def __init__(self, image):
        self.source = image
        self.copy = None

    def __enter__(self):
        self.copy = self.source.duplicate()
        self.copy.flatten()
        return self.copy

    def __exit__(self, *exc):
        if self.copy is not None:
            self.copy.delete()
        return False


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

# Extensions whose export procedure name doesn't match the extension.
EXPORT_PROC = {
    "jpg": "file-jpeg-export", "jpeg": "file-jpeg-export",
    "tif": "file-tiff-export", "tiff": "file-tiff-export",
    "ps": "file-ps-export", "eps": "file-eps-export",
    "htm": "file-html-table-export", "html": "file-html-table-export",
    "c": "file-csource-export",
}

# Formats with no alpha channel: exporting a layered/transparent image to
# these either fails or silently loses information, so flatten first.
NO_ALPHA = {"jpg", "jpeg", "bmp", "pnm", "ppm", "pgm", "eps", "ps", "pcx"}


def save_xcf(image, path):
    """Write GIMP's native layered format."""
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gfile(path), None)
    return path


def _normalize_quality(proc_name, options):
    """Make `quality` mean the same thing for every format.

    GIMP 3 is inconsistent: file-jpeg-export takes 0.0-1.0 while
    file-webp-export takes 0.0-100.0. Passing 0.85 to WebP is legal and gives
    you 0.85% quality - a silent disaster that looks like a working export.

    So: `quality` is always a 0-1 fraction here, rescaled to whatever the
    target procedure actually wants. Pass a value above 1.0 and it's taken as
    already being on a 0-100 scale.
    """
    if "quality" not in options:
        return options
    proc = Gimp.get_pdb().lookup_procedure(proc_name)
    spec = proc.create_config().find_property("quality") if proc else None
    if spec is None:
        return options
    value = float(options["quality"])
    wants_percent = getattr(spec, "maximum", 1.0) > 1.0
    if wants_percent and value <= 1.0:
        options["quality"] = value * 100.0
    elif not wants_percent and value > 1.0:
        options["quality"] = value / 100.0
    return options


def export(image, path, flatten=None, **options):
    """Export to any format, picking the right file-*-export procedure.

    Extra kwargs go to that procedure - `quality=0.85` for JPEG,
    `compression=9` for PNG. Discover them with:
        python gimp_cli.py args file-jpeg-export

    Set flatten=True/False to override the automatic decision.
    """
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if not ext:
        raise ValueError("export() needs a file extension: %r" % path)
    if ext == "xcf":
        return save_xcf(image, path)

    proc = EXPORT_PROC.get(ext, "file-%s-export" % ext)
    if Gimp.get_pdb().lookup_procedure(proc) is None:
        raise RuntimeError(
            "GIMP has no exporter for .%s (looked for %s)\n"
            "  (list them with: python gimp_cli.py doctor)" % (ext, proc))

    options = _normalize_quality(proc, options)

    if flatten is None:
        flatten = ext in NO_ALPHA or len(image.get_layers()) > 1
    if flatten:
        with flattened(image) as flat:
            pdb_run(proc, run_mode=Gimp.RunMode.NONINTERACTIVE, image=flat,
                    file=gfile(path), options=None, **options)
    else:
        pdb_run(proc, run_mode=Gimp.RunMode.NONINTERACTIVE, image=image,
                file=gfile(path), options=None, **options)
    return path


def export_each_layer(image, folder, ext="png", prefix=True):
    """Write every layer to its own file. Returns the paths written."""
    os.makedirs(folder, exist_ok=True)
    written = []
    layers = image.get_layers()
    for i, layer in enumerate(layers):
        single = Gimp.Image.new(image.get_width(), image.get_height(),
                                Gimp.ImageBaseType.RGB)
        copy = Gimp.Layer.new_from_drawable(layer, single)
        single.insert_layer(copy, None, 0)
        copy.set_offsets(*list(layer.get_offsets())[1:])
        stem = layer.get_name().replace("/", "-").replace("\\", "-")
        if prefix:
            stem = "%02d_%s" % (len(layers) - i, stem)
        path = os.path.join(folder, "%s.%s" % (stem, ext))
        export(single, path, flatten=False)
        single.delete()
        written.append(path)
    return written


def describe(image):
    """Human-readable summary - handy for inspecting an unknown file."""
    lines = ["%dx%d, %d layer(s), precision=%s"
             % (image.get_width(), image.get_height(),
                len(image.get_layers()), image.get_precision().value_nick)]
    for layer in image.get_layers():
        off = list(layer.get_offsets())[1:]
        lines.append(
            "  %-24s %4dx%-4d at (%d,%d) alpha=%s opacity=%.0f%% mode=%s"
            % (layer.get_name(), layer.get_width(), layer.get_height(),
               off[0], off[1], layer.has_alpha(), layer.get_opacity(),
               layer.get_mode().value_nick))
    return "\n".join(lines)
