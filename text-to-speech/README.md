# Text to Speech

Turn written content into a natural-sounding MP3 using `edge-tts` — the free Microsoft neural
voices behind Edge's Read Aloud. No API key, no quota, no account.

> **Heads up:** [`edge-tts`](https://github.com/rany2/edge-tts) is a community package, not a
> Microsoft product, and it talks to an **undocumented endpoint**. Cross-platform (Linux/macOS/
> Windows, Python ≥3.7) and free, but Microsoft can change it without notice. If renders start
> failing, run `pip install -U edge-tts` first — that fixes it most of the time. Commercial use is
> a grey area; see the Limits section in `SKILL.md`.

Covers the part that actually determines quality: rewriting the source into a **speakable
transcript** before rendering, rather than feeding a document straight into a synthesizer.

Install: see the [links in the repo README](../README.md#install).

## Requirements

```bash
pip install edge-tts
```

Internet connection required — rendering is a network call to Microsoft's endpoint. `ffprobe`
(from ffmpeg) is optional, for checking output duration.

## Layout

| File | Contents |
|---|---|
| `SKILL.md` | The workflow — writing a speakable transcript, rendering, voices, verification |
| `scripts/render_edge_tts.py` | The renderer: per-paragraph, retrying, text-sanitizing |

## Quick use

```bash
python scripts/render_edge_tts.py --input transcript.md --output briefing.mp3
python scripts/render_edge_tts.py --input transcript.md --output briefing.mp3 --voice en-GB-RyanNeural
edge-tts --list-voices | grep en-US
```

## Why a script instead of the `edge-tts` CLI

One-shot rendering of a long transcript is unreliable: short audio slices get dropped at internal
websocket chunk boundaries, clipping the starts of words and inserting dead silence mid-sentence.
It fails **silently** — exit code 0, plausible-looking MP3.

Rendering one paragraph at a time and concatenating the MP3 bytes keeps each render short enough
that the bug never triggers. The script also retries paragraphs on connection drops and strips
markdown/typography that TTS reads badly (headings, em dashes, curly quotes).

## Not for

Offline or confidential material (audio is synthesized remotely), voice cloning, precise prosody
control, or anything you're shipping commercially. For those, use a local engine (Piper, Coqui) or
a licensed API.
