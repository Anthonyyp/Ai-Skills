"""Renders an integration map, a tiered tree of everything an integration has in production, from a JSON spec.

  python render.py <spec.json> <out.pdf> [--png <preview.png>] [--browser <path to chrome or edge>]

Writes <out>.html beside the PDF (self-contained; open it and print to PDF if no browser is found). The PDF and
the PNG come from a headless Chromium-family browser: Chrome, Edge or Chromium. The type shrinks until the map
fits one landscape Letter page. The spec is described in ../SKILL.md.
"""
import argparse, html, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = {"system", "link", "ops", "gap"}

CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_browser(given=None):
    for c in ([given] if given else []) + [os.environ.get("MAP_BROWSER")] + CANDIDATES:
        if not c:
            continue
        p = shutil.which(c) or (c if os.path.isfile(c) else None)
        if p:
            return p
    return None


def inline(s):
    """Escapes text, then turns `backticks` into <code>."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(str(s)))


def build(spec):
    title = html.escape(spec["title"])
    if spec.get("emphasis"):
        title = title.replace(html.escape(spec["emphasis"]), "<em>%s</em>" % html.escape(spec["emphasis"]), 1)
    branches, systems = "", 0
    for b in spec["branches"]:
        kind = b.get("kind", "system")
        if kind not in KINDS:
            raise SystemExit("branch %r: kind must be one of %s" % (b.get("name"), ", ".join(sorted(KINDS))))
        cls = "k-" + kind
        if kind == "system":
            cls += " s%d" % (systems % 4)
            systems += 1
        groups = "".join(
            '<div class="cat"><div class="node t2">%s <span>%s</span></div><div class="leaf">%s</div></div>'
            % (inline(g["name"]), inline(g.get("count", "")), inline(g.get("items", "")))
            for g in b["groups"])
        branches += ('<div class="side %s"><div class="node t1">%s<small>%s</small></div><div class="cats">%s</div></div>'
                     % (cls, inline(b["name"]), inline(b.get("note", "")), groups))
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    return (tpl.replace("{{TITLE_TEXT}}", html.escape(spec["title"])).replace("{{TITLE}}", title)
            .replace("{{ASOF}}", "<br>".join(inline(x) for x in spec.get("asof", [])))
            .replace("{{SUBTITLE}}", inline(spec.get("subtitle", ""))).replace("{{ROOT}}", inline(spec["root"]))
            .replace("{{BRANCHES}}", branches))


def run(browser, args):
    # A throwaway profile, so an already-open browser window can't take the job over.
    with tempfile.TemporaryDirectory() as prof:
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--user-data-dir=" + prof, "--virtual-time-budget=4000", *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("pdf")
    ap.add_argument("--png"); ap.add_argument("--browser")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    out_html = os.path.splitext(os.path.abspath(a.pdf))[0] + ".html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(build(spec))
    print("wrote", out_html)
    browser = find_browser(a.browser)
    if not browser:
        sys.exit("No Chrome, Edge or Chromium found: open the HTML and print it to PDF (landscape, no margins), "
                 "or pass --browser.")
    url = "file:///" + out_html.replace("\\", "/").lstrip("/")
    r = run(browser, ["--no-pdf-header-footer", "--print-to-pdf=" + os.path.abspath(a.pdf), url])
    if not os.path.isfile(a.pdf):
        sys.exit("PDF failed: " + (r.stderr or r.stdout)[-400:])
    print("wrote", os.path.abspath(a.pdf))
    if a.png:
        run(browser, ["--window-size=1056,816", "--screenshot=" + os.path.abspath(a.png), url])
        print("wrote", os.path.abspath(a.png) if os.path.isfile(a.png) else "(no PNG: " + a.png + ")")


if __name__ == "__main__":
    main()
