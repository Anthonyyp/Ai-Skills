# GIMP Image Editor

Drive GIMP headlessly from the CLI (Script-Fu + Python batch) — layered
compositing, text layers, GEGL filters, chroma keying, batch conversion,
PSD/PDF/EPS output, and splitting layers back out of a page file.

Install: see the [links in the repo README](../README.md#install).

## Requirements

- **GIMP 2.10 or 3.x** with the console binary. GIMP 3 is strongly preferred;
  the skill documents both but the helpers target 3.x.
- **Python 3.8+ on the host** (for `scripts/gimp_cli.py`).
- **Python-Fu inside GIMP.** Bundled on Windows and macOS. On some Linux
  distributions it is a separate package (`gimp-python`). `doctor` will tell
  you if it's missing and fall back guidance points at Script-Fu.

Verify the install:

```bash
python ~/.claude/skills/gimp-image-editor/scripts/gimp_cli.py doctor
```

Expected: the GIMP path, version, both batch interpreters, and format counts.

If GIMP isn't found, set `GIMP_CONSOLE`:

```bash
export GIMP_CONSOLE=/Applications/GIMP.app/Contents/MacOS/gimp-console   # macOS
```
```powershell
$env:GIMP_CONSOLE = "C:\Program Files\GIMP 3\bin\gimp-console-3.2.exe"   # Windows
```

## Check it works on your machine

```bash
python3 scripts/gimp_cli.py run tests/selftest.py       # 25 checks of the helper API
python3 scripts/gimp_cli.py run tests/test_recipes.py   # 17 cookbook recipes
python3 scripts/gimp_cli.py scm tests/selftest.scm      # Script-Fu path
```

(The docs write `python` throughout; on macOS and most Linux distros that's
`python3`. Either is fine as long as it's Python 3.8+.)

All three should end with `0 failed` and exit 0. They write scratch files into
`tests/_selftest_out/` and `tests/_recipes_out/`.

These are also the fastest way to find out what a **new GIMP version** broke:
the failures name the procedure.

## Layout

```
gimp-image-editor/
  SKILL.md                  what Claude loads
  scripts/
    gimp_cli.py             runner + PDB/GEGL introspection (host python)
    gimp_helpers.py         helper library (runs inside GIMP)
  references/
    invocation.md           flags, per-OS paths, hangs, exit codes
    python-api.md           GIMP 3 GI API patterns
    script-fu.md            Scheme path
    recipes.md              task cookbook (generated from passing tests)
    migration.md            2.10 -> 3.x renames, verified against a live PDB
    formats.md              import/export formats and options
  examples/
    batch_convert.py        folder convert/resize in ONE gimp process
    chroma_key.py           solid background -> transparent PNG
  tests/
    selftest.py, test_recipes.py, selftest.scm
```

## Notes

`gimp_cli.py` exists because raw `gimp-console` is hostile to automation: it
needs `--batch-interpreter` (GIMP 3) and `--quit` or it hangs at an interactive
prompt, and **a failed script still exits 0**. The wrapper supplies the flags
and converts failures into a real non-zero exit code.

The `pdb` / `args` / `gegl` / `geglargs` subcommands let Claude look up the
exact API on *your* installed version rather than relying on recalled
documentation — which matters because GIMP 2.10 → 3.0 renamed a large fraction
of the API, and most examples online are still 2.10.

## Provenance / what's actually been verified

Everything here was developed against **GIMP 3.2.4 on Windows 11**, and every
recipe in `references/recipes.md` is extracted from a test that passes there.

Written carefully but **not verified on real hardware**: macOS and Linux binary
detection, the flatpak invocation, and the GIMP 2.10 fallback path. If you're
the first to run it on one of those, `doctor` plus the three test suites will
tell you in about a minute — and failures name the procedure that broke, so
they're straightforward to report or patch.

MIT-ish: do what you like with it.
