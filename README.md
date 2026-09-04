# Ai-Skills

Agent skills for Claude Code. Each top-level folder is one skill.

## Skills

### Image

| Skill | What it does | Requires |
|---|---|---|
| [gimp-image-editor](gimp-image-editor/) | GIMP control via Script-Fu / Python batch CLI — layered compositing, XCF/PSD, text layers, GEGL filters, chroma key, batch export, layer-preserving PDF/EPS. | GIMP 2.10+ (3.x preferred) · Python 3.8+ |

### Audio & Video

| Skill | What it does | Requires |
|---|---|---|
| [ffmpeg](ffmpeg/) | ffmpeg / ffprobe — probing, transcoding, lossless cut+concat, filter_complex pipelines, GIF↔video, subtitle burn-in, loudness normalization, HLS/DASH. | `ffmpeg` + `ffprobe` on PATH |
| [local-transcription](local-transcription/) | Offline speech-to-text via faster-whisper (Whisper models) — timestamped transcripts, SRT, word-level timings for editing, single-window transcription, coverage checks. | Python 3.8+ · `pip install faster-whisper` · `ffmpeg` on PATH |
| [longform-video-edit](longform-video-edit/) | Cut a long recording down for sharing — survey via timestamped contact sheets, dead-air trimming, blur private on-screen data, mute words, render, verify, size for delivery. | Python 3.8+ · `pip install pillow` · `ffmpeg` on PATH |
| [text-to-speech](text-to-speech/) | Written content → natural-sounding MP3 via edge-tts (free Microsoft neural voices, no API key) — speakable-transcript writing, reliable per-paragraph rendering, voice selection. | Python 3.7+ · `pip install edge-tts` |

### Claude Code

| Skill | What it does | Requires |
|---|---|---|
| [local-token-usage-claude-code](local-token-usage-claude-code/) | Report what your Claude Code sessions actually cost — parses the local session logs, breaks usage down per session and per model, prices each turn at the rate of the model that generated it, using pricing fetched live from Anthropic's docs rather than hardcoded. Optional printable HTML report. | Python 3.7+ · Claude Code session logs |

Each skill's own README has the full requirements; the column lists what you must install before
the skill is usable at all. Skills are self-contained — none depends on another.

<!--
Add new skills as a row above, under the right category heading.
Add a new "### Category" section when nothing fits.
Keep the "what it does" cell to one line.
"Requires" = external software the user must install first (binaries, packages, runtimes,
an account/API key). Optional extras don't belong here — put those in the skill's own README.
Write "none" if the skill is pure prompt guidance with no dependencies.
-->

## Install

These follow the [Agent Skills open standard](https://github.com/agentskills/agentskills),
so they work in any tool that supports it. Each tool documents its own install
locations:

| Tool | Docs |
|---|---|
| Claude Code / Claude | [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) |
| OpenAI Codex / ChatGPT | [learn.chatgpt.com/docs/build-skills](https://learn.chatgpt.com/docs/build-skills) |
| Cursor | [cursor.com/docs/skills](https://cursor.com/docs/skills) |
| Gemini CLI | [Agent Skills docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md) |

Short version: drop a skill folder in your agent's skills directory.
`~/.agents/skills/` is the cross-tool location — Codex, Cursor and Gemini CLI
all read it. Claude Code uses `~/.claude/skills/`, which Cursor also reads.

## Layout

Flat, one folder per skill, mirroring the install target so the repo is
clone-installable. Categories are headings in the table above, not directories —
the agent routes on each skill's `description` and never sees folder names.

```
Ai-Skills/
  README.md
  ffmpeg/
    SKILL.md          <- name + description frontmatter; what gets loaded
    recipes.md        <- detail loaded on demand
    reference.md
    troubleshooting.md
  gimp-image-editor/
    SKILL.md
    references/
    scripts/
    examples/
    tests/
```

A skill is just a folder with a `SKILL.md`. The frontmatter `description` is
what the agent matches against, so it carries the trigger wording; everything
else is loaded only when the skill is actually used.

Each skill's own README covers its requirements and how to verify it.
