---
name: text-to-speech
description: Turn written content into a natural-sounding spoken audio file (MP3) with Kokoro-82M, a small open voice model that runs entirely on your own machine — free, offline, Apache 2.0 so commercial use is fine, nothing uploaded. Covers writing a speakable transcript from source material (prose that sounds right read aloud, not markdown read literally), rendering it with natural pacing, and picking a voice. Trigger on "read this aloud", "convert to audio", "make an audio version", "narrate this", "TTS this", "audio briefing", "text to speech", or any request to listen to a document instead of reading it.
---

# Text to Speech

Convert written content into spoken audio with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M),
an 82-million-parameter open voice model. It runs locally on CPU: no API key, no quota, no account,
and nothing leaves the machine, so it's fine for confidential material.

**Requires:** a Python 3.10–3.12 environment with `kokoro` installed (setup below, about a minute),
and `ffmpeg` on PATH for MP3 output. First render downloads the model (~313 MB) once.

## Setup (once per machine)

Kokoro's package caps at **Python 3.12**: it refuses 3.13+, and on those versions pip falls back to
an old release that can't install. So give it its own environment. [uv](https://docs.astral.sh/uv/)
fetches Python 3.12 if you don't have it:

```bash
uv venv --python 3.12 ~/.venvs/kokoro
uv pip install --python ~/.venvs/kokoro torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python ~/.venvs/kokoro kokoro soundfile "transformers>=4.45" pip
```

Why each piece is there:
- **CPU torch first, from PyTorch's own index.** Without it you get the multi-gigabyte GPU build.
- **`transformers>=4.45`.** Unpinned, the resolver backtracks to a 2021 release that needs a Rust
  compiler and fails.
- **`pip` inside the environment.** On first run Kokoro installs a small English language model
  (spaCy `en_core_web_sm`, ~13 MB) and needs pip to do it.

The environment comes to about 950 MB, mostly PyTorch. Run the renderer with **that environment's
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

The name prefix gives language and gender: `a` = US English, `b` = British English; `f` = female,
`m` = male.

| | Voices |
|---|---|
| US male | `am_adam` `am_echo` `am_eric` `am_fenrir` `am_liam` `am_michael` `am_onyx` `am_puck` `am_santa` |
| US female | `af_alloy` `af_aoede` `af_bella` `af_heart` `af_jessica` `af_kore` `af_nicole` `af_nova` `af_river` `af_sarah` `af_sky` |
| UK male | `bm_daniel` `bm_fable` `bm_george` `bm_lewis` |
| UK female | `bf_alice` `bf_emma` `bf_isabella` `bf_lily` |

`af_heart` is the voice the model's authors rate highest. There are also Spanish (`e`), French
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
- **espeak-ng**, which Kokoro can use as a pronunciation fallback, is GPL. Using it as an installed
  tool is fine; it only matters if you bundle it into software you distribute.

## Limits

- **No voice cloning** and no SSML. Pronunciation is fixed in the transcript.
- **English is the strong suit.** The other languages work but are less polished.
- **First run downloads** the model (~313 MB) and a ~13 MB language model, then caches both.
