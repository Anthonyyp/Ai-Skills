# Formats: what GIMP can read, write, and preserve

Format support is a property of the **installed build**, not of GIMP in
general. The lists below came from GIMP 3.2.4 on Windows. Always confirm with:

```bash
python scripts/gimp_cli.py doctor          # lists every export procedure
python scripts/gimp_cli.py args file-webp-export   # that format's options
```

## Naming

Export procedures are `file-<name>-export`, loaders are `file-<name>-load`.
The name is usually the extension, with these exceptions:

| Extension | Procedure |
|---|---|
| `.jpg` / `.jpeg` | `file-jpeg-export` |
| `.tif` / `.tiff` | `file-tiff-export` |
| `.eps` | `file-eps-export` |
| `.ps` | `file-ps-export` |
| `.ora` | `file-openraster-export` |
| `.c` | `file-csource-export` |
| `.html` | `file-html-table-export` |

`gimp_helpers.export()` handles this mapping; `EXPORT_PROC` in that file is the
table.

**In GIMP 3 these are `-export`, not `-save`.** `file-png-save` was the 2.10
name and no longer exists. Only `.xcf` uses save (`Gimp.file_save`), because
XCF is the native format rather than an export target.

## Which formats keep layers

This is the question that actually matters when choosing an output format.

| Format | Layers | Notes |
|---|---|---|
| **XCF** | Yes, fully | GIMP native. Text layers stay editable, masks/paths/guides survive. The only lossless round trip. |
| **PSD / PSB** | Yes | Good interchange with Photoshop/Affinity. Some GIMP layer modes have no PSD equivalent and get approximated. PSB is the >2GB/30000px variant. |
| **OpenRaster (.ora)** | Yes | Open, zip-based, layer-preserving. Well supported by Krita/MyPaint, less so elsewhere. |
| **PDF** | One page per layer, with `layers-as-pages=True` | Not "layers" in the PDF sense, but it round-trips: GIMP reloads a multi-page PDF as one layer per page. |
| **TIFF** | Multi-page | Layers can be written as pages; readers vary in what they do with them. |
| **GIF / MNG / WebP / APNG** | Frames, not layers | Layers become animation frames. Palette limits apply to GIF. |
| **ICO / CUR / ICNS** | Multi-size | Layers become the different icon sizes. |
| **PNG / JPEG / WebP (still) / BMP / TGA** | No | Flattened on export. |
| **EPS / PS** | **No, and cannot** | PostScript has no layer model at all — it's an ordered list of drawing operators. Exporting always flattens; nothing can be recovered. Use PDF if you need pages. |

`gimp_helpers.export()` auto-flattens when the target can't hold alpha or when
the image has multiple layers. Pass `flatten=False` to force otherwise.

## Options worth knowing

Check exact parameters with `gimp_cli.py args <procedure>` — the defaults below
are from 3.2.4.

**PNG** (`file-png-export`) — `compression` 0-9 (default 9), `interlaced`,
`bkgd`, `save-transparent`, `optimize-palette`, plus the metadata toggles
(`include-exif`, `include-xmp`, `include-color-profile`, `include-thumbnail`).

### The `quality` trap

**Quality scales are inconsistent between formats**, and the wrong one is
silently accepted:

| Procedure | `quality` range | Default |
|---|---|---|
| `file-jpeg-export` | **0.0 – 1.0** | 0.9 |
| `file-webp-export` | **0.0 – 100.0** | 90.0 |

Passing `quality=0.85` to WebP is perfectly legal and gives you **0.85%**
quality — a ruined file that exports without complaint. Verify with
`gimp_cli.py args file-<fmt>-export` before hardcoding a number.

`gimp_helpers.export()` normalises this: `quality` is always a 0–1 fraction and
gets rescaled to whatever the procedure actually wants.

**JPEG** (`file-jpeg-export`) — `quality` 0.0-1.0 (default 0.9, **not** 0-100),
`smoothing`, `optimize` (True), `progressive` (True), `sub-sampling`
(`sub-sampling-1x1` default; use 1x1 for text/screenshots, 2x2 for photos),
`baseline`, `cmyk`.

**WebP** (`file-webp-export`) — `quality`, `lossless`, `animation` and friends.
Supports alpha, unlike JPEG.

**TIFF** (`file-tiff-export`) — `compression` matters a lot for size.

**PDF** (`file-pdf-export`) — `layers-as-pages`, `root-layers-only`,
`ignore-hidden`, `apply-masks`, `reverse-order`, `vectorize`,
`convert-text-layers`, `fill-background-color`. Leaving
`convert-text-layers=False` keeps text as selectable text rather than pixels.

**EPS** (`file-eps-export`) — `width`/`height` in `unit`, where **`unit` accepts
only `"inch"` or `"millimeter"`**; `"in"`, `"mm"`, `"pt"` are silently rejected
with a GLib warning and the default is used instead. Also `level` (PostScript
level 2), `eps-flag`, `rotation`, `show-preview`/`preview`.

**PSD** (`file-psd-export`) — `cmyk`, `duotone`, clipping-path options, metadata
toggles.

## Reading

91 loaders, including PSD, PDF (via poppler), SVG, EPS/PS (via Ghostscript),
HEIF, JPEG XL, camera RAW, and OpenRaster.

Notes on the PostScript family:

- **EPS/PS import needs Ghostscript, but the Windows GIMP 3 installer bundles
  it** (`libgs-10.dll`, ~22MB, in `GIMP 3\bin`), so EPS loads out of the box
  there. On Linux/macOS Ghostscript is more often a separate package, so don't
  assume. The procedure `file-eps-load` exists either way — its presence proves
  nothing. The only real test is loading a file and seeing whether it throws.
- EPS is rasterised on import at GIMP's chosen resolution, so dimensions come
  back larger than the nominal point size (a 768×960pt EPS loaded as
  3199×3999px here). Import is a **render**, not a recovery — vector structure
  and any notion of separate elements are gone.
- **PDF import uses poppler and never needs Ghostscript**, which makes PDF the
  more portable page-based round trip.

Loading a multi-page PDF non-interactively yields one layer per page, which is
how `layers-as-pages` export round-trips.
