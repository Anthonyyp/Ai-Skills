# FFmpeg Troubleshooting

Failure modes you'll hit on this Windows machine. Look here first when output looks wrong.

## "Why is my output broken?" — debugging order

When something looks wrong:
1. **Re-probe the output** (`ffprobe out.mp4`). 90% of the time the issue is visible — wrong dimensions, half the duration, no audio stream, wrong codec.
2. **Read stderr above the error.** ffmpeg often warns about the real problem 20 lines before the message that finally killed the encode.
3. **Bisect the filter graph.** If a `filter_complex` produces wrong output, comment out filters one at a time until you find the offender.
4. **Try with `-loglevel verbose`** to see filter graph negotiation. Pixel-format/timebase mismatches show up here as "auto-inserted" filters and explain a lot of weirdness.

## drawtext silently produces output without text

**Symptom:** `-vf "drawtext=text='hello'"` runs successfully, but the output has no visible text.

**Cause:** A broken fontconfig setup, common in Windows ffmpeg builds. Even with `--enable-fontconfig --enable-libfreetype` compiled in, the runtime can't find any fonts and `drawtext` silently no-ops instead of failing loudly.

**Fix:** On an affected build, don't use drawtext for text overlays. Alternatives:
- For subtitles → use `subtitles=` filter with an SRT file, or `ass=` with an ASS file (libass works fine here).
- For burned-in static text → render the text once in another tool (Photoshop, Inkscape, or even an HTML→PNG snapshot) and overlay the PNG with the `overlay` filter.
- For timestamps on contact sheets → infer time from grid position rather than overlaying. With `fps=1/N tile=ColxRow`, cell `(r, c)` is at `(r × Col + c) × N` seconds.

If you must try drawtext anyway, supply an explicit `fontfile=`:
```
drawtext=fontfile='/c/Windows/Fonts/arial.ttf':text='hello':...
```
Use forward slashes in the path even on Windows. Even with this, behavior is inconsistent — assume it might silently no-op.

## "height not divisible by 2" / yuv420p errors

**Symptom:**
```
[libx264 @ ...] height not divisible by 2 (...)
Error initializing output stream 0:0 -- Error while opening encoder for output stream
```

**Cause:** `yuv420p` (the universal pixel format for H.264 in .mp4) requires both dimensions to be even. GIF sources and some cropped videos have odd dimensions.

**Fix:** Add an even-rounding scale filter:
```bash
-vf "scale=trunc(iw/2)*2:trunc(ih/2)*2"
# or, if you also want to set a target width:
-vf "scale=1280:-2"           # height auto, rounded to even
```

`-2` in `scale` means "auto, preserve aspect, round to even". Always prefer it over `-1` for `yuv420p` outputs.

## Concat demuxer succeeds but output is broken

**Symptom:** `ffmpeg -f concat -i list.txt -c copy out.mp4` runs without errors but output has audio drift, frozen frames, wrong duration, or stuttering.

**Cause:** Concat demuxer requires identical codec parameters across all inputs (same codec, same dimensions, same fps, same pixel format, same audio sample rate, same audio channel layout). It silently produces broken output if anything differs.

**Fix:** Probe all inputs and compare:
```bash
for f in *.mp4; do
  echo "=== $f ==="
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt -of default=nw=1 "$f"
done
```

If they don't match, normalize first — see recipes.md "Normalize before concat" — or use the `concat` filter (filter_complex form) which can handle differences but requires re-encoding.

## Audio out of sync after speed changes

**Symptom:** After a `setpts=PTS/N` speed change, audio plays at original speed (or, conversely, video plays at original speed and audio is fast).

**Cause:** `setpts` only affects video timestamps. Audio needs `atempo` to actually play at a different speed.

**Fix:** Always pair them, with the inverse relationship:
- Video `setpts=PTS/N` (N× faster) ↔ audio `atempo=N`
- Video `setpts=PTS*N` (1/N speed) ↔ audio `atempo=1/N`

`atempo` clamps to 0.5–2.0 per instance. For larger ratios, chain:
```
atempo=2.0,atempo=2.0       # 4× faster
atempo=2.0,atempo=2.0,atempo=1.5    # 6× faster
atempo=0.5,atempo=0.5       # 0.25× speed
```

## "Filter complex_filter failed: Invalid data found"

**Symptom:** filter_complex errors out with "Invalid data" or "no such filter" or "could not find pad".

**Causes & fixes:**

1. **Stream label typo or reuse.** Each `[label]` must be defined exactly once and consumed exactly once. Splitting requires the `split`/`asplit` filter:
   ```
   [0:v]split=2[a][b]    # not [0:v][0:v]
   ```

2. **Wrong stream index.** `[0:v]` is the first video stream of input 0. If your input has the video as its second stream, use `[0:v:0]` or `[0:1]`. Probe to check.

3. **Mixed audio/video filterchain.** Video filters and audio filters can't share a chain. Separate them:
   ```
   [0:v]scale=1920:-2[v];      # video chain
   [0:a]aresample=48000[a]     # audio chain
   ```

4. **Whitespace inside expressions.** Filter argument parsing is brittle. Inside an expression, `between(t, 5, 10)` may break — write `between(t,5,10)` with no spaces.

5. **Forgot to escape `:` or `,` inside an `enable=` or `text=`.** Use `\:` and `\,` for literal characters inside expressions:
   ```
   enable='between(t,5,10)'                       # no escaping needed
   drawtext=text='10\:30\:45'                     # escape colons in displayed text
   ```

## "filter requires same timebase / framerate" (xfade, concat)

**Symptom:**
```
[Parsed_xfade_2 @ ...] First input link main parameters (size 1920x1080, SAR 1:1) do not match the corresponding second input link xfade parameters (size 1280x720, SAR 1:1)
```

**Cause:** xfade and concat filter both require all inputs to have matching properties.

**Fix:** Normalize each input branch first:
```
[0:v]fps=30,scale=1920:1080,setsar=1,settb=AVTB,format=yuv420p[v0];
[1:v]fps=30,scale=1920:1080,setsar=1,settb=AVTB,format=yuv420p[v1];
[v0][v1]xfade=transition=fade:duration=1:offset=4[v]
```

The four normalizations to apply universally before xfade/concat:
- `fps=N` (frame rate)
- `scale=W:H` (dimensions)
- `setsar=1` (sample aspect ratio = 1:1)
- `settb=AVTB` (timebase to AV's default)
- `format=yuv420p` (pixel format)

## Cuts land on the wrong frame

**Symptom:** Asked for a cut at 30s, output starts at 28s or 31s.

**Cause:** `-c copy` cuts can only happen on keyframes. Your video has keyframes every ~2–10s, so the cut snaps to the nearest one.

**Fix:** Either accept the snap (and use a keyframe-aware tool to pick exact frames), or re-encode for frame-accuracy:
```bash
# Frame-accurate
ffmpeg -ss 30 -i in.mp4 -t 10 \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 160k out.mp4
```

To inspect where keyframes actually are:
```bash
ffprobe -v error -select_streams v:0 -skip_frame nokey \
  -show_entries frame=pts_time -of csv=p=0 in.mp4
```

## HEVC plays in VLC but not in Safari/QuickTime

**Symptom:** Output `.mp4` from `libx265` plays in VLC/Chrome but Safari/QuickTime says "unsupported format".

**Cause:** Apple expects the codec tag `hvc1` in the .mp4 container. ffmpeg writes `hev1` by default, which Apple doesn't recognize.

**Fix:** Add `-tag:v hvc1`:
```bash
ffmpeg -i in.mp4 -c:v libx265 -crf 24 -tag:v hvc1 -c:a copy out.mp4
```

## .mp4 output stutters when streamed but plays fine locally

**Symptom:** Local playback is smooth. When uploaded and accessed via HTTP, the video pauses for a long time before starting.

**Cause:** The `moov` atom (the index telling the player where things are) is at the end of the file, so the player has to download the whole file before starting.

**Fix:** Add `-movflags +faststart`:
```bash
ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4
```

This rewrites the file to put `moov` at the front. For new encodes, just include this flag from the start.

## ".m4s/.ts segments are not aligned across renditions" (HLS)

**Symptom:** Adaptive HLS playlist has all renditions, but the player rebuffers awkwardly when switching quality.

**Cause:** Renditions don't share keyframe positions. The player can only switch on keyframe boundaries.

**Fix:** Force fixed-GOP encoding. With `KEYINT = fps × segment_duration`:
```bash
-x264-params "keyint=120:min-keyint=120:scenecut=0"
# or
-force_key_frames "expr:gte(t,n_forced*4)"
```

`scenecut=0` disables x264's adaptive keyframe insertion at scene boundaries — necessary for true fixed-GOP.

## Output file is enormous (10× the source)

**Symptom:** Source is 100 MB; output is 1 GB.

**Causes & fixes:**

1. **Forgot CRF / used very low one.** Default x264 with no `-crf` uses CRF 23. If you're getting big files, you might be using `-crf 0` (lossless) or a very low value. Bump `-crf` up.
2. **Enormous fps after a speed change.** A 16× speedup of 100fps source produces 1600fps timestamps — you encode every duplicate frame. Always add `fps=60` (or `fps=30`) at the end of speed-up branches.
3. **No re-encode of audio when extracting.** WAV/PCM is lossless and very large. Use `-c:a libopus -b:a 128k` or AAC for size-conscious workflows.
4. **Encoding from a high-bitrate source with `-c:v copy`.** If you only meant to clip, `-c copy` keeps the original bitrate. Re-encode if you wanted to shrink it.

## "Could not find tag for codec" or "muxer not compatible"

**Symptom:**
```
Could not find tag for codec opus in stream #0, codec not currently supported in container
```

**Cause:** Some codec/container combinations aren't legal. Opus in `.mp4` was unsupported for years (now possible but flaky); H.264 with PCM audio in `.mp4` is fine; AAC in `.webm` is illegal.

**Fix:** See the container compatibility table in `reference.md`. Common legal pairings:
- .mp4 → H.264/H.265/AV1 video + AAC/MP3 audio
- .webm → VP8/VP9/AV1 video + Opus/Vorbis audio
- .mkv → anything works

When in doubt, use `.mkv` as an intermediate.

## Hardware encoder is slower than software / fails to initialize

**Symptom:** `h264_nvenc` errors with "Cannot load nvcuda.dll" or "No NVENC capable devices found", or runs at 5 fps.

**Causes & fixes:**

1. **Driver not installed.** NVENC needs the NVIDIA display driver (it does NOT need the CUDA toolkit). Update GeForce/Studio drivers.
2. **Discrete GPU disabled / laptop on iGPU.** Force discrete GPU via Windows graphics settings or manufacturer utility.
3. **Source is already on CPU and conversion overhead dominates.** For small videos, software is sometimes faster than the round-trip CPU↔GPU overhead. Try `-hwaccel cuda -hwaccel_output_format cuda` to keep frames on GPU end-to-end.
4. **NVENC session limit reached.** Consumer NVIDIA cards limit to 3 simultaneous NVENC sessions. The 4th one fails. Close other recording/streaming software.

## "Unknown encoder 'libfdk_aac'"

This build has `--disable-libfdk-aac` (FDK AAC has a non-redistributable license). Use the built-in `aac` encoder instead:
```bash
-c:a aac -b:a 192k
```
Quality is comparable for 128 kbps+ targets. For very low bitrates (< 64 kbps), libfdk's HE-AAC was meaningfully better, but you can't use it here without a custom build.

## EBU R128 loudnorm pass 2 doesn't produce target loudness

**Symptom:** After two-pass loudnorm, re-measuring shows the output is at -18 LUFS instead of the requested -16.

**Cause:** Either the measured values weren't transcribed correctly into pass 2, or `linear=true` isn't being honored because the source is too dynamic.

**Fix:** Double-check that `measured_I`, `measured_LRA`, `measured_TP`, `measured_thresh`, and `offset` all came from the JSON output of pass 1, and `linear=true` was set in pass 2. If the dynamic range is too wide for linear normalization, the filter falls back to dynamic mode and won't hit the exact target — that's expected. Re-measure with:
```bash
ffmpeg -i out.mp4 -af loudnorm=print_format=json -f null - 2>&1 | grep '"input_'
```

## Subtitle filter can't find subs.srt with absolute path

**Symptom:**
```
[subtitles @ ...] Unable to open C:\path\to\subs.srt
```

**Cause:** The `subtitles=` filter parses its argument as an ffmpeg filter string. Backslashes in Windows paths and the colon after the drive letter both break parsing.

**Fix:** Use forward slashes and escape the colon:
```
-vf "subtitles=C\\:/Users/you/Videos/subs.srt"
```
or copy the SRT into the cwd and reference it by basename:
```
-vf "subtitles=subs.srt"
```

## Filter graph "auto-inserted" something unexpected

**Symptom:** With `-loglevel verbose`, you see things like:
```
auto_scale_0 ... yuv422p -> yuv420p
auto_resample_0 ... 44100 Hz stereo -> 48000 Hz stereo
```

**Cause:** ffmpeg's filter graph negotiator inserted automatic conversions to make endpoints compatible. This is usually fine, but it costs CPU and can introduce subtle quality loss (color subsampling, resampling).

**Fix:** Make endpoints match explicitly. Add `format=yuv420p`, `aresample=48000`, `scale=` etc. to tell the graph what you want, instead of letting it guess.

## "Process killed" / "WSAEAGAIN" on large files

**Symptom:** ffmpeg dies partway through with "Killed" or memory-related error on a long encode.

**Causes:**

1. **Out of memory.** Some filters (especially scene detection on long sources, or motion interpolation) buffer entire windows in RAM. Process in chunks: cut to 5-min pieces, encode each, concat losslessly.
2. **OS resource limit.** On Windows, very long pipelines with many filter stages can exhaust handle limits. Reduce filter count by combining (`scale=...,fps=...,format=...` in one chain rather than three).

## When to abandon a complex filter graph

If your `filter_complex` is past ~20 filterchains, has lots of conditional logic, or you're regenerating it programmatically anyway: stop, render an intermediate `.mkv` after the first half of the work, then run a second ffmpeg call on that. Two simple commands are easier to debug than one heroic filter graph, and the .mkv intermediate is essentially free if you use a fast preset (`-c:v libx264 -preset ultrafast -crf 18`).
