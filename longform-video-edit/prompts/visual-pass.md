# Visual pass

The picture, not the words. Run it over contact sheets at one frame per 10–30 s for the whole
runtime, then again at one frame per 2–5 s over every stretch the first pass or the segment map
flagged as a demo. Same windowing as the segment map. If a cloud video model is used instead, feed
it 10-minute slices and re-derive every timestamp from the frames it names — its clock drifts.

Slots: `{audience}` `{start}` `{end}`

---

You are doing a VISUAL pass over a recorded session so an editor knows which moments must survive
for what is on screen, regardless of how interesting the speech is, and which moments must not go
out to {audience}. Cover **{start} to {end}** only. Watch the picture, not the words.

Produce markdown with these sections:

## Demos and screen shares
Every stretch where something is actually done on screen. For each:
- **[H:MM:SS - H:MM:SS]** — the application or interface, and the concrete sequence of actions
  (clicks, typing, files opened, results returned). "Opens a folder picker and selects Downloads",
  not "shows the interface".
- Whether the visual is self-explanatory or depends on what the speaker is saying.

## Moments where the picture carries the meaning
Timestamps where the audio alone would be useless — a result appearing, a diff, a before/after.
These survive even if the speech is slow or hesitant. Say why.

## Slides
Every slide change: timestamp and the slide's title or main content.

## Static or dead screen
Stretches over 30 s where nothing meaningful changes — a stationary slide, an idle desktop, a
frozen share, a spinner. Ranges. These are cut candidates.

## Anything that should not be circulated
CRITICAL. Any timestamp where the screen shows something that must not reach {audience}: real
client or customer names, records, email addresses, personal data, credentials, API keys, tokens,
private file paths, an unrelated application, a notification or message preview. For each:
- **[H:MM:SS - H:MM:SS]** — exactly what is exposed, and **where on screen** (left rail, main
  pane, address bar, a toast in the corner). Where matters: the fix is a blur box.
- Whether the same thing stays on screen for the whole range or scrolls/changes.
If none, write "none observed". Do not invent any.

Rules:
- Timestamps are taken from the frame stamps; never estimate.
- Describe only what is genuinely visible. Never guess at text you cannot read.
- A recurring element (a sidebar with names, a URL bar with a tenant) gets listed once with every
  range it appears in, not once per frame.
