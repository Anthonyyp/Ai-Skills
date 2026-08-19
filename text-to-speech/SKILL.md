---
name: text-to-speech
description: Turn written content into a natural-sounding spoken audio file (MP3) using edge-tts — free Microsoft neural voices, no API key, no quota. Covers writing a speakable transcript from source material (prose that sounds right read aloud, not markdown read literally), rendering it reliably, and picking a voice. Trigger on "read this aloud", "convert to audio", "make an audio version", "narrate this", "TTS this", "audio briefing", "text to speech", or any request to listen to a document instead of reading it.
---

# Text to Speech

Convert written content into spoken audio using `edge-tts` (Microsoft Edge's online neural voices).
Free, no API key, no quota, no account — it uses the same endpoint Edge's Read Aloud feature does.
Quality is close to paid cloud TTS.

**Requires:** `pip install edge-tts` and an internet connection (rendering is a network call).

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
part is…"), and read it back in your head — anything that makes you stumble will make the
synthesizer stumble.

Keep the transcript as a deliverable in its own right. People often want to skim what they just
heard.

### 2. Render

```bash
python scripts/render_edge_tts.py --input transcript.md --output briefing.mp3
```

Options: `--voice <name>` (default `en-US-AndrewNeural`).

**Do not replace this script with a one-shot `edge-tts --file ... --write-media ...` call.** On long
texts, single-call rendering drops short audio slices at internal websocket chunk boundaries — the
start of words gets clipped (a real example: "zero" came out as "euro") and dead silence appears
mid-sentence. The failure is silent: the command exits 0 and the MP3 looks fine until you listen.

The script avoids it by rendering **one paragraph at a time** and concatenating the MP3 bytes, which
keeps every individual render short enough that the bug never triggers. It also retries each
paragraph up to three times, since the endpoint occasionally drops a connection mid-stream.

It sanitizes the text first, which matters more than it sounds:

- strips markdown headings, so they aren't read as "hash hash"
- replaces em/en dashes and `·` with commas — dashes otherwise produce a long, unnatural pause
- straightens curly quotes, which some voices articulate oddly

## Voices

Default is `en-US-AndrewNeural` — natural, conversational, holds up well over several minutes.

```bash
edge-tts --list-voices                        # all of them (hundreds, many languages)
edge-tts --list-voices | grep en-US           # US English
```

Other solid English options: `en-US-BrianNeural`, `en-US-EmmaNeural`, `en-US-GuyNeural`,
`en-US-AriaNeural`, `en-GB-RyanNeural`, `en-GB-SoniaNeural`.

Pick one and stay with it across a series — a voice change between episodes of the same thing is
jarring.

## Checking the result

```bash
ffprobe -v error -show_entries format=duration,bit_rate -of default=noprint_wrappers=1 out.mp3
```

Roughly 150 words per minute, so ~1,000 words lands near 6–7 minutes. If the duration is wildly
short, a paragraph render probably failed — check the per-paragraph progress the script prints.

**Always listen to at least the first 20 seconds before delivering.** Mispronounced proper nouns and
acronyms are the usual defects, and they're fixed in the transcript (spell it phonetically), not in
the renderer.

## ⚠️ This is an unofficial client — read before depending on it

`edge-tts` is **not a Microsoft product**. It's an independent package
([github.com/rany2/edge-tts](https://github.com/rany2/edge-tts)) that speaks to the same cloud
endpoint Microsoft Edge's "Read Aloud" uses. The *voices* are Microsoft's; the *client* is
community-built and reverse-engineered. There is no published API, no terms of service covering
this use, no SLA, and no support channel.

**If it suddenly stops working** — renders failing, HTTP 403, connection errors, or empty audio —
that is the expected failure mode, not a bug in your setup. In order:

1. **Update the package first:** `pip install -U edge-tts`. When Microsoft changes something, the
   maintainer usually ships a fix quickly, and an outdated client is the most common cause.
2. Check [the issue tracker](https://github.com/rany2/edge-tts/issues) — if the endpoint changed,
   someone will have reported it within hours.
3. If it's genuinely broken, fall back to another engine (a local one such as Piper or Coqui, or a
   paid API). **Don't build anything you can't afford to lose on this without a fallback path.**

**Commercial use is a grey area.** The neural voices are Microsoft's licensed property and this
route isn't a licensed way to reach them. Fine for personal projects, drafts, and internal
listening. If you're shipping generated audio in a product or monetizing it, use a service whose
terms actually cover you.

## Other limits

- **Online only.** Audio is synthesized remotely, so it doesn't work offline — and **anything
  confidential shouldn't go through it.** Use a local engine for sensitive material.
- **No voice cloning, no fine-grained SSML** through this path. If you need a specific licensed
  voice or precise prosody control, this is the wrong tool.
- **Rate limits are undocumented.** Very large batches may start failing; the per-paragraph retry
  in the script absorbs occasional drops, not sustained throttling.
