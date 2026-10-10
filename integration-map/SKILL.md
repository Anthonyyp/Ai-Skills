---
name: integration-map
description: Map the surface area of a software integration as it will run in production, on one page. It's a tiered tree of every system the integration touches, what flows between them, how it's run, and what isn't ready for go-live. Each kind of piece has a real count, and every piece is named. Trigger on "integration map", "map the surface area", "everything this integration touches", "what does this integration consist of", "go-live overview of the integration", "inventory of the build" or "tiered map of the integration". Renders a PDF and a PNG from a small JSON spec.
---

# Integration map

One page that answers "what is this integration, all of it?" for whoever approves it, inherits it or
supports it. It's a tree read left to right:

```
the integration ── where it lives ── what kind of piece, and how many ── the pieces
```

It is an overview, not a design document. Someone should be able to look at it for a minute and know
three things: how big the integration is, where every part sits, and what's still missing.

## The shape: three tiers under one root

- **Root:** the integration's name.
- **Tier 1, where the pieces live.** One branch per place, each with a `kind`:

  | Kind | Use it for | Typical tier 2 groups |
  |---|---|---|
  | `system` | Each system the integration lives in: a CRM, a billing platform, a database, a marketing tool | Fields added, fields synced, automations and workflows, functions or code, rules and validations, access, screens |
  | `link` | What moves between the systems, and how records are matched | Each direction of traffic, scheduled syncs, webhooks, shared ids |
  | `ops` | What it takes to run it | Schedules, credentials, monitoring and alerts, logs, the people or teams who own it |
  | `gap` | What isn't ready for go-live | One group, or one per area if there are many |

  Systems are coloured in the order they appear, so put the system of record first. `gap` is always
  last and always drawn dashed.
- **Tier 2, the kinds of piece**, each with a count.
- **Tier 3, the pieces themselves**, in one or two lines per group.

## Map it as it will go live

- **Include what will exist in production:**
  - fields and objects;
  - automations, workflows and functions;
  - code;
  - rules and validations;
  - permissions and integration users;
  - credentials;
  - endpoints and webhooks;
  - schedules;
  - screens;
  - monitoring.
- **Leave out how it was built:**
  - setup scripts;
  - test suites;
  - repositories;
  - demo or seed data;
  - prototype-only sign-ins;
  - sandboxes.

  None of that is running in production. A check that does run in production, such as a monitor or
  a nightly reconcile, goes under `ops`.
- **Where what's built differs from what will go live,** map the production piece and list it under
  `gap` until it exists. A prototype's temporary credential is the usual example.
- **Always include the `gap` branch.** If nothing is missing, say that in it. The gap branch is what
  makes the map a go-live overview rather than an inventory.

## Count, don't estimate

- **Every count comes from the source:**
  - the metadata or config files;
  - the code;
  - the system's own setup screens;
  - the scripts that create things.

  List the pieces first and then count the list. The pieces go in the group's `items`, so a reader
  can check the number.
- **Show combined counts with `+`,** such as `8 + 2` for classes and triggers or `13 + 19` for new
  fields and existing fields written. Say in the items what each number is.
- **Recount just before rendering.** Counts drift as a build changes. On the first map this skill
  made, a recount caught 16 where the real number was 18.
- **A count can be a time**, such as `seconds` or `2am`, for traffic and schedules, where "how often"
  says more than "how many".

## Write the spec

```json
{
  "title": "The integration's surface area",
  "emphasis": "surface area",
  "asof": ["Customer sync: Harbor CRM and Ledgerline Billing", "As it will go live · 14 Mar 2027"],
  "subtitle": "Everything the integration has in production, tier by tier. Dashed: not ready for go-live.",
  "root": "Customer sync",
  "branches": [
    { "name": "Harbor CRM", "note": "The system of record", "kind": "system",
      "groups": [ { "name": "Fields added", "count": "4", "items": "Accounts: `Billing_Customer_ID`, ..." } ] }
  ]
}
```

- **`emphasis`** highlights those words in the title.
- **`asof`** is the line or two at the top right: what the map covers, and its date.
- **Backticks** in any text become code. Use them for API names, so readers can search for them.

`examples/crm-billing-sync.json` is a full example. It's fictional.

**Keep it to one page.** About five branches and 25 groups fit. The renderer shrinks the type to fit,
down to about 65%. Beyond that, make one map per system plus an overview, rather than one unreadable
map.

## Render

```
python scripts/render.py <spec.json> <out.pdf> --png <preview.png>
```

It needs Python 3.8+ and a Chromium-family browser: Chrome, Edge or Chromium, run headless. The script
finds the usual installs. Pass `--browser <path>`, or set `MAP_BROWSER`, if yours is elsewhere. It
always writes the HTML beside the PDF. With no browser available, open the HTML and print it to PDF in
landscape.

## Check it before handing it over

- **Look at the PNG:**
  - it fits one page and nothing is cut off;
  - every group has a count;
  - the connectors reach every box.
- **Check the content:**
  - the `gap` branch is there;
  - no development or test tooling slipped in;
  - names match what each system calls them;
  - the counts were recounted today.

## Keep it current

Keep the spec in the project's documentation and re-render it whenever the build changes, with the new
date in `asof`. A map that's a month stale is worse than none, because it looks authoritative.

## What it isn't

- **Not a flow diagram.** "What sets off what when a record changes" is a different picture: boxes and
  arrows in sequence. Draw that separately if it's needed.
- **Not a field mapping.** Which field goes where, and who owns it at each stage, is a table.
- **Not an architecture diagram of the systems themselves.** Only what the integration adds to them,
  uses in them, or depends on.
