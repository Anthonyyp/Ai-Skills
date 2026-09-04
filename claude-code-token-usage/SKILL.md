---
name: claude-code-token-usage
description: >
  Analyze Claude Code token usage and estimate API costs for a given time period.
  Parses local session JSONL files, breaks down usage per session with per-model
  pricing fetched live from Anthropic's pricing docs. Use this skill when the user
  asks about their token usage, API spend, how much they've used Claude, cost
  breakdown by model, or invokes /claude-code-token-usage.
---

# Token Usage Analyzer

## Purpose
Parse Claude Code session logs to report token consumption and estimated API costs,
broken down by session and by model. Costs are calculated **per turn per model**
using **live pricing fetched from Anthropic's docs** — never hardcoded values.

**This is a Claude Code skill.** It reads the session logs Claude Code writes to
`~/.claude/projects/**/*.jsonl`; with no Claude Code history on the machine there is nothing to
report. It is, however, fully **OS-agnostic** — Windows, macOS and Linux all work, and nothing below
assumes a particular shell.

⚠ **Costs are estimates** derived from logged token counts. Good for a directional read and for
comparing sessions; the provider's own billing is the authority.

---

## Step 1 — Ask These Three Questions

Ask all three before doing any file work:

```
I'll pull your token usage stats. Just need 3 quick answers:

1. **Time span** — how far back should I look?
   - 5 hours
   - 24 hours  ← default
   - 72 hours
   - 1 week
   - 1 month
   (Or type any custom duration, e.g. "2 days", "6 hours", "3 weeks")

2. **Scope** — which projects?
   - Current project only
   - All projects

3. **HTML output** — generate a printable HTML report?
   - Yes
   - No
```

Wait for the user's answers. Default: 24 hours, all projects.

---

## Step 2 — Fetch Current Pricing

**Before running any analysis**, use WebFetch to get current model pricing:

```
URL: https://platform.claude.com/docs/en/about-claude/pricing
Prompt: Extract the complete model pricing table. For every model listed, give me:
model name, input price per MTok, output price per MTok, 5-minute cache write price per MTok,
cache read (hits & refreshes) price per MTok. Return as a simple list, one model per line.
```

Parse the response into a prices dict. The format you're building toward is:

```json
{
  "claude-opus-4-7": {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
  "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}
}
```

**Matching rule**: the script matches model log strings against pricing keys using `startswith`,
so dated variants like `claude-sonnet-4-6-20250929` automatically hit the right tier.

---

## Step 3 — Parse the Time Span

| Answer | Hours |
|--------|-------|
| 5 hours / 5h | 5 |
| 24 hours / 1 day | 24 |
| 72 hours / 3 days | 72 |
| 1 week / 7 days | 168 |
| 1 month / 30 days | 720 |
| "2 days" | 48 |

---

## Step 4 — Run the Analysis Script

Write the pricing you fetched to a JSON file — **anywhere you like**, since you pass the path in.
Use whatever file-writing tool your environment gives you.

Set `pricing_source` to say where the rates actually came from. **It is printed on the report**, so
make it honest: `"live from Anthropic docs, <date>"`, or `"FALLBACK - fetch failed"` if Step 2 didn't
work. The script separately flags any model that fell back to `default_prices`.

```json
{
  "pricing_source": "live from Anthropic docs, <date>",
  "prices": {
    "<model-id>": {"input": 0.00, "output": 0.00, "cache_write": 0.00, "cache_read": 0.00}
  },
  "default_prices": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}
}
```

Then run the bundled script, adding `--html` if the user asked for the HTML report:

```
<python> <skill-dir>/scripts/token_usage.py --hours HOURS --scope SCOPE --config <config-path> [--html]
```

- **`<python>`** — `python3` on macOS/Linux, usually `python` on Windows. **Don't chain them with
  `||`**: that's shell-specific and is a parse error in PowerShell, which is the default shell on the
  one platform where `python3` typically *doesn't* exist. Use whichever works.
- **Quote any path containing spaces** — skill directories often live under a user profile path that has them.

The script prints results to stdout. With `--html` it also prints `HTML written to: <path>`.

---

## Rules & Notes

- **Always fetch live pricing** (Step 2) — pricing changes frequently. Never skip the WebFetch.
- **Per-model pricing is mandatory** — cost each assistant turn by the model that generated it using that model's rates.
- **`startswith` matching** — model strings in logs include dated variants (e.g. `claude-sonnet-4-6-20250929`). Match against base names with `startswith` so all variants hit the right price tier.
- **`<synthetic>` model** — skip for cost and model tracking; it's internal scaffolding with no billable tokens.
- **Session files**: `~/.claude/projects/<project-dir>/<session-id>.jsonl`. Skip anything under `subagents/`.
- **Project name**: read from the `cwd` field in the first user entry that has it (`os.path.basename(cwd)`). Falls back to slug-based extraction if no `cwd` found.
- **Sort sessions by cost descending** — heaviest first.
- **4 decimal places on costs** — small sessions otherwise show $0.00.
- **Show pricing source** in both text and HTML output so the user knows if fallback was used.
- **HTML pricing footer** — render the actual prices dict used as a table so the user can verify what rates were applied.
