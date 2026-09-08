# Stretch decisions

This is the inference a human editor does by feel: "five seconds of this is enough" versus "you
have to watch all thirty". `scan_signals.py` has already found every silent stretch where the screen
was moving. Nothing here is about *whether* the stretch is content — it measured as content, so the
default is to keep it. The question is only **how long it needs to be on screen.**

Answer it from three things: what the stretch shows (contact sheet at 1 fps over the stretch), what
was said just before and after it (transcript), and how important the surrounding segment is
(segment map). Run once over the whole list — it is short.

Slots: `{objective}`

---

You are deciding how long each silent-but-moving stretch of a recorded session should run in the
edited version. The objective of the recording is: {objective}.

For each stretch you are given: its id, source time range and length; what changed on screen
(percentage of the frame, peak second); a contact sheet of the stretch at one frame per second;
the transcript for 20 seconds either side; and the segment map entry it falls inside.

Give one line per stretch, in this exact form:

```
S### keep                 — reason
S### cap <seconds>        — reason
S### cut                  — reason
```

- **keep** — leave it exactly as recorded. The action *is* the content: the viewer needs to see
  each step at real speed, or a result appears and needs a beat to be read. Anything under about
  four seconds is nearly always keep; ramping it saves nothing and reads as a glitch.
- **cap N** — the viewer needs to see that it happened and roughly what, but not every second of
  it. The stretch is speed-ramped to last N seconds, so every frame of action still passes — a
  page filling in, a scroll to the bottom, a build running with visible progress. Pick N as the
  time a viewer needs to register what happened: usually 3–6 s. Never cap below 2 s.
- **cut** — the motion is not information: a spinner, a cursor idling, a blinking caret, a
  notification sliding in, the presenter's camera moving with nothing else. The stretch is treated
  as a still screen and trimmed like dead air.

Rules:
- Decide from what the screen shows, not from the length. A 40-second stretch where a report
  streams in line by line is a `cap 6`; a 40-second stretch where the presenter clicks through
  five settings is a `keep`.
- If the transcript resumes with a reference to what just appeared ("so as you can see…"), the
  viewer must have had time to see it: keep, or cap generously.
- If you cannot tell what the motion was from the sheet, say `keep — unclear` rather than guessing.
  Keeping costs seconds; cutting costs content.
- A stretch inside a segment scored importance 1–2 may still be `keep` if the segment survives
  the structural cut; you are not deciding structural cuts here.
