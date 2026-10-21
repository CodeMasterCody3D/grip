"""No models or paid compute: durable queue, activation and fake-session proofs."""
import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grip
import mission
import objective_watch


def goal_report(s):
    return {**{k:s['objective_guard'][k] for k in ('objective','done_when','scope')},
            'signature':objective_watch.signature(s),'questions_reviewed':list(range(1,12)),
            'passed':True,'checks':{'full_objective_verified':True}}


def satisfy_goal(s, root):
    s['workspace']=str(root)
    grip.atomic(root/'goal.json',goal_report(s))
    objective_watch.review(s,result='satisfied',note='Fixture full-objective review',
                          evidence=grip.evidence_receipt(s,'goal.json'),report=grip.load(root/'goal.json'))
    mission.refresh(s)


def task(identifier, *, status="pending", deps=()):
    return {"id": identifier, "content": "Implement " + identifier, "status": status,
            "done_when": identifier + " has retained passing evidence", "depends_on": list(deps)}


def manifest():
    return {"schema": 1, "mission_id": "fixture-mission", "workspace": "/fixture", "session_id": "fixture",
            "session_directory": "/fixture", "objective": "Finish the existing integration",
            "done_when": "All selected checks and wiring complete", "continuation_instructions": "No new models or VMs",
            "context_refs": ["current chat: latest explicit decisions", "PROJECT.md"],
            "tasks": [task("consumer"), task("wiring", deps=["consumer"])]}


def state():
    return {"workspace": "/fixture", "session_id": "fixture", "session_directory": "/fixture", "status": "active", "tasks": []}


def active():
    result = state()
    mission.activate(result, manifest(), now="start")
    return result


class DurableTasks(unittest.TestCase):
    def update(self, state, identifier, status, **kwargs):
        return mission.update_task(state, identifier, status, "observed progress", now="now",
                                   expected=state["plan_revision"], **kwargs)

    def complete(self, state, identifier):
        return self.update(state, identifier, "completed", evidence=[{"path": "saved.json", "sha256": "fixture"}])

    def test_done_is_terminal_and_stale_edits_are_transactional(self):
        s = active()
        self.complete(s, "consumer")
        before = copy.deepcopy(s)
        with self.assertRaisesRegex(ValueError, "stay done"):
            self.update(s, "consumer", "pending")
        self.assertEqual(s, before)
        with self.assertRaisesRegex(ValueError, "Stale"):
            mission.update_task(s, "wiring", "in_progress", "outdated reminder", now="now", expected=1)
        self.assertEqual(s, before)
        with self.assertRaisesRegex(ValueError, "requires --revision"):
            mission.update_task(s, "wiring", "in_progress", "missing revision", now="now")

    def test_reopen_requires_explicit_flag_and_preserves_old_evidence(self):
        s = active()
        self.complete(s, "consumer")
        self.update(s, "consumer", "pending", reopen=True)
        self.assertEqual(s["tasks"][0]["status"], "pending")
        self.assertEqual(s["tasks"][0]["completion_history"][0]["evidence"][0]["path"], "saved.json")
        self.assertEqual(s["task_events"][-1]["before"], "completed")

    def test_cannot_reuse_historical_completion_evidence_after_reopen(self):
        s = active()
        self.complete(s, "consumer")
        self.update(s, "consumer", "pending", reopen=True)
        # A reopened task needs fresh evidence for its new attempt.
        with self.assertRaises(ValueError):
            self.update(s, "consumer", "completed")

    def test_in_progress_and_waiting_take_precedence_over_new_tasks(self):
        s = active()
        self.update(s, "consumer", "in_progress")
        self.assertEqual(mission.next_task(s)["id"], "consumer")
        self.update(s, "consumer", "waiting")
        self.assertEqual(mission.next_task(s)["status"], "waiting")
        snapshot = copy.deepcopy(s)
        mission.activate(s, manifest(), now="repeat activation")
        self.assertEqual(s, snapshot)

    def test_completion_requires_evidence_then_advances_dependency(self):
        s = active()
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.update(s, "consumer", "completed")
        self.complete(s, "consumer")
        self.assertEqual(mission.next_task(s)["id"], "wiring")
        self.complete(s, "wiring")
        self.assertEqual(s['status'],'active')
        self.assertEqual(mission.next_task(s)['id'],'grip:objective-review')
        with tempfile.TemporaryDirectory() as root:
            satisfy_goal(s,Path(root))
            self.assertEqual(s["status"], "complete")
            self.assertIsNone(mission.next_task(s))

    def test_repeat_activation_does_not_reset_done_or_create_another_plan(self):
        s = active()
        self.complete(s, "consumer")
        before = copy.deepcopy(s)
        mission.activate(s, manifest(), now="repeat")
        self.assertEqual(s, before)
        self.complete(s, "wiring")
        with tempfile.TemporaryDirectory() as root:
            satisfy_goal(s,Path(root))
            before = copy.deepcopy(s)
            result = mission.activate(s, manifest(), now="repeat after all done")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(s, before)

    def test_omitted_old_task_is_not_lost(self):
        s = active()
        plan = manifest()
        plan["tasks"] = plan["tasks"][:1]
        mission.activate(s, plan, now="repeat")
        self.assertEqual([task["id"] for task in s["tasks"]], ["consumer", "wiring"])

    def test_dependencies_and_single_active_ownership_refuse_bad_plan(self):
        for alter in ("cycle", "unknown", "two-active", "not-ready"):
            plan = manifest()
            if alter == "cycle":
                plan["tasks"][0]["depends_on"] = ["wiring"]
            elif alter == "unknown":
                plan["tasks"][0]["depends_on"] = ["missing"]
            elif alter == "two-active":
                plan["tasks"][1]["depends_on"] = []
                for item in plan["tasks"]:
                    item["status"] = "in_progress"
            else:
                plan["tasks"][1]["status"] = "in_progress"
            s = state()
            before = copy.deepcopy(s)
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                mission.activate(s, plan, now="bad")
            self.assertEqual(s, before)

    def test_blocked_and_parked_tasks_are_not_finished_or_restarted(self):
        s = active()
        self.update(s, "consumer", "blocked")
        self.assertEqual(s["status"], "blocked")
        self.assertIsNone(mission.next_task(s))
        self.update(s, "consumer", "parked")
        self.assertEqual(s["status"], "blocked")
        self.update(s, "consumer", "pending")
        self.assertEqual(s["status"], "active")

    def test_repeated_completion_is_idempotent(self):
        s = active()
        self.complete(s, "consumer")
        before = copy.deepcopy(s)
        self.complete(s, "consumer")
        self.assertEqual(s, before)

    def test_activation_cannot_change_scope_or_task_definition(self):
        for field in ("objective", "mission_id", "continuation_instructions", "content"):
            s, plan = active(), manifest()
            before = copy.deepcopy(s)
            if field == "content":
                plan["tasks"][0][field] = "Start from scratch"
            else:
                plan[field] = "new incompatible instruction"
            with self.subTest(field=field), self.assertRaises(ValueError):
                mission.activate(s, plan, now="new")
            self.assertEqual(s, before)

    def test_legacy_schedule_never_resets_completed_or_running_or_dispatch(self):
        for status in ("completed", "in_progress", "waiting"):
            s = state()
            s.update(tasks=[task("consumer", status=status)], dispatch_active="wake-1")
            mission.schedule(s, task_id="consumer", content="Implement consumer", instructions="same scope", now="now")
            self.assertEqual(s["tasks"][0]["status"], status)
            self.assertEqual(s["dispatch_active"], "wake-1")

    def test_legacy_schedule_cannot_bypass_durable_mission_guards(self):
        s = active()
        before = copy.deepcopy(s)
        with self.assertRaises(ValueError):
            mission.schedule(s, task_id="consumer", content="start over", instructions="new scope", now="now")
        self.assertEqual(s, before)

    def test_paused_mission_is_not_resumed_by_task_progress(self):
        s = active()
        s["status"] = "paused"
        self.complete(s, "consumer")
        self.assertEqual(s["status"], "paused")


class WakeSafety(unittest.TestCase):
    def test_all_done_suppresses_watchdog_before_any_network_calls(self):
        s = active()
        for item in s["tasks"]:
            item.update(status="completed", evidence=["existing result"])
        s["progress_watch"] = {"enabled": True}
        with tempfile.TemporaryDirectory() as root:
            satisfy_goal(s,Path(root))
            with patch.object(grip, "Client", side_effect=AssertionError("no calls after completion")):
                result = grip.tick(s)
            self.assertEqual(s["status"], "complete")
            self.assertEqual(result["reason"], "complete")

    def test_wake_says_read_latest_and_never_reopen_done(self):
        s = active()
        s.update(state_path="/fixture/state.json", compute_target="rig only")
        text = grip.prompt(s)
        for required in ("Reload state from disk", "Completed tasks stay completed", "never restart the project",
                         "waiting", "--revision", "interrupted", "BEFORE selecting another"):
            self.assertIn(required, text)

    def test_start_reuses_verified_watcher_without_launch(self):
        with patch.object(grip, "watcher_status", return_value={"alive": True, "pid": 7}), \
             patch.object(grip, "command", side_effect=AssertionError("duplicate watcher")):
            self.assertTrue(grip.start_watch("/fixture/state.json")["reused"])

    def test_foreign_named_tmux_is_never_overwritten(self):
        with patch.object(grip, "watcher_status", return_value={"alive": False}), \
             patch.object(grip.subprocess, "run", return_value=type("Exit", (), {"returncode": 0})()), \
             patch.object(grip, "command", side_effect=AssertionError("must not kill or replace")):
            with self.assertRaisesRegex(RuntimeError, "do not overwrite"):
                grip.start_watch("/fixture/state.json")

    def test_unknown_pid_cannot_count_as_running_watcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            grip.atomic(path.with_suffix(".watcher.json"), {"pid": os.getpid(), "start_ticks": grip.proc_start(os.getpid()), "state_path": str(path)})
            self.assertFalse(grip.watcher_status(path)["alive"])

    def test_wrong_session_activation_refuses_before_contact(self):
        s, plan = state(), manifest()
        plan["session_id"] = "another-chat"
        with patch.object(grip, "Client", side_effect=AssertionError("wrong connection")):
            with self.assertRaisesRegex(ValueError, "exact workspace/session"):
                grip.activate_mission(s, plan)


class SkillInstall(unittest.TestCase):
    def test_reviewed_replacement_vaults_previous_bytes_without_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "controller/skills/grip/SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("new reviewed trigger instructions")
            target = root / "user/.agents/skills/grip/SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("old installed instructions")
            old = target.read_bytes()
            with patch.object(grip, "HOME", root / "controller"), patch.object(grip.Path, "home", return_value=root / "user"):
                with self.assertRaises(ValueError):
                    grip.install_skill()
                with self.assertRaises(ValueError):
                    grip.install_skill("incorrect")
                self.assertEqual(target.read_bytes(), old)
                result = grip.install_skill(grip.sha(old))
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertFalse(result["activation_started"])
                self.assertEqual((root / "controller/code_vault" / grip.sha(old)[:2] / grip.sha(old)).read_bytes(), old)
                self.assertEqual(grip.install_skill()["sha256"], result["sha256"])


@unittest.skipUnless(shutil.which("tmux"), "needs tmux for actual watcher lifecycle")
class WatcherLifecycle(unittest.TestCase):
    """Real tmux/poller/CLI, fake HTTP session. No inference or GitHub writes."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="grip-activation-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "state.json"
        self.state = state()
        self.writes = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                route = self.path.split("?", 1)[0]
                if route == "/session/fixture":
                    result = {"id": "fixture", "directory": str(owner.root)}
                elif route == "/session/status":
                    result = {"fixture": {"type": "idle"}}
                elif route == "/session/fixture/message":
                    result = [{"info": {"id": "final", "role": "assistant", "finish": "stop",
                                         "time": {"created": time.time()*1000-10, "completed": time.time()*1000}}, "parts": []}]
                else:
                    self.send_error(404)
                    return
                body = json.dumps(result).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                owner.writes.append(self.path)
                self.send_error(500, "fixture must never dispatch work")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        secret = self.root / "secret"
        secret.write_text("fixture-only-not-a-real-credential")
        self.state.update(workspace=str(self.root), session_directory=str(self.root), server_url="http://127.0.0.1:"+str(self.server.server_port),
                          server_secret_file=str(secret), state_path=str(self.path), project_id="fixture", provider_id="fixture", model_id="fixture",
                          compute_target="fake session only", source_roots=[], github_repo="fixture/private", poll_seconds=0.05,
                          idle_grace_seconds=300, maximum_packet_seconds=60,
                          deadline=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat(), deadline_basis="test fixture")
        self.plan = manifest()
        self.plan.update(workspace=str(self.root), session_directory=str(self.root))
        self.plan_path = self.root / "mission.json"
        grip.atomic(self.plan_path, self.plan)
        self.profile = self.root / "profile.json"
        grip.atomic(self.profile, self.state)
        self.addCleanup(self.stop_owned_watcher)

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(grip.HOME / "grip.py"), "--state", str(self.path), *args],
                                cwd=grip.HOME, capture_output=True, text=True, timeout=15)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result

    def stop_owned_watcher(self):
        record = grip.watcher_status(self.path)
        if record["alive"]:
            os.kill(record["pid"], signal.SIGTERM)
            until = time.monotonic()+4
            while grip.watcher_status(self.path)["alive"] and time.monotonic() < until:
                time.sleep(0.02)
            self.assertFalse(grip.watcher_status(self.path)["alive"], "owned fixture watcher did not stop")

    def test_activation_starts_once_reuses_and_all_done_stops_waking(self):
        result = self.cli("activate", "--mission", str(self.plan_path), "--profile", str(self.profile))
        self.assertTrue(result["watcher"]["alive"])
        first = result["watcher"]["pid"]
        repeated = self.cli("activate", "--mission", str(self.plan_path))
        self.assertTrue(repeated["watcher"]["reused"])
        self.assertEqual(repeated["watcher"]["pid"], first)
        (self.root / "result.json").write_text('{"fixture":"passed"}')
        for identifier in ("consumer", "wiring"):
            revision = grip.load(self.path)["plan_revision"]
            self.cli("task", "--id", identifier, "--status", "completed", "--note", "verified fixture", "--revision", str(revision),
                     "--evidence", "result.json")
        current = self.cli("status")
        self.assertEqual(current['status'],'active')
        self.assertEqual(current['next_task']['id'],'grip:objective-review')
        grip.atomic(self.root/'goal.json',goal_report(grip.load(self.path)))
        self.cli('goal-review','--result','satisfied','--note','Actual fixture goal closure',
                 '--evidence','goal.json','--revision',str(current['plan_revision']))
        current=self.cli('status')
        self.assertEqual(current["status"], "complete")
        self.assertIsNone(current["next_task"])
        again = self.cli("activate", "--mission", str(self.plan_path))
        self.assertEqual(again["status"], "complete")
        self.assertFalse(again["watcher"]["started"])
        self.assertEqual(self.writes, [])

    def test_configure_only_does_not_start_and_invalid_evidence_preserves_state(self):
        result = self.cli("activate", "--mission", str(self.plan_path), "--profile", str(self.profile), "--configure-only")
        self.assertFalse(result["watcher"]["started"])
        self.assertFalse(grip.watcher_status(self.path)["alive"])
        before = self.path.read_bytes()
        self.cli("task", "--id", "consumer", "--status", "completed", "--note", "not saved", "--revision", "1", "--evidence", "missing.json", success=False)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
