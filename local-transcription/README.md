# Local Transcription

Speech-to-text on your own machine using [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
— a CTranslate2 reimplementation of OpenAI's Whisper that's several times faster than the reference
implementation at the same accuracy.

No API key, no quota, no account, no upload. That last point is the reason to use it: confidential
recordings never leave the machine.

Covers the parts that matter beyond "get me the text" — **word-level timings** precise enough to cut
or mute a single word, transcribing **one window** of a long file without re-running the whole thing,
and verifying nothing was silently dropped.

Install: see the [links in the repo README](../README.md#install).

## Requirements

```bash
pip install faster-whisper
```

`ffmpeg` and `ffprobe` on PATH (audio extraction). Model weights download on first use and are
cached — `large-v3` is about 3 GB. A CUDA GPU is optional; the script detects one and falls back to
CPU.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | The workflow — models, word timings, windows, verification, sweeping |
| `scripts/transcribe.py` | The transcriber: extract, transcribe, txt/SRT/word output, coverage check |

## Quick use

```bash
python scripts/transcribe.py recording.mp4
python scripts/transcribe.py recording.mp4 --srt --words
python scripts/transcribe.py long.mp4 --start 3130 --duration 30 --words --model base
python scripts/transcribe.py recording.mp4 --model base --device cuda
```

Writes `<name>.transcript.txt` (`[h:mm:ss - h:mm:ss] text`), plus `.srt` and `.words.tsv` on request.

## Why a script instead of the `faster-whisper` API directly

Three things this handles that a bare `model.transcribe()` call doesn't:

**Absolute timestamps on a window.** `--start 3130 --duration 30` transcribes half a minute out of a
three-hour file and still reports times on the original timeline, so the output drops straight into
a full-length transcript. Doing this by hand is where offset bugs come from — it's easy to
double-count, or to forget that a trimmed clip starts at zero.

**A coverage check.** It flags gaps over two minutes and warns when the transcript ends short of the
media. A missing stretch is invisible downstream: you don't find out until something built on the
transcript is wrong, and by then the cause is several steps back.

**Cleaning up after itself.** Audio extraction produces roughly 115 MB per hour of WAV. The script
deletes it unless you ask otherwise.

## Speed

`large-v3` on CPU runs at roughly **0.6× realtime** — a 90-minute recording takes about 2.5 hours.
Measure on your own hardware before quoting a number, run it in the background, and don't silently
downgrade the model to save time on work someone will depend on. CUDA is dramatically faster.

## Not for

**Speaker labels** — Whisper has no diarisation. Pair it with something that does, or infer from
context and say so.

**Anything about the picture** — it only hears. For screen recordings where what's *shown* matters,
you need a video model as well.

**Verbatim legal or medical transcription** — it's very good, not certified. And like all
Whisper-family models it can hallucinate over long silences, so spot-check stretches where nobody is
speaking.
