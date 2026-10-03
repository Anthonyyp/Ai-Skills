---
name: text-to-speech
description: Turn written content into a natural-sounding spoken audio file (MP3) with Kokoro-82M, a small open voice model that runs entirely on your own machine — free, offline, Apache 2.0 so commercial use is fine, nothing uploaded. Covers writing a speakable transcript from source material (prose that sounds right read aloud, not markdown read literally), rendering it with natural pacing, and picking a voice. Trigger on "read this aloud", "convert to audio", "make an audio version", "narrate this", "TTS this", "audio briefing", "text to speech", or any request to listen to a document instead of reading it.
---

# Text to Speech

Convert written content into spoken audio with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M),
an 82-million-parameter open voice model. It runs locally on CPU: no API key, no quota, no account,
and nothing leaves the machine, so it's fine for confidential material.

**Requires:** a Python 3.10–3.12 environment with `kokoro` installed (setup below, about a minute),
and `ffmpeg` on PATH for MP3 output. The first render downloads the model (~313 MB) from Hugging Face
and spaCy's English model (~13 MB, via pip from GitHub). **After that it runs fully offline**: the
renderer detects the cached model and makes no network calls.

**On Linux (`uname -s` → `Linux`), check whether this is Claude Cowork before starting.** If it is,
read `environments/cowork.md` first: four domains must be allowlisted, and PyTorch must never be
installed from PyPI there.

## Setup (once per machine)

Kokoro's package caps at **Python 3.12**: it refuses 3.13+, and on those versions pip falls back to
an old release that can't install. So give it its own environment. [uv](https://docs.astral.sh/uv/)
fetches Python 3.12 if you don't have it:

```bash
uv venv --python 3.12 ~/.venvs/kokoro
uv pip install --python ~/.venvs/kokoro "torch==2.14.1" --index-url https://download.pytorch.org/whl/cpu
uv pip install --python ~/.venvs/kokoro kokoro soundfile "transformers>=4.45" pip
```

Why each piece is there:
- **CPU torch first, from PyTorch's own index, at an exact version.** Without the index you get the
  multi-gigabyte GPU build (on Linux, PyPI only carries that one). The pinned version means a newly
  published release, good or bad, never sneaks in. Verified with Kokoro: 2.14.1. For a fingerprint
  pin as well (`--require-hashes`), see `environments/cowork.md`; hashes differ per OS and Python.
- **`transformers>=4.45`.** Unpinned, the resolver backtracks to a 2021 release that needs a Rust
  compiler and fails.
- **`pip` inside the environment.** On first run Kokoro installs a small English language model
  (spaCy `en_core_web_sm`, ~13 MB) and needs pip to do it.

**No system espeak-ng needed.** Kokoro's pronunciation package bundles its own copy
(`espeakng-loader`, from PyPI). Verified on a machine with none installed.

The environment comes to about 1–1.2 GB (950 MB measured on Windows, 1.2 GB on Linux), mostly PyTorch. Run the renderer with **that environment's
python**: `~/.venvs/kokoro/bin/python` on macOS/Linux, `~\.venvs\kokoro\Scripts\python.exe` on
Windows. Run it with any other Python and it prints these instructions instead of failing obscurely.

## The two-step shape

Good narration is **not** the source document piped into a synthesizer. It's a rewrite, then a
render. Skipping step 1 is the single biggest quality difference.

### 1. Write a speakable transcript

Rewrite the source as spoken-word prose and save it as a separate `.md` or `.txt` file. What changes:

| In writing | Spoken |
|---|---|
| Headings | Either drop them, or turn into a spoken transition ("First, the costs.") |
| Bullet lists | Sentences, or "three things: X, Y, and Z" |
| Tables | Prose — say the comparison out loud instead of reading cells |
| `$6,559.70` | "six thousand five hundred fifty-nine dollars" |
| `~30%`, `KB5121003` | "about thirty percent", "K B five one two one zero zero three" |
| Symbols: `→`, `·`, `&` | "becomes", pause, "and" |
| URLs, file paths, code | Describe them; don't read them character by character |

Also: keep sentences shorter than you would in writing, signpost transitions ("The interesting
part is…"), and **put a blank line between ideas**. Paragraph breaks become pauses (next section),
so they're your main pacing control.

Keep the transcript as a deliverable in its own right. People often want to skim what they just
heard.

### 2. Render

```bash
~/.venvs/kokoro/bin/python scripts/render_kokoro.py --input transcript.md --output briefing.mp3
```

Options: `--voice` (default `am_eric`), `--speed` (default 1.0), `--gap` (seconds between
paragraphs, default 0.65). `--output` ending in `.wav` skips the MP3 encode.

**Use the script rather than a one-liner; pacing is the reason.** It renders one paragraph at a time
and inserts a gap between them. Fed one long block, the voice runs ideas together and sounds
recited. Within a paragraph Kokoro paces sentences well on its own. The script also sanitizes the
text first:

- strips markdown heading markers, so they aren't read as "hash hash" (the heading text itself is
  still spoken)
- replaces em/en dashes and `·` with commas, which otherwise produce odd pauses
- straightens curly quotes

## Voices

Default is **`am_eric`**: clear, natural US male, holds up over several minutes.

### Ask before rendering, unless the voice is already settled

If the user hasn't named a voice, and nothing they've set up (a wrapper skill, an earlier choice in
the same series) already decides it, **ask once before rendering**:

> I'll use **Eric** (a natural US male voice) unless you'd like another. There are 28 English
> voices. Want to hear a four-minute sampler first?

If they want to hear it, give them **`samples/voice-samples.mp3`** (1.25 MB): every English voice
says its number and name, then the same line, in the order of the table below. They answer with a
number or a name, and you pass the matching code to `--voice`. If they just say go, use Eric.
Don't re-ask within a series; the voice stays fixed once chosen.

| # | Code | # | Code | # | Code | # | Code |
|---|---|---|---|---|---|---|---|
| **US female** | | | | | | | |
| 1 | `af_alloy` | 4 | `af_heart` | 7 | `af_nicole` | 10 | `af_sarah` |
| 2 | `af_aoede` | 5 | `af_jessica` | 8 | `af_nova` | 11 | `af_sky` |
| 3 | `af_bella` | 6 | `af_kore` | 9 | `af_river` | | |
| **US male** | | | | | | | |
| 12 | `am_adam` | 14 | **`am_eric`** (default) | 16 | `am_liam` | 18 | `am_onyx` |
| 13 | `am_echo` | 15 | `am_fenrir` | 17 | `am_michael` | 19 | `am_puck` |
| 20 | `am_santa` | | | | | | |
| **British female** | | | | | | | |
| 21 | `bf_alice` | 22 | `bf_emma` | 23 | `bf_isabella` | 24 | `bf_lily` |
| **British male** | | | | | | | |
| 25 | `bm_daniel` | 26 | `bm_fable` | 27 | `bm_george` | 28 | `bm_lewis` |

The code's prefix gives language and gender: `a` = US English, `b` = British English; `f` = female,
`m` = male. `af_heart` (#4) is the voice the model's authors rate highest. There are also Spanish (`e`), French
(`f`), Hindi (`h`), Italian (`i`), Japanese (`j`), Brazilian Portuguese (`p`) and Mandarin (`z`)
voices; the script picks the language from the first letter. The full list and the authors' quality
grades are in `VOICES.md` on the [model page](https://huggingface.co/hexgrad/Kokoro-82M).

Pick one and stay with it across a series. A voice change between episodes of the same thing is
jarring.

## Checking the result

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 out.mp3
```

Roughly 150 words per minute, so ~1,000 words lands near 6–7 minutes. **Always listen to at least
the first 20 seconds before delivering.** Mispronounced proper nouns and acronyms are the usual
defects, and they're fixed in the transcript (spell it phonetically), not in the renderer.

## Speed

CPU only, no GPU needed. Measured at **2–3× realtime** on a 4-core laptop; a 2-core machine is
roughly realtime. A 10-minute briefing renders in a few minutes. Measure once on your hardware
before quoting a time for something long.

## License and provenance

- **Apache 2.0, model and code.** Free for commercial use; keep the license notice if you
  redistribute it. The authors: *"Kokoro has been deployed in numerous projects and commercial
  APIs. We welcome the deployment of the model in real use cases."*
- **Get it only from the official sources:** `hexgrad/Kokoro-82M` on Hugging Face (the script pins
  this) and the `kokoro` package on PyPI. The model page warns that websites with "kokoro" in their
  domain are not affiliated with it.
- **Training data** was public-domain and openly licensed audio, plus some synthetic audio from
  commercial TTS systems. That's a question about how the model was built, not about your use of it.
- **espeak-ng**, which Kokoro bundles (via `espeakng-loader`) as a pronunciation fallback, is GPL.
  Using it is fine; it only matters if you redistribute it inside software you sell.

## Limits

- **No voice cloning** and no SSML. Pronunciation is fixed in the transcript.
- **English is the strong suit.** The other languages work but are less polished.
- **First run needs internet** for the model (~313 MB) and a ~13 MB language model. Both are cached,
  and every later render is offline.
