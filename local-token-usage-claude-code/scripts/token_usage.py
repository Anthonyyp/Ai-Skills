import argparse, json, os, re, sys
from datetime import datetime, timezone, timedelta

parser = argparse.ArgumentParser()
parser.add_argument('--hours', type=int, required=True)
parser.add_argument('--scope', default='all')
parser.add_argument('--html', action='store_true')
parser.add_argument('--config', required=True)
args = parser.parse_args()

HOURS = args.hours
SCOPE = args.scope
GENERATE_HTML = args.html

# utf-8-sig, not the platform default: on Windows the natural ways to write this file
# (PowerShell's Out-File -Encoding utf8, Notepad) emit a UTF-8 BOM, and a bare open()
# both reads with the locale codepage and chokes on the BOM with a confusing
# "Expecting value: line 1 column 1". utf-8-sig accepts a BOM or no BOM.
with open(args.config, encoding='utf-8-sig') as f:
    cfg = json.load(f)
MODEL_PRICES = cfg['prices']
DEFAULT_PRICES = cfg.get('default_prices', {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30})

# Longest key first. A dict-order startswith would price "claude-opus-5-5" at the
# "claude-opus-5" rate whenever the shorter key happened to come first.
_PRICE_KEYS = sorted(MODEL_PRICES, key=len, reverse=True)

def get_prices(model):
    for key in _PRICE_KEYS:
        if model.startswith(key): return MODEL_PRICES[key]
    return DEFAULT_PRICES

def cache_write_1h_rate(p):
    # 1-hour cache writes bill at 2x base input; 5-minute writes ("cache_write") at 1.25x.
    # Use the config's own rate when it has one.
    return p.get("cache_write_1h", p["input"] * 2.0)

cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=HOURS)).timestamp()
claude_dir = os.path.expanduser("~/.claude/projects")

if not os.path.isdir(claude_dir):
    sys.stdout.buffer.write(
        f"ERROR: Claude projects directory not found: {claude_dir}\nRun Claude Code at least once to generate session logs.\n".encode("utf-8")
    )
    sys.exit(1)

cwd = os.getcwd()
project_slug = re.sub(r'[-]+', '-', re.sub(r'[/\\:.]', '-', cwd)).strip('-')
search_dirs = [os.path.join(claude_dir, project_slug)] if SCOPE == "current" else [claude_dir]

# -- Collect transcripts: main sessions plus the subagents they spawned --------------
# A subagent's transcript lives at <project>/<session-id>/subagents/<agent>.jsonl. Its
# usage is real spend, so it is counted under the session that spawned it.
def parent_of(sub_fp):
    return os.path.dirname(os.path.dirname(sub_fp)) + '.jsonl'

main_files, sub_files = set(), []
for base in search_dirs:
    for root, dirs, fnames in os.walk(base):
        for fname in fnames:
            if not fname.endswith('.jsonl'): continue
            fp = os.path.join(root, fname)
            try:
                if os.path.getmtime(fp) <= cutoff_ts: continue
            except OSError:
                continue
            if os.path.basename(root) == 'subagents': sub_files.append(fp)
            else: main_files.add(fp)
for sp in sub_files:
    if os.path.exists(parent_of(sp)): main_files.add(parent_of(sp))

cutoff_dt = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc)

def read_entries(fp):
    with open(fp, 'r', encoding='utf-8', errors='replace') as f:
        for n, line in enumerate(f):
            line = line.strip()
            if not line: continue
            try: yield n, json.loads(line)
            except: continue

def entry_ts(entry):
    ts_str = entry.get("timestamp", "")
    if not ts_str: return None
    try: return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except: return None

# -- Count each API request ONCE ------------------------------------------------------
# Claude Code writes one transcript line per content block of a response (thinking,
# text, each tool_use), and EVERY one of those lines carries the usage of the whole
# request. Lines written mid-stream carry a partial output_tokens; the last carries the
# completed figure. A resumed or forked session can also copy the same lines into a
# second file. So: key on (message.id, requestId), keep the line with the largest
# output_tokens, and attribute the request to the first session that logged it.
# Summing every line instead overstates spend by roughly 2x.
calls = {}
raw_lines = 0

def record_usage(entry, fp, n, session_key, is_sub):
    global raw_lines
    msg = entry.get("message") or {}
    usage = msg.get("usage")
    model = msg.get("model", "")
    if not usage or model == "<synthetic>": return
    raw_lines += 1
    mid, rid = msg.get("id"), entry.get("requestId")
    key = (mid, rid) if (mid and rid) else ("line", fp, n)   # no ids: can't be matched, count as-is
    out_tok = usage.get("output_tokens", 0) or 0
    prev = calls.get(key)
    if prev is None:
        calls[key] = dict(session=session_key, sub=is_sub, model=model, usage=usage, out=out_tok)
    elif out_tok > prev["out"]:
        prev["usage"], prev["out"] = usage, out_tok

def blank_meta():
    return dict(project=None, user_msgs=0, first_prompt="", first_ts=None, last_ts=None, tool_counts={})

meta = {}
for fpath in sorted(main_files):
    md = blank_meta()
    try:
        for n, entry in read_entries(fpath):
            if md["project"] is None and entry.get("cwd"):
                md["project"] = os.path.basename(entry["cwd"].rstrip('/\\'))
            ts = entry_ts(entry)
            if ts is None or ts < cutoff_dt: continue
            if md["first_ts"] is None: md["first_ts"] = ts
            md["last_ts"] = ts
            if entry.get("type") == "user":
                md["user_msgs"] += 1
                if not md["first_prompt"]:
                    c = entry.get("message", {}).get("content", "")
                    if isinstance(c, list):
                        for item in c:
                            if isinstance(item, dict) and item.get("type") == "text":
                                md["first_prompt"] = item.get("text", "")[:120]; break
                    elif isinstance(c, str):
                        md["first_prompt"] = c[:120]
            if entry.get("type") == "assistant":
                record_usage(entry, fpath, n, fpath, False)
                for c in (entry.get("message", {}).get("content") or []):
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        t = c.get("name", "?")
                        md["tool_counts"][t] = md["tool_counts"].get(t, 0) + 1
    except Exception as e:
        sys.stderr.write(f"ERR {fpath}: {e}\n"); continue
    meta[fpath] = md

for fpath in sorted(sub_files):
    try:
        for n, entry in read_entries(fpath):
            ts = entry_ts(entry)
            if ts is None or ts < cutoff_dt: continue
            if entry.get("type") == "assistant":
                record_usage(entry, fpath, n, parent_of(fpath), True)
    except Exception as e:
        sys.stderr.write(f"ERR {fpath}: {e}\n")

# -- Price each request once, then roll up per session and per model -----------------
def blank_totals():
    return dict(inp=0, out=0, cw=0, cr=0, cost=0.0, input_cost=0.0, output_cost=0.0, cw_cost=0.0,
                cr_cost=0.0, sub_cost=0.0, calls=0, model_costs={}, models=set())

sessions = {}
global_model_costs = {}
for c in calls.values():
    u, p = c["usage"], get_prices(c["model"])
    i_tok  = u.get("input_tokens", 0) or 0
    o_tok  = c["out"]
    cw_tok = u.get("cache_creation_input_tokens", 0) or 0
    cr_tok = u.get("cache_read_input_tokens", 0) or 0
    cw_1h  = min((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) or 0, cw_tok)
    _ic = i_tok / 1e6 * p["input"]
    _oc = o_tok / 1e6 * p["output"]
    _wc = ((cw_tok - cw_1h) * p["cache_write"] + cw_1h * cache_write_1h_rate(p)) / 1e6
    _rc = cr_tok / 1e6 * p["cache_read"]
    turn_cost = _ic + _oc + _wc + _rc
    s = sessions.setdefault(c["session"], blank_totals())
    s["inp"] += i_tok; s["out"] += o_tok; s["cw"] += cw_tok; s["cr"] += cr_tok; s["calls"] += 1
    s["cost"] += turn_cost
    s["input_cost"] += _ic; s["output_cost"] += _oc; s["cw_cost"] += _wc; s["cr_cost"] += _rc
    if c["sub"]: s["sub_cost"] += turn_cost
    m = c["model"]
    if m:
        s["models"].add(m)
        s["model_costs"][m] = s["model_costs"].get(m, 0.0) + turn_cost
        global_model_costs[m] = global_model_costs.get(m, 0.0) + turn_cost

def project_from_path(fpath):
    try:
        proj_raw = fpath.split("projects")[1].split(os.sep)[1]
    except:
        proj_raw = os.path.basename(os.path.dirname(fpath))
    home_slug = re.sub(r'[^a-zA-Z0-9]', '-', os.path.expanduser('~'))
    rel = proj_raw[len(home_slug):].lstrip('-') if proj_raw.startswith(home_slug) else proj_raw
    segs = re.split(r'-{2,}', rel)
    return re.sub(r'-+', ' ', segs[-1]).strip() or re.sub(r'-+', ' ', rel).strip() or proj_raw

results = []
for key in set(meta) | set(sessions):
    md = meta.get(key) or blank_meta()
    s = sessions.get(key)
    if s is None and md["first_ts"] is None:
        continue
    s = s or blank_totals()
    first_ts, last_ts = md["first_ts"], md["last_ts"]
    results.append(dict(
        project=md["project"] or project_from_path(key),
        session_id=os.path.splitext(os.path.basename(key))[0][:8],
        first_prompt=md["first_prompt"], user_msgs=md["user_msgs"],
        input_tokens=int(s["inp"]), output_tokens=int(s["out"]),
        cache_write=int(s["cw"]), cache_read=int(s["cr"]), cost=s["cost"], model_costs=s["model_costs"],
        input_cost=s["input_cost"], output_cost=s["output_cost"], cw_cost=s["cw_cost"], cr_cost=s["cr_cost"],
        sub_cost=s["sub_cost"], calls=s["calls"],
        dur_min=int((last_ts - first_ts).total_seconds() / 60) if first_ts and last_ts else 0,
        top_tools=sorted(md["tool_counts"].items(), key=lambda x: -x[1])[:6],
        models=sorted(s["models"]),
        start=first_ts.astimezone().strftime("%b %d %I:%M %p") if first_ts else "?",
    ))

results.sort(key=lambda r: -r["cost"])

tc = sum(r["cost"]          for r in results)
tm = sum(r["user_msgs"]     for r in results)
to = sum(r["output_tokens"] for r in results)
tr = sum(r["cache_read"]    for r in results)
tw = sum(r["cache_write"]   for r in results)
ti = sum(r["input_tokens"]  for r in results)
g_input_cost = sum(r["input_cost"]  for r in results)
g_output_cost = sum(r["output_cost"] for r in results)
g_cw_cost     = sum(r["cw_cost"]    for r in results)
g_cr_cost     = sum(r["cr_cost"]    for r in results)

period_label = f"Last {HOURS}h" if HOURS < 168 else (f"Last {HOURS//24} days" if HOURS < 720 else "Last 30 days")
# Honest by default: the config says where its rates came from. Hardcoding
# "live from Anthropic docs" made the report claim live pricing even when the
# fetch had failed and fallback rates were used - the one thing the report must
# not lie about, since every figure below it is derived from those rates.
pricing_note = cfg.get('pricing_source') or 'UNKNOWN - source not recorded in config'
_unpriced = sorted(m for m in global_model_costs
                   if not any(m.startswith(k) for k in MODEL_PRICES))
if _unpriced:
    pricing_note += f"  [!] fallback rates used for: {', '.join(_unpriced)}"

# ── TEXT OUTPUT ──────────────────────────────────────────
lines = []
lines.append("")
lines.append("=" * 66)
lines.append(f"  TOKEN USAGE REPORT  --  {period_label}")
lines.append(f"  Pricing: {pricing_note}")
lines.append("=" * 66)
lines.append(f"  Sessions:       {len(results)}")
lines.append(f"  API calls:      {len(calls):,}  (from {raw_lines:,} log lines - each request counted once)")
lines.append(f"  User messages:  {tm:,}")
lines.append(f"  Output tokens:  {to:,}")
lines.append(f"  Cache reads:    {tr:,}")
lines.append(f"  Est. total:     ${tc:.4f}")
lines.append(f"  Cost breakdown: input=${g_input_cost:.2f}  output=${g_output_cost:.2f}  cache_w=${g_cw_cost:.2f}  cache_r=${g_cr_cost:.2f}")
lines.append("")
lines.append("  By model:")
for m, mc in sorted(global_model_costs.items(), key=lambda x: -x[1]):
    short = m.replace("claude-", "")
    pct = mc / tc * 100 if tc else 0
    lines.append(f"    {short:<24}  ${mc:.4f}  ({pct:.0f}%)")
lines.append("=" * 66)

for r in results:
    model_short = ", ".join(m.replace("claude-","") for m in r["models"]) or "unknown"
    lines.append("")
    lines.append(f"  [{r['session_id']}]  {r['project'][:52]}")
    lines.append(f"    Start:   {r['start']}  |  {r['dur_min']}min  |  {r['user_msgs']} msgs")
    lines.append(f"    Model:   {model_short}")
    if r.get("sub_cost"):
        lines.append(f"    Subagents: ${r['sub_cost']:.4f} of this session's cost")
    lines.append(f"    Tokens:  out={r['output_tokens']:,}  cache_r={r['cache_read']:,}")
    lines.append(f"    Cost:    ${r['cost']:.4f}  (in=${r['input_cost']:.2f}  out=${r['output_cost']:.2f}  cw=${r['cw_cost']:.2f}  cr=${r['cr_cost']:.2f})")
    if r["model_costs"] and len(r["model_costs"]) > 1:
        bd = "  ".join(f"{m.replace('claude-','')} ${c:.4f}" for m,c in sorted(r["model_costs"].items(), key=lambda x: -x[1]))
        lines.append(f"    By model: {bd}")
    if r["top_tools"]:
        lines.append(f"    Tools:   {'  '.join(f'{t.split(chr(95)*2)[-1]}x{c}' for t,c in r['top_tools'])}")
    if r["first_prompt"] and not r["first_prompt"].startswith("<local-command-caveat>"):
        lines.append(f"    Topic:   {r['first_prompt'][:80]}")

lines.append("")
lines.append("  Max Plan = flat monthly rate. These are API-equivalent reference figures.")
lines.append("=" * 66)
lines.append("")

sys.stdout.buffer.write("\n".join(lines).encode("utf-8"))
sys.stdout.buffer.write(b"\n")

# ── HTML OUTPUT ──────────────────────────────────────────
if not GENERATE_HTML:
    sys.exit(0)

def fmt_num(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}K"
    return str(int(n))

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

now_str = datetime.now().strftime("%B %d, %Y %I:%M %p")

model_card_html = ""
for m, mc in sorted(global_model_costs.items(), key=lambda x: -x[1]):
    short = re.sub(r'-\d{8}$', '', m.replace("claude-",""))
    pct = (mc / tc * 100) if tc else 0
    card_class = "opus" if "opus" in short else ("sonnet" if "sonnet" in short else "")
    model_card_html += (
        f'<div class="stat-card {card_class}">'
        f'<div class="stat-label">{esc(short)}</div>'
        f'<div class="stat-value cost">${mc:.2f}</div>'
        f'<div class="stat-sub">{pct:.0f}% of total</div>'
        f'</div>'
    )

rows = []
for r in results:
    cost_class = "cost-high" if r["cost"] > 20 else ("cost-med" if r["cost"] > 5 else "cost-low")
    tool_tags = "".join(
        f'<span class="tool-tag">{esc(t.split("__")[-1])} x{c}</span>'
        for t, c in r["top_tools"]
    )
    topic = esc(r["first_prompt"][:90]) if r["first_prompt"] else ""
    if "&lt;local-command-caveat&gt;" in topic or not topic:
        topic = "<em style='color:#aaa'>resumed session</em>"

    model_display = ""
    if r["model_costs"]:
        for mm, mc in sorted(r["model_costs"].items(), key=lambda x: -x[1]):
            short = re.sub(r'-\d{8}$', '', mm.replace("claude-",""))
            tag_class = "model-opus" if "opus" in short else ("model-sonnet" if "sonnet" in short else "model-haiku")
            label = short if len(r["model_costs"]) == 1 else f"{short} ${mc:.2f}"
            model_display += f'<span class="model-tag {tag_class}">{esc(label)}</span> '
    else:
        model_display = '<span style="color:#ccc">unknown</span>'

    rows.append(
        "<tr>"
        f'<td><span class="session-id">{esc(r["session_id"])}</span></td>'
        f'<td>{esc(r["project"][:46])}</td>'
        f'<td style="white-space:nowrap">{esc(r["start"])}</td>'
        f'<td>{r["user_msgs"]}</td>'
        f'<td>{fmt_num(r["output_tokens"])}</td>'
        f'<td>{fmt_num(r["cache_read"])}</td>'
        f'<td class="{cost_class}">${r["cost"]:.4f}<br><span class="cost-breakdown">in ${r["input_cost"]:.2f} &bull; out ${r["output_cost"]:.2f}<br>cw ${r["cw_cost"]:.2f} &bull; cr ${r["cr_cost"]:.2f}</span></td>'
        f'<td>{model_display}</td>'
        f'<td>{tool_tags}</td>'
        f'<td class="topic">{topic}</td>'
        "</tr>"
    )

pricing_rows = ""
for m, p in sorted(MODEL_PRICES.items(), key=lambda x: -x[1]["output"]):
    pricing_rows += f'<tr><td>{esc(m.replace("claude-",""))}</td><td>${p["input"]}</td><td>${p["output"]}</td><td>${p["cache_write"]}</td><td>${p["cache_read"]}</td></tr>'

html_parts = [
    '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">',
    f'<title>Claude Token Usage - {period_label}</title>',
    '<style>',
    '*,*::before,*::after{box-sizing:border-box}',
    'body{font-family:system-ui,-apple-system,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#1a1a1a;background:#fff}',
    'h1{font-size:1.6rem;margin-bottom:4px;color:#111}',
    '.subtitle{color:#666;font-size:.85rem;margin-bottom:28px}',
    '.section-label{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#aaa;margin:0 0 10px}',
    '.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin-bottom:12px}',
    '.model-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin-bottom:32px}',
    '.stat-card{background:#f8f9fa;border-radius:10px;padding:14px 16px;border:1px solid #e9ecef}',
    '.stat-card.opus{background:#fff7ed;border-color:#fed7aa}',
    '.stat-card.sonnet{background:#eff6ff;border-color:#bfdbfe}',
    '.stat-label{font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.07em;font-weight:600}',
    '.stat-value{font-size:1.5rem;font-weight:700;margin-top:6px;color:#111}',
    '.stat-value.cost{color:#2563eb}',
    '.stat-sub{font-size:.7rem;color:#aaa;margin-top:3px}',
    '.note-box{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;margin-bottom:28px;font-size:.82rem;color:#92400e}',
    'table{width:100%;border-collapse:collapse;font-size:.8rem}',
    'th{text-align:left;padding:9px 10px;background:#f1f5f9;border-bottom:2px solid #dde3ea;color:#555;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}',
    'td{padding:9px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top}',
    'tr:hover td{background:#fafbfc}',
    '.session-id{font-family:"Courier New",monospace;color:#999;font-size:.75rem}',
    '.topic{color:#555;font-size:.75rem;max-width:180px;line-height:1.4}',
    '.tool-tag{display:inline-block;background:#e0f2fe;color:#0369a1;border-radius:4px;padding:1px 5px;font-size:.68rem;margin:2px 2px 2px 0;white-space:nowrap}',
    '.model-tag{display:inline-block;border-radius:4px;padding:2px 6px;font-size:.7rem;margin:2px 2px 2px 0;white-space:nowrap;font-weight:600}',
    '.model-opus{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa}',
    '.model-sonnet{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}',
    '.model-haiku{background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0}',
    '.cost-high{color:#dc2626;font-weight:700}',
    '.cost-med{color:#d97706;font-weight:600}',
    '.cost-low{color:#16a34a;font-weight:500}',
    '.cost-breakdown{font-size:.65rem;font-weight:400;color:#999;display:block;margin-top:3px;line-height:1.5}',
    '.pricing-table{width:auto;margin-top:8px}',
    '.pricing-table td,.pricing-table th{padding:4px 12px;font-size:.72rem}',
    '.footer{margin-top:36px;font-size:.72rem;color:#aaa;border-top:1px solid #eee;padding-top:14px;line-height:1.8}',
    '@media print{body{margin:20px;padding:0;max-width:100%}.stat-card{border:1px solid #ccc}tr:hover td{background:transparent}}',
    '</style></head><body>',
    '<h1>Claude Code &mdash; Token Usage Report</h1>',
    f'<p class="subtitle">Period: {period_label} &nbsp;&bull;&nbsp; Scope: {SCOPE} &nbsp;&bull;&nbsp; Generated: {now_str} &nbsp;&bull;&nbsp; Pricing: {pricing_note}</p>',
]

html_parts += [
    '<div class="note-box">Costs calculated <strong>per model per turn</strong> using current Anthropic API rates. Max Plan = flat monthly rate &mdash; these are API-equivalent reference figures.</div>',
    '<p class="section-label">Totals</p>',
    '<div class="summary-grid">',
    f'<div class="stat-card"><div class="stat-label">Sessions</div><div class="stat-value">{len(results)}</div><div class="stat-sub">{period_label.lower()}</div></div>',
    f'<div class="stat-card"><div class="stat-label">User Messages</div><div class="stat-value">{fmt_num(tm)}</div></div>',
    f'<div class="stat-card"><div class="stat-label">Output Tokens</div><div class="stat-value">{fmt_num(to)}</div></div>',
    f'<div class="stat-card"><div class="stat-label">Cache Reads</div><div class="stat-value">{fmt_num(tr)}</div><div class="stat-sub">billed per model rate</div></div>',
    f'<div class="stat-card"><div class="stat-label">Cache Writes</div><div class="stat-value">{fmt_num(tw)}</div></div>',
    f'<div class="stat-card"><div class="stat-label">Total Est. Cost</div><div class="stat-value cost">${tc:.2f}</div><div class="stat-sub">all models combined</div></div>',
    '</div>',
    '<p class="section-label">By Model</p>',
    f'<div class="model-grid">{model_card_html}</div>',
    '<p class="section-label">Sessions &mdash; sorted by estimated cost</p>',
    '<table><thead><tr>',
    '<th>Session</th><th>Project</th><th>Start</th><th>Msgs</th><th>Output</th><th>Cache Reads</th><th>Est. Cost</th><th>Model(s)</th><th>Top Tools</th><th>Topic</th>',
    '</tr></thead><tbody>',
    "\n".join(rows),
    '</tbody></table>',
    '<div class="footer">',
    f'<strong>Pricing used ({pricing_note}, per 1M tokens):</strong><br>',
    '<table class="pricing-table"><thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Cache Write</th><th>Cache Read</th></tr></thead><tbody>',
    pricing_rows,
    '</tbody></table><br>',
    'Session files from <code>~/.claude/projects/</code> &mdash; subagent logs excluded.',
    '</div></body></html>',
]

html = "\n".join(html_parts)
out_dir = os.path.expanduser("~/.claude/usage-data")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "token-usage-report.html")
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

sys.stdout.buffer.write(f"\nHTML written to: {out_path}\n".encode("utf-8"))
