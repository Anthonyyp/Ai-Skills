# Ai-Skills

Agent skills for Claude Code. Each top-level folder is one skill.

## Skills

### Image & Video

| Skill | What it does |
|---|---|
| [gimp-image-editor](gimp-image-editor/) | GIMP control via Script-Fu / Python batch CLI — layered compositing, XCF/PSD, text layers, GEGL filters, chroma key, batch export, layer-preserving PDF/EPS. |

<!--
Add new skills as a row above, under the right category heading.
Keep the "what it does" cell to one line.
-->

## Install

Skills must sit **exactly one level** under a `skills/` directory —
`skills/<skill-name>/SKILL.md`. Anything nested deeper is silently ignored, so
copy the skill folder itself, not a category folder.

```bash
# personal — available in every project
mkdir -p ~/.claude/skills
cp -r gimp-image-editor ~/.claude/skills/

# or per-project, committed alongside your code
mkdir -p .claude/skills && cp -r gimp-image-editor .claude/skills/
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force .\gimp-image-editor "$env:USERPROFILE\.claude\skills\"
```

To take everything at once, clone and symlink each skill:

```bash
git clone https://github.com/Anthonyyp/Ai-Skills.git ~/Ai-Skills
mkdir -p ~/.claude/skills
for d in ~/Ai-Skills/*/; do
  [ -f "$d/SKILL.md" ] && ln -sfn "$d" ~/.claude/skills/"$(basename "$d")"
done
```

Start a new session afterwards — skills are picked up at session start.

## Layout

Flat, one folder per skill, because that mirrors the install target exactly and
keeps the repo clone-installable. Categories live as headings in the table
above rather than as directories; the agent routes on each skill's
`description` field and never sees folder names, so nesting would add friction
without buying anything.

```
Ai-Skills/
  README.md
  gimp-image-editor/
    SKILL.md          <- name + description frontmatter; what gets loaded
    references/       <- detail loaded on demand
    scripts/
    examples/
    tests/
```

Each skill's own README covers its requirements and how to verify it.
