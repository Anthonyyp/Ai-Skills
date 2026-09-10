---
name: longform-video-edit
description: Cut a long recording (webinar, training session, meeting, screen-share, lecture) into a tight shareable video, end to end — measure the dead air and the on-screen motion, read the content, decide what goes, ask the owner the few questions that are theirs, blur private information on screen, mute words, render, then run machine QA until it passes and deliver with a QC sheet. Trigger on "cut this down", "edit this recording", "make this shorter", "trim the dead air", "blur the client names", "make a shareable version", or being handed a 45+ minute recording that needs to circulate. Reads the video itself from contact sheets — no cloud video model required.
---

# Editing long-form recordings

**Content is measured, not guessed.** The recording has speech (from `silencedetect`) and it has a
screen doing things (from a frame-diff). Everything that is neither is dead air and comes out.
Everything that is either stays — the only judgement calls are *structural* (this whole segment is a
tangent) and *how long a silent demo moment needs on screen*. Those are the two decisions this skill
asks a model to make; the rest is arithmetic in `build_edit.py`, and `qa_check.py` proves the render
matches the plan before a person sees it.

Runs as: **intake → extract → decide → ask once → render → QA until clean → deliver.** The owner is
consulted once, at "ask", and then not again until the file is ready.

Pairs with **local-transcription** (the words) and **ffmpeg** (anything about encoding).

## 1. Intake

Get from the brief, or ask now if missing: **who it's for** (audience), **what a viewer should be
able to do afterwards** (objective), **who the presenter is**, and **whether there's a target
length**. Objective drives every importance score; without it "important" means nothing.

```bash
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_type,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 in.mp4
```

## 2. Extract — three measured signals, two readings

**Signals** (deterministic, minutes):
```bash
python scripts/scan_signals.py in.mp4 --out signals.json
```
Finds every silence ≥ 3 s, then frame-diffs each one at 1 fps to find where the screen was moving.
Output: `silence` (all of them), `motion` (runs inside silence), and **`stretches`** — the silent
spans where the picture was doing something, each with an id `S###`. It prints how many stretches
need a decision and how much dead air will go. Defaults are tuned for screen recordings; a
face-cam-only recording wants `--area 0.05` so a head moving doesn't register as content.

**Words** — `local-transcription` with `--words`, model `large-v3` for a transcript people will
read, `base` if you only need the timings. Cut edges snap to the word gaps in this file.
```bash
python ../local-transcription/scripts/transcribe.py in.mp4 --words
```

**Contact sheets** — one frame per 30 s for the whole runtime, then 1 fps over every stretch:
```bash
python scripts/contact_sheet.py in.mp4 --interval 30 --out sheets/
python scripts/contact_sheet.py in.mp4 --start 4480 --end 4493 --interval 1 --out sheets/S025/
```
You chose the timestamps, so they're exact — the reason to prefer this over asking a video model to
narrate the file (they drift and truncate on long inputs). If a video model *is* available, feed it
10-minute slices and re-derive every time from a frame.

**Two readings**, prompts in `prompts/` with the slots from intake filled in, run in 20–35 minute
windows with 2-minute overlaps, stitched:

| Reading | Prompt | Gives |
|---|---|---|
| Segment map | `prompts/segment-map.md` | segments with importance 1–5, cut taxonomy, first/last words |
| Visual pass | `prompts/visual-pass.md` | demos, picture-carries-meaning moments, static screen, **disclosures with where-on-screen** |

Then the words that shouldn't circulate: `build_edit.py` sweeps the `.words.tsv` for profanity
(`flag_words` in the plan overrides the built-in list; add names to it) and refuses to build while
any hit is neither cut, muted nor listed in `allow`. Each mute is `[word start, word end]` in
**source** seconds, straight from the TSV.

## 3. Decide

**Structural cuts** come from the segment map: importance 1–2 is proposed as a cut, importance 3
is proposed either way with a stated lean, 4–5 stays. *Every* proposed cut goes on the question
sheet (step 4) — what is and isn't worth keeping is the owner's call, so the owner sees the whole
list, not just the borderline ones. Check every cut against the visual pass — a segment can be
scored low for its speech while a demo runs underneath it. Write cuts as `[start, end, why]`.

**Stretches** — run `prompts/stretch-decisions.md` over the list in `signals.json`, with the 1 fps
sheet, the transcript ±20 s and the segment-map entry for each. This is the "five seconds is enough
vs. you need all thirty" inference:
- `keep` — the action is the content; leave it at real speed (anything under ~4 s is a keep).
- `cap N` — speed-ramp to N seconds; every frame still passes, faster. Usually 3–6 s.
- `cut` — spinner, idle cursor, notification; treat as still and trim like dead air.
Most stretches are 1–3 s blips, and for those the call is **transition or action**: a slide wipe,
tab switch or popup closing leaves a different still screen behind — cut it, the jump reads
better; typing, a click that creates something, a response appearing — keep. Decide every one:
unlisted stretches are kept at real speed, and a recording has dozens of transitions. When unsure,
keep — a kept stretch costs seconds, a cut one costs content. Stretches inside a structural cut
are swallowed by it; you don't need to list them. These are the agent's calls, not the owner's —
the owner decides *what* goes (tangents, chit-chat, private material); how long anything stays
on screen is editing, and editing is not a question.

**Redactions.** Each disclosure from the visual pass is either inside a cut or gets a blur window.
Regions are **fractions of the frame** named in `regions`; blur the *field* (the whole rail, the
whole message pane), not the words — pages scroll and a box sized to today's text misses tomorrow's.
Keep what carries meaning: the app's layout, the shape of a report.

A region that comes and goes across the runtime — the client's channel list every time the
presenter tabs to the chat app — is the case spot-checking loses: a 30 s contact sheet misses the
two-second flashes. Scan for it instead, with the times you've already identified as examples:
```bash
python scripts/find_regions.py in.mp4 --region 0.004,0.085,0.192,0.99     --positive 4310,4480,4742 --negative 100,777,2600,4400 --out rail-windows.json
```
It scores the region every 2 s against the examples and prints the matching windows with a
margin; anything flagged close, look at with `contact_sheet.py --times`. If a wrong kind of
screen shows up in the hits (a dark title slide reads like a dark sidebar), add one of those
times as a negative and run again — one pass on a 100-minute file is about three minutes. On the
recording this was built on it reproduced the hand-built blur list to the second.
**List every disclosure in the plan** — `build_edit.py` refuses to build if one is neither cut
nor blurred.

Write the plan — `templates/plan.example.json` is the shape — and dry-run it:
```bash
python scripts/build_edit.py plan.json
```
It derives dead air from the signals, snaps cut edges to word gaps, dies on any conflict (a stretch
marked keep inside a cut, an unknown region, a cap longer than its stretch, an uncovered disclosure),
and prints what it spared, ramped and demoted plus the output length.

## 4. Ask — once

Fill `templates/questions.md` and send it. This is a **proposal to confirm, not a questionnaire**:
you have already found everything and decided a default for each; the owner reads the list and
overrides what they disagree with. What goes on it — the calls that are the owner's, not yours:
every proposed cut (tangents, repeats, chit-chat, the pre-show — with the confident ones grouped
and the borderline ones called out), each disclosure found on screen (blur or cut the moment), each
flagged word, target length if the brief had none, and anything the two readings disagreed on.
Give your default for each so "all yes" is a valid answer. What does *not* go on it: dead-air
trims, stretch decisions, cut-edge placement, blur mechanics — that is editing, and editing is
never a question. Then **no more questions until the file is done.**

## 5. Render

```bash
python scripts/build_edit.py plan.json --render EDIT.mp4
```
Builds a trim/concat graph: every edit point snapped to a frame boundary, video trimmed by frame
index, pieces split at blur-window edges so the crop/blur/overlay chain runs only on the frames
that get blurred, `setpts`/`atempo` for ramps, concat. Test-encodes to find a hardware encoder
that actually works (the `-encoders` list lies — nvenc is listed on boxes with no NVIDIA card),
renders with `-map_chapters -1` and `+faststart`, then applies mutes in a separate `-c:v copy`
pass. Writes `manifest.json`: every piece, removal, join, ramp, blur checkpoint and mute, in
output time, for QA.

Time it: a 100-minute 2560×1600 source cut to 78 minutes took 15 min 40 s on `h264_qsv` (decode
is ~3 min of that, the rest is encode). `libx264 -preset veryfast` is only ~25 % slower on the same box;
the medium preset is the one that takes an hour. Two things that *do* cost a fortune, both
avoided by the graph above: `enable=`-gated blur over the whole source (a full-frame copy per
region per frame, even outside the window — it doubled the render), and edges between frames
(`concat` pads each segment to the longer stream, so the output drifts a frame per join and the
manifest goes stale by the end).

## 6. QA — the agent, until it passes

```bash
python scripts/qa_check.py EDIT.mp4 --manifest manifest.json --sheet QC-CHEAT-SHEET.md
```
Every check is something a person would otherwise scrub for:

| Group | Check |
|---|---|
| container | duration = planned ±1 s · no chapter track · frame size and fps match source · A/V stream lengths agree |
| mute | peak < −70 dB strictly inside each window · audio back within a second after (that the window is on the *right word* is `build_edit.py`'s check, at plan time) |
| blur | in-region detail < 25 % of the source frame's (or below the absolute level where anything is legible, for a source region that is nearly flat itself) at three points per window · **and** > 60 % just outside the window, at the first offset where the source region holds still (blur landed, on the right pane, at the right time) |
| motion | every kept or ramped stretch still shows motion in the output |
| privacy | every listed disclosure sits inside a cut or a matching blur window |
| join | whisper on the source ±4 s: neither edge splits a word · output waveform up to 2 s either side (clipped to the piece) correlates > 0.6 with the source it should be, lag refined to the sample |

Exit 1 on any FAIL. **Loop: read the failure → fix the plan → re-render → re-check.** A mute-only
fix re-runs the copy pass (seconds); a blur or cut fix is a full render. Don't hand a file to a
person until it exits 0. Then look at the verify frames yourself — `contact_sheet.py FINAL.mp4
--times …` with the blur checkpoints from the manifest — and check the *main pane*, not just that a
blur exists somewhere. The classic miss is a blurred sidebar with the private content centre-screen.

## 7. Deliver

Three files plus two documents:
```bash
python scripts/deliver.py EDIT.mp4      # -> EDIT-share.mp4, EDIT-phone.mp4, each verified
```

| Purpose | Settings | ~80 min 2560×1600 |
|---|---|---|
| Master | source resolution, as rendered | ~200 MB |
| Share | 1280×800, 15 fps, 32k mono | ~40–55 MB |
| Phone | 1152×720, 10 fps, 24k mono | ~30–40 MB |

Audio is often half the file: 32 kbps mono is plenty for speech. Don't go below 1280×800 if UI text
matters (`--width` overrides). Attachment limits are 10–25 MB; deliver a link.

- `CUT-LIST.md` (`templates/`) — what came out, what was protected, the one section worth arguing about.
- `QC-CHEAT-SHEET.md` — `qa_check.py --sheet` writes the skeleton in output time; add the "expect to
  see" column. This is the human's pass: every timestamp already passed machine QA.

## Gotchas
- Trim silence to `leave_silence` (0.5–1.0 s), never zero — a beat between sentences is not slack.
- `-ss` before `-i` with `-c copy` snaps to a keyframe; fine for an excerpt, not for a cut.
- Measure mutes with `atrim`, not `-ss`: AAC frames are ~21 ms and a straddling sample reads −14 dB
  and looks like a failed mute. `build_edit.py` pads each mute window by 50 ms for the same reason.
- `-frames:v 1` to a `.jpg` needs `-update 1`.
- A waveform correlation of 0.7 on audio that is actually identical means the lag search is too
  coarse: speech at 16 kHz decorrelates within a few samples. `qa_check.py` refines to the sample.
- Every boundary in the plan is rounded to the frame grid by `build_edit.py`; expect the manifest
  to differ from the plan by up to half a frame.
- Mute times are source seconds. A plan that inherits mutes from an earlier cut of the same
  recording inherits *output* times, and the render mutes two harmless words while the swearing
  stays in — and QA passes, because it measures the windows it was given. `build_edit.py` now
  prints the words under each mute and dies on an uncovered flagged word; read that report.
- Delete frame grids and excerpts when done; they run to gigabytes.

## Roadmap — filler-word removal ("uh"/"um"), not shipped yet

**Goal:** cut "uh"/"um" and dead hesitation as well as Descript does — that's the bar, not "better
than nothing." Investigated 2026-09-09 on a real recording; not in `build_edit.py` yet because the
honest result was real words getting clipped, and shipping that would be worse than not having the
feature. Findings, so the next attempt doesn't re-learn these the hard way:

- **Whisper doesn't transcribe fillers.** `large-v3` decodes straight through "uh"/"um" — they
  don't appear as words, gap or no gap, `--words` or not. A `initial_prompt` seeded with example
  filler-laden sentences (`"Um, so, uh, this is like, uh, a really, um, informal..."`) makes it
  transcribe them with real timestamps — but the same bias causes outright hallucination on a long
  run (14 of 42 hits on one test were the identical phantom phrase repeated at different
  timestamps, all zero-duration — a classic decoder repetition loop). Filter to `end - start > 0.1s`
  before trusting a hit; that alone cleared every hallucination in testing.
- **The harder failure mode: a hesitation with *no gap on either side* is invisible to any
  gap-based method.** Whisper often absorbs the whole thing into one adjacent word's reported
  span — a 1.46 s drawn-out "uhhhh" was found sitting entirely inside the timestamp Whisper gave
  the word "stuff" (reported as 3.08 s long; a real word doesn't take 3 seconds). Caught by
  flagging words whose duration is implausible for their length (`duration > 2.2x` a
  characters-based estimate), then re-probing that word's own audio locally with `silencedetect`
  at a stricter threshold (~`-35dB`) to find the real sound/silence islands inside it.
- **That detector is also what clipped real words.** A word spoken a little slowly, or one with a
  natural internal consonant stop, produces the same acoustic signature as "word + hidden filler" —
  duration and energy alone can't tell them apart. Automating a cut on that signal is a coin flip
  on real speech, confirmed by testing it against actual output audio.
- **Conclusion:** this is the one place in the skill that would need a human actually listening
  before a cut commits, unlike everything else here (which decides on its own and never asks
  *how*). Either build a review step — proposed cuts with enough context to approve/reject by ear
  or by reading the surrounding words — or find a model that flags hesitation with real confidence,
  not a duration heuristic. Don't re-ship the aggressive auto-cut version; it reads as broken
  speech, not tightened speech.
