# Long-Form Video Edit

Cut a long recording — a webinar, training session, all-hands, lecture, screen-share — down to
something people will actually watch, with private information blurred and nothing leaked, and
have the agent prove the render is right before a person looks at it.

The hard part isn't ffmpeg. It's **deciding** what to remove, **finding** what shouldn't circulate,
and **proving** it's gone. This skill is that decision layer; the mechanics lean on the
[`ffmpeg`](../ffmpeg/) and [`local-transcription`](../local-transcription/) skills.

**No cloud video model required.** The agent reads the video itself, from timestamped contact
sheets, and measures the rest.

Install: see the [links in the repo README](../README.md#install).

## Requirements

```bash
pip install pillow numpy faster-whisper
```

`ffmpeg` and `ffprobe` on PATH. A hardware H.264 encoder (`h264_qsv`, `h264_nvenc`, `h264_amf`) is
optional; `build_edit.py` finds one by test-encoding, because the `-encoders` list includes
encoders that can't open on your hardware. Without one it falls back to `libx264`. A 100-minute
2560×1600 source cut to 78 minutes rendered in 15 min 40 s on an Intel laptop's `h264_qsv`, and
`libx264 -preset veryfast` is only about a quarter slower — the graph is built to touch only the
frames it changes, so the encoder is not where the time hides.

`faster-whisper` is used by `qa_check.py` to confirm cut edges land between words, and by
[`local-transcription`](../local-transcription/) for the word timings the cuts snap to.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | The workflow — intake, extract, decide, ask once, render, QA until clean, deliver |
| `scripts/scan_signals.py` | Silence + motion-inside-silence → `signals.json`; the measured content map |
| `scripts/contact_sheet.py` | Frames → timestamped contact sheets, for reading the video and for verifying |
| `scripts/build_edit.py` | Plan + signals → trim/concat filter graph, render, mute pass, `manifest.json` |
| `scripts/qa_check.py` | Rendered file + manifest → PASS/FAIL report and a QC cheat-sheet skeleton |
| `scripts/deliver.py` | QA-passed master → Share and Phone encodes, each verified |
| `prompts/segment-map.md` | Reading 1: segments, importance vs. the objective, cut taxonomy |
| `prompts/visual-pass.md` | Reading 2: demos, moments the picture carries, disclosures with where-on-screen |
| `prompts/stretch-decisions.md` | The inference: how long each silent-but-moving stretch needs |
| `templates/` | `plan.example.json`, `questions.md`, `CUT-LIST.md`, `QC-CHEAT-SHEET.md` |

## Quick use

```bash
# measure: every silence, and whether the screen was moving during it
python scripts/scan_signals.py in.mp4 --out signals.json

# read: frames you chose, so the timestamps are exact
python scripts/contact_sheet.py in.mp4 --interval 30 --out sheets/

# words, for snapping cut edges and for muting
python ../local-transcription/scripts/transcribe.py in.mp4 --words

# plan (see templates/plan.example.json), dry-run, then render
python scripts/build_edit.py plan.json
python scripts/build_edit.py plan.json --render EDIT.mp4

# prove it, until it passes
python scripts/qa_check.py EDIT.mp4 --manifest manifest.json --sheet QC-CHEAT-SHEET.md

# then the small versions
python scripts/deliver.py EDIT.mp4
```

## How it decides

**Content = speech ∪ motion.** `scan_signals.py` finds the silences and frame-diffs each one; a
silent span where the screen was moving is a *stretch*, a silent span where it wasn't is dead air.
Dead air is trimmed automatically. Stretches are content by measurement and are kept by default —
there is no "protect" list to forget an entry in.

The model makes exactly two kinds of call:

1. **Structural** — this segment is a tangent / a restart / a repeat, from the segment map's
   importance scores against the stated objective.
2. **How long** — for each stretch, `keep` it at real speed, `cap` it to N seconds (a speed ramp:
   every frame still passes), or `cut` it because the motion was a spinner. The prompt is
   `prompts/stretch-decisions.md`; when unsure it keeps.

Anything on screen that shouldn't circulate is listed as a *disclosure* and must be inside a cut or
a blur window, or the build refuses. Anything *said* that shouldn't circulate is found by a sweep of
the word timings and must be inside a cut or a mute, or the build refuses — and it prints the words
under every mute, so a window on the wrong word is visible before the render, not after.

The owner is asked once, before the render, about the calls that are theirs — borderline cuts,
blur-or-cut for each disclosure, flagged words, target length — and then not again.

## Why `qa_check.py` exists

A render can be wrong in ways that are invisible in the log and obvious in the file: a blur on the
sidebar while the private content sits centre-screen, a mute that missed by a frame, a join that
clips a syllable, a chapter track that makes the player report the source's length. `qa_check.py`
tests each of those against the manifest — blur by comparing in-region detail with the source frame
(and confirming it's *sharp* just outside the window), mutes by peak level strictly inside, joins by
whisper on the source edges plus waveform correlation across the seam, motion by re-diffing the
output where a stretch was kept. It exits 1 on any failure and the agent loops until it exits 0.
The `--sheet` output is the human's QC pass, in output time, with every line already machine-checked.

## Why contact sheets instead of a video model

A cloud video model can describe a recording, but on long inputs they **truncate silently** and
**compress their timestamps** — content roughly right, times off by minutes. Extracting frames
yourself inverts that: you choose the moments, so every timestamp is exact by construction. A
90-minute recording at one frame per 30 seconds is about eight sheets. Any agent with vision can do
it, offline, with no API key. The prompts in `prompts/` work either way.

## Not for

Multi-camera or multi-track editing, colour grading, motion graphics, or anything needing a timeline
UI — use a real NLE. Tracking a moving object for redaction — regions here are rectangles over time
windows. Short-form: for a two-minute clip the survey overhead isn't worth it, just cut it.
