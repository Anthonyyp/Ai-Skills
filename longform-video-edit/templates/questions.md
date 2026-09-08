# Questions before I render — {title}

Source {source_duration}. The plan below lands at about **{planned_duration}** ({minutes_removed}
min out). Everything I'm confident about is already decided; these are the calls that are yours.
Answer inline — a number, a word, "all yes" — and I'll render, run QA until it passes, and send the
file with a QC sheet.

## 1. Borderline cuts
Segments scored 3/5 — real content, but the recording says it twice or wanders. Default is what's
in **bold**.

| # | Source range | What it is | Saves | Cut / keep |
|---|---|---|---|---|
| 1 | {h:mm:ss}–{h:mm:ss} | {one line, e.g. "AI validation rabbit holes — repeats the 56:31 point"} | {m:ss} | **cut** |
| 2 | … | … | … | **keep** |

## 2. Things on screen that shouldn't circulate
Each one is either blurred (you can see what's happening, not who it's about) or cut. Default in
**bold**; say "cut" if the whole moment should go.

| # | Source range | What shows, where | Blur / cut |
|---|---|---|---|
| 1 | {h:mm:ss}–{h:mm:ss} | {e.g. "client names in the left rail; main pane is the demo"} | **blur rail** |
| 2 | … | {e.g. "a customer's email open full-screen"} | **cut** |

## 3. Words
{n} words flagged in the transcript (profanity, names). Default **mute** each one — the sentence
continues either side. Say "leave" for any that should stay.

- {h:mm:ss} "{word}" — {context}

## 4. Length
{Only if the brief didn't say.} It honestly lands at {planned_duration}. Getting to {target} would
mean dropping {what}, which is your call, not mine. Fine where it lands, or push harder?

## 5. Anything the readings disagreed on
{e.g. "The segment map calls 1:03:53–1:05:51 'transition', the visual pass says a demo is running
in it — I'm keeping it, ramped to 8 s. Shout if you'd rather it went."}

---
*No more questions after this: render → machine QA until clean → file + QC cheat sheet.*
