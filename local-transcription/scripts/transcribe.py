#!/usr/bin/env python3
"""Transcribe audio/video locally with faster-whisper. Nothing leaves the machine.

  python transcribe.py recording.mp4
  python transcribe.py recording.mp4 --srt --words
  python transcribe.py recording.mp4 --start 3130 --duration 30 --words --model base

Accepts anything ffmpeg reads. Extracts to 16 kHz mono WAV, transcribes, writes:
  transcript.txt   [h:mm:ss - h:mm:ss] text
  transcript.srt   --srt
  words.tsv        --words   start<TAB>end<TAB>word

--start/--duration transcribe one window and still report ABSOLUTE times, so a
window's output drops straight into the full-length timeline.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

GAP_WARN = 120.0  # flag silent-looking holes larger than this


def ts(t, sep=".", ms=False):
    h, rem = divmod(float(t), 3600)
    m, s = divmod(rem, 60)
    if ms:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int((s % 1) * 1000):03d}"
    return f"{int(h)}:{int(m):02d}:{int(s):02d}"


def extract(src, wav, start, duration):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(src)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", str(wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffmpeg failed\n{r.stderr[-800:]}")


def pick_device(choice):
    if choice != "auto":
        return (choice, "float16" if choice == "cuda" else "int8")
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return ("cuda", "float16")
    except Exception:
        pass
    return ("cpu", "int8")


def main():
    p = argparse.ArgumentParser(description="Local speech-to-text via faster-whisper.")
    p.add_argument("input")
    p.add_argument("--model", default="large-v3",
                   help="tiny|base|small|medium|large-v3 (default large-v3)")
    p.add_argument("--out", default=None, help="output dir (default: alongside input)")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--language", default=None, help="force a language code, e.g. en")
    p.add_argument("--start", type=float, default=0.0, help="window start in seconds")
    p.add_argument("--duration", type=float, default=None, help="window length in seconds")
    p.add_argument("--words", action="store_true", help="also write word-level timings")
    p.add_argument("--srt", action="store_true", help="also write subtitles")
    p.add_argument("--keep-audio", action="store_true", help="keep the extracted WAV")
    args = p.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"ERROR: input not found: {src}")
    out = Path(args.out).expanduser().resolve() if args.out else src.parent
    out.mkdir(parents=True, exist_ok=True)

    stem = src.stem + (f"-{int(args.start)}s" if args.start or args.duration else "")
    wav = out / f"{stem}.audio.wav"
    off = float(args.start or 0.0)

    print(f"[1/3] extracting audio -> {wav.name}", flush=True)
    extract(src, wav, args.start, args.duration)

    device, compute = pick_device(args.device)
    print(f"[2/3] loading {args.model} on {device}/{compute} "
          f"(first run downloads weights)", flush=True)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("ERROR: pip install faster-whisper")
    t0 = time.time()
    model = WhisperModel(args.model, device=device, compute_type=compute)
    print(f"      ready in {time.time() - t0:.0f}s", flush=True)

    print("[3/3] transcribing...", flush=True)
    t0 = time.time()
    segments, info = model.transcribe(
        str(wav), language=args.language, word_timestamps=args.words)

    txt = out / f"{stem}.transcript.txt"
    srt = out / f"{stem}.srt"
    wtsv = out / f"{stem}.words.tsv"
    rows, words, n, last_end = [], [], 0, off

    fh_srt = open(srt, "w", encoding="utf-8") if args.srt else None
    fh_w = open(wtsv, "w", encoding="utf-8") if args.words else None
    if fh_w:
        fh_w.write("start\tend\tword\n")

    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"# source: {src.name} | model: {args.model} | lang: {info.language} "
                f"(p={info.language_probability:.2f}) | window: {ts(off)}"
                f"{'-' + ts(off + args.duration) if args.duration else ''}\n")
        for seg in segments:
            a, b = seg.start + off, seg.end + off
            text = seg.text.strip()
            f.write(f"[{ts(a)} - {ts(b)}] {text}\n")
            rows.append((a, b))
            if fh_srt:
                n += 1
                fh_srt.write(f"{n}\n{ts(a, ',', True)} --> {ts(b, ',', True)}\n{text}\n\n")
            if fh_w:
                for w in (seg.words or []):
                    fh_w.write(f"{w.start + off:.2f}\t{w.end + off:.2f}\t{w.word.strip()}\n")
                    words.append(w)
            last_end = max(last_end, b)
            if len(rows) % 25 == 0:
                print(f"      ...{ts(b)} ({len(rows)} segments)", flush=True)

    for fh in (fh_srt, fh_w):
        if fh:
            fh.close()
    if not args.keep_audio:
        wav.unlink(missing_ok=True)

    # coverage check - a missing stretch is invisible downstream
    gaps = [(rows[i][1], rows[i + 1][0]) for i in range(len(rows) - 1)
            if rows[i + 1][0] - rows[i][1] > GAP_WARN]
    print(f"\nDONE  {len(rows)} segments in {time.time() - t0:.0f}s -> {txt.name}")
    if args.srt:
        print(f"      {srt.name}")
    if args.words:
        print(f"      {wtsv.name}  ({len(words)} words)")
    if gaps:
        print(f"\n!! {len(gaps)} gap(s) over {int(GAP_WARN)}s - check these are real silence:")
        for a, b in gaps:
            print(f"     {ts(a)} -> {ts(b)}  ({(b - a) / 60:.1f} min)")
    expected = args.duration or (info.duration if not args.start else None)
    if expected and (off + expected) - last_end > GAP_WARN:
        print(f"\n!! transcript ends at {ts(last_end)} but the media runs to "
              f"{ts(off + expected)} - output may be truncated.")


if __name__ == "__main__":
    main()
