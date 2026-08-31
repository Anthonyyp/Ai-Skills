---
name: local-transcription
description: Speech-to-text that runs entirely on your own machine using faster-whisper (OpenAI's Whisper models). Produces timestamped transcripts, SRT subtitles, and word-level timings precise enough to cut or mute a single word. Covers transcribing one window of a long recording, verifying nothing was dropped, and sweeping a transcript for names or profanity before it circulates. Trigger on "transcribe", "what was said in", "get me a transcript", "subtitles for", "word timings", "caption this", or any audio/video file whose speech needs reading. Offline and private — nothing is uploaded.
---

# Local transcription

Speech-to-text with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), a CTranslate2
reimplementation of OpenAI's Whisper. Runs offline: no API key, no quota, nothing leaves the
machine. That last part is the reason to reach for it over a cloud model for anything confidential.

**Requires:** `pip install faster-whisper` and `ffmpeg` on PATH. Weights download once (~3 GB for
`large-v3`) and are cached thereafter.

## 1. Transcribe

```bash
python scripts/transcribe.py recording.mp4
python scripts/transcribe.py recording.mp4 --srt --words
```

Accepts anything ffmpeg reads. Writes `<name>.transcript.txt` as `[h:mm:ss - h:mm:ss] text`, plus
`.srt` and `.words.tsv` on request. The extracted WAV is deleted unless you pass `--keep-audio` —
it's roughly 115 MB per hour and easy to forget.

**Model choice.** `large-v3` is the default and the right one when accuracy matters — proper nouns,
technical terms, crosstalk. `base` is ~10× faster and fine for locating a passage you'll re-run
properly. Don't quietly downgrade to save time on work someone will rely on.

**Timing is the thing people get wrong.** On CPU, `large-v3` runs at roughly **0.6× realtime** — a
90-minute recording takes about 2.5 hours. Measure once on your hardware and quote real numbers.
Run it in the background and give an ETA rather than blocking. With CUDA it's far faster; the script
auto-detects and falls back to CPU.

## 2. Word-level timings

`--words` writes `start<TAB>end<TAB>word`. This is what makes editing possible — segment timings are
far too coarse to cut on. With word timings you can mute one word, or splice at a sentence boundary
without clipping a syllable.

Only ask for words when you need them; it costs extra time on long files.

## 3. One window of a long recording

Never re-run a three-hour file to check thirty seconds:

```bash
python scripts/transcribe.py long.mp4 --start 3130 --duration 30 --words --model base
```

`--start` is applied to every timestamp, so output lands on the **original** timeline and drops
straight into a full-length transcript or an edit decision list.

## 4. Check it didn't drop anything

The script flags gaps over 120 s and warns if the transcript ends well short of the media. Both are
worth reading. A hole is invisible downstream — you don't discover it until an edit built on the
transcript cuts something that was never in it.

Whisper is reliable here, but verify anyway when the transcript feeds an automated decision.

## 5. Sweep before it circulates

Once you have text, grep it. Cheap, and it catches things watching never would:

- **Profanity**, before the recording goes to a wider audience
- **Names** — people, clients, companies. What is *spoken* is separate from what is on screen;
  blurring video does nothing for audio
- **Topic location** — find where something is discussed instead of scrubbing a timeline

## When a cloud video model is the better tool

| Need | Use |
|---|---|
| The words, reliably, with timings | **This skill** |
| Word-level precision for editing | **This skill** |
| Anything confidential | **This skill** — it never leaves the machine |
| Who is speaking | A cloud model — Whisper has **no diarisation** |
| What is *on screen* | A cloud video model — Whisper is deaf to picture |
| Structure, topic segmentation, importance | A cloud model |

They're complementary, not competing. A common shape is: cloud model for structure and visuals,
Whisper for the words, then reconcile. Cloud video models can silently truncate long inputs; a local
transcript is a useful control to check them against.

## Gotchas

- **No speaker labels.** If you need them, infer from context and say that you inferred, or pair
  with a model that diarises.
- **Silence invites hallucination** in Whisper-family models — a long musical or silent stretch can
  produce invented lines. Spot-check anywhere nobody is talking.
- **The first run downloads weights.** On a metered or offline machine, fetch them ahead of time.
- **Output is UTF-8 with the platform's line endings.** On Windows, strip `\r` before feeding
  filenames or timestamps into a shell loop.
- A `huggingface_hub` symlink warning on Windows is harmless noise.
