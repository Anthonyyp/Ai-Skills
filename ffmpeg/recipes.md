# FFmpeg Recipes

Copy-paste commands for common tasks. All commands assume bash on Windows. Replace `in.*` / `out.*` with actual filenames.

## Inspection

### Basic probe
```bash
ffprobe -hide_banner in.mp4
```

### One-line summary
```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,codec_name,duration \
  -show_entries format=duration,size,bit_rate \
  -of default=nw=1 in.mp4
```

### Get just the duration in seconds
```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 in.mp4
```

### Get keyframe timestamps (before stream-copy cut)
```bash
ffprobe -v error -select_streams v:0 -skip_frame nokey \
  -show_entries frame=pts_time -of csv=p=0 in.mp4
```

### Build a contact sheet (single tiled JPEG covering the whole video)
```bash
mkdir -p analysis
ffmpeg -hide_banner -loglevel error -y -i in.mp4 \
  -vf "fps=1/4,scale=384:-2,tile=8x10" \
  -frames:v 1 analysis/contact_sheet.jpg
```
Tune `fps=1/N` so total frames ≈ rows × cols. For a 5-min source: `fps=1/4` × `tile=8x10` (=80 frames). Cell `(row, col)` is at time `(row × cols + col) × interval` seconds. Don't try to overlay timestamps with `drawtext` on this Windows build — it silently fails.

### Zoom-in tile sheet for a specific section
```bash
ffmpeg -ss 120 -i in.mp4 -t 60 \
  -vf "fps=2,scale=480:-2,tile=4x14" -frames:v 1 \
  analysis/zoom_120_180.jpg
```

## Format conversion

### Remux to .mp4 (no re-encode, web-streamable)
```bash
ffmpeg -i in.mkv -c copy -movflags +faststart out.mp4
```

### Convert to .mp4 with H.264 (universal compatibility)
```bash
ffmpeg -i in.mkv \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

### Convert to .mp4 with H.265 (smaller file)
```bash
ffmpeg -i in.mkv \
  -c:v libx265 -crf 24 -preset medium -pix_fmt yuv420p \
  -tag:v hvc1 \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```
The `-tag:v hvc1` is required for QuickTime/Safari to recognize HEVC in .mp4.

### Convert to .webm (VP9 + Opus, open formats)
```bash
ffmpeg -i in.mp4 \
  -c:v libvpx-vp9 -crf 32 -b:v 0 -row-mt 1 \
  -c:a libopus -b:a 128k \
  out.webm
```

### Convert to AV1 (.mp4)
```bash
ffmpeg -i in.mp4 \
  -c:v libsvtav1 -crf 28 -preset 6 -pix_fmt yuv420p10le \
  -svtav1-params tune=0 \
  -c:a libopus -b:a 128k \
  -movflags +faststart out.mp4
```

### GIF → MP4 (preparing for editing)
```bash
ffmpeg -i in.gif -movflags +faststart -pix_fmt yuv420p \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" in.mp4
```
The `scale=trunc(iw/2)*2:trunc(ih/2)*2` is mandatory — yuv420p requires even dimensions and gif sources are often odd-sized.

## Trimming and cutting

### Lossless cut (snaps to keyframes)
```bash
# 30s clip starting at 1:30
ffmpeg -ss 90 -i in.mp4 -t 30 -c copy out.mp4

# Same, with end timestamp instead of duration
ffmpeg -ss 90 -i in.mp4 -to 120 -c copy out.mp4
```

### Frame-accurate cut (re-encodes)
```bash
ffmpeg -ss 90 -i in.mp4 -t 30 \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  -movflags +faststart out.mp4
```

### Keep only the audio
```bash
ffmpeg -i in.mp4 -vn -c:a copy out.m4a       # whatever the source audio is
ffmpeg -i in.mp4 -vn -c:a libmp3lame -q:a 2 out.mp3
ffmpeg -i in.mp4 -vn -c:a libopus -b:a 128k out.opus
ffmpeg -i in.mp4 -vn -c:a pcm_s16le out.wav
```

### Drop audio, keep video
```bash
ffmpeg -i in.mp4 -an -c:v copy out.mp4
```

## Concatenation

### Lossless join (same codec, resolution, fps)
```bash
printf "file 'a.mp4'\nfile 'b.mp4'\nfile 'c.mp4'\n" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy joined.mp4
```

### Normalize before concat (different sources)
```bash
# Re-encode each input to a common spec first
for f in a.mp4 b.mov c.mkv; do
  ffmpeg -i "$f" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1" \
    -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
    -c:a aac -b:a 160k -ar 48000 -ac 2 \
    "norm_${f%.*}.mp4"
done
printf "file 'norm_a.mp4'\nfile 'norm_b.mp4'\nfile 'norm_c.mp4'\n" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy joined.mp4
```

### Concat via filter_complex (no list file, no demuxer requirements)
```bash
ffmpeg -i a.mp4 -i b.mp4 -i c.mp4 \
  -filter_complex "
    [0:v]scale=1920:1080,setsar=1,fps=30[v0];[0:a]aresample=48000[a0];
    [1:v]scale=1920:1080,setsar=1,fps=30[v1];[1:a]aresample=48000[a1];
    [2:v]scale=1920:1080,setsar=1,fps=30[v2];[2:a]aresample=48000[a2];
    [v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]
  " -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 160k \
  -movflags +faststart joined.mp4
```

## Cut-list edits (trim + speed + concat)

The pattern for condensing recordings: pick a list of (start, end, speed) tuples and render them all in one pass.

```bash
ffmpeg -y -i in.mp4 -filter_complex "
  [0:v]trim=0:5,setpts=PTS-STARTPTS,scale=1920:-2,fps=60[v1];
  [0:v]trim=5:60,setpts=(PTS-STARTPTS)/8,scale=1920:-2,fps=60[v2];
  [0:v]trim=120:140,setpts=PTS-STARTPTS,scale=1920:-2,fps=60[v3];
  [v1][v2][v3]concat=n=3:v=1:a=0[out]
" -map "[out]" -movflags +faststart -pix_fmt yuv420p \
  -c:v libx264 -crf 20 -preset medium out.mp4
```

With audio and matching tempo changes:
```bash
ffmpeg -y -i in.mp4 -filter_complex "
  [0:v]trim=0:5,setpts=PTS-STARTPTS,scale=1920:-2,fps=60[v1];
  [0:a]atrim=0:5,asetpts=PTS-STARTPTS[a1];
  [0:v]trim=5:60,setpts=(PTS-STARTPTS)/4,scale=1920:-2,fps=60[v2];
  [0:a]atrim=5:60,asetpts=PTS-STARTPTS,atempo=2.0,atempo=2.0[a2];
  [v1][a1][v2][a2]concat=n=2:v=1:a=1[v][a]
" -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

## Resize / crop / pad

### Scale to 1920 wide, preserve aspect, even height
```bash
ffmpeg -i in.mp4 -vf "scale=1920:-2:flags=lanczos" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
  -c:a copy out.mp4
```

### Scale, but never upscale
```bash
ffmpeg -i in.mp4 -vf "scale='min(1920,iw)':-2:flags=lanczos" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Center crop
```bash
ffmpeg -i in.mp4 -vf "crop=in_w-400:in_h-200" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Fit-to-1920x1080 with letterbox (no cropping)
```bash
ffmpeg -i in.mp4 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Square crop (Instagram-style)
```bash
ffmpeg -i in.mp4 \
  -vf "crop=ih:ih,scale=1080:1080" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### 9:16 portrait crop (TikTok/Reels)
```bash
ffmpeg -i in.mp4 \
  -vf "crop=ih*9/16:ih,scale=1080:1920" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

## Rotation

### 90° clockwise (e.g. portrait phone shot)
```bash
ffmpeg -i in.mp4 -vf "transpose=1" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```
`transpose=2` for counter-clockwise. For 180° use `transpose=2,transpose=2`.

### Set rotation metadata only (no re-encode, .mp4 only)
```bash
ffmpeg -i in.mp4 -c copy -metadata:s:v:0 rotate=90 out.mp4
```

## Speed changes (whole file)

### 2× faster, audio synced
```bash
ffmpeg -i in.mp4 \
  -filter_complex "[0:v]setpts=PTS/2[v];[0:a]atempo=2.0[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -c:a aac -b:a 160k out.mp4
```

### 4× faster (chained atempo)
```bash
ffmpeg -i in.mp4 \
  -filter_complex "[0:v]setpts=PTS/4[v];[0:a]atempo=2.0,atempo=2.0[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -c:a aac -b:a 160k out.mp4
```

### 0.5× slower
```bash
ffmpeg -i in.mp4 \
  -filter_complex "[0:v]setpts=PTS*2[v];[0:a]atempo=0.5[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -c:a aac -b:a 160k out.mp4
```

### Silent video, video-only speed (no audio handling)
```bash
ffmpeg -i in.mp4 -vf "setpts=PTS/4" -an \
  -c:v libx264 -crf 20 out.mp4
```

## GIF

### High-quality GIF from MP4 (two-pass, palettegen)
```bash
ffmpeg -i in.mp4 -vf "fps=15,scale=480:-2:flags=lanczos,palettegen=stats_mode=diff" -y palette.png
ffmpeg -i in.mp4 -i palette.png \
  -lavfi "fps=15,scale=480:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -y out.gif
rm palette.png
```

### High-quality GIF, single command
```bash
ffmpeg -i in.mp4 \
  -vf "fps=15,scale=480:-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -y out.gif
```

### GIF → high-quality MP4
```bash
ffmpeg -i in.gif -movflags +faststart -pix_fmt yuv420p \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
  -c:v libx264 -crf 18 -preset slow out.mp4
```

## Audio

### Normalize loudness (EBU R128, two-pass — best quality)
```bash
# Pass 1: measure
ffmpeg -i in.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 \
  | tee /tmp/loudnorm.log

# Read measured_I, measured_LRA, measured_TP, measured_thresh, target_offset from the JSON output.
# Pass 2: apply with measured values
ffmpeg -i in.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-23.5:measured_LRA=8.2:measured_TP=-5.4:measured_thresh=-34.6:offset=-0.7:linear=true" \
  -c:v copy -c:a aac -b:a 192k out.mp4
```

Targets:
- **Streaming/podcasts**: I=-16 LUFS, TP=-1.5 dBTP (the values above)
- **Broadcast**: I=-23 LUFS, TP=-1.0 dBTP
- **YouTube**: I=-14 LUFS (YouTube targets -14 in their normalization)

### Normalize loudness (single-pass — quicker, less accurate)
```bash
ffmpeg -i in.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v copy -c:a aac -b:a 192k out.mp4
```

### Mix two audio tracks
```bash
ffmpeg -i a.wav -i b.wav -filter_complex "amix=inputs=2:duration=longest" out.wav
```

### Replace video's audio with a different file
```bash
ffmpeg -i video.mp4 -i music.mp3 \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 192k -shortest \
  out.mp4
```

## Subtitles

### Burn SRT into video (hard subs)
```bash
ffmpeg -i in.mp4 -vf "subtitles=subs.srt" \
  -c:v libx264 -crf 20 -preset medium \
  -c:a copy out.mp4
```

### Burn with custom style
```bash
ffmpeg -i in.mp4 -vf "subtitles=subs.srt:force_style='FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,BorderStyle=1,Outline=2,Shadow=0,MarginV=40'" \
  -c:v libx264 -crf 20 -preset medium \
  -c:a copy out.mp4
```

ASS color is `&HBBGGRR&` hex. `BorderStyle=1` = outline only; `BorderStyle=3` = box behind text; `BorderStyle=4` = semi-transparent box.

### Burn ASS (style is in the file)
```bash
ffmpeg -i in.mp4 -vf "ass=subs.ass" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Add soft subs (toggleable in player)
```bash
ffmpeg -i in.mp4 -i subs.srt \
  -map 0 -map 1 \
  -c copy -c:s mov_text \
  -metadata:s:s:0 language=eng \
  -metadata:s:s:0 title="English" \
  out.mp4
```

For .mkv use `-c:s srt` (or just `-c:s copy` if input is already .srt). For .webm use `-c:s webvtt`.

## Watermarks / overlays

### PNG watermark, bottom-right
```bash
ffmpeg -i in.mp4 -i logo.png \
  -filter_complex "[0:v][1:v]overlay=W-w-20:H-h-20" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Watermark with reduced opacity
```bash
ffmpeg -i in.mp4 -i logo.png \
  -filter_complex "[1:v]format=rgba,colorchannelmixer=aa=0.5[wm];[0:v][wm]overlay=W-w-20:H-h-20" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Watermark only visible during a time range
```bash
ffmpeg -i in.mp4 -i logo.png \
  -filter_complex "[0:v][1:v]overlay=W-w-20:H-h-20:enable='between(t,5,15)'" \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

### Picture-in-picture (small video over big video)
```bash
ffmpeg -i main.mp4 -i pip.mp4 \
  -filter_complex "[1:v]scale=320:-2[pip];[0:v][pip]overlay=W-w-20:H-h-20" \
  -map 0:a? \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

## Transitions

### Crossfade between two clips (1s fade starting at t=4 in clip A)
```bash
ffmpeg -i a.mp4 -i b.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=1:offset=4[v];
    [0:a][1:a]acrossfade=d=1[a]
  " -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -c:a aac -b:a 160k out.mp4
```

If inputs have different fps/resolution/timebase, normalize first:
```bash
ffmpeg -i a.mp4 -i b.mp4 \
  -filter_complex "
    [0:v]fps=30,scale=1920:1080,setsar=1,settb=AVTB,format=yuv420p[v0];
    [1:v]fps=30,scale=1920:1080,setsar=1,settb=AVTB,format=yuv420p[v1];
    [v0][v1]xfade=transition=fade:duration=1:offset=4[v]
  " -map "[v]" -map 0:a \
  -c:v libx264 -crf 20 -c:a copy out.mp4
```

## Hardware encoding

### NVIDIA NVENC (H.264)
```bash
ffmpeg -i in.mp4 \
  -c:v h264_nvenc -preset p5 -cq 21 -rc vbr -b:v 0 \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

### NVIDIA NVENC (H.265)
```bash
ffmpeg -i in.mp4 \
  -c:v hevc_nvenc -preset p5 -cq 23 -rc vbr -b:v 0 \
  -tag:v hvc1 \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

### Intel QSV (H.264)
```bash
ffmpeg -i in.mp4 \
  -c:v h264_qsv -preset medium -global_quality 22 \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

### AMD AMF (H.264)
```bash
ffmpeg -i in.mp4 \
  -c:v h264_amf -quality quality -rc cqp -qp_i 20 -qp_p 22 \
  -c:a aac -b:a 160k \
  -movflags +faststart out.mp4
```

## HLS

### Single-rendition VOD HLS
```bash
mkdir -p hls
ffmpeg -i in.mp4 \
  -c:v libx264 -crf 22 -preset medium -profile:v high -level 4.0 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 \
  -force_key_frames "expr:gte(t,n_forced*4)" \
  -hls_time 4 -hls_playlist_type vod -hls_segment_type fmp4 \
  -f hls hls/master.m3u8
```

### Adaptive HLS (3 renditions, fixed-GOP)
```bash
mkdir -p hls
# Common args
KEYINT=120  # 4s × 30fps

# 1080p
ffmpeg -i in.mp4 -vf "scale=-2:1080" \
  -c:v libx264 -crf 22 -preset medium -profile:v high -pix_fmt yuv420p \
  -x264-params "keyint=${KEYINT}:min-keyint=${KEYINT}:scenecut=0" \
  -c:a aac -b:a 128k -ar 48000 \
  -hls_time 4 -hls_playlist_type vod -hls_segment_type fmp4 \
  -hls_segment_filename "hls/1080p_%03d.m4s" \
  -f hls hls/1080p.m3u8

# 720p
ffmpeg -i in.mp4 -vf "scale=-2:720" \
  -c:v libx264 -crf 23 -preset medium -profile:v high -pix_fmt yuv420p \
  -x264-params "keyint=${KEYINT}:min-keyint=${KEYINT}:scenecut=0" \
  -c:a aac -b:a 96k -ar 48000 \
  -hls_time 4 -hls_playlist_type vod -hls_segment_type fmp4 \
  -hls_segment_filename "hls/720p_%03d.m4s" \
  -f hls hls/720p.m3u8

# 480p
ffmpeg -i in.mp4 -vf "scale=-2:480" \
  -c:v libx264 -crf 24 -preset medium -profile:v high -pix_fmt yuv420p \
  -x264-params "keyint=${KEYINT}:min-keyint=${KEYINT}:scenecut=0" \
  -c:a aac -b:a 64k -ar 48000 \
  -hls_time 4 -hls_playlist_type vod -hls_segment_type fmp4 \
  -hls_segment_filename "hls/480p_%03d.m4s" \
  -f hls hls/480p.m3u8

# Master playlist
cat > hls/master.m3u8 <<'EOF'
#EXTM3U
#EXT-X-VERSION:6
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2"
1080p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"
720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1400000,RESOLUTION=854x480,CODECS="avc1.64001f,mp4a.40.2"
480p.m3u8
EOF
```

## Frame extraction

### Single frame at a timestamp
```bash
ffmpeg -ss 30 -i in.mp4 -frames:v 1 -q:v 2 frame.jpg
```

### Every Nth second
```bash
ffmpeg -i in.mp4 -vf "fps=1/5" -q:v 2 frame_%04d.jpg
```

### Just keyframes
```bash
ffmpeg -i in.mp4 -vf "select=eq(pict_type\,I)" -vsync vfr -q:v 2 keyframe_%04d.jpg
```

### Scene-change frames (good thumbnail candidates)
```bash
ffmpeg -i in.mp4 -vf "select='gt(scene,0.4)'" -vsync vfr -q:v 2 scene_%04d.jpg
```

## Streaming / live

### Push to RTMP (e.g. Twitch, YouTube Live)
```bash
ffmpeg -i in.mp4 \
  -c:v libx264 -preset veryfast -tune zerolatency -b:v 4500k -maxrate 4500k -bufsize 9000k \
  -g 60 -keyint_min 60 \
  -c:a aac -b:a 160k -ar 48000 \
  -f flv rtmp://server/app/streamkey
```

### Capture screen (Windows, gdigrab)
```bash
ffmpeg -f gdigrab -framerate 30 -i desktop \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  out.mp4
```

### Capture screen with audio
```bash
ffmpeg -f gdigrab -framerate 30 -i desktop \
  -f dshow -i audio="Stereo Mix" \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 160k \
  out.mp4
```
List dshow audio devices: `ffmpeg -list_devices true -f dshow -i dummy`.

## Misc

### Reverse a video
```bash
ffmpeg -i in.mp4 -vf reverse -af areverse out.mp4
```

### Loop a clip N times
```bash
ffmpeg -stream_loop 4 -i in.mp4 -c copy out.mp4   # plays 5 times total
```

### Generate a still video from an image (e.g. for a podcast on YouTube)
```bash
ffmpeg -loop 1 -i cover.jpg -i audio.mp3 \
  -c:v libx264 -tune stillimage -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest \
  -movflags +faststart out.mp4
```

### Strip metadata
```bash
ffmpeg -i in.mp4 -map_metadata -1 -c copy out.mp4
```

### Add chapter marks (from a CSV)
Build a metadata file:
```
;FFMETADATA1
[CHAPTER]
TIMEBASE=1/1000
START=0
END=120000
title=Intro

[CHAPTER]
TIMEBASE=1/1000
START=120000
END=300000
title=Main Section
```
Then:
```bash
ffmpeg -i in.mp4 -i chapters.txt -map_metadata 1 -codec copy out.mp4
```
