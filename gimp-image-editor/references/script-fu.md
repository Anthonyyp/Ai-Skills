# Script-Fu (TinyScheme)

Prefer Python. Use Script-Fu when Python-Fu isn't installed, when you're
adapting an existing `.scm`, or for a genuinely tiny one-liner.

```bash
python scripts/gimp_cli.py scm script.scm
python scripts/gimp_cli.py scm '(gimp-message (car (gimp-version)))'
```

`tests/selftest.scm` is a working, verified example.

## The rule that breaks everyone: every PDB call returns a list

```scheme
(gimp-image-new 320 240 RGB)          ; => (<image>)     a LIST
(car (gimp-image-new 320 240 RGB))    ; => <image>       the value
```

Unchanged from 2.10, and still the number one source of Script-Fu bugs. For
multi-value returns use `cadr`, `caddr`, or destructure:

```scheme
(let* ((info (gimp-image-get-width image))
       (w    (car info)))
  ...)
```

Procedures that return nothing still return `(#t)` or similar — calling `car`
on a genuinely empty return is an error, so check with `gimp_cli.py args`.

## Naming

Python `Gimp.Image.new` ↔ Script-Fu `gimp-image-new`. Hyphens everywhere, no
namespacing. Constants are bare uppercase symbols with hyphens:

```scheme
RGB  RGBA-IMAGE  LAYER-MODE-NORMAL  FILL-BACKGROUND  FILL-FOREGROUND
CHANNEL-OP-REPLACE  RUN-NONINTERACTIVE  TRUE  FALSE
```

## A complete working script

```scheme
(let* ((width 320)
       (height 240)
       (image (car (gimp-image-new width height RGB)))
       (layer (car (gimp-layer-new image "bg" width height
                                   RGBA-IMAGE 100 LAYER-MODE-NORMAL))))
  (gimp-image-insert-layer image layer 0 0)
  (gimp-context-set-background "#204060")
  (gimp-drawable-fill layer FILL-BACKGROUND)
  (gimp-context-set-foreground "#e8a33d")
  (gimp-image-select-ellipse image CHANNEL-OP-REPLACE 60 40 200 160)
  (gimp-drawable-fill layer FILL-FOREGROUND)
  (gimp-selection-none image)
  (file-png-export RUN-NONINTERACTIVE image "C:/tmp/out.png" 0)
  (gimp-image-delete image))
```

Note `file-png-export`, not `file-png-save` — see `migration.md`.

## Strings and paths

Backslash is an escape character in TinyScheme strings, so **use forward
slashes** even on Windows: `"C:/tmp/out.png"`. `"C:\tmp\out.png"` is wrong and
fails in a confusing way.

String helpers are sparse. You get `string-append`, `substring`,
`string-length`, `number->string`, `string->number`. There is no regex, no
`printf`, no path manipulation. This is the main reason to prefer Python.

## Output and debugging

- `(gimp-message "text")` is the print statement. With `-c` it goes to the
  console, prefixed `script-fu.exe-Warning:` — that prefix is normal, not an
  error.
- There are no tracebacks. An error gives one line: `Error: eval: unbound
  variable: foo`. Bisect by adding `gimp-message` calls.
- Loading a file: `-b '(load "C:/path/script.scm")'`. `gimp_cli.py scm` does
  this for you, converting the path.

## Installing reusable scripts

A `.scm` in GIMP's `scripts/` directory is found automatically and can register
menu entries. User scripts directory:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\GIMP\3.2\scripts\` |
| macOS | `~/Library/Application Support/GIMP/3.2/scripts/` |
| Linux | `~/.config/GIMP/3.2/scripts/` |

The version segment tracks the *user config* version (`3.2` on GIMP 3.2), not
the stable `3.0` ABI directory used for system plug-ins
(`lib/gimp/3.0/plug-ins/`). Both appear in documentation; only the system path
is pinned at `3.0`. Confirm with
`gimp_cli.py eval "print(Gimp.directory())"`.

```scheme
(script-fu-register "script-fu-my-thing"
  "My Thing..." "What it does" "Author" "Author" "2026"
  ""                                  ; image types; "" = no image needed
  SF-STRING "Text" "default")
(script-fu-menu-register "script-fu-my-thing" "<Image>/Filters/Custom")
```

For batch use none of this is needed — just `load` the file.

## When Script-Fu is genuinely the right call

- The environment has no Python-Fu (some minimal Linux builds).
- You're maintaining an existing `.scm`.
- A one-line query where writing a file is overkill.

Everything else — string handling, JSON, filesystem walking, error reporting,
arithmetic beyond the trivial — is materially easier in Python.
