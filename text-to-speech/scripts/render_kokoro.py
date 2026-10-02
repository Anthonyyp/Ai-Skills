#!/usr/bin/env python3
"""Render a transcript to speech locally with Kokoro-82M. Nothing leaves the machine.

  python render_kokoro.py --input transcript.md --output briefing.mp3
  python render_kokoro.py --input transcript.md --output briefing.mp3 --voice bm_george

Run it with the Python environment that has `kokoro` installed (see SKILL.md, "Setup").

Why a script and not a one-liner:
  - Pacing. The transcript is rendered one paragraph at a time with a deliberate gap between
    paragraphs. Fed one long block, any engine runs ideas together; the gap is what makes a
    briefing sound composed rather than recited.
  - Sanitizing. Markdown headings would be read aloud, dashes produce odd pauses, and curly quotes
    trip some voices.
  - MP3 out. Kokoro produces raw 24 kHz audio; ffmpeg encodes it.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

SAMPLE_RATE = 24000
DEFAULT_VOICE = "am_eric"
LANG_BY_PREFIX = {  # first letter of the voice name -> Kokoro language code
    "a": "a", "b": "b", "e": "e", "f": "f", "h": "h", "i": "i", "j": "j", "p": "p", "z": "z",
}

SETUP_HELP = """Kokoro isn't installed in this Python ({py}).

One-time setup (needs Python 3.10-3.12; uv fetches one if you don't have it):
  uv venv --python 3.12 ~/.venvs/kokoro
  uv pip install --python ~/.venvs/kokoro torch --index-url https://download.pytorch.org/whl/cpu
  uv pip install --python ~/.venvs/kokoro kokoro soundfile "transformers>=4.45" pip

Then run this script with that environment's python (~/.venvs/kokoro/bin/python, or
Scripts\\python.exe on Windows). See SKILL.md for why each step is there."""


def sanitize(text: str) -> str:
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)           # markdown headings
    text = text.replace("—", ", ").replace("–", ", ")  # em/en dashes -> comma pause
    text = text.replace("·", ", ")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text


def split_paragraphs(text: str):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def main():
    ap = argparse.ArgumentParser(description="Render a transcript to speech with Kokoro-82M.")
    ap.add_argument("--input", required=True, help="Transcript (.md/.txt) to narrate")
    ap.add_argument("--output", required=True, help="Output .mp3 (or .wav)")
    ap.add_argument("--voice", default=DEFAULT_VOICE, help=f"Kokoro voice (default {DEFAULT_VOICE})")
    ap.add_argument("--speed", type=float, default=1.0, help="Speaking rate (default 1.0)")
    ap.add_argument("--gap", type=float, default=0.65, help="Seconds of silence between paragraphs")
    args = ap.parse_args()

    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError:
        sys.exit(SETUP_HELP.format(py=sys.executable))

    lang = LANG_BY_PREFIX.get(args.voice[:1])
    if not lang:
        sys.exit(f"Unknown voice '{args.voice}'. Voice names look like am_eric, bf_emma.")

    with open(args.input, encoding="utf-8") as fh:
        paras = split_paragraphs(sanitize(fh.read()))
    if not paras:
        sys.exit("Transcript is empty.")
    print(f"{len(paras)} paragraphs, {sum(len(p) for p in paras)} chars, voice {args.voice}",
          flush=True)

    t0 = time.time()
    # repo_id pinned to the official model; first run downloads ~313 MB from Hugging Face.
    pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    print(f"model ready in {time.time() - t0:.0f}s", flush=True)

    gap = np.zeros(int(args.gap * SAMPLE_RATE), dtype=np.float32)
    chunks, t0 = [], time.time()
    for i, para in enumerate(paras, 1):
        for _, _, audio in pipe(para, voice=args.voice, speed=args.speed):
            chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        if i < len(paras):
            chunks.append(gap)
        print(f"  [{i}/{len(paras)}] done", flush=True)
    audio = np.concatenate(chunks)
    secs = len(audio) / SAMPLE_RATE
    took = time.time() - t0

    out = args.output
    if out.lower().endswith(".wav"):
        sf.write(out, audio, SAMPLE_RATE)
    else:
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            sf.write(wav, audio, SAMPLE_RATE)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", wav,
                            "-c:a", "libmp3lame", "-q:a", "2", out], check=True)
        except FileNotFoundError:
            sys.exit("ffmpeg not found on PATH. Install it, or pass --output with a .wav name.")
        finally:
            os.unlink(wav)

    print(f"DONE  {secs:.1f}s of audio in {took:.1f}s ({secs / took:.1f}x realtime) -> {out}")


if __name__ == "__main__":
    main()
