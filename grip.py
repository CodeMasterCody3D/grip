#!/usr/bin/env python3
"""External single-session GRIP proxy. Stdlib orchestration; never trains models."""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import select
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import progress_watch
import mission
import completion
import event_hooks
import stream_events
import v2_control
import objective_watch

HOME = Path(__file__).resolve().parent
EXTENSIONS = {".py", ".md", ".json", ".js", ".mjs", ".ts", ".yaml", ".yml", ".toml", ".txt", ".svg", ".yml"}
IGNORE = {".git", "__pycache__", "node_modules", ".venv", "hf-transfer-cache", "cache", "code_vault"}
MARKER = "[GRIP AUTHORIZED CONTINUATION]"

def stamp(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(Path(path).read_text())
def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(tmp, path)

@contextmanager
def locked(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def command(args, cwd=HOME, timeout=60, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[-500:]}")
    return result.stdout.strip()

def project(state): return Path(state["workspace"]).resolve()
def storage(state):
    """An explicitly selected private backup checkout; legacy profiles retain HOME."""
    return Path(state.get("backup_directory", HOME)).expanduser().resolve()

def area(state):
    identifier = state["project_id"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier):
        raise ValueError("project_id must be a single safe directory name")
    return storage(state) / "projects" / identifier

def installed_skill_path():
    return Path(os.environ.get("GRIP_SKILL_PATH", Path.home() / ".agents/skills/grip/SKILL.md")).expanduser().absolute()
def owned(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root) or p == root or any(x in relative.split("/") for x in (".git", ".venv")):
        raise ValueError("Owned file escapes project scope")
    return p

def clean_payload(path, data):
    text = data.decode("utf-8", errors="replace")
    for name, value in os.environ.items():
        if re.search(r"TOKEN|PASSWORD|API_KEY|SECRET", name) and len(value) >= 12 and value.encode() in data:
            raise ValueError(f"Credential-bearing file refused:{path}")
    patterns = (r'(?i)(?:apiKey|api_key|access_token)\s*["\']?\s*[:=]\s*["\']([A-Za-z0-9_.-]{24,})["\']',
                r'(?i)Bearer\s+[A-Za-z0-9_.-]{24,}', r'gh[pousr]_[A-Za-z0-9]{25,}')
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError(f"Possible hardcoded credential refused:{path}")

def source_files(state):
    root = project(state)
    for relative in dict.fromkeys(state["source_roots"] + state.get("completion", {}).get("source_paths", [])):
        start = owned(root, relative)
        candidates = [start] if start.is_file() else (
            Path(parent) / name for parent, dirs, names in os.walk(start, followlinks=False)
            for _ in [dirs.__setitem__(slice(None), sorted(d for d in dirs if d not in IGNORE))]
            for name in sorted(names))
        for path in candidates:
            if path.is_symlink() or not path.is_file() or path.suffix not in EXTENSIONS:
                continue
            if path.name in ("opencode.json", "opencode.jsonc") or path.stat().st_size > state.get("max_source_file_bytes", 4194304):
                continue
            yield path
    for pattern in state.get("metadata_globs", []):
        for path in root.glob(pattern):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 4194304:
                yield path

def vault(state, paths=None):
    root = project(state); result = {}
    files = source_files(state) if paths is None else [owned(root, relative) for relative in paths]
    for path in files:
        relative = str(path.relative_to(root))
        if not path.exists():
            result[relative] = {"exists": False}; continue
        data = path.read_bytes(); clean_payload(relative, data); identity = sha(data)
        destination = storage(state) / "code_vault" / identity[:2] / identity
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha(destination.read_bytes()) != identity: raise RuntimeError("Vault corruption")
        else:
            with destination.open("xb") as f: f.write(data)
        result[relative] = {"exists": True, "sha256": identity, "bytes": len(data), "mode": path.stat().st_mode & 0o777}
    return result

def backup(state, note):
    root = storage(state)
    if not root.is_dir():
        raise ValueError("backup_directory must name an existing private Git checkout")
    def git(args, **kwargs):
        return command(["git", *args], cwd=root, **kwargs)
    if Path(git(["rev-parse", "--show-toplevel"])).resolve() != root:
        raise ValueError("backup_directory must be the Git repository root")
    if shutil.disk_usage(root).free < state.get("minimum_free_bytes", 5368709120):
        raise RuntimeError("GRIP storage floor reached; checkpoint/cleanup decision required")
    expected = state["github_repo"]
    if command(["gh", "repo", "view", expected, "--json", "isPrivate", "--jq", ".isPrivate"], cwd=root) != "true":
        raise RuntimeError("GRIP backup remote must be private")
    remote = git(["remote", "get-url", "origin"])
    if not remote.endswith(expected + ".git") and not remote.endswith(expected):
        raise RuntimeError("GRIP remote identity mismatch")
    branch = state.get("backup_branch") or git(["branch", "--show-current"])
    if not branch or git(["branch", "--show-current"]) != branch:
        raise ValueError("Check out the configured backup_branch before backing up")
    command(["git", "check-ref-format", "--branch", branch], cwd=root)
    git(["status", "--short"])
    git(["diff", "--stat"])
    git(["log", "--oneline", "-10"], check=False)
    staged = git(["diff", "--cached", "--name-only"]).splitlines()
    if any(not name.startswith(("code_vault/", "projects/")) for name in staged):
        raise ValueError("Unrelated staged work in backup repository; automatic commit refused")
    atomic(area(state) / "MISSION.json", {key: state.get(key) for key in (
        "workspace", "project_id", "status", "deadline", "compute_target", "tasks", "families",
        "best", "best_by_contract", "active_iteration", "last_iteration", "minimum_method_attempts",
        "mission_id", "objective", "done_when", "context_refs", "plan_revision", "task_events",
         "operating_mode", "completion", "native_event_health", "last_hook_event", "objective_guard", "objective_history")})
    git(["add", "--", "code_vault", "projects"])
    if git(["diff", "--cached", "--name-only"]):
        git(["commit", "-m", note[:160]], timeout=120)
    git(["push", "origin", branch], timeout=120)
    head = git(["rev-parse", "HEAD"])
    observed = git(["ls-remote", "origin", "refs/heads/" + branch]).split()[0]
    if head != observed: raise RuntimeError("Private backup commit not observed remotely")
    return head

def checkpoint(state, note):
    snapshot = vault(state)
    identity = sha(json.dumps(snapshot, sort_keys=True).encode())
    destination = area(state) / "checkpoints" / (identity + ".json")
    if not destination.exists():
        atomic(destination, {"created_at": stamp(), "note": note, "source": snapshot})
    atomic(area(state) / "LATEST.json", {"snapshot": identity, "note": note, "at": stamp()})
    return {"snapshot": identity, "commit": backup(state, state["project_id"] + ": " + note)}

def deadline_reached(state, margin=0, now=None):
    deadline=state.get("deadline")
    return bool(deadline and (time.time() if now is None else now)+margin >= datetime.fromisoformat(deadline).timestamp())

def begin(state, args):
    if state["status"] != "active" or state.get("active_iteration"):
        raise ValueError("Mission paused or another iteration owns the lease")
    if deadline_reached(state, args.estimate_seconds + state.get("backup_margin_seconds", 120)):
        raise ValueError("Packet plus backup margin would cross mission deadline")
    if args.estimate_seconds < 1 or args.estimate_seconds > state["maximum_packet_seconds"]:
        raise ValueError("Packet exceeds authorized bounded duration")
    identifier = f"i{state.get('iteration_count', 0)+1:04d}"
    folder = area(state) / "iterations" / identifier
    before = vault(state, args.file)
    record = {"id": identifier, "status": "running", "family": args.family,
              "hypothesis": args.hypothesis, "mirror_hypothesis": args.mirror, "what_changes": args.change,
              "owned_files": args.file, "before": before, "started_at": stamp(), "estimated_seconds": args.estimate_seconds}
    atomic(folder / "ITERATION.json", record)
    commit = backup(state, f"{state['project_id']}: {identifier} before {args.family}")
    state.update(active_iteration=identifier, iteration_count=state.get("iteration_count", 0)+1)
    return {"iteration": identifier, "before_commit": commit, "owned_files": args.file}

def finish(state, args):
    folder = area(state) / "iterations" / args.iteration
    record = load(folder / "ITERATION.json")
    if record["status"] != "running" or state.get("active_iteration") != args.iteration:
        raise ValueError("Iteration lease/status mismatch")
    evidence = owned(project(state), args.evidence)
    if not evidence.is_file(): raise ValueError("Actual saved evidence is required")
    record.update(status=args.verdict, reason=args.reason, finished_at=stamp(),
                  after=vault(state, record["owned_files"]),
                  evidence={"path": args.evidence, "sha256": sha(evidence.read_bytes())},
                  evidence_snapshot=vault(state, [args.evidence]))
    if args.best:
        best = owned(project(state), args.best)
        if args.verdict != "better" or not best.is_file() or not args.metric_contract:
            raise ValueError("Only a verified better saved artifact may be promoted")
        key = record["family"] + ":" + args.metric_contract
        by_contract = state.setdefault("best_by_contract", {})
        previous = by_contract.get(key)
        by_contract[key] = {"path": args.best, "sha256": sha(best.read_bytes()), "iteration": args.iteration,
                            "metric_contract": args.metric_contract, "previous": previous}
        record["new_best"] = by_contract[key]
    atomic(folder / "ITERATION.json", record)
    family = state.setdefault("families", {}).setdefault(args.family or record["family"], {"attempts": []})
    family["attempts"].append({"id": args.iteration, "verdict": args.verdict, "change": record["what_changes"], "reason": args.reason})
    family["minimum_distinct_attempts"] = state.get("minimum_method_attempts", 3)
    family["distinct_attempt_count"] = family.get("prior_distinct_attempts", 0) + len({a["change"] for a in family["attempts"]})
    family["can_park_after_failure"] = family["distinct_attempt_count"] >= family["minimum_distinct_attempts"]
    record["backup_commit"] = backup(state, f"{state['project_id']}: {args.iteration} {args.verdict} {record['family']}")
    state["active_iteration"] = None
    state["last_iteration"] = {"id": args.iteration, "verdict": args.verdict, "reason": args.reason, "commit": record["backup_commit"]}
    return state["last_iteration"]

def rollback(state, identifier):
    folder = area(state) / "iterations" / identifier
    record = load(folder / "ITERATION.json")
    if "after" not in record: raise ValueError("Bank candidate state before rollback")
    root = project(state)
    for relative, expected in record["after"].items():
        path = owned(root, relative)
        if path.exists() != expected["exists"] or (path.exists() and sha(path.read_bytes()) != expected["sha256"]):
            raise ValueError("Concurrent user change; rollback refused:" + relative)
    payloads = {}
    for relative, before in record["before"].items():
        if before["exists"]:
            payload = (storage(state) / "code_vault" / before["sha256"][:2] / before["sha256"]).read_bytes()
            if sha(payload) != before["sha256"]: raise RuntimeError("Vault corruption")
            payloads[relative] = payload
    for relative, before in record["before"].items():
        path = owned(root, relative)
        if before["exists"]:
            payload = payloads[relative]
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".grip-restore")
            tmp.write_bytes(payload); os.chmod(tmp, before["mode"]); os.replace(tmp, path)
        elif path.exists(): path.unlink()
    atomic(folder / "ROLLBACK.json", {"at": stamp(), "owned_files": record["owned_files"], "candidate_preserved": True})
    return {"rolled_back": identifier, "candidate_preserved": True}

def message_text(message):
    return " ".join(p.get("text", "") for p in message.get("parts", []) if p.get("type") == "text")

def eligible(state, status, messages, now=None):
    now = time.time() if now is None else now
    if state.get("status") != "active" or deadline_reached(state, now=now): return False
    if mission.next_task(state) is None: return False
    if status.get("type") != "idle" or not messages: return False
    if event_hooks.suppress(state, messages): return False
    latest = max(messages, key=lambda m: m["info"]["time"]["created"])
    info = latest["info"]
    # Persisted final-turn proof is required even if another server's in-memory
    # status map cannot see the TUI's active loop. Tool-call completions are not idle.
    if info.get("role") != "assistant" or info.get("finish") != "stop" or not info["time"].get("completed") or info.get("error"): return False
    users = [m for m in messages if m["info"].get("role") == "user"]
    if users:
        user = max(users, key=lambda m: m["info"]["time"]["created"])
        if re.match(r"\s*(stop|pause|cancel|hold on)\b", message_text(user), re.I): return False
    return not any(p.get("type") == "tool" and p.get("state", {}).get("status") in ("running", "pending") for m in messages for p in m.get("parts", []))

class Client:
    """Existing OpenCode HTTP/session API; localhost only, no new inference bus."""
    def __init__(self, state):
        self.state = state
        parsed = urllib.parse.urlsplit(state["server_url"])
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Only an owned loopback OpenCode server is supported")
    def request(self, path, body=None):
        if self.state.get('server_api') == 'v2':
            return v2_control.request(self,path,body)
        return self.http(path,body)
    def http(self, path, body=None, method=None):
        query = urllib.parse.urlencode({"directory": self.state["session_directory"]}) if self.state.get('server_api') != 'v2' else ''
        url = self.state["server_url"].rstrip("/") + path + (("&" if "?" in path else "?") + query if query else '')
        password = event_hooks.control_password(self.state)
        headers = {"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(("opencode:"+password).encode()).decode()}
        req = urllib.request.Request(url, headers=headers, data=None if body is None else json.dumps(body).encode(), method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
        return json.loads(data) if data else None
    def snapshot(self):
        sid = self.state["session_id"]
        info = self.request("/session/" + sid)
        if info["id"] != sid or info["directory"] != self.state["session_directory"]:
            raise ValueError("Session identity/directory mismatch")
        status = self.request("/session/status").get(sid, {"type": "idle"})
        messages = self.request("/session/" + sid + "/message?limit=32")
        return status, messages

def prompt(state):
    tasks = [{key: t.get(key) for key in ("id", "content", "status", "done_when", "depends_on", "note", "evidence")}
             for t in state["tasks"]]
    skill = state.get("skill_path", str(installed_skill_path()))
    return (MARKER + "\nContinue the current project and apply the GRIP skill. Continue the explicitly authorized GRIP mission in " + state["workspace"] + ". "
        "Read " + skill + ", project AGENTS.md, PROJECT.md, current records and " + state["state_path"] + ". "
        "Controller CLI: " + shlex.join([sys.executable, str(HOME/"grip.py"), "--state", state["state_path"]]) + ". "
        "Latest explicit policy:several distinct justified attempts per method (minimum" + str(state.get("minimum_method_attempts",3)) + "), mirror/opposite hypotheses, preserve best, "
        "bank every iteration privately; rotate/revisit rather than declare an idea dead after one failure. "
        "Use GRIP begin before edits and finish/rollback after evidence. Do not just update a task list:execute one useful bounded packet. "
        "No new VMs. Workers require explicit current user authorization and the tmux workflow. Use the authorized compute/tools: " + state["compute_target"] + ". "
        "Scheduling window: " + (state.get("deadline") or "until user stops or pauses; verify runtime availability/lifetime before compute") + ". Honor newer human stop/pause immediately. "
        "Keep source/data/format and failed arms; judge actual task outputs and compatible metrics. Recover any active iteration first. "
        "Use the task CLI for queue changes, not whole-state rewrites; finish/checkpoint the packet before final. "
        "Project scope: " + state.get("continuation_instructions", "Follow the recorded project authorization; do not import another project's recipe.") + " "
        "This wake is a reminder, NOT a new assignment. Reload state from disk before acting: the embedded revision "
        + str(mission.revision(state)) + " may already be stale. Completed tasks stay completed; never restart the project or recreate the checklist. "
        "Inspect/resume an in_progress or waiting task and its existing job before launching anything. If completion was interrupted, "
        "inspect saved evidence and reconcile rather than repeating work. Mark verified tasks completed with evidence BEFORE selecting another. "
        "Use task --revision CURRENT to reject stale edits. Reopening needs explicit --reopen and a concrete reason, never just this wake. "
        "If task work is done, review the FULL objective through goal-review before closing; blocked is not done. Do not manufacture experiments. "
        "Mode1 status: " + json.dumps(state.get("completion", {}), ensure_ascii=False) + ". "
        "If Mode1 is selected, empty task lists are NOT project completion: recover missing specs, add necessary in-scope gap tasks, "
        "verify requirements, audit the whole spec, then challenge provisional green through real end-to-end use and counterexamples. "
        "Never invent Modes2/3 or enlarge permissions. Report programmed versus trained versus integrated versus measured. "
        "Objective: " + state.get("objective", "Follow existing mission") + ". Mission done when: " + state.get("done_when", "existing scope completed") + ". "
         "Current task snapshot (completed entries are history, not instructions): " + json.dumps(tasks, ensure_ascii=False)
         + objective_watch.prompt(state))

def alert(state, text):
    path = Path(state.get("alarm_script", ""))
    if path.is_file():
        subprocess.Popen([str(path), "ERROR", "GRIP: " + text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def progress_note(state,client,assessment,kind='watchdog'):
    memory=state.setdefault('progress_watch_state',{})
    text=(MARKER+'\n[GRIP PROGRESS CHECK] Continue the current project and apply GRIP. '
          +assessment.get('reason','Progress watchdog delivery check')+'. '
          'Inspect actual assigned-VM job/progress and recover the active iteration. '
          'Launch the prepared bounded test now if ready;otherwise state the specific blocker and next concrete action. '
          'Tool calls or a busy chat flag alone do not establish progress. Do not duplicate/kill a healthy model job or spawn agents/VMs. '
          +' State: '+state.get('state_path','recorded GRIP mission')+'. Active iteration: '+str(state.get('active_iteration'))+'. '
          'Reload the current plan revision first. Completed tasks stay done; inspect/resume the recorded running job rather than launch it again. '
          'This reminder cannot reopen a task or supersede newer user instructions. Report the concrete action,not another broad plan.')
    identifier='msg_'+format(int(time.time()*1000),'x')+secrets.token_hex(9)
    client.request('/session/'+state['session_id']+'/prompt_async',{'messageID':identifier,'noReply':True,
        'parts':[{'type':'text','text':text}]})
    memory.update(last_notice_at=time.time(),pending={'message_id':identifier,'sent_at':time.time(),'kind':kind})
    receipt={'at':stamp(),'stage':'progress_note_sent','message_id':identifier,'kind':kind,'assessment':assessment}
    atomic(area(state)/'LAST_PROGRESS_NUDGE.json',receipt)
    return receipt

def progress_intervention(state,client,status,messages,dry=False):
    if not state.get('progress_watch',{}).get('enabled'):return None
    assessment=progress_watch.assess(state,progress_watch.observe(state,HOME),messages)
    action=assessment['action']
    if dry:return assessment
    if action=='send_note':return progress_note(state,client,assessment)
    if action not in ('recover_owned_stall','resume_after_note'):return assessment
    # Recheck human ownership/tool/job signals immediately before any recovery.
    fresh_status,fresh_messages=client.snapshot()
    users=[m for m in fresh_messages if m['info'].get('role')=='user']
    newest=max(users,key=lambda m:m['info']['time']['created']) if users else None
    if newest is None or not message_text(newest).startswith(MARKER):return {'action':'human_turn_protected'}
    fresh=progress_watch.assess(state,progress_watch.observe(state,HOME),fresh_messages)
    if fresh['action'] not in ('recover_owned_stall','resume_after_note'):return fresh
    if fresh['action']=='recover_owned_stall':
        if not state.get('dispatch_active'):return {'action':'non_owned_turn_protected'}
        checkpoint(state,'bank before no-progress recovery')
        check_status,check_messages=client.snapshot()
        human=[m for m in check_messages if m['info'].get('role')=='user']
        if not human or not message_text(max(human,key=lambda m:m['info']['time']['created'])).startswith(MARKER):return {'action':'fresh_human_protected'}
        if progress_watch.active_tools(check_messages):return {'action':'fresh_tool_protected'}
        decision=progress_watch.assess(state,progress_watch.observe(state,HOME),check_messages)
        if decision['action']!='recover_owned_stall':return decision
        client.request('/session/'+state['session_id']+'/abort',{})
        fresh_status,fresh_messages=client.snapshot()
        if fresh_status.get('type')!='idle':return {'action':'waiting_for_owned_abort'}
        errors=[m['info'] for m in fresh_messages if (m['info'].get('error') or {}).get('name')=='MessageAbortedError']
        if errors:state['last_agent_error_id']=max(errors,key=lambda i:i['time']['created'])['id']
    elif fresh_status.get('type')!='idle':return {'action':'wait_for_turn_completion'}
    client.request('/session/'+state['session_id']+'/prompt_async',{'agent':'build',
        'model':{'providerID':state['provider_id'],'modelID':state['model_id']},
        'parts':[{'type':'text','text':MARKER+'\n[GRIP PROGRESS RECOVERY] Resume the saved active iteration and apply GRIP. Launch ready work or identify a concrete blocker immediately.\n'+prompt(state)}]})
    state['wake_count']=state.get('wake_count',0)+1;state['dispatch_active']='progress-recovery-'+str(state['wake_count'])
    state['dispatched_at_ms']=int(time.time()*1000)
    state['progress_watch_state'].pop('pending',None);state['progress_watch_state']['last_material_at']=time.time()
    receipt={'at':stamp(),'stage':'progress_recovery_accepted','reason':action,'wake':state['dispatch_active']}
    atomic(area(state)/'LAST_PROGRESS_NUDGE.json',receipt);return receipt

def tick(state, dry=False):
    if not dry:
        completion.sync(state)
        mission.refresh(state)
    if state.get("status") != "active":
        if not dry and state.get('server_api') == 'v2' and state.get('dispatch_receipt'):
            v2_control.cancel_pending(Client(state))
            state['dispatch_active'] = None
        return {"at":stamp(), "stage":"paused", "reason":state.get("status")}
    # A completed/blocked queue cannot be restarted by the progress watchdog.
    if mission.next_task(state) is None and not state.get("active_iteration"):
        return {"at":stamp(), "stage":"suppressed", "reason":"no actionable tasks"}
    client = Client(state)
    status, messages = client.snapshot()
    if state.get('server_api') == 'v2':
        human = [m for m in messages if m['info'].get('role') == 'user']
        newest_human = max(human, key=lambda m:m['info']['time']['created']) if human else None
        if newest_human and re.match(r'\s*(stop|pause|cancel|hold on)\b', message_text(newest_human), re.I):
            v2_control.cancel_pending(client)
            state.update(status='paused', dispatch_active=None)
            return {'at':stamp(), 'stage':'paused', 'reason':'new human stop/pause; active tools not interrupted'}
    blocked = event_hooks.suppress(state, messages)
    if blocked:
        return {"at": stamp(), "stage": "suppressed", "reason": blocked}
    latest = max(messages, key=lambda m: m["info"]["time"]["created"]) if messages else None
    heartbeat = {"at": stamp(), "session": state["session_id"], "server_status": status, "stage": "suppressed"}
    if latest:
        heartbeat.update(latest_role=latest["info"].get("role"),latest_finish=latest["info"].get("finish"),
                         latest_completed=latest["info"].get("time",{}).get("completed"))
    if deadline_reached(state):
        state["status"] = "deadline"
        if not state.get("deadline_alarm"):
            checkpoint(state, "deadline checkpoint"); alert(state, "Operating deadline reached; work banked, review assigned VM."); state["deadline_alarm"] = True
        heartbeat["reason"] = "mission deadline"; return heartbeat
    # Only this proxy's running session may be aborted when a newer human takes over.
    users = [m for m in messages if m["info"].get("role") == "user"]
    newest_user = max(users, key=lambda m:m["info"]["time"]["created"]) if users else None
    if (state.get("dispatch_active") and newest_user and not message_text(newest_user).startswith(MARKER)
            and newest_user["info"]["time"]["created"] > state.get("dispatched_at_ms", 0)):
        if state.get('server_api') == 'v2': v2_control.cancel_pending(client)
        elif status.get("type") != "idle": client.request("/session/"+state["session_id"]+"/abort", {})
        state["dispatch_active"] = None
        heartbeat["stage"] = "human_took_over"
        if re.match(r"\s*(stop|pause|cancel|hold on)\b", message_text(newest_user), re.I): state["status"] = "paused"
        return heartbeat
    if newest_user and re.match(r"\s*(stop|pause|cancel|hold on)\b", message_text(newest_user), re.I):
        if state.get('server_api') == 'v2': v2_control.cancel_pending(client)
        if state.get("dispatch_active") and status.get("type") != "idle" and state.get('server_api') != 'v2': client.request("/session/"+state["session_id"]+"/abort", {})
        state["status"] = "paused"; heartbeat["reason"] = "new human stop/pause"; return heartbeat
    progress=progress_intervention(state,client,status,messages,dry)
    if progress:
        heartbeat['progress_watch']=progress
        if progress.get('stage') in ('progress_note_sent','progress_recovery_accepted'):return heartbeat
    if state.get("dispatch_active"):
        dispatch_id = state["dispatch_active"]
        if status.get("type") != "idle":
                heartbeat["stage"] = "agent_started" if state.get('server_api') != 'v2' or (newest_user and message_text(newest_user).startswith(MARKER)) else 'awaiting_dispatch_delivery'
        elif (latest and latest["info"].get("finish") == "stop" and latest["info"]["time"].get("completed")
              and (state.get('server_api') != 'v2' or (latest['info']['time']['created'] >= state.get('dispatched_at_ms',0)
                   and newest_user and message_text(newest_user).startswith(MARKER)))):
            heartbeat["stage"] = "agent_turn_completed"; state["dispatch_active"] = None
            checkpoint(state, "completed autonomous turn " + dispatch_id)
    if latest and latest["info"].get("error") and status.get("type") == "idle":
        error=latest['info']['error']
        if error.get('name')=='MessageAbortedError' and newest_user and not message_text(newest_user).startswith(MARKER) and newest_user['info']['time']['created']>state.get('dispatched_at_ms',0):
            state['last_agent_error_id']=latest['info']['id'];heartbeat['stage']='human_handoff';return heartbeat
        if state.get("last_agent_error_id") != latest["info"]["id"]:
            state["last_agent_error_id"] = latest["info"]["id"]
            state["status"] = "agent_error"
            checkpoint(state, "agent error checkpoint")
            alert(state, "Agent returned an error; work banked, inspect credentials/quota/session before resuming.")
        heartbeat["stage"] = "agent_error"; return heartbeat
    if not eligible(state, status, messages): return heartbeat
    info = latest["info"]; fingerprint = info["id"] + ":" + str(info["time"]["completed"])
    if state.get("last_dispatched_fingerprint") == fingerprint: return heartbeat
    if time.time()*1000 - info["time"]["completed"] < state["idle_grace_seconds"]*1000: return heartbeat
    if state.get("maximum_wakes") is not None and state.get("wake_count", 0) >= state["maximum_wakes"]:
        state["status"] = "wake_budget"; alert(state, "Wake budget reached; inspect saved handoff."); return heartbeat
    # Back up before dispatch, then repeat the freshness check after network I/O.
    if not dry: checkpoint(state, "before autonomous continuation")
    fresh_status, fresh_messages = client.snapshot()
    newest = max(fresh_messages, key=lambda m:m["info"]["time"]["created"])
    if newest["info"]["id"] != info["id"] or not eligible(state, fresh_status, fresh_messages):
        heartbeat["reason"] = "freshness race suppressed"; return heartbeat
    heartbeat["stage"] = "would_dispatch" if dry else "api_accepted"
    if not dry:
        state["dispatched_at_ms"] = int(time.time()*1000)
        accepted = client.request("/session/"+state["session_id"]+"/prompt_async", {
            "agent": "build", "model": {"providerID": state["provider_id"], "modelID": state["model_id"]},
            "parts": [{"type": "text", "text": prompt(state)}]})
        state["last_dispatched_fingerprint"] = fingerprint
        state["wake_count"] = state.get("wake_count", 0)+1
        state["dispatch_active"] = f"wake-{state['wake_count']}"
        if isinstance(accepted,dict): state['dispatch_receipt'] = {'id':accepted.get('id')}
        atomic(area(state)/"LAST_WAKE.json", {"at":stamp(),"stage":"api_accepted",
               "wake":state["dispatch_active"],"parent_final_message":info["id"]})
        try:
            backup(state, state["project_id"] + ": " + state["dispatch_active"] + " accepted")
        except Exception as exc:
            # The pre-dispatch source backup already passed. Persist the accepted
            # wake even if its additional receipt push has a transient failure.
            state["wake_receipt_backup_error"]={"at":stamp(),"type":type(exc).__name__}
            heartbeat["receipt_backup"]="pending"
            alert(state,"Wake accepted; receipt push failed. Pre-dispatch source is banked; inspect backup status.")
    return heartbeat

def serve(state):
    path = Path(state["server_secret_file"]); path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        descriptor = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as f: f.write(secrets.token_urlsafe(36))
    env = dict(os.environ, OPENCODE_SERVER_PASSWORD=path.read_text().strip())
    port = urllib.parse.urlsplit(state["server_url"]).port
    return subprocess.call(["opencode", "serve", "--hostname", "127.0.0.1", "--port", str(port)], cwd=state["session_directory"], env=env)

def evidence_receipt(state, relative):
    path = owned(project(state), relative)
    if not path.is_file():
        raise ValueError("Completion needs an existing saved evidence file")
    data = path.read_bytes()
    clean_payload(relative, data)
    return {"path": relative, "sha256": sha(data), "bytes": len(data)}


def activate_mission(state, manifest):
    # Only an explicit current-chat command activates. Do not keyword-match
    # historical/quoted messages or adopt another project's assigned runtime.
    for key in ("workspace", "session_id", "session_directory"):
        if manifest.get(key) != state.get(key):
            raise ValueError("Activation must name this exact workspace/session binding: " + key)
    prepared = json.loads(json.dumps(manifest, allow_nan=False))
    for task in prepared.get("tasks", []):
        if task.get("status") == "completed":
            paths = task.get("evidence")
            if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                raise ValueError("Activation completed tasks need relative saved evidence paths")
            task["evidence"] = [evidence_receipt(state, path) for path in paths]
    Client(state).snapshot()  # read-only identity check before changing the plan
    return mission.activate(state, prepared, now=stamp())


def proc_start(pid):
    try:
        return int(Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError, TypeError):
        return None


def watcher_status(path):
    path = Path(path).resolve()
    try:
        record = load(path.with_suffix(".watcher.json"))
        start = proc_start(record["pid"])
        args = Path(f"/proc/{int(record['pid'])}/cmdline").read_bytes().split(b"\0")
        alive = (record.get("state_path") == str(path) and start is not None and start == record.get("start_ticks") and
                 str(path).encode() in args and b"watch" in args and str(HOME / "grip.py").encode() in args)
        return {**record, "alive": bool(alive)}
    except (OSError, ValueError, KeyError, TypeError):
        return {"alive": False, "state_path": str(path)}


def start_watch(path, timeout=10):
    """One named tmux watcher, verified by its PID/start-time/argv receipt."""
    path = Path(path).resolve()
    observed = watcher_status(path)
    if observed["alive"]:
        return {**observed, "reused": True}
    name = "grip-watch-" + sha(str(path).encode())[:12]
    exists = subprocess.run(["tmux", "has-session", "-t", "=" + name], capture_output=True)
    if exists.returncode == 0:
        raise RuntimeError("Named watcher exists without a matching live receipt; inspect it, do not overwrite")
    line = "exec " + shlex.join([sys.executable, str(HOME / "grip.py"), "--state", str(path), "watch"])
    command(["tmux", "new-session", "-d", "-s", name, "-c", str(HOME), line])
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        observed = watcher_status(path)
        if observed["alive"]:
            return {**observed, "reused": False, "tmux_session": name}
        time.sleep(0.05)  # bounded readiness condition, not a fixed startup delay
    raise RuntimeError("Watcher did not produce a live identity receipt; activation is not confirmed running")


def install_skill(expected=None, target=None):
    source = HOME / "skills/grip/SKILL.md"
    target = Path(target).expanduser().absolute() if target is not None else installed_skill_path()
    if target.is_symlink():
        raise ValueError("Symlinked installed skill needs explicit manual review")
    payload = source.read_bytes()
    if target.exists() and target.read_bytes() != payload:
        if expected is None or sha(target.read_bytes()) != expected:
            raise ValueError("Existing different GRIP skill preserved; supply --replace-sha256 of the reviewed installed bytes")
        vault({"workspace": str(target.parent), "source_roots": ["SKILL.md"]}, ["SKILL.md"])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(".SKILL.md." + str(os.getpid()) + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    return {"installed": str(target), "sha256": sha(target.read_bytes()), "activation_started": False}


def bind_hooks(path, state):
    registry = event_hooks.cache_root()/"bindings.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    with locked(registry.with_suffix(".lock")):
        data = load(registry) if registry.exists() else {"sessions": {}}
        old = data["sessions"].get(state["session_id"])
        if old and old["state_path"] != str(path) and watcher_status(old["state_path"])["alive"]:
            raise ValueError("Another live watcher owns this session; do not create competing continuation")
        Client(state).snapshot()
        data["sessions"][state["session_id"]] = {"state_path": str(path)}
        atomic(registry, data)
    state["native_events"] = True
    return {"bound": True, "session_id": state["session_id"], "hook_loaded": False,
            "native_events": True, "note": "Binding is not a loaded-hook or observed-native-event receipt"}


def adopt_server(path, state, service_file):
    if watcher_status(path)['alive'] or state.get('dispatch_active'):
        raise ValueError('Stop the owned watcher/dispatch before explicit server adoption')
    if os.environ.get('OPENCODE_SESSION_ID') != state['session_id']:
        raise ValueError('Server adoption must run from this exact real tool-context session')
    service_path = Path(service_file).resolve()
    service = load(service_path)
    candidate = dict(state, server_url=service['url'], server_service_file=str(service_path), server_api='v2')
    Client(candidate).snapshot()  # same persisted ID/directory on the actual service
    state.setdefault('server_history', []).append({'url': state['server_url'], 'at': stamp(),
        'reason': 'Explicit current-tool-session adoption; old service retained, never stopped'})
    state.update(server_url=candidate['server_url'], server_service_file=str(service_path), server_api='v2')
    return {'adopted': True, 'url': state['server_url'], 'same_session_verified': True,
            'credential_copied': False, 'watcher_started': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--state", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("status", "pause", "resume", "serve", "watch"): sub.add_parser(action)
    p=sub.add_parser("install-skill"); p.add_argument("--replace-sha256", help="reviewed current installed skill digest")
    p.add_argument("--target", type=Path, help="skill destination; otherwise GRIP_SKILL_PATH or the current user's .agents directory")
    p=sub.add_parser("activate", help="merge a current-chat mission and start/reuse its single poller")
    p.add_argument("--mission", type=Path, required=True)
    p.add_argument("--profile", type=Path, help="explicit connection/compute/backup profile, only for a new state")
    p.add_argument("--configure-only", action="store_true", help="save/verify without starting the poller")
    p=sub.add_parser("schedule");p.add_argument("--until-stopped",action="store_true",required=True)
    p.add_argument("--instructions",required=True);p.add_argument("--task-id",required=True);p.add_argument("--task",required=True)
    p=sub.add_parser("tick"); p.add_argument("--dry-run", action="store_true")
    p=sub.add_parser('watchdog');p.add_argument('--snapshot',required=True);p.add_argument('--no-progress-seconds',type=int,default=180);p.add_argument('--vm-idle-seconds',type=int,default=300)
    p.add_argument('--source-path', action='append', default=[], help='explicit progress source file; repeatable')
    p.add_argument('--progress-glob', action='append', default=[], help='workspace-relative progress JSON glob; repeatable')
    p.add_argument('--progress-field', action='append', help='material progress JSON field; repeatable, exclude heartbeat-only fields')
    p.add_argument('--snapshot-schema', default='grip_progress_beacon_v1', help='schema supplied by your project beacon')
    sub.add_parser('test-progress-note')
    p=sub.add_parser("checkpoint"); p.add_argument("--note", required=True)
    p=sub.add_parser("begin"); p.add_argument("--family", required=True); p.add_argument("--hypothesis", required=True)
    p.add_argument("--mirror", required=True); p.add_argument("--change", required=True); p.add_argument("--file", action="append", required=True)
    p.add_argument("--estimate-seconds", type=int, required=True)
    p=sub.add_parser("finish"); p.add_argument("--iteration", required=True); p.add_argument("--family")
    p.add_argument("--verdict", choices=("better","same","worse","failed"), required=True)
    p.add_argument("--reason", required=True); p.add_argument("--evidence", required=True); p.add_argument("--best")
    p.add_argument("--metric-contract", help="Required for promoting a best artifact; separates incompatible tasks/rulers")
    p=sub.add_parser("task"); p.add_argument("--id",required=True); p.add_argument("--status",choices=mission.STATUSES,required=True); p.add_argument("--note",required=True)
    p.add_argument("--revision", type=int); p.add_argument("--reopen", action="store_true")
    p.add_argument("--evidence", action="append", help="relative saved evidence; required for durable mission completion")
    p=sub.add_parser("add-task"); p.add_argument("--id", required=True); p.add_argument("--content", required=True)
    p.add_argument("--done-when", required=True); p.add_argument("--depends-on", action="append", default=[]); p.add_argument("--revision", type=int, required=True)
    p=sub.add_parser("spec"); p.add_argument("--file", required=True); p.add_argument("--revision", type=int, required=True)
    p=sub.add_parser("review"); p.add_argument("--stage", choices=("requirement", "audit", "challenge"), required=True)
    p.add_argument("--result", choices=("pass", "fail"), required=True); p.add_argument("--note", required=True)
    p.add_argument("--evidence", required=True); p.add_argument("--requirement"); p.add_argument("--revision", type=int, required=True)
    sub.add_parser("bind-hooks")
    p=sub.add_parser('goal');p.add_argument('--objective',required=True);p.add_argument('--done-when',required=True)
    p.add_argument('--scope',choices=('project','milestone'),required=True);p.add_argument('--note',required=True);p.add_argument('--revision',type=int,required=True)
    p=sub.add_parser('goal-review');p.add_argument('--result',choices=('satisfied','unfinished','blocked'),required=True)
    p.add_argument('--note',required=True);p.add_argument('--evidence',required=True);p.add_argument('--revision',type=int,required=True)
    p=sub.add_parser('adopt-server'); p.add_argument('--service-file', required=True)
    p=sub.add_parser('scope-source'); p.add_argument('--file', required=True); p.add_argument('--revision', type=int, required=True)
    p=sub.add_parser("event"); p.add_argument("--session-id", required=True); p.add_argument("--kind", choices=sorted(event_hooks.KINDS), required=True)
    p.add_argument("--call-id"); p.add_argument("--agent", choices=("build", "plan")); p.add_argument("--event-id")
    p.add_argument('--at-ms',type=int,help='Native source event timestamp, not receipt time')
    p=sub.add_parser("rollback"); p.add_argument("--iteration", required=True)
    args=parser.parse_args(); path=args.state.expanduser().resolve()
    if args.action == "install-skill":
        print(json.dumps(install_skill(args.replace_sha256, args.target))); return
    if args.action == "serve": raise SystemExit(serve(load(path)))
    if args.action == "activate":
        with locked(path.with_suffix(".lock")):
            if path.exists():
                if args.profile:
                    raise ValueError("An existing state owns this binding; do not replace it with another profile")
                state = load(path)
            else:
                if not args.profile:
                    raise ValueError("New mission needs an explicit current-session profile; no guessed connection/model/compute")
                state = load(args.profile)
                required = ("workspace", "project_id", "session_id", "session_directory", "server_url", "server_secret_file",
                            "provider_id", "model_id", "compute_target", "source_roots", "github_repo", "poll_seconds",
                            "idle_grace_seconds", "maximum_packet_seconds", "deadline", "deadline_basis")
                if any(key not in state for key in required):
                    raise ValueError("Profile is missing an explicit session/compute/backup/scheduling field")
                state.setdefault("tasks", [])
            state["state_path"] = str(path)
            result = activate_mission(state, load(args.mission))
            atomic(path, state)
        # Release the lock before waiting for the watcher that also needs it.
        if args.configure_only or result["status"] != "active":
            result["watcher"] = {"started": False, "reason": "configure-only or no actionable work"}
        else:
            result["watcher"] = start_watch(path)
        print(json.dumps(result, indent=2)); return
    if args.action == "watch":
        stop=False
        def stopping(*_):
            nonlocal stop; stop=True
        signal.signal(signal.SIGTERM, stopping); signal.signal(signal.SIGINT, stopping)
        with (path.with_suffix(".watch.lock")).open("a+") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
            listener = event_hooks.listen(path)
            observer = None
            initial = load(path)
            if initial.get("native_events"):
                def receive(event):
                    with locked(path.with_suffix(".lock")):
                        current = load(path)
                        result = event_hooks.record(current, **event)
                        current["last_hook_event"] = result
                        atomic(path, current)
                    event_hooks.notify(path)
                def health(status, detail):
                    with locked(path.with_suffix(".lock")):
                        current = load(path)
                        current["native_event_health"] = {"at": stamp(), "status": status, "detail": detail}
                        atomic(path, current)
                observer = stream_events.Observer(initial, receive, health).start()
            receipt = {"pid": os.getpid(), "start_ticks": proc_start(os.getpid()), "state_path": str(path), "started_at": stamp()}
            atomic(path.with_suffix(".watcher.json"), receipt)
            while not stop:
                try:
                    with locked(path.with_suffix(".lock")):
                        state=load(path); heartbeat=tick(state); state["last_heartbeat"]=heartbeat; state["consecutive_errors"]=0; atomic(path,state)
                    print(json.dumps(heartbeat),flush=True)
                except Exception as exc:
                    with locked(path.with_suffix(".lock")):
                        state=load(path); n=state.get("consecutive_errors",0)+1; state["consecutive_errors"]=n
                        state["last_error"]={"at":stamp(),"type":type(exc).__name__,"reason":str(exc)[:300]}; atomic(path,state)
                    print(json.dumps(state["last_error"]),flush=True)
                    if n == 3: alert(state,"Three proxy/backup errors; inspect GRIP heartbeat, no new jobs launched.")
                ready, _, _ = select.select([listener], [], [], state.get("poll_seconds",20))
                if ready:
                    listener.recv(128)
                    # Coalesce hook bursts; all durable state is reread under lock.
                    while select.select([listener], [], [], 0)[0]: listener.recv(128)
            listener.close()
            if observer: observer.close()
        return
    with locked(path.with_suffix(".lock")):
        state=load(path)
        if args.action == "status":
            mission.refresh(state)
            result={**state, "watcher": watcher_status(path), "next_task": mission.next_task(state),
                    "objective_signature":objective_watch.signature(state)}
        elif args.action == "bind-hooks": result=bind_hooks(path,state)
        elif args.action == 'goal':
            mission.revision(state,args.revision)
            objective_watch.configure(state,objective=args.objective,done_when=args.done_when,scope=args.scope,note=args.note)
            mission.event(state,None,None,'Explicit authorized objective recorded',stamp());mission.refresh(state)
            result=state['objective_guard']
        elif args.action == 'goal-review':
            mission.revision(state,args.revision);receipt=evidence_receipt(state,args.evidence)
            result=objective_watch.review(state,result=args.result,note=args.note,evidence=receipt,report=load(owned(project(state),args.evidence)))
            mission.event(state,None,None,'Objective review: '+args.result,stamp());mission.refresh(state)
        elif args.action == 'adopt-server': result=adopt_server(path,state,args.service_file)
        elif args.action == 'scope-source':
            mission.revision(state,args.revision)
            receipt=vault(state,[args.file])
            if not receipt[args.file]['exists']: raise ValueError('Source must exist')
            if args.file not in state['source_roots']: state['source_roots'].append(args.file)
            if state.get('completion') and args.file not in state['completion']['source_paths']:
                state['completion']['source_paths'].append(args.file)
                completion.sync(state)
            mission.event(state,None,None,'Tracked necessary scoped source: '+args.file,stamp())
            result=receipt
        elif args.action == "event":
            result=event_hooks.record(state,session_id=args.session_id,kind=args.kind,call_id=args.call_id,
                agent=args.agent,event_id=args.event_id,at_ms=args.at_ms)
        elif args.action == "spec":
            mission.revision(state,args.revision)
            receipt=evidence_receipt(state,args.file)
            result=completion.configure(state,load(owned(project(state),args.file)),receipt)
            mission.event(state,None,None,"Mode1 specification established",stamp()); mission.refresh(state)
        elif args.action == "review":
            mission.revision(state,args.revision)
            receipt=evidence_receipt(state,args.evidence)
            result=completion.review(state,stage=args.stage,passed=args.result=="pass",note=args.note,
                evidence=receipt,report=load(owned(project(state),args.evidence)),requirement=args.requirement)
            mission.event(state,None,None,args.stage+": "+args.result,stamp()); mission.refresh(state)
        elif args.action == "add-task":
            result=mission.add_task(state,{"id":args.id,"content":args.content,"done_when":args.done_when,
                "depends_on":args.depends_on,"status":"pending"},now=stamp(),expected=args.revision)
        elif args.action in ("pause","resume"):
            if args.action=='pause' and state.get('server_api')=='v2':
                v2_control.cancel_pending(Client(state)); state['dispatch_active']=None
            if args.action=="pause" and state.get("dispatch_active") and state.get('server_api') != 'v2':
                Client(state).request("/session/"+state["session_id"]+"/abort", {})
                state["dispatch_active"]=None
            state["status"]="paused" if args.action=="pause" else "active"; result={"status":state["status"]}
        elif args.action == "schedule":
            result=mission.schedule(state,task_id=args.task_id,content=args.task,instructions=args.instructions,now=stamp())
        elif args.action == 'watchdog':
            if args.no_progress_seconds<30 or args.vm_idle_seconds<30:raise ValueError('Watchdog thresholds must be at least30seconds')
            state['progress_watch']={'enabled':True,'activated_at':time.time(),'vm_snapshot':args.snapshot,
                'no_progress_seconds':args.no_progress_seconds,'vm_idle_seconds':args.vm_idle_seconds,
                'escalate_seconds':60,'cooldown_seconds':180,'snapshot_max_age':150,
                'source_paths':args.source_path,'progress_globs':args.progress_glob,'snapshot_schema':args.snapshot_schema}
            if args.progress_field:state['progress_watch']['progress_fields']=args.progress_field
            state['progress_watch_state']={};result=state['progress_watch']
        elif args.action == 'test-progress-note':
            result=progress_note(state,Client(state),{'reason':'Explicit live delivery test:receipt must be observed in this same session;not a claim that a stall timer fired'},'delivery_test')
        elif args.action == "task":
            receipts=[evidence_receipt(state,relative) for relative in args.evidence] if args.evidence else None
            result=mission.update_task(state,args.id,args.status,args.note,now=stamp(),expected=args.revision,
                                       reopen=args.reopen,evidence=receipts)
        elif args.action == "checkpoint": result=checkpoint(state,args.note)
        elif args.action == "begin": result=begin(state,args)
        elif args.action == "finish": result=finish(state,args)
        elif args.action == "rollback": result=rollback(state,args.iteration)
        else: result=tick(state,args.dry_run)
        atomic(path,state)
    if args.action == "event": event_hooks.notify(path)
    print(json.dumps(result,indent=2))

if __name__ == "__main__": main()
