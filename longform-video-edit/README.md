# Long-Form Video Edit

Cut a long recording — a webinar, training session, all-hands, lecture, screen-share — down to
something people will actually watch, with private information blurred and nothing leaked.

The hard part isn't ffmpeg. It's **deciding** what to remove, **finding** what shouldn't circulate,
and **proving** it's gone. This skill is that decision layer; the mechanics lean on the
[`ffmpeg`](../ffmpeg/) and [`local-transcription`](../local-transcription/) skills.

**No cloud video model required.** The agent reads the video itself, from timestamped contact sheets.

Install: see the [links in the repo README](../README.md#install).

## Requirements

```bash
pip install pillow
```

`ffmpeg` and `ffprobe` on PATH. Hardware encoding (`h264_qsv`, `h264_nvenc`, `h264_amf`) is optional
but turns hours into minutes on a long render — check with `ffmpeg -encoders | grep -E "nvenc|qsv|amf"`.

For the spoken-word half, [`local-transcription`](../local-transcription/) — it supplies the
word-level timings used to place cuts without clipping syllables.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | The workflow — survey, decide, redact, render, verify, deliver |
| `scripts/contact_sheet.py` | Frames → timestamped contact sheets, for surveying and for verifying |
| `scripts/build_edit.py` | Edit plan (JSON) → ffmpeg filter graph, mute remapping, verify list |

## Quick use

```bash
# see what's in it
python scripts/contact_sheet.py in.mp4 --interval 30 --out sheets/

# find the dead air
ffmpeg -i in.mp4 -af "silencedetect=noise=-32dB:d=2.0" -f null - 2>&1 | grep silence_

# plan -> filter graph, render command, and the timestamps to verify
python scripts/build_edit.py plan.json --filter filter.txt

# check the result
python scripts/contact_sheet.py FINAL.mp4 --times 120,240,360 --out verify/
```

## Why contact sheets instead of a video model

A cloud video model can describe a recording, but on long inputs they **truncate silently** and
**compress their timestamps** — content roughly right, times off by minutes. You end up re-deriving
the timings anyway.

Extracting frames yourself inverts that: you choose the moments, so every timestamp is exact by
construction. A 90-minute recording at one frame per 30 seconds is about eight sheets to read. Any
agent with vision can do it, offline, with no API key.

Where you need precision across the whole runtime — *exactly* when an app is on screen — score
frames on a cheap pixel signature rather than reading thousands of tiles. `SKILL.md` covers how to
calibrate one.

## Why `build_edit.py` exists

The filter graph is fiddly in three specific ways, and each is silent when wrong:

**Ordering.** Blur must be applied *before* `select`, so its `enable` expressions run on source
timestamps while everything downstream runs on output timestamps. Get it backwards and blurs land in
the wrong places.

**Remapping.** After cuts, every timestamp moves. Mute spans, verification points, and anything you
noted while surveying all need mapping through the keep-list. Done by hand, this is where errors
come from.

**Removals that overlap.** A muted word inside a cut segment is already gone; a dead-air trim inside
a structural cut is double-counted. The script merges removals and tells you what got swallowed.

It also prints the timestamps to verify, so the check is a paste rather than an exercise.

## Not for

Multi-camera or multi-track editing, colour grading, motion graphics, or anything needing a timeline
UI — use a real NLE.

Frame-accurate compositing beyond rectangular blur regions. If you need to track a moving object,
this isn't it.

Short-form. For a two-minute clip the survey overhead isn't worth it — just cut it.
