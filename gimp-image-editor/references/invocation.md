# Invoking GIMP headlessly

`scripts/gimp_cli.py` handles all of this. Read this file when you need to
invoke `gimp-console` directly, debug a hang, or support an unusual install.

## The binary

Use **`gimp-console`**, not `gimp`. The console build has no GUI dependency and
won't try to open a display. Running plain `gimp --no-interface` mostly works
but still links the UI stack and fails on headless servers.

| OS | Typical path |
|---|---|
| Windows | `C:\Program Files\GIMP 3\bin\gimp-console-3.2.exe` (also a `gimp-console-3.exe` alias) |
| macOS | `/Applications/GIMP.app/Contents/MacOS/gimp-console` |
| Linux | `gimp-console-3.0` / `gimp-console` on `PATH` |
| Linux (flatpak) | `flatpak run --command=gimp-console org.gimp.GIMP` |
| GIMP 2.10 | same shape, `gimp-console-2.10` |

`gimp_cli.py` searches these in order and honours a `GIMP_CONSOLE` override.
An override that points at a missing file is a hard error, not a fallback —
otherwise you'd silently run a different GIMP than you asked for.

## The command line that works

```bash
gimp-console-3.2.exe -i -c --quit \
    --batch-interpreter python-fu-eval \
    -b "exec(open(r'C:\path\to\script.py').read())"
```

| Flag | Why it's there |
|---|---|
| `-i` / `--no-interface` | No GUI. |
| `-c` / `--console-messages` | Send messages to the console instead of trying to open a dialog — a dialog in batch mode is a hang. |
| `--quit` | **Quit when the batch commands finish.** Without it, a *failed* `-b` leaves gimp-console sitting at an interactive prompt forever. |
| `--batch-interpreter` | **Mandatory in GIMP 3.** `python-fu-eval` or `plug-in-script-fu-eval`. Omit it and every `-b` aborts with *"No batch interpreter specified"*. GIMP 2.10 defaults to Script-Fu when it's absent. `gimp_cli.py` always passes it and only retries without if the binary rejects the flag — dropping it silently would feed Python source to the Scheme interpreter. |
| `-b` | The batch command. Repeatable; they run in order. |
| `-d` / `--no-data` | Skip brushes, gradients, patterns, palettes. Faster start, but gradient fills and brush ops then fail. |
| `-f` / `--no-fonts` | Skip fonts. Faster start, but **all text operations fail**. |
| `-n` / `--new-instance` | Don't reuse a running GIMP. Worth it in CI where a stale instance would otherwise be adopted. |
| `--verbose` | Startup diagnostics. Useful when a plug-in isn't loading. |
| `--stack-trace-mode never` | Stops a crash from waiting on a debugger prompt. |

## Startup cost (measured, GIMP 3.2.4, Windows, warm)

| Invocation | Time |
|---|---|
| default | ~3.7 s |
| `-d -f` (`--fast`) | ~2.8 s |

The **first** run after installation is dramatically slower — GIMP builds its
font cache, which can take a minute or more. A CI job that seems hung on first
use is usually just doing that. It is a one-time cost per machine/profile.

Because ~3s is charged per *process*, batch work must loop inside a single
script. Launching GIMP per file is the single most common performance mistake.

## Why batch mode hangs, and how to stop it

Three independent hang sources, all of which `gimp_cli.py` closes:

1. **No `--quit`.** On a failed batch command GIMP prints
   `Stopping at failing batch command [0]` and then waits at the Script-Fu
   prompt. In a non-TTY shell (which is what a coding agent has) that is an
   indefinite hang.
2. **A dialog.** Anything that tries to prompt — a missing font substitution, a
   colour-profile conversion query, an overwrite confirmation — blocks. Pass
   `run-mode=NONINTERACTIVE` to *every* PDB call that takes one, and use `-c`.
3. **Cold font cache.** Not really a hang; just slow. Give the first run a
   generous timeout.

Always run under an external timeout anyway. `gimp_cli.py --timeout N` does
this and reports exit code 124 with an explanation.

## Exit codes

GIMP maps batch outcomes to these process exit codes:

| Outcome | Exit |
|---|---|
| success | 0 |
| `GIMP_PDB_CALLING_ERROR` (incl. any uncaught Python exception) | 64 |
| missing/unknown batch interpreter | 69 |
| `GIMP_PDB_EXECUTION_ERROR` | 70 |
| `GIMP_PDB_CANCEL` | 130 |

Two critical caveats:

- **The exit status is only propagated when `--quit` is given.** Without it
  GIMP idles as a daemon forever — on success as well as failure.
- **`sys.exit(n)` from your script does not choose the exit code.** Exiting
  kills the plug-in process, which GIMP reports as a crash
  (`gimp_wire_read(): unexpected EOF`) and maps to 64 regardless of `n`. So
  test `if exitcode != 0`, never `if exitcode == 1`.

**A PDB call that fails does not affect the exit code at all** — it just prints
`GIMP-Error:` and returns a non-SUCCESS status. Only an uncaught Python
exception propagates. That is the single most dangerous thing about GIMP batch
mode in a pipeline: a broken step looks like a successful one.

`gimp_cli.py` fixes this by wrapping the payload in a try/except that prints a
sentinel, and by scanning output for GIMP's own error strings
(`batch command experienced an execution error`, `... a calling error`,
`Stopping at failing batch command`). Either one produces exit code 1.

If you invoke `gimp-console` directly, do the same: wrap your script body and
signal failure yourself.

```python
import sys, traceback
try:
    main()
except BaseException:
    traceback.print_exc()
    sys.stderr.write("FAILED\n")
```

## Paths

GIMP is a **native binary**. On Windows it needs Windows paths. A Git-Bash or
MSYS path like `/c/Users/...` or `/tmp/foo.py` raises `FileNotFoundError`
*inside* GIMP even though the same path works in the calling shell — a
genuinely confusing failure, because the shell can see the file and GIMP can't.

In Script-Fu strings, use forward slashes: `"C:/path/to/file.png"`. Backslash
is an escape character in TinyScheme string literals, so `"C:\path"` is wrong.

## Passing arguments in

`-b` takes one string, and quoting a complex script through a shell is a
reliable way to lose an afternoon. Two robust options:

- **Environment variables.** `gimp_cli.py` JSON-encodes arguments into
  `GIMP_CLI_ARGS` and exposes them to your script as the `ARGS` list. No
  quoting problems, any payload.
- **A file.** Write parameters to JSON, pass the path, read it inside.

Avoid building long `-b` strings with embedded user data.

### `-b -` reads the script from stdin

`python-eval.py` (GIMP's own batch interpreter) does `if code == '-': code =
sys.stdin.read()`. So you can pipe an entire script in and skip Windows
quoting/backslash escaping completely:

```powershell
Get-Content .\build.py |
  & "C:\Program Files\GIMP 3\bin\gimp-console-3.2.exe" `
      -c --quit --batch-interpreter python-fu-eval -b -
if ($LASTEXITCODE -ne 0) { throw "GIMP batch failed ($LASTEXITCODE)" }
```

```bash
cat build.py | gimp-console-3.0 -c --quit --batch-interpreter python-fu-eval -b -
```

Failures still exit non-zero, so this is a fine minimal alternative to
`gimp_cli.py` — you just lose the introspection subcommands and the friendly
error handling.

## Stderr noise that does NOT mean failure

Expect these on healthy runs and don't treat them as errors:

```
GIMP-Warning: Welcome to GIMP 3.2.4!
INFO: a stray image seems to have been left around by a plug-in
EEEEeEeek! 1 GeglBuffers leaked
GEGL-WARNING ... gegl_tile_cache_destroy: runtime check failed
```

The last two indicate images you didn't `delete()`. Harmless for a short
script; worth fixing in a long batch loop since memory does grow.

## Script-Fu vs Python

Both reach the same PDB. Choose Python unless you have a reason not to.

| | Script-Fu | Python |
|---|---|---|
| Availability | Always built in | Bundled on Windows/macOS; a separate package on some Linux distros and absent in some minimal builds |
| Language | TinyScheme — no libraries, awkward strings, everything is a list | Full Python 3 with stdlib |
| Errors | Terse, no traceback | Real tracebacks |
| Best for | Tiny one-liners, environments without Python-Fu | Everything else |

Check what's available: `gimp-console --batch-interpreter` with a bogus value
prints the installed interpreters, and `gimp_cli.py doctor` will fail clearly
if Python-Fu is missing.
