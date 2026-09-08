# QC cheat sheet — {output file}

Output **{output_duration}** from a {source_duration} source. Machine QA passed on every line below
(`qa-report.md` has the numbers); this is the eyes-and-ears pass. **All timestamps are in the
edited file.** Scrub to each and check the right-hand column.

`qa_check.py --sheet` writes the skeleton with the timestamps filled in; the agent adds the
"expect to see" column from the plan and its own verify frames.

## 1. Blur — the important ones

| Go to | Expect to see |
|---|---|
| **{h:mm:ss}** | {region} blurred ({where}). Main pane clear. |
| **{h:mm:ss}** | {two regions} blurred; {what stays readable} readable. |

## 2. Mutes — audio drops for ~0.6 s, speech continues either side

| Go to | Word (context) |
|---|---|
| **{h:mm:ss}** | "{word}" — "{the words either side} ___ {…}" |

Left in: {the flagged words the owner allowed}. Say the word and it becomes a mute in seconds — no re-render.

## 3. Joins — listen for a clean sentence boundary, no clipped word, no jump

| Go to | What was removed just before this point |
|---|---|
| **{h:mm:ss}** | {what it was} ({source range} of the original) |

## 4. Speed ramps — should read as a natural fast-forward

| Go to | What it is |
|---|---|
| **{h:mm:ss}–{h:mm:ss}** | {what the screen does} at ×{speed} |

## 5. Quick sanity

- **0:00:00** — opens on {the actual start}, not {what was cut before it}.
- **End** — finishes on {the wrap-up}, before {what was cut after it}.
- Anything that looks wrong: give me the output timestamp and I'll re-cut that region only.
