# Text to Speech

Turn written content into a natural-sounding MP3 with
[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), an open voice model that runs entirely
on your own machine. Free, offline, CPU-only, and **Apache 2.0, so commercial use is fine**.

Covers the part that actually determines quality: rewriting the source into a **speakable
transcript** before rendering, and rendering it with natural pacing rather than feeding a document
straight into a synthesizer.

Install: see the [links in the repo README](../README.md#install).

## Requirements

- **Python 3.10–3.12** in its own environment. Kokoro's package refuses 3.13+.
  [uv](https://docs.astral.sh/uv/) will fetch 3.12 for you.
- **`kokoro`, `soundfile`, CPU PyTorch.** The exact three commands, and why each one is needed,
  are in `SKILL.md` under "Setup". About 1–1.2 GB installed. No system espeak-ng needed (bundled).
- **`ffmpeg`** on PATH, for MP3 output. Not needed if you write `.wav`.
- **Internet once**, for the first render's ~313 MB model download. The renderer goes offline automatically after that.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | The workflow: setup, writing a speakable transcript, rendering, voices, licensing |
| `scripts/render_kokoro.py` | The renderer: per-paragraph pacing, text sanitizing, MP3 output |
| `samples/voice-samples.mp3` | 4-minute sampler of all 28 English voices, numbered to match the table in `SKILL.md` (1.25 MB) |

## Quick use

```bash
~/.venvs/kokoro/bin/python scripts/render_kokoro.py --input transcript.md --output briefing.mp3
~/.venvs/kokoro/bin/python scripts/render_kokoro.py --input transcript.md --output briefing.mp3 --voice bm_george
```

Default voice is `am_eric`. 54 voices in total; the 28 English ones are numbered in `SKILL.md`, and
`samples/voice-samples.mp3` lets you hear them all before choosing. The skill asks which voice to
use (offering the sampler) unless one is already chosen.

## Why a script instead of calling Kokoro directly

Pacing. The script renders one paragraph at a time and puts a deliberate gap between paragraphs,
which is what makes narration sound composed instead of recited. It also strips markdown heading
markers, turns dashes into commas, and straightens curly quotes before rendering.

## Not for

Voice cloning, SSML-level prosody control, or real-time streaming. It renders files.
