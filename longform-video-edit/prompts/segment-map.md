# Segment map

Fill the slots, then run this over the transcript **and** the contact sheets (or over the video
itself if a video model is in play). Run it in windows of 20–35 minutes of source, each window
overlapping the previous by two minutes, and stitch — one pass over 90 minutes drifts and truncates.
The transcript carries the real timestamps; if the picture and the transcript disagree about *when*,
the transcript wins.

Slots: `{presenter}` `{audience}` `{subject}` `{objective}` `{start}` `{end}`

---

You are analysing a recorded session so it can be edited down for {audience}. The presenter is
{presenter}; any other voice is an ATTENDEE. The subject is {subject}. The objective of the
recording — the thing a viewer should be able to do or understand afterwards — is: {objective}.

You have the transcript with timestamps and a set of contact sheets (frames stamped with their
source time). Cover **{start} to {end}** only.

Produce a TIMESTAMPED SEGMENT MAP in markdown. Break this window into segments at natural
boundaries — topic change, demo start or end, a question, a tangent. Segments run 30 seconds to
5 minutes. Do not summarise; map.

For EVERY segment give exactly this block:

```
### [H:MM:SS - H:MM:SS] Short segment title
- **Speaker:** PRESENTER | ATTENDEE | BOTH
- **On screen:** slides | live demo (name the application) | face cam | code/terminal | nothing changing
- **What happens:** two or three concrete sentences. Name what is actually shown or done.
- **Teaching point:** the one idea a viewer takes away, or "none" if this is transition, admin or chat.
- **Importance:** 1-5. 5 = essential to the objective; 1 = could vanish and nobody would notice.
- **Cut candidate:** none | dead air | tech fumbling | restart/false start | repeats [H:MM:SS] | tangent | off-topic chat | over-long pause | admin/housekeeping
- **First words:** the literal opening 6-10 words
- **Last words:** the literal closing 6-10 words
```

Rules:
- Timestamps come from the transcript and must run in order with no gaps across the window.
- If nobody speaks, write the segment anyway and mark it dead air. NEVER invent dialogue.
- Be blunt about importance. Every live recording has slack; finding it is the job. Importance is
  measured against the objective above, not against how interesting the moment is in isolation.
- Repetition must name the earlier timestamp that already made the point.
- A segment can be importance 5 and still contain a cut candidate (a tangent inside a demo). Say so.
- End with `## Overall arc` — the major phases of this window with their time ranges.
