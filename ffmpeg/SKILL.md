---
name: ffmpeg
description: Use this skill any time the user wants to do anything with video or audio files via ffmpeg / ffprobe. Covers probing/inspection, format conversion, lossless cut+concat, re-encoding (libx264/x265/svtav1, plus hardware-accelerated nvenc/qsv/amf), filtering (scale/crop/pad/rotate/fps), filter_complex pipelines (trim+setpts+concat for cut-list edits), GIF↔video with palette generation, subtitle burn-in, watermarks/overlays, audio extraction and EBU R128 loudness normalization, scene/freeze detection, xfade transitions, and HLS/DASH packaging. Trigger on .mp4/.mov/.mkv/.webm/.gif/.mp3/.wav/.flac/.opus filenames, or any verb like "transcode", "trim", "convert", "concatenate", "burn subtitles", "extract audio", "normalize loudness", "make a gif", "speed up video".
---

# FFmpeg Skill

Requires `ffmpeg` and `ffprobe` on PATH. Commands are written for a POSIX shell (bash/zsh, or Git Bash on Windows) — use Unix path syntax and `2>&1 | grep ...` style pipelines. On Windows, prefer Git Bash over PowerShell for these, since the quoting rules for filter graphs differ; where a path must be given to a filter argument, forward slashes are required regardless of platform.

## When to use which file

| You need to... | Read |
|---|---|
| Pick the right approach for a task | This file (decision tree below) |
| Look up a specific filter/codec/flag | `reference.md` |
| Copy-paste a working command for a common task | `recipes.md` |
| Debug a confusing failure (silent drawtext, A/V drift, even-dim errors, etc.) | `troubleshooting.md` |

If the working directory's `CLAUDE.md` defines a project-specific media workflow (house encode settings, a fixed clip length, a delivery spec), **it is authoritative** — follow it rather than this skill's defaults when the two disagree.

## Decision tree

Before running ffmpeg, decide which path you're on:

```
Question 1: Is the user just inspecting a file?
  → ffprobe (Section: "Probing")

Question 2: Are they cutting/joining without changing codec/resolution?
  → -c copy + concat demuxer (Section: "Lossless ops")
  → ~10× faster, no quality loss, but cut points snap to keyframes

Question 3: Do they need an exact frame cut, speed change, multi-source mix, or filter?
  → Re-encode with -filter_complex (Section: "Re-encode pipeline")

Question 4: Are they batch processing or quality-targeting?
  → Pick a codec/CRF (reference.md "Codec selection")
  → Consider hardware encoder if speed > quality
```

## Always do this first: probe the input

Never guess input properties. Run ffprobe and read the duration, dimensions, frame rate, and codec before writing a command.

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,codec_name,duration \
  -show_entries format=duration,size,bit_rate \
  -of default=nw=1 in.mp4
```

For a structured/JSON view (e.g. when extracting fields programmatically):
```bash
ffprobe -v error -print_format json -show_format -show_streams in.mp4
```

## The two big mental models

### Stream copy vs. re-encode

- **Stream copy (`-c copy`)** = remux only. Fast, lossless, but cuts snap to **keyframes** (typically every 2–10s). Use when you're not changing pixels.
- **Re-encode (`-c:v libx264 -crf N`)** = decode → filter → encode. Slow, slight quality loss, but **frame-accurate** and can apply filters.

You almost never want partial re-encoding — pick one mode per output.

### Input seek (`-ss` before `-i`) vs. output seek (`-ss` after `-i`)

- `-ss 30 -i in.mp4`: container-index seek. **Fast.** Lands on nearest keyframe ≤ requested time. Usually invisible — use this by default.
- `-i in.mp4 -ss 30`: decode-and-discard. **Slow** (decodes everything before the seek point) but **frame-accurate**.

When stream copying, input seek is fine; the cut still lands on a keyframe either way. When re-encoding and you need an exact frame, output seek (or input seek + `-noaccurate_seek` removed in modern builds — input is accurate enough since 4.x).

## Probing recipes

```bash
# Basic info
ffprobe -hide_banner in.mp4

# One-line summary, machine-parseable
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,duration \
  -of csv=p=0 in.mp4

# All keyframe timestamps (useful before stream-copy cuts)
ffprobe -v error -select_streams v:0 -skip_frame nokey \
  -show_entries frame=pts_time -of csv=p=0 in.mp4

# Detect scene changes (returns a list of pts_time values)
ffmpeg -hide_banner -i in.mp4 \
  -vf "select='gt(scene,0.05)',showinfo" -f null - 2>&1 \
  | grep pts_time

# Detect frozen sections (≥1.5s static, very tight pixel tolerance)
ffmpeg -hide_banner -i in.mp4 \
  -vf "freezedetect=n=0.003:d=1.5" -map 0:v:0 -f null - 2>&1 \
  | grep -E "freeze_(start|end|duration)"
```

## Lossless ops (no re-encode)

### Trim
```bash
# Cut from 30s for 10s, snapping to nearest keyframe
ffmpeg -ss 30 -i in.mp4 -t 10 -c copy out.mp4
```

### Concat (same codec, same resolution, same fps required)
```bash
# Build a list file
printf "file 'a.mp4'\nfile 'b.mp4'\nfile 'c.mp4'\n" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy joined.mp4
```

If concat demuxer fails with timing/sync errors, the inputs aren't actually compatible — you must re-encode them to a common spec first (see recipes.md "Normalize before concat").

### Remux container only
```bash
# .mkv → .mp4, no re-encode
ffmpeg -i in.mkv -c copy -movflags +faststart out.mp4
```

`-movflags +faststart` moves the moov atom to the front so the file plays immediately when streamed over HTTP. **Always include it for .mp4 outputs intended for the web.**

## Re-encode pipeline (the workhorse)

### Single-input, simple filter
```bash
ffmpeg -i in.mp4 \
  -vf "scale=1920:-2,fps=60" \
  -c:v libx264 -crf 20 -preset medium \
  -c:a copy \
  -movflags +faststart -pix_fmt yuv420p \
  out.mp4
```

### Multi-clip cut-list with speed changes (filter_complex)
```bash
ffmpeg -y -i in.mp4 -filter_complex "
  [0:v]trim=A1:B1,setpts=PTS-STARTPTS,scale=1920:-2,fps=60[v1];
  [0:v]trim=A2:B2,setpts=(PTS-STARTPTS)/N2,scale=1920:-2,fps=60[v2];
  [v1][v2]concat=n=2:v=1:a=0[out]
" -map "[out]" -movflags +faststart -pix_fmt yuv420p \
  -c:v libx264 -crf 20 -preset medium out.mp4
```

Critical rules for filter_complex concat:
- `setpts=(PTS-STARTPTS)/N` divides timestamps by `N` → playback is `N×` faster. Bare `setpts=PTS-STARTPTS` is 1× speed (still required to reset the timeline after `trim`).
- **Every branch must end at the same width, height, pixel format, and frame rate** before `concat`. That's why `scale=...` and `fps=...` are repeated in each branch.
- `concat=n=K:v=1:a=0` — `K` must equal the number of `[vN]` branches. Use `a=1` and add `[a1][a2]...` audio branches if you have audio.
- For audio speed changes, pair `setpts=PTS/N` with `atempo=N` (chained — `atempo` clamps to 0.5–2.0 per instance, so 4× is `atempo=2.0,atempo=2.0`).

## Codec selection (quick guide)

| Goal | Encoder | Quality knob | Notes |
|---|---|---|---|
| Compatible web/social | `libx264` | `-crf 18–23` (lower = better) | `-preset medium` is the sweet spot. Add `-tune film` for live action. |
| Smaller file, same quality | `libx265` | `-crf 22–28` | ~50% smaller than x264 at the same visual quality, but slower and less compatible. |
| Smallest file (modern) | `libsvtav1` | `-crf 25–35`, `-preset 6` | AV1, 2026-era. Use `-pix_fmt yuv420p10le`. |
| Fast (real-time / batch) | `h264_nvenc` / `hevc_nvenc` | `-cq 19–23 -preset p5` | NVIDIA GPU. ~5–10× faster, lower compression efficiency. |
| Fast (Intel iGPU) | `h264_qsv` / `hevc_qsv` | `-global_quality 20–25` | Intel iGPU. Low-power, decent quality. |
| Fast (AMD GPU) | `h264_amf` / `hevc_amf` | `-quality quality -rc cqp -qp_i 20 -qp_p 22` | AMD. Quality lags behind nvenc/qsv but works. |

For full encoder details (parameters, presets, profiles), see `reference.md`.

## Common pitfalls (Windows + this build specifically)

1. **`drawtext` silently fails on this Windows ffmpeg build.** Fontconfig errors out and produces output without text. Don't use `drawtext` for timestamp overlays — use `subtitles=` with an SRT/ASS file instead, or tile-position math.
2. **`yuv420p` requires even dimensions.** When scaling from sources with odd dimensions (gifs especially), use `scale=trunc(iw/2)*2:trunc(ih/2)*2` or `scale=W:-2` (the `-2` rounds height to even).
3. **Concat demuxer is strict.** "Same codec" really means same codec parameters. If you mix recordings with different fps/resolution/profile, the demuxer will silently produce a broken file. Probe both first.
4. **`-c copy` cuts are not frame-accurate.** They snap to the nearest preceding keyframe. If you need an exact cut, re-encode.
5. **Forgot `+faststart`.** The output plays fine locally but stutters when streamed. Always set `-movflags +faststart` for .mp4 web output.

See `troubleshooting.md` for full failure mode catalog.

## Working directory etiquette

- For non-trivial multi-step jobs (probe → analyze → render), create a subfolder per project (`<name>/`) with an `analysis/` directory for contact sheets, marker files, etc. Don't litter the cwd.
- Always render to a new file. Never overwrite the source.
- When the output looks wrong, re-probe it (`ffprobe out.mp4`) before re-rendering — the issue is often dimensions or duration, visible in the probe output.

## Quick links

- Cookbook of working commands → `recipes.md`
- Filter and codec reference → `reference.md`
- "Why is my output broken?" → `troubleshooting.md`
- Project-specific encode/delivery conventions (these override the above) → `<cwd>/CLAUDE.md`
