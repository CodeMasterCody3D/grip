"""The Claude Code binding (claude_bridge.py), end to end through its own CLI with a private GRIP cache: unbound sessions are silent,
events land in the mission state and the observation log (metadata only), a human stop pauses, the Stop gate continues an actionable
task exactly once and never spins, an armed waiter lets the session stop, and the waiter wakes on its condition or says why it will not."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parents[1]
BRIDGE = str(HERE / "claude_bridge.py")
SID = "11111111-2222-3333-4444-555555555555"


class ClaudeBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = dict(os.environ, GRIP_CACHE_DIR=str(root / "cache"), CLAUDE_CODE_SESSION_ID=SID)
        self.ws = root / "ws"
        self.ws.mkdir()
        self.state = root / "mission" / "state.json"
        mission = {"schema": 1, "mission_id": "claude-test", "objective": "Train and record", "done_when": "both tasks done",
                   "continuation_instructions": "test scope only", "context_refs": ["unit test"],
                   "tasks": [{"id": "job", "content": "watch the running job", "status": "pending", "done_when": "the job printed DONE"},
                             {"id": "read", "content": "read the outputs", "status": "pending", "depends_on": ["job"], "done_when": "every output read"}]}
        self.mission = root / "mission.json"
        self.mission.write_text(json.dumps(mission))

    def tearDown(self):
        self.tmp.cleanup()

    def run_bridge(self, *args, stdin=None, check=True):
        r = subprocess.run([sys.executable, BRIDGE, *args], input=stdin, capture_output=True, text=True, env=self.env, timeout=60)
        if check and r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        return r

    def hook(self, event, **extra):
        payload = dict(session_id=SID, hook_event_name=event, permission_mode="default")
        payload.update(extra)
        return self.run_bridge("hook", stdin=json.dumps(payload)).stdout

    def init(self):
        self.run_bridge("--state", str(self.state), "init", "--mission", str(self.mission), "--workspace", str(self.ws),
                        "--compute", "test only")

    def load(self):
        return json.loads(self.state.read_text())

    def observations(self):
        p = self.state.with_name("claude_observations.jsonl")
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def test_unbound_session_is_silent(self):
        out = self.run_bridge("hook", stdin=json.dumps({"session_id": "nobody", "hook_event_name": "Stop"})).stdout
        self.assertEqual(out, "")

    def test_events_and_metadata_only_observations(self):
        self.init()
        ctx = json.loads(self.hook("SessionStart", source="startup"))
        self.assertIn("claude-test", ctx["hookSpecificOutput"]["additionalContext"])
        self.hook("PreToolUse", tool_name="Bash", tool_use_id="t1",
                  tool_input={"command": "echo SECRET-TOKEN", "description": "Say hello"})
        self.hook("PostToolUse", tool_name="Bash", tool_use_id="t1",
                  tool_input={"command": "echo SECRET-TOKEN", "description": "Say hello"},
                  tool_response={"stdout": "SECRET-TOKEN"})
        self.hook("PostToolUseFailure", tool_name="Edit", tool_use_id="t2", tool_input={"file_path": "/x/y.py"})
        st = self.load()
        self.assertEqual(st["hook_state"]["counts"]["tool_start"], 1)
        self.assertEqual(st["hook_state"]["counts"]["tool_end"], 2)
        obs = self.observations()
        text = json.dumps(obs)
        self.assertNotIn("SECRET-TOKEN", text)                       # never command text or output
        post = [o for o in obs if o["event"] == "PostToolUse"][0]
        self.assertTrue(post["ok"])
        self.assertEqual(post["description"], "Say hello")
        self.assertIn("seconds", post)
        fail = [o for o in obs if o["event"] == "PostToolUseFailure"][0]
        self.assertFalse(fail["ok"])
        self.assertEqual(fail["file_path"], "/x/y.py")

    def test_human_stop_pauses_and_prompt_text_is_not_stored(self):
        self.init()
        self.hook("UserPromptSubmit", prompt="stop the run please, my private words")
        self.assertEqual(self.load()["status"], "paused")
        self.assertNotIn("private words", json.dumps(self.observations()))
        self.assertEqual(self.hook("Stop", stop_hook_active=False), "")  # a paused mission never continues

    def test_stop_gate_continues_once_and_never_spins(self):
        self.init()
        self.hook("PreToolUse", tool_name="Read", tool_use_id="a", tool_input={"file_path": "/f"})
        out = json.loads(self.hook("Stop", stop_hook_active=False))
        self.assertEqual(out["decision"], "block")
        self.assertIn("[GRIP AUTHORIZED CONTINUATION]", out["reason"])
        self.assertIn("claude_bridge.py", out["reason"])
        self.assertEqual(self.hook("Stop", stop_hook_active=True), "")   # the continued turn may stop
        self.assertEqual(self.hook("Stop", stop_hook_active=False), "")  # no tool work since the block: no spin
        self.hook("PreToolUse", tool_name="Read", tool_use_id="b", tool_input={"file_path": "/f"})
        self.assertEqual(json.loads(self.hook("Stop", stop_hook_active=False))["decision"], "block")
        self.assertEqual(self.hook("Stop", stop_hook_active=False, permission_mode="plan"), "")

    def test_armed_waiter_lets_the_session_stop_and_wakes_on_its_condition(self):
        self.init()
        flag = Path(self.tmp.name) / "done.flag"
        p = subprocess.Popen([sys.executable, BRIDGE, "--state", str(self.state), "wait", "--until", f"test -f {flag}", "--poll", "0.2",
                              "--every-min", "5"], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(50):
                if self.state.with_name("claude_waiter.json").exists():
                    break
                time.sleep(0.1)
            self.hook("PreToolUse", tool_name="Bash", tool_use_id="c", tool_input={"description": "arm"})
            self.assertEqual(self.hook("Stop", stop_hook_active=False), "")  # the waiter is armed
            flag.write_text("x")
            out, _err = p.communicate(timeout=30)
        finally:
            if p.poll() is None:
                p.kill()
        self.assertEqual(p.returncode, 0)
        self.assertIn("[GRIP AUTHORIZED CONTINUATION]", out)
        self.assertIn("condition met", out)
        self.assertFalse(self.state.with_name("claude_waiter.json").exists())
        self.assertEqual(self.load()["claude"]["last_wake"]["task"], "job")

    def test_failing_health_check_wakes_early_and_a_passing_one_does_not(self):
        self.init()
        r = self.run_bridge("--state", str(self.state), "wait", "--health", "echo gpu idle, no finish line; exit 1", "--health-strikes",
                            "2", "--poll", "0.1", "--every-min", "5")
        self.assertIn("HEALTH CHECK FAILED 2 times in a row", r.stdout)
        self.assertIn("gpu idle, no finish line", r.stdout)
        flag = Path(self.tmp.name) / "done2.flag"
        p = subprocess.Popen([sys.executable, BRIDGE, "--state", str(self.state), "wait", "--health", "true", "--health-strikes", "2",
                              "--until", f"test -f {flag}", "--poll", "0.1", "--every-min", "5"], env=self.env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(1.0)
            self.assertIsNone(p.poll())                               # healthy: no early wake
            flag.write_text("x")
            out, _err = p.communicate(timeout=30)
        finally:
            if p.poll() is None:
                p.kill()
        self.assertIn("condition met", out)

    def test_waiter_refuses_a_paused_mission(self):
        self.init()
        self.hook("UserPromptSubmit", prompt="pause")
        r = self.run_bridge("--state", str(self.state), "wait", "--until", "true", "--poll", "0.1", check=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("paused", r.stdout)

    def test_install_hooks_is_idempotent_and_keeps_existing(self):
        s = Path(self.tmp.name) / "settings.json"
        s.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}, "model": "x"}))
        first = json.loads(self.run_bridge("install-hooks", "--settings", str(s)).stdout)
        second = json.loads(self.run_bridge("install-hooks", "--settings", str(s)).stdout)
        d = json.loads(s.read_text())
        self.assertEqual(len(first["added"]), 7)
        self.assertEqual(second["added"], [])
        self.assertEqual(d["model"], "x")
        self.assertEqual(len(d["hooks"]["Stop"]), 2)                 # the existing Stop hook kept
        self.assertTrue(list(Path(self.tmp.name).glob("settings.json.pre_grip_*")))


if __name__ == "__main__":
    unittest.main()
