# FFmpeg Reference

Reference material for filters, codecs, encoders, and command structure. Pair with `recipes.md` for ready-to-run commands.

## Command anatomy

```
ffmpeg [global_opts] {[input_opts] -i input}... {[output_opts] output}...
```

**Position matters.** Options before `-i` apply to the input (decoding, demuxing, seeking). Options after `-i` apply to the output (encoding, muxing). The same option (e.g. `-ss`, `-t`, `-r`) means different things in each position.

Common global options:
- `-y` — overwrite output without asking
- `-hide_banner` — suppress build/version banner
- `-loglevel error` (or `-v error`) — suppress everything except errors. Use `info` for default, `verbose` for debugging filters.
- `-stats` — show progress while encoding (default off when stderr is non-tty)

## ffprobe

```bash
# Default human-readable
ffprobe in.mp4

# JSON output (parseable)
ffprobe -v error -print_format json -show_format -show_streams in.mp4

# Just the first video stream
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,codec_name,pix_fmt,duration \
  -of default=nw=1 in.mp4

# Just the duration
ffprobe -v error -show_entries format=duration -of csv=p=0 in.mp4

# Frame-level info (heavy — only on small files)
ffprobe -v error -select_streams v:0 -show_frames in.mp4

# Keyframe timestamps
ffprobe -v error -select_streams v:0 -skip_frame nokey \
  -show_entries frame=pts_time -of csv=p=0 in.mp4
```

Output formats: `default`, `json`, `xml`, `csv`, `flat`, `ini`. `default=nw=1` means "no wrapper, no key prefix" — bare values one per line.

## Seeking

| Form | Speed | Accuracy | Use when |
|---|---|---|---|
| `-ss T -i input` | Fast (index seek) | Near-frame-accurate on modern builds | Default — works for almost everything |
| `-i input -ss T` | Slow (decode-and-discard) | Exact frame | You proved input seek lands wrong |
| `-ss T -i input -c copy` | Fast | Snaps to keyframe | Lossless cuts |

`-t DURATION` and `-to TIMESTAMP` are interchangeable for length specification. `-to` accepts an absolute end time, which is clearer when stitching multiple cuts.

## Filter syntax

### Single-stream filter (`-vf` / `-af`)
```
-vf "filter1=arg1=v1:arg2=v2,filter2=arg=v"
```
- `,` chains filters (output of one feeds the next).
- `:` separates filter arguments.
- `=` separates filter name from its first arg, and arg names from their values.

### Multi-stream filter (`-filter_complex` / `-fc`)
```
-filter_complex "
  [0:v]filter1[label1];
  [label1][1:v]filter2[label2];
  [label2]filter3[out]
"
-map "[out]"
```
- `;` separates filterchains.
- `[name]` are stream labels. Inputs come from `[N:type]` (file index, stream type) or earlier filter outputs.
- Use `-map "[out]"` to pick which labeled stream goes to the output.

### Stream specifiers
- `[0:v]` — first video stream of input 0
- `[0:a]` — first audio stream of input 0
- `[0:v:1]` — second video stream of input 0
- `[1:s:0]` — first subtitle stream of input 1

### Splitting one input into multiple branches
```
[0:v]split=3[a][b][c];
[0:a]asplit=3[a1][b1][c1]
```
You **must** split before using the same input in multiple branches — referencing `[0:v]` more than once is a filter graph error.

## Video filters

### Resize / aspect
```
scale=W:H[:flags=algorithm]
  W,H integers (or -1/-2 for "auto, preserve aspect, round to even")
  flags: lanczos (best quality default), bicubic, bilinear, neighbor
  
  scale=1920:-2          # 1920 wide, height auto, even
  scale=-2:1080          # height 1080, width auto, even
  scale=trunc(iw/2)*2:trunc(ih/2)*2   # round both to even (gif sources)
  scale='min(1920,iw)':-2              # cap at 1920 wide, never upscale
```

### Crop
```
crop=W:H:X:Y                  # WxH starting at (X,Y) from top-left
crop=in_w-200:in_h-200        # 100px off each side
crop=(in_w/2):in_h:0:0        # left half
```

### Pad (letter/pillarbox)
```
pad=W:H:X:Y[:color]
pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black   # center on 1920x1080 black
pad=ceil(iw/2)*2:ceil(ih/2)*2             # pad to nearest even dims
```

### Rotate
- **Right-angle rotation:** use `transpose` (lossless, fast)
  ```
  transpose=0   # 90° counter-clockwise + vertical flip
  transpose=1   # 90° clockwise
  transpose=2   # 90° counter-clockwise
  transpose=3   # 90° clockwise + vertical flip
  ```
  For 180°, chain: `transpose=2,transpose=2`.
- **Arbitrary angle:** `rotate=PI/4` (radians). Adds black corners; quality loss from interpolation. Avoid unless needed.
- **Apply rotate before scale** — scale sees post-rotate dimensions.

### Frame rate
```
fps=30                   # resample to 30 fps (drops/duplicates frames)
fps=60                   # resample to 60
minterpolate=fps=60:mi_mode=mci   # motion-interpolated (slow, sometimes ghosty)
setpts=PTS/2             # 2× speed (timestamps halved); pair with audio atempo
```

### Speed changes (cut-list pattern)
```
[0:v]trim=10:20,setpts=PTS-STARTPTS[v1]      # 1× speed, 10s clip
[0:v]trim=30:60,setpts=(PTS-STARTPTS)/4[v2]  # 4× speed, 7.5s clip
[0:a]atrim=10:20,asetpts=PTS-STARTPTS[a1]
[0:a]atrim=30:60,asetpts=PTS-STARTPTS,atempo=2.0,atempo=2.0[a2]
[v1][a1][v2][a2]concat=n=2:v=1:a=1[v][a]
```
- `atempo` per-instance range is **0.5–2.0**. For 4× speed, chain two `atempo=2.0`. For 0.25×, chain two `atempo=0.5`.
- Always pair video `setpts=PTS/N` with audio `atempo=N` chains, or audio drifts.

### Common visual filters
```
eq=contrast=1.1:brightness=0.05:saturation=1.2   # color grading
unsharp=5:5:1.0:5:5:0.0                          # subtle sharpen (luma only)
hflip                                            # horizontal mirror
vflip
negate
boxblur=5:1                                      # gaussian-ish blur
gblur=sigma=10                                   # true gaussian blur
```

### Overlay (compositing)
```
overlay=X:Y[:format=yuv420|yuv444|rgb|auto][:enable='expr']
  X,Y can use main_w/main_h/W/H (main video) and overlay_w/overlay_h/w/h (overlay)
  
  overlay=10:10                              # top-left, 10px in
  overlay=W-w-10:H-h-10                      # bottom-right, 10px from edges
  overlay=(W-w)/2:(H-h)/2                    # center
  overlay=10:10:enable='between(t,5,10)'     # only visible from t=5 to t=10
```

For 50% transparency on the overlay before compositing:
```
[1:v]format=rgba,colorchannelmixer=aa=0.5[wm];
[0:v][wm]overlay=W-w-10:H-h-10
```

### Subtitles
```
# Burn SRT subtitles into video (hard subs)
subtitles=subs.srt
subtitles=subs.srt:force_style='FontName=Arial,FontSize=24,PrimaryColour=&H00FFFFFF&,BackColour=&H80000000&,BorderStyle=4'

# Burn ASS subtitles (style is in the file)
ass=subs.ass

# Soft subs (no filter — mux as a separate stream)
ffmpeg -i in.mp4 -i subs.srt -c copy -c:s mov_text -metadata:s:s:0 language=eng out.mp4
```

ASS color is `&HBBGGRR&` (alpha-blue-green-red, hex). `BackColour=&H80000000&` is 50%-transparent black.

### Scene / freeze detection
```
# Scene-change frames (returns pts_time list to stderr via showinfo)
select='gt(scene,0.05)',showinfo
  threshold 0.0–1.0; 0.05 is a good default; raise for noisy sources

# Freeze detection (logs freeze_start/freeze_duration/freeze_end)
freezedetect=n=0.003:d=1.5
  n: noise tolerance (lower = stricter, 0.003 means truly identical pixels)
  d: minimum duration in seconds to flag as a freeze

# scdet: alternative scene detection that can pass through scene-change frames
scdet=t=10:s=1
  t: threshold 0–100, default 10
  s: 1 to mark scene-change frames in metadata
```

## Audio filters

### Tempo / pitch
```
atempo=1.5            # 1.5× speed, pitch preserved (range 0.5–2.0 per instance)
atempo=2.0,atempo=2.0 # 4× (chained)
asetrate=44100*2      # 2× speed AND 2× pitch (chipmunk effect)
rubberband=tempo=2    # high-quality time-stretch (libsamplerate)
```

### Volume / normalize
```
volume=0.5                  # 50% (linear)
volume=-6dB                 # 6dB attenuation
loudnorm=I=-16:TP=-1.5:LRA=11    # EBU R128 single-pass (live or quick fix)
```

For best results, use **two-pass loudnorm** — see recipes.md "Normalize loudness (EBU R128)".

### Mix / route
```
amix=inputs=2:duration=longest          # mix two audio streams
[0:a]pan=stereo|c0=c0|c1=c1[a]          # explicit channel routing
amerge=inputs=2                         # combine into multi-channel
```

## Codec parameters

### libx264 (H.264 / AVC)
| Flag | Meaning | Common values |
|---|---|---|
| `-crf` | Constant rate factor (quality) | 18–23 (18=visually lossless, 23=default, 28=acceptable) |
| `-preset` | Speed/compression trade | ultrafast, superfast, veryfast, faster, fast, **medium** (default), slow, slower, veryslow |
| `-tune` | Content tuning | film, animation, grain, stillimage, fastdecode, zerolatency |
| `-profile:v` | Compatibility | baseline, main, **high** (default), high10, high422, high444 |
| `-level` | Decoder level | 3.0, 3.1, 4.0, 4.1, 4.2, 5.0, 5.1, 5.2 |
| `-pix_fmt` | Pixel format | **yuv420p** (universal), yuv420p10le (10-bit, less compatible) |
| `-x264-params` | Pass-through to encoder | `keyint=120:min-keyint=120:scenecut=0` (fixed-GOP for HLS) |

Each +1 CRF step is ~10–12% smaller file. +6 CRF roughly halves file size. Slower presets give 5–15% better compression at the same CRF, at 2–10× the encode time.

### libx265 (H.265 / HEVC)
Same flag structure as x264 (`-crf`, `-preset`, `-tune`, `-pix_fmt`).
- Quality range: `-crf 22–28` (similar visual quality to x264 at -crf 18–23).
- Add `-tag:v hvc1` for QuickTime/Safari compatibility.
- Hand more options through `-x265-params "key=value:key=value"`.

### libsvtav1 (AV1)
| Flag | Meaning | Common values |
|---|---|---|
| `-crf` | Quality | 0–63, default 35; 25–35 is the practical range |
| `-preset` | Speed | 0–13, higher = faster; **6** is a good starting point |
| `-pix_fmt` | Format | **yuv420p10le** strongly recommended (free quality) |
| `-g` | Keyframe interval | `-g 240` for 10s @ 24fps |
| `-svtav1-params` | Pass-through | `tune=0:enable-overlays=1:scd=1` |

`tune=0` optimizes for subjective sharpness; `tune=1` (default) optimizes PSNR.

For batch quality-targeting, consider `ab-av1` (third-party tool) which auto-finds CRF for a target VMAF.

### Hardware encoders

#### NVIDIA NVENC
```bash
-c:v h264_nvenc -preset p5 -cq 21 -rc vbr -b:v 0
-c:v hevc_nvenc -preset p5 -cq 23 -rc vbr -b:v 0
-c:v av1_nvenc -preset p5 -cq 23   # RTX 4000+ only
```
- Presets `p1` (fastest) – `p7` (slowest/best). `p5` is a good default.
- `-cq` is roughly equivalent to CRF (lower = better).
- `-rc vbr -b:v 0` enables VBR mode driven by `-cq`.

#### Intel QSV
```bash
-c:v h264_qsv -preset medium -global_quality 22
-c:v hevc_qsv -preset medium -global_quality 24
```

#### AMD AMF
```bash
-c:v h264_amf -quality quality -rc cqp -qp_i 20 -qp_p 22
-c:v hevc_amf -quality quality -rc cqp -qp_i 22 -qp_p 24
```

Hardware encoders trade quality for speed. Rule of thumb: at the same bitrate, NVENC ≈ x264 -preset veryfast; QSV ≈ x264 -preset fast; AMF ≈ x264 -preset superfast. For archival/streaming where re-encoding cost matters once, prefer software (libx264/265). For real-time or large batches where speed matters, use hardware.

## Audio codecs

| Codec | Encoder | Quality knob | Use case |
|---|---|---|---|
| AAC | `aac` | `-b:a 128k–256k` or `-q:a 1–5` | Universal, fine for video |
| AAC (HE) | `aac` + `-profile:a aac_he_v2` | `-b:a 32k–64k` | Voice-only at very low bitrates |
| Opus | `libopus` | `-b:a 96k–192k` | Best quality per bit; not in .mp4 (use .webm/.mkv/.opus) |
| MP3 | `libmp3lame` | `-q:a 0–9` (0=best) or `-b:a 192k–320k` | Legacy compatibility |
| FLAC | `flac` | `-compression_level 0–12` | Lossless |
| PCM | `pcm_s16le`/`pcm_s24le` | n/a | Lossless WAV |

**Mappings cheat-sheet:** `-c:a copy` to passthrough, `-an` to drop audio, `-c:a libopus -b:a 128k` to re-encode.

## Container compatibility

| Container | Video codecs | Audio codecs | Subtitles |
|---|---|---|---|
| .mp4 | H.264, H.265 (`-tag:v hvc1`), AV1 | AAC, MP3 | mov_text |
| .mkv | Anything | Anything | SRT, ASS, PGS |
| .webm | VP8, VP9, AV1 | Vorbis, Opus | WebVTT |
| .mov | H.264, H.265, ProRes | AAC, PCM | mov_text |
| .gif | n/a (frames only) | n/a | n/a |

When in doubt, .mkv accepts everything — useful as an intermediate format. `.mp4` is the right choice for web/social.

## GIF specifics

GIFs are limited to 256 colors per frame. Naive conversion looks awful. Always use `palettegen` + `paletteuse`:

```bash
# Two-pass (better quality)
ffmpeg -i in.mp4 -vf "fps=15,scale=480:-2:flags=lanczos,palettegen=stats_mode=diff" -y palette.png
ffmpeg -i in.mp4 -i palette.png -lavfi "fps=15,scale=480:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" -y out.gif

# Single-pass (one pipeline, slightly larger output)
ffmpeg -i in.mp4 -vf "fps=15,scale=480:-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" -y out.gif
```

Knobs:
- `fps=` — 10–15 for talking-head-style content, 15–24 for motion. Higher = much larger files.
- `scale=` — width is the biggest file-size lever. 480 for chat embeds, 720 for higher-quality previews.
- `palettegen=stats_mode=diff` — focuses palette on changing regions (best for screen recordings, talking heads).
- `paletteuse=dither=bayer:bayer_scale=5` — best dithering for screen content. Use `dither=floyd_steinberg` for photographic content but expect bigger files.

## HLS / DASH packaging

### HLS (single rendition)
```bash
ffmpeg -i in.mp4 \
  -c:v libx264 -crf 22 -preset medium -profile:v high -level 4.0 \
  -c:a aac -b:a 128k \
  -force_key_frames "expr:gte(t,n_forced*4)" \
  -hls_time 4 -hls_playlist_type vod \
  -hls_segment_type fmp4 \
  -f hls out.m3u8
```

### Multi-bitrate HLS (adaptive)
Encode each rendition separately at fixed-GOP (use `-x264-params "keyint=K:min-keyint=K:scenecut=0"` with `K = fps × segment_seconds`), then write a master playlist by hand or with `-master_pl_name`. See recipes.md "Adaptive HLS".

### Segment guidance
- 4–6s segments: typical VOD sweet spot (Apple's HLS authoring spec recommends 6s).
- 2s: lower latency, more HTTP requests.
- All renditions must have aligned keyframes — that's the point of forcing fixed GOP.
- `fmp4` (CMAF) segments are usable by both HLS and DASH from a single set.

## xfade transitions

```bash
ffmpeg -i a.mp4 -i b.mp4 \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=1:offset=4[v]" \
  -map "[v]" -c:v libx264 -crf 20 out.mp4
```

- `offset` is the start time of the transition relative to the first input.
- For audio crossfade: pair with `[0:a][1:a]acrossfade=d=1[a]`.
- Both inputs must have the **same resolution, pixel format, frame rate, and timebase**. If not: prepend `[0:v]fps=30,format=yuv420p,setsar=1,settb=AVTB[v0]; [1:v]fps=30,format=yuv420p,setsar=1,settb=AVTB[v1]; [v0][v1]xfade=...`.
- ~44 transition types: fade, dissolve, wipeleft, wiperight, slideleft, slideright, slideup, slidedown, circlecrop, rectcrop, distance, fadeblack, fadewhite, radial, smoothleft, smoothright, smoothup, smoothdown, circleopen, circleclose, vertopen, vertclose, horzopen, horzclose, dissolve, pixelize, diagtl, diagtr, diagbl, diagbr, hlslice, hrslice, vuslice, vdslice, hblur, fadegrays, wipetl, wipetr, wipebl, wipebr, squeezeh, squeezev, zoomin, fadefast, fadeslow.

## Commonly-needed expressions

In filters that accept expressions (overlay X/Y, crop coords, drawtext text, enable=, etc.):
- `t` — current timestamp (seconds, float)
- `n` — frame number (integer)
- `pts` — presentation timestamp in stream timebase
- `iw` / `ih` — input width/height
- `ow` / `oh` — output width/height (in some filters)
- `main_w` / `main_h` — main video dimensions (overlay context)
- `overlay_w` / `overlay_h` — overlay dimensions
- `W` / `H` / `w` / `h` — short aliases for the above (overlay context)

Operators: `+ - * / %`, `< <= == >= >`, `and or not`, `if(cond,then,else)`, `between(x,low,high)`, `gt(a,b)`, `eq(a,b)`, `mod(a,b)`, `floor(x)`, `ceil(x)`, `trunc(x)`, `min(a,b)`, `max(a,b)`.

Inside a filter argument string, escape `:` as `\:` and `,` as `\,` when they're literal data (e.g. inside an `enable=` expression or a `drawtext=text=`).
