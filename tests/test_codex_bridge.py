"""Native hook contract and continuation boundaries, isolated from real chats."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "codex_bridge.py"
SID = "11111111-2222-3333-4444-555555555555"


class CodexBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.state = root / "mission" / "state.json"
        self.env = dict(os.environ, GRIP_CACHE_DIR=str(root / "cache"), CODEX_THREAD_ID=SID)
        self.manifest = root / "mission.json"
        self.manifest.write_text(json.dumps({
            "schema": 1, "mission_id": "codex-test", "objective": "Finish this fixture",
            "done_when": "Fixture outputs verified", "continuation_instructions": "Isolated test only",
            "context_refs": ["fixture"], "tasks": [
                {"id": "build", "content": "Implement the fixture", "done_when": "Fixture works", "status": "pending"},
                {"id": "check", "content": "Inspect outputs", "done_when": "Outputs verified", "status": "pending", "depends_on": ["build"]}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, payload=None, check=True):
        proc = subprocess.run([sys.executable, str(BRIDGE), *map(str, args)],
                              input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True, env=self.env, timeout=10)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def configure(self, *extra):
        return self.run_cli("--state", self.state, "configure", "--mission", self.manifest,
                            "--workspace", self.workspace, "--compute", "local fixture only", *extra)

    def activate(self):
        self.configure()
        self.run_cli("--state", self.state, "activate")

    def configure_infinite(self, *extra, check=True):
        return self.run_cli("--state", self.state, "configure-infinite", "--workspace", self.workspace,
                            "--compute", "local fixture only", "--instructions",
                            "Repair the current fixture, then existing approved backlog", *extra, check=check)

    def load(self):
        return json.loads(self.state.read_text())

    def save(self, state):
        self.state.write_text(json.dumps(state))

    def hook(self, event, **extra):
        payload = {"session_id": SID, "hook_event_name": event, "cwd": str(self.workspace),
                   "turn_id": "turn-1", "permission_mode": "default"}
        payload.update(extra)
        return json.loads(self.run_cli("hook", payload=payload).stdout)

    def progress(self, call="tool-1", **extra):
        self.hook("PreToolUse", tool_use_id=call, tool_name="exec_command", **extra)
        self.hook("PostToolUse", tool_use_id=call, tool_name="exec_command", **extra)

    def prediction(self, text="Continue the fixture", turn="turn-1", sid=SID, kind="completed"):
        return json.loads(self.run_cli("ingest-prediction", payload={
            "method": "thread/prediction/updated", "params": {
                "threadId": sid, "sourceTurnId": turn, "result": {"type": kind, "text": text}}}).stdout)

    def test_setup_stays_paused_and_reconfiguration_does_not_resume(self):
        self.configure()
        self.assertEqual(self.load()["status"], "paused")
        self.assertEqual(self.hook("Stop"), {})
        self.configure()
        self.assertEqual(self.load()["status"], "paused")

    def test_infinite_setup_needs_no_mission_and_activation_needs_desktop(self):
        self.configure_infinite()
        state = self.load()
        self.assertNotIn("mission_id", state)
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["status"], "paused")
        self.assertIsNone(state["maximum_wakes"])
        result = self.run_cli("--state", self.state, "activate", check=False)
        self.assertNotEqual(result.returncode, 0)
        state["codex"]["desktop"] = {"fixture": True}
        self.save(state)
        self.run_cli("--state", self.state, "activate")
        status = json.loads(self.run_cli("--state", self.state, "status").stdout)
        self.assertTrue(status["continuation_active"])
        self.assertEqual(status["continuation_mode"], "infinite")
        self.assertIsNone(status["maximum_wakes"])
        self.assertIsNone(status["next_task"])
        completed = self.load()
        completed["status"] = "complete"
        self.save(completed)
        status = json.loads(self.run_cli("--state", self.state, "status").stdout)
        self.assertTrue(status["continuation_active"])
        self.assertNotEqual(self.configure_infinite(check=False).returncode, 0)
        self.run_cli("--state", self.state, "pause")
        self.configure_infinite()
        self.assertFalse(self.load()["codex"]["infinite_active"])

    def test_infinite_conversion_keeps_completed_evidence_counts_and_deadline(self):
        self.configure("--max-wakes", "1", "--deadline", "2099-01-01T00:00:00+00:00")
        state = self.load()
        state["tasks"][0].update(status="completed", evidence=["saved-proof.json"])
        state["wake_count"] = 12
        self.save(state)
        self.configure_infinite()
        changed = self.load()
        self.assertEqual(changed["tasks"], state["tasks"])
        self.assertEqual(changed["objective_guard"], state["objective_guard"])
        self.assertEqual(changed["wake_count"], 12)
        self.assertEqual(changed["deadline"], state["deadline"])
        self.configure_infinite()
        self.assertEqual(changed, self.load())
        other = self.state.with_name("other.json")
        self.assertNotEqual(self.run_cli("--state", other, "configure-infinite", "--workspace", self.workspace,
                            "--compute", "fixture", "--instructions", "fixture", check=False).returncode, 0)

    def test_infinite_can_return_to_paused_mission_without_resetting_wakes(self):
        self.configure_infinite()
        state = self.load()
        state["wake_count"] = 23
        self.save(state)
        self.configure("--max-wakes", "50")
        state = self.load()
        self.assertEqual(state["codex"]["continuation_mode"], "mission")
        self.assertFalse(state["codex"]["infinite_active"])
        self.assertEqual(state["maximum_wakes"], 50)
        self.assertEqual(state["wake_count"], 23)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(len(state["tasks"]), 2)

    def test_infinite_pause_interrupt_and_deadline_remain_boundaries(self):
        self.configure_infinite()
        state = self.load()
        state["codex"]["desktop"] = {"fixture": True}
        self.save(state)
        self.run_cli("--state", self.state, "activate")
        self.hook("Interrupt")
        self.assertFalse(self.load()["codex"]["infinite_active"])
        self.assertEqual(self.hook("Stop"), {})
        self.run_cli("--state", self.state, "activate")
        self.hook("UserPromptSubmit", prompt="pause grip")
        self.hook("SessionStart")
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(self.load()["status"], "paused")
        state = self.load()
        state["deadline"] = "2000-01-01T00:00:00+00:00"
        self.save(state)
        self.assertNotEqual(self.run_cli("--state", self.state, "activate", check=False).returncode, 0)

    def test_unbound_wrong_workspace_and_subagents_are_inert(self):
        self.assertEqual(self.hook("Stop"), {})
        self.activate()
        before = self.state.read_bytes()
        self.assertEqual(self.hook("Stop", session_id="other"), {})
        self.assertEqual(self.hook("Stop", cwd="/different"), {})
        self.assertEqual(self.hook("Stop", agent_id="child"), {})
        self.assertEqual(self.state.read_bytes(), before)

    def test_fallback_then_progress_gated_continuations(self):
        self.activate()
        out = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(out["decision"], "block")
        self.assertIn("[GRIP AUTHORIZED CONTINUATION]", out["reason"])
        self.assertEqual(self.load()["codex"]["last_wake_source"], "grip_fallback")
        self.assertEqual(self.hook("Stop", stop_hook_active=True), {})
        self.progress()
        self.assertEqual(self.hook("Stop", stop_hook_active=True)["decision"], "block")
        self.assertEqual(self.load()["wake_count"], 2)

    def test_concurrent_duplicate_stop_cannot_dispatch_twice(self):
        self.activate()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.hook("Stop"), range(4)))
        self.assertEqual(sum(x.get("decision") == "block" for x in results), 1)
        self.assertEqual(self.load()["wake_count"], 1)

    def test_duplicate_tool_delivery_is_not_new_progress(self):
        self.activate()
        self.progress()
        self.hook("Stop")
        self.progress()
        self.assertEqual(self.hook("Stop"), {})

    def test_fresh_prediction_is_preferred_without_new_authority(self):
        self.activate()
        self.progress()
        self.assertTrue(self.prediction()["accepted"])
        out = self.hook("Stop")
        self.assertIn("Continue the fixture", out["reason"])
        self.assertIn("not new human authorization", out["reason"])
        self.assertEqual(self.load()["codex"]["last_wake_source"], "composer_prediction")

    def test_prediction_stale_wrong_thread_and_future_turn_rejected(self):
        self.activate()
        self.progress()
        self.assertFalse(self.prediction(turn="turn-0")["accepted"])
        self.assertFalse(self.prediction(turn="turn-2")["accepted"])
        self.assertFalse(self.prediction(sid="other")["accepted"])
        self.prediction()
        state = self.load()
        state["codex"]["prediction"]["received_at"] = time.time() - 121
        self.save(state)
        self.hook("Stop")
        self.assertEqual(self.load()["codex"]["last_wake_source"], "grip_fallback")

    def test_empty_and_failed_predictions_fall_back(self):
        for kind, text in [("completed", None), ("completed", "  "), ("failed", "bad")]:
            with self.subTest(kind=kind, text=text):
                self.activate()
                self.progress(str((kind, text)))
                self.prediction(text=text, kind=kind)
                self.hook("Stop")
                self.assertEqual(self.load()["codex"]["last_wake_source"], "grip_fallback")

    def test_user_prompt_invalidates_prediction_and_stop_pauses(self):
        self.activate()
        self.progress()
        self.prediction()
        self.hook("UserPromptSubmit", prompt="please pause GRIP, private words", turn_id="turn-2")
        state = self.load()
        self.assertEqual(state["status"], "paused")
        self.assertNotIn("prediction", state["codex"])
        self.assertNotIn("private words", self.state.read_text())
        self.assertEqual(self.hook("Stop"), {})

    def test_interrupt_survives_session_restart(self):
        self.activate()
        self.hook("Interrupt")
        self.hook("SessionStart")
        self.assertEqual(self.load()["status"], "paused")
        self.assertEqual(self.hook("Stop"), {})

    def test_interrupt_during_lock_contention_still_suppresses_wake(self):
        self.activate()
        with self.state.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.hook("Interrupt"), {})
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(self.load()["status"], "paused")
        self.run_cli("--state", self.state, "activate")
        self.assertEqual(self.hook("Stop")["decision"], "block")

    def test_plan_mode_and_missing_turn_cannot_wake(self):
        self.activate()
        self.assertEqual(self.hook("Stop", permission_mode="plan"), {})
        self.assertEqual(self.hook("Stop", turn_id=None), {})
        self.assertEqual(self.load()["wake_count"], 0)

    def test_deadline_and_wake_budget(self):
        self.configure("--max-wakes", "1")
        self.run_cli("--state", self.state, "activate")
        self.hook("Stop")
        self.progress()
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(self.load()["status"], "wake_budget")
        state = self.load()
        state.update(status="active", deadline="2000-01-01T00:00:00+00:00")
        self.save(state)
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(self.load()["status"], "deadline")

    def test_blocked_objective_and_completed_state_suppress_wakes(self):
        self.activate()
        state = self.load()
        state["objective_guard"]["status"] = "blocked"
        self.save(state)
        self.assertEqual(self.hook("Stop"), {})
        state = self.load()
        state["status"] = "complete"
        self.save(state)
        self.assertEqual(self.hook("Stop"), {})

    def test_setup_cannot_rebind_or_reset_progress(self):
        self.activate()
        self.hook("Stop")
        self.configure()
        self.assertEqual(self.load()["wake_count"], 1)
        other = self.state.with_name("other.json")
        proc = self.run_cli("--state", other, "configure", "--mission", self.manifest,
                            "--workspace", self.workspace, "--compute", "test", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(other.exists())

    def test_install_merges_idempotently_without_changing_trust_or_activating(self):
        target = Path(self.tmp.name) / "hooks.json"
        existing = {"description": "User settings", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-command"}]}]}}
        target.write_text(json.dumps(existing))
        self.run_cli("install-hooks", "--hooks-file", target)
        once = target.read_bytes()
        self.run_cli("install-hooks", "--hooks-file", target)
        self.assertEqual(once, target.read_bytes())
        data = json.loads(once)
        self.assertEqual(data["description"], "User settings")
        self.assertEqual(data["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
        self.assertEqual(len(data["hooks"]), 7)
        self.assertFalse(self.state.exists())

    def test_tool_and_prompt_contents_are_not_observation_logs(self):
        self.activate()
        self.hook("PreToolUse", tool_use_id="test", tool_input={"command": "PRIVATE-TOKEN"})
        self.hook("PostToolUse", tool_use_id="test", tool_response={"output": "PRIVATE-TOKEN"})
        self.assertNotIn("PRIVATE-TOKEN", self.state.read_text())
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_malformed_hook_is_nonblocking_and_nonleaking(self):
        proc = self.run_cli("hook", payload=["PRIVATE"])
        self.assertEqual(json.loads(proc.stdout), {})
        self.assertNotIn("PRIVATE", proc.stderr)


if __name__ == "__main__":
    unittest.main()
