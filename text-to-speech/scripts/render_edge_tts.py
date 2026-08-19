"""
Render a transcript to speech with edge-tts (free Microsoft neural voices).

WHY PER-PARAGRAPH RENDERING:
Rendering a long transcript in a single edge-tts Communicate().stream() call is unreliable —
on long texts, short audio slices get dropped right at internal websocket chunk boundaries.
This clips the start of words (e.g. "zero" gets heard as "euro") and inserts dead silence
mid-sentence. Splitting the transcript into paragraphs and rendering each one separately (then
concatenating the raw MP3 bytes) keeps every individual render short enough that the bug never
triggers, while the concatenated output plays back seamlessly.

Also sanitizes the source text before rendering:
  - strips markdown headings (not meant to be read aloud as "hash hash")
  - replaces em/en dashes and middle dots with commas (dashes otherwise produce ugly, unnatural
    pauses in the synthesized speech)
  - straightens curly quotes to plain quotes

Requires: pip install edge-tts

Usage:
  python render_edge_tts.py --input transcript.md --output briefing.mp3 [--voice en-US-AndrewNeural]
"""

import argparse
import asyncio
import re
import sys

import edge_tts

DEFAULT_VOICE = "en-US-AndrewNeural"


def load_and_sanitize(path: str) -> str:
    text = open(path, encoding="utf-8-sig").read()
    text = re.sub(r"(?m)^#+ .*$", "", text)             # headings are not speech
    text = text.replace("—", ", ").replace("–", ", ")   # em/en dashes -> comma pause
    text = text.replace("·", ", ")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_paragraphs(text: str):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    paras = [re.sub(r"\s*\n\s*", " ", p) for p in paras]
    return paras


async def render(paras, out_path: str, voice: str):
    with open(out_path, "wb") as f:
        for i, p in enumerate(paras, 1):
            audio = b""
            for attempt in range(3):
                try:
                    audio = b""
                    async for chunk in edge_tts.Communicate(p, voice).stream():
                        if chunk["type"] == "audio":
                            audio += chunk["data"]
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    print(f"  para {i} retry after: {e}", file=sys.stderr)
                    await asyncio.sleep(2)
            f.write(audio)
            print(f"  para {i}/{len(paras)} ok ({len(audio)//1024} KB)")


def main():
    parser = argparse.ArgumentParser(description="Render a transcript to MP3 via edge-tts, per-paragraph.")
    parser.add_argument("--input", required=True, help="Path to the transcript (.md/.txt) to narrate")
    parser.add_argument("--output", required=True, help="Path to write the output .mp3")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"edge-tts voice name (default: {DEFAULT_VOICE})")
    args = parser.parse_args()

    text = load_and_sanitize(args.input)
    paras = split_paragraphs(text)
    print(f"{len(paras)} paragraphs, {sum(len(p) for p in paras)} chars")

    asyncio.run(render(paras, args.output, args.voice))
    print("done ->", args.output)


if __name__ == "__main__":
    main()
