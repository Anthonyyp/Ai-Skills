"""Known-answer tests for token_usage.py.

Each test writes a tiny fake ~/.claude/projects tree, runs the real script against it, and checks the
total against a number worked out by hand. Prices are round ($1 per million tokens unless a test says
otherwise) so every expected value is obvious.

Run from the skill folder:   python -m unittest discover -s tests -v
"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone

SCRIPT = os.environ.get("TOKEN_USAGE_SCRIPT") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "token_usage.py")
M = 1_000_000
FLAT = {"input": 1.0, "output": 1.0, "cache_write": 1.25, "cache_read": 0.1}


def ts(minutes_ago=10):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.isoformat().replace("+00:00", "Z")


def usage(inp=0, out=0, cw=0, cr=0, cw_1h=0):
    u = {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw,
         "cache_read_input_tokens": cr}
    if cw_1h:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": cw - cw_1h, "ephemeral_1h_input_tokens": cw_1h}
    return u


def response_lines(msg_id, req_id, u, model="test-model", blocks=("thinking", "text", "tool_use"),
                   minutes_ago=10):
    """One API response as Claude Code logs it: one line per content block, each repeating usage."""
    out = []
    for b in blocks:
        block = {"type": b, "name": "Bash", "input": {}} if b == "tool_use" else {"type": b, b: "..."}
        out.append({"type": "assistant", "timestamp": ts(minutes_ago), "requestId": req_id,
                    "message": {"id": msg_id, "model": model, "role": "assistant",
                                "content": [block], "usage": u}})
    return out


class TokenUsageTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.projects = os.path.join(self.home, ".claude", "projects", "C--proj")
        os.makedirs(self.projects)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def write(self, relpath, lines):
        fp = os.path.join(self.projects, relpath)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        user = {"type": "user", "timestamp": ts(11), "cwd": "/work/proj",
                "message": {"role": "user", "content": "hi"}}
        with open(fp, "w", encoding="utf-8") as f:
            for l in [user] + lines:
                f.write(json.dumps(l) + "\n")

    def run_report(self, prices=None, hours=1):
        cfg = os.path.join(self.home, "prices.json")
        with open(cfg, "w") as f:
            json.dump({"pricing_source": "test", "prices": prices or {"test-model": FLAT}}, f)
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, SCRIPT, "--hours", str(hours), "--config", cfg],
                           cwd=self.home, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        total = float(re.search(r"Est\. total:\s+\$([\d.]+)", r.stdout).group(1))
        mc = re.search(r"API calls:\s+([\d,]+)", r.stdout)
        calls = int(mc.group(1).replace(",", "")) if mc else None
        return total, calls, r.stdout

    def test_one_request_logged_as_three_lines_counts_once(self):
        # 1M input + 1M output at $1/M = $2.00. Summing every line would give $6.00.
        self.write("s1.jsonl", response_lines("msg_1", "req_1", usage(inp=M, out=M)))
        total, calls, _ = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)
        self.assertEqual(calls, 1)

    def test_streaming_partial_keeps_completed_output(self):
        # First line written mid-stream (output 2), last line complete (output 1M). Truth: $2.00.
        lines = response_lines("msg_1", "req_1", usage(inp=M, out=2), blocks=("thinking",))
        lines += response_lines("msg_1", "req_1", usage(inp=M, out=M), blocks=("text", "tool_use"))
        self.write("s1.jsonl", lines)
        total, calls, _ = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)
        self.assertEqual(calls, 1)

    def test_request_copied_into_a_resumed_session_counts_once(self):
        lines = response_lines("msg_1", "req_1", usage(inp=M))
        self.write("original.jsonl", lines)
        self.write("resumed.jsonl", lines)
        total, calls, _ = self.run_report()
        self.assertAlmostEqual(total, 1.00, places=4)
        self.assertEqual(calls, 1)

    def test_distinct_requests_all_count(self):
        lines = response_lines("msg_1", "req_1", usage(inp=M)) + response_lines("msg_2", "req_2", usage(inp=M))
        self.write("s1.jsonl", lines)
        total, calls, _ = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)
        self.assertEqual(calls, 2)

    def test_longer_model_name_is_not_priced_as_its_prefix(self):
        # "claude-x-5-5" must use its own $10 rate, not the "claude-x-5" $1 rate listed first.
        prices = {"claude-x-5": dict(FLAT), "claude-x-5-5": dict(FLAT, input=10.0)}
        self.write("s1.jsonl", response_lines("msg_1", "req_1", usage(inp=M), model="claude-x-5-5-20260101"))
        total, _, _ = self.run_report(prices=prices)
        self.assertAlmostEqual(total, 10.00, places=4)

    def test_one_hour_cache_write_defaults_to_twice_input(self):
        # 1M cache-write tokens, all 1-hour: 2 x $1 input = $2.00 (the 5-minute rate would give $1.25).
        self.write("s1.jsonl", response_lines("msg_1", "req_1", usage(cw=M, cw_1h=M)))
        total, _, _ = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)

    def test_one_hour_cache_write_uses_config_rate_when_given(self):
        self.write("s1.jsonl", response_lines("msg_1", "req_1", usage(cw=M, cw_1h=M)))
        total, _, _ = self.run_report(prices={"test-model": dict(FLAT, cache_write_1h=3.0)})
        self.assertAlmostEqual(total, 3.00, places=4)

    def test_five_minute_cache_write_uses_cache_write_rate(self):
        self.write("s1.jsonl", response_lines("msg_1", "req_1", usage(cw=M)))
        total, _, _ = self.run_report()
        self.assertAlmostEqual(total, 1.25, places=4)

    def test_subagent_usage_is_counted_under_its_parent_session(self):
        self.write("parent.jsonl", response_lines("msg_1", "req_1", usage(inp=M)))
        self.write(os.path.join("parent", "subagents", "agent-a.jsonl"), response_lines("msg_2", "req_2", usage(inp=M)))
        total, calls, out = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)
        self.assertEqual(calls, 2)
        self.assertEqual(out.count("[parent]"), 1, "subagent must not appear as its own session")
        self.assertIn("Subagents: $1.0000", out)

    def test_lines_without_ids_are_each_counted(self):
        # Without message.id + requestId there's no safe way to match lines, so each one counts.
        lines = response_lines("msg_1", "req_1", usage(inp=M), blocks=("text",))
        for l in lines:
            del l["requestId"]
        self.write("s1.jsonl", lines + [dict(lines[0])])
        total, calls, _ = self.run_report()
        self.assertAlmostEqual(total, 2.00, places=4)
        self.assertEqual(calls, 2)

    def test_lines_outside_the_window_are_ignored(self):
        lines = response_lines("msg_1", "req_1", usage(inp=M))
        lines += response_lines("msg_old", "req_old", usage(inp=M), minutes_ago=180)
        self.write("s1.jsonl", lines)
        total, _, _ = self.run_report(hours=1)
        self.assertAlmostEqual(total, 1.00, places=4)

    def test_synthetic_entries_are_skipped(self):
        lines = response_lines("msg_1", "req_1", usage(inp=M))
        lines += response_lines("msg_s", "req_s", usage(inp=M), model="<synthetic>")
        self.write("s1.jsonl", lines)
        total, _, _ = self.run_report()
        self.assertAlmostEqual(total, 1.00, places=4)


if __name__ == "__main__":
    unittest.main()
