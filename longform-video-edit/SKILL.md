---
name: longform-video-edit
description: Cut a long recording (webinar, training session, meeting, screen-share, lecture) into a tight shareable video — survey what's in it, decide what to remove, blur private information on screen, mute words, render, verify nothing leaked, and deliver at sensible file sizes. Trigger on "cut this down", "edit this recording", "make this shorter", "trim the dead air", "blur the client names", "make a shareable version", or being handed a 45+ minute recording that needs to circulate. Uses your own vision to read the video — no cloud video model required.
---

# Editing long-form recordings

**The one rule: verify by looking at output frames.** Every mistake this workflow guards against was
invisible in logs and obvious in a picture. Expect two or three render passes on anything with
private data on screen, and budget for that up front rather than treating it as failure.

Pairs with the **local-transcription** skill (the words) and the **ffmpeg** skill (anything about
encoding). This skill is the decision layer.

## 1. Survey

```bash
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_type,width,height -of default=noprint_wrappers=1 in.mp4
```

**Dead air** — deterministic and free, so do it first:
```bash
ffmpeg -i in.mp4 -af "silencedetect=noise=-32dB:d=2.0" -f null - 2>&1 | grep silence_
```
Bucket the gaps per five minutes. Dense clusters mean setup or waiting. A stretch with *no* silence
is your densest content — protect it.

**Look at the video.** Extract a frame grid and read it yourself:
```bash
python scripts/contact_sheet.py in.mp4 --interval 30 --out sheets/
```
One frame per 30s over 90 minutes is ~180 tiles, about 8 sheets. Read them and you know what's on
screen and roughly when. Zoom in where it matters:
```bash
python scripts/contact_sheet.py in.mp4 --start 4200 --end 4500 --interval 5 --out sheets/
```

Because you chose the timestamps, **they're exact**. This is the main advantage over asking a cloud
video model to describe the recording: those drift on long inputs and truncate silently, so their
times need re-deriving anyway.

**The words** — see `local-transcription`. Last, not first: used to place cuts precisely and to
sweep for names and profanity.

**Detecting state changes at scale.** When you need to know exactly when an app or view is on screen
across the whole runtime, score frames on a cheap pixel signature instead of reading thousands of
tiles. Calibrate on a handful of frames you have already identified, then run it over a dense grid
(one frame per 2s). A blue-tinted UI versus a neutral one separates on mean `B−R` in a sidebar strip;
a full-page view separates from a chrome-heavy one on the variance of a nav column. This is what
catches 2-second flashes that spot-checking never will.

## 2. Decide the cuts

Score each segment for importance and tag why it might go — dead air, fumbling, restarts, repetition
of an earlier point, tangents, housekeeping. Then cut from the scores, not from vibes.

- **Trim silence ≥3s down to ~1.0s, not to zero.** During a demo a long pause usually means
  *something is running on screen*; removing it makes the demo incoherent.
- **Snap boundaries to sentence gaps** using word timings, or you clip syllables.
- Removing a segment can take other things with it — a muted word, a disclosure. Recompute after
  every change.

Expect **15–25%** off a live recording without losing content. Deeper than that means dropping
material, which is the owner's decision, not yours.

## 3. Redact

Define regions as **fractions** of the frame, apply them over time windows.

- Blur the **field**, not the words. Pages scroll; a box sized to today's text won't cover it after
  a scroll. Detect the scrolled state and use a taller band, or blur generously.
- Keep what carries meaning — a channel name, a dashboard's layout, the shape of a report. The goal
  is "you can see what's happening, not who it's about".
- **Audio is separate.** Blurring the picture does nothing for names spoken aloud. Sweep the
  transcript too.

## 4. Build and render

Write the plan as JSON, then:
```bash
python scripts/build_edit.py plan.json --filter filter.txt
```
It emits the filter graph, the output duration, mute spans remapped to output time, the render
command, and the timestamps to verify. It also tells you when a mute has been swallowed by a cut.

Ordering is the part that's easy to get wrong and the script handles it: **blur before `select`**, so
blur `enable` expressions use source time while everything after uses output time.

```bash
ffmpeg -i in.mp4 -/filter_complex filter.txt -map "[vout]" -map "[aout]" \
  -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 128k \
  -map_chapters -1 -movflags +faststart -y EDIT.mp4
```

- Use hardware encoding if present (`h264_qsv`, `h264_nvenc`) — hours become minutes.
- **`-map_chapters -1` always.** Recorders (Zoom especially) embed a chapter track that survives
  `-map` and `-dn`, carries the *original* duration, and makes players report the wrong length.
- Do trims as entries in the cut list, not as a later `-ss` pass. One pass, no metadata surprises.

Mute words afterwards with `-c:v copy` — seconds to run, no quality cost. Verify with `volumedetect`
**strictly inside** the window: a sample straddling the edge reads about −35 dB and looks like a
failure, while inside reads −91 dB.

## 5. Verify

Non-negotiable when anything private was on screen.

```bash
python scripts/contact_sheet.py FINAL.mp4 --times <list from build_edit> --out verify/
```
Three frames per blur window, and one just after each cut join. **Look at the main pane, not just
whether a blur is present** — the common failure is blurring the sidebar while the private content
sits in the middle of the screen.

Then listen across each join, or transcribe a few seconds either side, to confirm nothing clips.

## 6. Deliver

Measured on ~80 minutes of 2560×1600 screen recording:

| Purpose | Settings | Size |
|---|---|---|
| Master | source resolution | ~200 MB |
| Share | 1280×800, 15fps, 32k mono | ~38 MB |
| Phone | 1152×720, 10fps, 24k mono | ~27 MB |

- **Audio is often half the file.** 64 kbps stereo over 80 minutes is ~38 MB; 32 kbps mono is plenty
  for speech and saves more than any resolution change.
- Screen content compresses far better than camera video — most of the frame is static, and 25→15fps
  costs almost nothing.
- **Don't go below 1280×800 if UI text matters.** Check a real demo frame before committing.
- Email attachment limits are commonly 10–25 MB. A long recording will not fit; deliver a link.

## Gotchas
- `-frames:v 1` to a `.jpg` needs `-update 1`, or the image2 muxer refuses to write.
- `-ss` before `-i` with `-c copy` snaps to a keyframe — fine for a rough trim, not for a precise cut.
- Python writes CRLF on Windows; strip `\r` before feeding its output into a shell loop.
- Delete frame grids and working splits when done — they run to thousands of files and gigabytes.
