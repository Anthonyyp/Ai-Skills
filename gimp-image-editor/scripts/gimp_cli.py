#!/usr/bin/env python3
"""gimp_cli.py - run and introspect a local GIMP install headlessly.

Runs on the HOST python (any 3.8+). It locates gimp-console, drives it in
batch mode, and turns GIMP's famously quiet batch failures into real non-zero
exit codes.

    python gimp_cli.py doctor                 # what GIMP is installed, where
    python gimp_cli.py pdb text               # PDB procedures matching "text"
    python gimp_cli.py args file-png-export   # that procedure's parameters
    python gimp_cli.py gegl blur              # GEGL operations matching "blur"
    python gimp_cli.py geglargs gegl:unsharp-mask
    python gimp_cli.py run myscript.py --  a b c
    python gimp_cli.py eval "print(Gimp.version())"
    python gimp_cli.py scm myscript.scm

Why this exists rather than calling gimp-console directly:
  * GIMP 3 aborts every -b without --batch-interpreter, and hangs on error
    without --quit. Easy to forget; this never forgets.
  * A failing batch script still exits 0. This wraps user code and converts a
    traceback into exit code 1, so pipelines actually stop.
  * The PDB/GEGL introspection subcommands mean you can look up the real
    signature on THIS machine instead of guessing at an API that changed
    between 2.10 and 3.x.
"""

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

FAIL_MARKER = "__GIMP_CLI_FAIL__"

# Emitted by GIMP itself when a -b command blows up. Script-Fu has no clean
# way to signal failure back to us, so we watch for these too.
GIMP_ERROR_STRINGS = (
    "batch command experienced an execution error",
    "batch command experienced a calling error",
    "Stopping at failing batch command",
)


# --------------------------------------------------------------------------
# locating gimp-console
# --------------------------------------------------------------------------

def candidate_binaries():
    """Yield plausible gimp-console paths, best/newest first."""
    system = platform.system()

    if system == "Windows":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            if not root:
                continue
            pattern = os.path.join(root, "GIMP *", "bin", "gimp-console-*.exe")
            for path in sorted(glob.glob(pattern), reverse=True):
                yield path
    elif system == "Darwin":
        pattern = "/Applications/GIMP*.app/Contents/MacOS/gimp-console*"
        for path in sorted(glob.glob(pattern), reverse=True):
            yield path
        for path in sorted(glob.glob(os.path.expanduser(
                "~/Applications/GIMP*.app/Contents/MacOS/gimp-console*")), reverse=True):
            yield path

    # PATH works on every platform; newest names first.
    for name in ("gimp-console-3.2", "gimp-console-3.0", "gimp-console-3",
                 "gimp-console", "gimp-console-2.10"):
        found = shutil.which(name)
        if found:
            yield found

    # Flatpak is common on Linux and has no plain binary on PATH.
    if system == "Linux" and shutil.which("flatpak"):
        yield "flatpak:org.gimp.GIMP"


def find_binary():
    # An explicit GIMP_CONSOLE is a hard assertion, not a hint: if it's wrong,
    # say so rather than quietly running some other GIMP the user didn't pick.
    env = (os.environ.get("GIMP_CONSOLE") or "").strip()
    if env:
        if env.startswith("flatpak:") or os.path.isfile(env):
            return env
        raise SystemExit(
            "GIMP_CONSOLE is set to %r but that file does not exist.\n"
            "Fix or unset it to fall back to auto-detection." % env)

    for path in candidate_binaries():
        if path.startswith("flatpak:"):
            return path
        if os.path.isfile(path):
            return path
    raise SystemExit(
        "Could not find gimp-console.\n"
        "Install GIMP, or set GIMP_CONSOLE to the gimp-console binary, e.g.\n"
        r"  Windows: set GIMP_CONSOLE=C:\Program Files\GIMP 3\bin\gimp-console-3.2.exe"
        "\n  macOS:   export GIMP_CONSOLE=/Applications/GIMP.app/Contents/MacOS/gimp-console"
        "\n  Linux:   export GIMP_CONSOLE=$(which gimp-console-3.0)")


def base_command(binary):
    if binary.startswith("flatpak:"):
        return ["flatpak", "run", "--command=gimp-console", binary.split(":", 1)[1]]
    return [binary]


def available_interpreters(binary):
    """Which batch interpreters this build has.

    Asking for a deliberately invalid one makes GIMP list the valid ones. This
    is the only way to detect a missing Python-Fu *before* trying to use it -
    which matters on Linux builds where python-fu is a separate package.
    """
    argv = base_command(binary) + [
        "-i", "-c", "--quit", "--batch-interpreter", "gimp-cli-probe",
        "-b", "(gimp-version)"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    except Exception:
        return []
    found = []
    for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
        line = line.strip()
        if line.startswith("- ") and "(" in line:
            found.append(line[2:].split("(")[0].strip())
    return found


_MAJOR_CACHE = {}


def gimp_major(binary):
    """2 or 3. Determines which batch flags are legal.

    Cached: this costs a whole extra process launch, and invoke() would
    otherwise pay it on every call.
    """
    if binary in _MAJOR_CACHE:
        return _MAJOR_CACHE[binary]
    major = 3          # sane default: unknown builds are far likelier to be 3.x
    try:
        out = subprocess.run(base_command(binary) + ["--version"],
                             capture_output=True, text=True, timeout=120).stdout
        for token in out.split():
            if token[:1].isdigit():
                major = int(token.split(".")[0])
                break
    except Exception:
        pass
    _MAJOR_CACHE[binary] = major
    return major


# --------------------------------------------------------------------------
# running things
# --------------------------------------------------------------------------

# Lines GIMP always prints that carry no information for the caller.
NOISE = (
    "GIMP-Warning: Welcome to GIMP",
    "batch command executed successfully",
    "Welcome to GIMP",
    FAIL_MARKER,          # internal sentinel; the traceback says it better
)


def quiet(text):
    """Drop GIMP's unconditional banner chatter, keep everything else."""
    kept = [ln for ln in text.splitlines()
            if not any(n in ln for n in NOISE)]
    while kept and not kept[0].strip():
        kept.pop(0)
    return "\n".join(kept) + ("\n" if kept else "")


def invoke(binary, interpreter, command, timeout, extra_env=None, fast=False):
    def build(with_interpreter):
        argv = base_command(binary) + ["-i", "-c", "--quit"]
        if fast:
            # Skips loading brushes/gradients/patterns/fonts. Big startup win,
            # but it breaks anything that needs them - text needs fonts,
            # gradient fills need gradients. Opt-in only.
            argv += ["-d", "-f"]
        if with_interpreter:
            argv += ["--batch-interpreter", interpreter]
        return argv + ["-b", command]

    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)

    # --batch-interpreter is mandatory in GIMP 3. Older builds may not know the
    # flag at all, and we can't test every one - so try with it, and retry
    # without only if the binary rejects the flag itself. Silently dropping it
    # would send Python source to the Script-Fu interpreter, which fails in a
    # deeply confusing way.
    argv = build(True)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, env=env)
        combined = (proc.stdout or "") + (proc.stderr or "")
        if "Unknown option --batch-interpreter" in combined:
            if interpreter != "plug-in-script-fu-eval":
                raise SystemExit(
                    "This GIMP does not support --batch-interpreter, so it "
                    "cannot run Python batch scripts.\nUse Script-Fu "
                    "(`gimp_cli.py scm ...`) or install GIMP 3.")
            proc = subprocess.run(build(False), capture_output=True, text=True,
                                  timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "\ngimp_cli: TIMED OUT after %ss.\n"
            "GIMP batch mode hangs when a command fails and --quit is absent, "
            "and on a cold first run it can spend a while building its font "
            "cache. Retry, or raise --timeout.\n" % timeout)
        return 124

    out = (proc.stdout or "") + (proc.stderr or "")
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(quiet(proc.stderr or ""))

    if FAIL_MARKER in out:
        sys.stderr.write("\ngimp_cli: the script failed (details above).\n")
        return 1
    if any(s in out for s in GIMP_ERROR_STRINGS):
        sys.stderr.write("\ngimp_cli: GIMP reported a batch command error.\n")
        return 1
    return proc.returncode


def run_python(binary, code=None, script=None, script_args=None,
               timeout=600, fast=False):
    """Run python inside GIMP, reporting failures as a non-zero exit code."""
    tmpdir = tempfile.mkdtemp(prefix="gimpcli-")
    payload = os.path.join(tmpdir, "payload.py")
    boot = os.path.join(tmpdir, "boot.py")

    if script:
        if not os.path.isfile(script):
            raise SystemExit("no such script: %s" % os.path.abspath(script))
        with open(script, "r", encoding="utf-8") as fh:
            body = fh.read()
        origin = os.path.abspath(script)
    else:
        body = code
        origin = "<eval>"

    with open(payload, "w", encoding="utf-8") as fh:
        fh.write(body)

    # Preamble gives every script Gimp/Gegl/Gio without boilerplate, and the
    # try/except is what makes failure visible to the caller.
    # Scripts can `import gimp_helpers` (shipped beside this file) and can
    # import modules sitting next to themselves.
    path_seed = [os.path.dirname(os.path.abspath(__file__))]
    if script:
        path_seed.append(os.path.dirname(os.path.abspath(script)))

    with open(boot, "w", encoding="utf-8") as fh:
        fh.write(
            "import os, sys, json, traceback, html\n"
            "sys.path[0:0] = %r\n" % (path_seed,) +
            "import gi\n"
            "gi.require_version('Gimp', '3.0')\n"
            "gi.require_version('Gegl', '0.4')\n"
            "from gi.repository import Gimp, Gegl, Gio, GLib\n"
            "Gegl.init(None)\n"
            "ARGS = json.loads(os.environ.get('GIMP_CLI_ARGS', '[]'))\n"
            "g = dict(globals())\n"
            "g['__name__'] = '__main__'\n"
            "g['__file__'] = %r\n"
            "try:\n"
            "    exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), g)\n"
            # A deliberate SystemExit is a *message*, not a crash - print it
            # plainly instead of burying it in a traceback.
            "except SystemExit as e:\n"
            "    if e.code:\n"
            "        sys.stderr.write('%s\\n')\n"
            "        sys.stderr.write('%%s\\n' %% (e.code,) if not isinstance(e.code, int)\n"
            "                         else 'script exited with code %%s\\n' %% e.code)\n"
            "except BaseException:\n"
            "    sys.stderr.write('%s\\n')\n"
            "    traceback.print_exc()\n"
            % (origin, payload, origin, FAIL_MARKER, FAIL_MARKER))

    command = "exec(open(r'%s').read())" % boot
    env = {"GIMP_CLI_ARGS": json.dumps(script_args or [])}
    return invoke(binary, "python-fu-eval", command, timeout, env, fast)


def run_scm(binary, path_or_code, timeout=600, fast=False):
    if os.path.isfile(path_or_code):
        # Forward slashes: TinyScheme strings treat backslash as an escape.
        safe = os.path.abspath(path_or_code).replace("\\", "/")
        command = '(load "%s")' % safe
    else:
        command = path_or_code
    return invoke(binary, "plug-in-script-fu-eval", command, timeout, None, fast)


# --------------------------------------------------------------------------
# introspection - the payloads below run *inside* GIMP
# --------------------------------------------------------------------------

PDB_LIST = r'''
pdb = Gimp.get_pdb()
pattern = ARGS[0].lower() if ARGS else ""
names = sorted(pdb.query_procedures("", "", "", "", "", "", "", ""))
hits = [n for n in names if pattern in n.lower()]
print("%d of %d procedures match %r\n" % (len(hits), len(names), pattern or "*"))
for n in hits:
    proc = pdb.lookup_procedure(n)
    blurb = ""
    try:
        blurb = (proc.get_blurb() or "").strip().replace("\n", " ")
    except Exception:
        pass
    print("  %-44s %s" % (n, blurb[:96]))
'''

PDB_ARGS = r'''
name = ARGS[0]
proc = Gimp.get_pdb().lookup_procedure(name)
if proc is None:
    raise SystemExit("no such procedure: %s" % name)
print("=== %s" % name)
for getter in ("get_blurb", "get_help"):
    try:
        text = getattr(proc, getter)()
        if text:
            print("%s" % text.strip())
    except Exception:
        pass
print("\nparameters (pass these as keyword args, '-' not '_'):")
cfg = proc.create_config()
for spec in cfg.list_properties():
    if spec.name == "procedure":
        continue
    line = "  %-26s %-22s" % (spec.name, spec.value_type.name)
    try:
        default = spec.default_value
        if default is not None and not hasattr(default, "__gtype__"):
            line += " default=%r" % (default,)
    except Exception:
        pass
    try:
        enum_cls = spec.value_type.pytype
        if enum_cls is not None and hasattr(enum_cls, "__enum_values__"):
            line += "  values=%s" % [v.value_nick for v in
                                     enum_cls.__enum_values__.values()]
    except Exception:
        pass
    print(line)
    if spec.blurb:
        print("      %s" % html.unescape(spec.blurb).strip().replace("\n", " ")[:110])
'''

GEGL_LIST = r'''
pattern = ARGS[0].lower() if ARGS else ""
gegl_ops = set(Gegl.list_operations())
try:
    filter_ops = set(Gimp.DrawableFilter.operation_get_available())
except Exception:
    filter_ops = set()
# GIMP registers ~51 gimp:* ops in its core process that a plug-in's GEGL
# cannot enumerate. They ARE usable as drawable filters, so show both sets.
ops = sorted(gegl_ops | filter_ops)
hits = [o for o in ops if pattern in o.lower()]
print("%d of %d operations match %r" % (len(hits), len(ops), pattern or "*"))
print("[F] = usable as a drawable filter\n")
for o in hits:
    print("  %s %s" % ("[F]" if o in filter_ops else "   ", o))
if any(o.startswith("gimp:") for o in hits):
    print("\nNote: gimp:* ops mirror the GIMP UI (and honour the selection by")
    print("default). The gegl:* op of the same name often behaves differently.")
'''

GEGL_ARGS = r'''
op = ARGS[0]
try:
    known = set(Gegl.list_operations()) | set(Gimp.DrawableFilter.operation_get_available())
except Exception:
    known = set(Gegl.list_operations())
if op not in known:
    raise SystemExit("no such operation: %s  (try: gimp_cli.py gegl <pattern>)" % op)
print("=== %s" % op)
for key in ("title", "description"):
    try:
        val = Gegl.Operation.get_key(op, key)
        if val:
            print("%s: %s" % (key, val))
    except Exception:
        pass
print("\nproperties:")
props = Gegl.Operation.list_properties(op) or []
if not props:
    # gimp:* ops live in GIMP's core process, so GEGL can't introspect them.
    try:
        raw = Gimp.DrawableFilter.operation_get_pspecs(op)
        # returns a GimpValueArray, not a python list
        if hasattr(raw, "length"):
            props = [raw.index(i) for i in range(raw.length())]
        else:
            props = list(raw or [])
    except Exception as exc:
        print("  (could not introspect: %s)" % exc)
        props = []
if not props:
    print("  (none - check the exact op name, e.g. gegl:dropshadow not gegl:drop-shadow)")
for p in props:
    line = "  %-24s %-20s" % (p.name, p.value_type.name)
    try:
        if p.default_value is not None and not hasattr(p.default_value, "__gtype__"):
            line += " default=%r" % (p.default_value,)
    except Exception:
        pass
    print(line)
    if p.blurb:
        print("      %s" % html.unescape(p.blurb).strip().replace("\n", " ")[:110])
'''

DOCTOR = r'''
print("GIMP version      : %s" % Gimp.version())
print("PDB procedures    : %d" % len(Gimp.get_pdb().query_procedures(
    "", "", "", "", "", "", "", "")))
print("GEGL operations   : %d" % len(Gegl.list_operations()))
names = Gimp.get_pdb().query_procedures("", "", "", "", "", "", "", "")
imp = sorted(n for n in names if n.startswith("file-") and n.endswith("-load"))
exp = sorted(n for n in names if n.startswith("file-") and n.endswith("-export"))
print("import formats    : %d" % len(imp))
print("export formats    : %d" % len(exp))
print("\nexport procedures:")
for n in exp:
    print("   %s" % n)
'''


def main():
    parser = argparse.ArgumentParser(
        prog="gimp_cli.py",
        description="Run and introspect a local GIMP install headlessly.")
    parser.add_argument("--timeout", type=int, default=600,
                        help="seconds before giving up (default 600)")
    parser.add_argument("--fast", action="store_true",
                        help="add -d -f (skip data+fonts). Faster startup, but "
                             "breaks text, gradients, brushes and patterns.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="report the detected GIMP and its capabilities")

    p = sub.add_parser("pdb", help="list PDB procedures matching a pattern")
    p.add_argument("pattern", nargs="?", default="")

    p = sub.add_parser("args", help="show a PDB procedure's parameters")
    p.add_argument("procedure")

    p = sub.add_parser("gegl", help="list GEGL operations matching a pattern")
    p.add_argument("pattern", nargs="?", default="")

    p = sub.add_parser("geglargs", help="show a GEGL operation's properties")
    p.add_argument("operation")

    p = sub.add_parser("run", help="run a python script inside GIMP")
    p.add_argument("script")
    p.add_argument("args", nargs=argparse.REMAINDER,
                   help="passed to the script as the ARGS list")

    p = sub.add_parser("eval", help="run a python snippet inside GIMP")
    p.add_argument("code")

    p = sub.add_parser("scm", help="run a Script-Fu file or expression")
    p.add_argument("target")

    opts = parser.parse_args()
    binary = find_binary()

    if opts.cmd == "doctor":
        print("gimp-console      : %s" % binary)
        print("host python       : %s" % sys.version.split()[0])
        interps = available_interpreters(binary)
        print("batch interpreters: %s" % (", ".join(interps) or "(could not detect)"))
        if interps and not any("python" in i for i in interps):
            print("\nWARNING: this GIMP has no Python-Fu, so `run`/`eval` will not work.")
            print("         Install it (Debian/Ubuntu: gimp-python) or use `scm`.")
            return 1
        return run_python(binary, code=DOCTOR, timeout=opts.timeout)

    simple = {
        "pdb": (PDB_LIST, lambda o: [o.pattern]),
        "args": (PDB_ARGS, lambda o: [o.procedure]),
        "gegl": (GEGL_LIST, lambda o: [o.pattern]),
        "geglargs": (GEGL_ARGS, lambda o: [o.operation]),
    }
    if opts.cmd in simple:
        code, argf = simple[opts.cmd]
        return run_python(binary, code=code, script_args=argf(opts),
                          timeout=opts.timeout)

    if opts.cmd == "run":
        extra = [a for a in opts.args if a != "--"]
        return run_python(binary, script=opts.script, script_args=extra,
                          timeout=opts.timeout, fast=opts.fast)
    if opts.cmd == "eval":
        return run_python(binary, code=opts.code, timeout=opts.timeout,
                          fast=opts.fast)
    if opts.cmd == "scm":
        return run_scm(binary, opts.target, timeout=opts.timeout, fast=opts.fast)
    return 2


if __name__ == "__main__":
    sys.exit(main())
