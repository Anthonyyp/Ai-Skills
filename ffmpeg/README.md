# FFmpeg

Video and audio work through `ffmpeg` / `ffprobe`: probing, format conversion,
lossless cut + concat, re-encoding (x264/x265/SVT-AV1, plus NVENC/QSV/AMF),
filter_complex pipelines, GIF↔video with palette generation, subtitle burn-in,
overlays, loudness normalization, scene detection, xfade, and HLS/DASH.

Install: see the [links in the repo README](../README.md#install).

## Requirements

`ffmpeg` and `ffprobe` on PATH. Check with `ffmpeg -version`.

Commands assume a POSIX shell (bash/zsh, or Git Bash on Windows). Which codecs
and hardware encoders you actually have depends on your build — verify with
`ffmpeg -encoders | grep -E "nvenc|qsv|amf|svt"` before relying on one.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | Decision tree — which approach for which task |
| `recipes.md` | Copy-pasteable commands for common jobs |
| `reference.md` | Filter, codec and flag lookup |
| `troubleshooting.md` | Silent drawtext, A/V drift, odd-dimension errors, subtitle path escaping |

## Note

Written and used primarily on Windows with Git Bash. The commands are portable,
but a few troubleshooting entries describe quirks most often seen in Windows
ffmpeg builds (notably `drawtext` silently producing no text when fontconfig
can't find fonts).
