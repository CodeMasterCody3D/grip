"""Durable mission/task transitions. No agents, timers, network or model code."""
import copy
import completion
import objective_watch

STATUSES = ("pending", "in_progress", "waiting", "blocked", "completed", "parked")


def revision(state, expected=None):
    current = state.get("plan_revision", 0)
    if expected is not None and expected != current:
        raise ValueError("Stale plan revision; reload current progress before changing tasks")
    return current


def event(state, task, before, note, now):
    state["plan_revision"] = revision(state) + 1
    state.setdefault("task_events", []).append({"revision": state["plan_revision"], "task": task,
                                               "before": before, "note": note, "at": now})


def next_task(state):
    if state.get('objective_guard',{}).get('status')=='blocked':
        return None  # Explicit goal blocker is not permission to dispatch other tasks.
    tasks = state.get("tasks", [])
    if completion.selected(state) and not state.get("completion"):
        return completion.next_action(state)
    completed = {task.get("id") for task in tasks if task.get("status") == "completed"}
    # A running job or interrupted packet is resumed/inspected, never restarted.
    for task in tasks:
        if task.get("status") in ("in_progress", "waiting"):
            return task
    ready = next((task for task in tasks if task.get("status") == "pending" and
                 set(task.get("depends_on", [])) <= completed), None)
    return ready or completion.next_action(state) or objective_watch.next_action(state)


def validate(tasks):
    ids = [task.get("id") for task in tasks]
    if not tasks or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Mission needs nonempty tasks with unique stable IDs")
    by_id = {task["id"]: task for task in tasks}
    active = []
    for task in tasks:
        if (task.get("status") not in STATUSES or not isinstance(task.get("content"), str) or not task["content"].strip() or
                not isinstance(task.get("done_when"), str) or not task["done_when"].strip()):
            raise ValueError("Each mission task needs a status, content and measurable done_when condition")
        deps = task.get("depends_on", [])
        if (not isinstance(deps, list) or any(not isinstance(dep, str) or dep not in by_id or dep == task["id"] for dep in deps)
                or len(set(deps)) != len(deps)):
            raise ValueError("Unknown, duplicate or self-referencing task dependency")
        if task["status"] in ("in_progress", "waiting"):
            active.append(task)
            if any(by_id[dep]["status"] != "completed" for dep in deps):
                raise ValueError("Cannot start a task before its prerequisites are complete")
        if task["status"] == "completed" and not task.get("evidence"):
            raise ValueError("Completed mission tasks need saved evidence, not an unsupported done label")
    if len(active) > 1:
        raise ValueError("Only one in-progress or waiting task may own this mission")
    def visit(identifier, visiting, visited):
        if identifier in visiting:
            raise ValueError("Cyclic task dependencies")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dep in by_id[identifier].get("depends_on", []):
            visit(dep, visiting, visited)
        visiting.remove(identifier)
        visited.add(identifier)
    visited = set()
    for identifier in ids:
        visit(identifier, set(), visited)


def refresh(state):
    if not state.get("mission_id") or state.get("status") not in ("active", "complete", "blocked"):
        return
    objective_watch.sync(state)
    if state.get('objective_guard',{}).get('status')=='blocked':
        state['status']='blocked'
    elif not state.get('active_iteration') and all(task["status"] == "completed" for task in state["tasks"]) and completion.next_action(state) is None and objective_watch.allowed_complete(state):
        state["status"] = "complete"
    elif next_task(state) is None:
        state["status"] = "blocked"
    else:
        state["status"] = "active"


def activate(state, manifest, *, now):
    """Merge repeat activation without losing progress or changing mission scope."""
    if manifest.get("schema") != 1:
        raise ValueError("Unknown GRIP mission schema")
    fields = ("mission_id", "objective", "done_when", "continuation_instructions")
    if any(not isinstance(manifest.get(key), str) or not manifest[key].strip() for key in fields):
        raise ValueError("Mission needs identity, objective, finish condition and current scope")
    refs = manifest.get("context_refs")
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
        raise ValueError("Record current chat/project evidence references, not a guessed objective")
    candidate = copy.deepcopy(state)
    if candidate.get("mission_id"):
        for key in fields:
            if manifest[key] != candidate.get(key):
                raise ValueError("Activation cannot replace an existing mission; revise its scope explicitly")
    incoming = copy.deepcopy(manifest.get("tasks"))
    if not isinstance(incoming, list):
        raise ValueError("Mission tasks must be an ordered list")
    validate(incoming)
    old = {task.get("id"): task for task in candidate.get("tasks", [])}
    merged = []
    for task in incoming:
        previous = old.get(task["id"])
        if previous:
            for key in ("content", "done_when", "depends_on"):
                if key in previous and previous[key] != task.get(key, [] if key == "depends_on" else None):
                    raise ValueError("Activation cannot rewrite an existing task definition")
            # The live task wins over a stale activation plan, especially DONE.
            task.update(copy.deepcopy(previous))
        merged.append(task)
    # Do not lose an omitted old task, its evidence or a currently running job.
    merged.extend(copy.deepcopy(task) for task in candidate.get("tasks", []) if task.get("id") not in {t["id"] for t in incoming})
    validate(merged)
    changed = not candidate.get("mission_id") or merged != candidate.get("tasks")
    candidate.update({key: manifest[key] for key in fields})
    candidate.update(tasks=merged, context_refs=list(dict.fromkeys(candidate.get("context_refs", []) + refs)))
    if not candidate.get('objective_guard') and not state.get('mission_id'):
        objective_watch.configure(candidate,objective=manifest.get('project_objective',manifest['objective']),
            done_when=manifest.get('project_done_when',manifest['done_when']),scope=manifest.get('scope_kind','milestone'),
            note='Explicit activation scope; recover broader user intent before closing, never silently promote milestone to project')
    elif candidate.get('objective_guard'):
        for field,key in (('project_objective','objective'),('project_done_when','done_when'),('scope_kind','scope')):
            if field in manifest and manifest[field]!=candidate['objective_guard'][key]:
                raise ValueError('Activation cannot replace the authorized objective; use revision-checked goal')
    if changed:
        event(candidate, None, None, "Mission activation reconciled with saved progress", now)
    candidate["status"] = "active"
    refresh(candidate)
    state.clear()
    state.update(candidate)
    return {"status": state["status"], "plan_revision": revision(state), "next_task": next_task(state)}


def update_task(state, identifier, status, note, *, now, expected=None, reopen=False, evidence=None):
    revision(state, expected)
    if status not in STATUSES or not isinstance(note, str) or not note.strip():
        raise ValueError("Task transition requires a valid status and reason/progress note")
    if state.get("mission_id") and expected is None:
        raise ValueError("Task transition requires --revision from the current mission state")
    candidate = copy.deepcopy(state)
    task = next((task for task in candidate["tasks"] if task.get("id") == identifier), None)
    if task is None:
        raise ValueError("Unknown task ID; do not silently recreate a task")
    before = task["status"]
    if before == "completed" and status != "completed" and not reopen:
        raise ValueError("Completed tasks stay done; explicit --reopen and a reason are required")
    if reopen and (before != "completed" or status not in ("pending", "in_progress")):
        raise ValueError("Reopen applies only to a completed task becoming pending/in_progress")
    if before == "completed" and status == "completed":
        return copy.deepcopy(task)  # duplicate completion is harmless and preserves its evidence
    if reopen:
        task.setdefault("completion_history", []).append({"evidence": task.pop("evidence", None),
                                                           "reopened_at": now, "reason": note})
    completion.invalidate(candidate, "Task progress changed: " + identifier)
    task.update(status=status, note=note, updated_at=now)
    if evidence is not None:
        task["evidence"] = copy.deepcopy(evidence)
    if status == "completed" and candidate.get("mission_id") and not evidence:
        raise ValueError("Mark complete only after supplying saved --evidence")
    if candidate.get("mission_id"):
        validate(candidate["tasks"])
    event(candidate, identifier, before, note, now)
    refresh(candidate)
    state.clear()
    state.update(candidate)
    return copy.deepcopy(task)


def add_task(state, item, *, now, expected):
    revision(state, expected)
    if any(t.get("id") == item.get("id") for t in state["tasks"]):
        raise ValueError("Task ID already exists; never overwrite saved progress")
    if item.get("status") != "pending":
        raise ValueError("New scoped gaps start pending")
    candidate = copy.deepcopy(state)
    candidate["tasks"].append(copy.deepcopy(item))
    validate(candidate["tasks"])
    completion.invalidate(candidate, "New necessary gap: " + item["id"])
    event(candidate, item["id"], None, "Added necessary in-scope gap", now)
    refresh(candidate)
    state.clear(); state.update(candidate)
    return copy.deepcopy(item)


def schedule(state, *, task_id, content, instructions, now):
    """Legacy schedule, without resetting completed/running work or clearing leases."""
    candidate = copy.deepcopy(state)
    task = next((task for task in candidate["tasks"] if task.get("id") == task_id), None)
    if candidate.get("mission_id"):
        raise ValueError("Use activate/task for a durable mission; schedule cannot replace its plan")
    if task is not None and task["content"] != content:
        raise ValueError("Do not rewrite an existing task through schedule")
    if task is None:
        candidate["tasks"].append({"id": task_id, "content": content, "status": "pending", "updated_at": now})
        event(candidate, task_id, None, "Scheduled new task", now)
    candidate.setdefault("schedule_history", []).append({"at": now, "previous_deadline": candidate.get("deadline"),
                                                         "previous_maximum_wakes": candidate.get("maximum_wakes")})
    candidate.update(status="active", deadline=None, maximum_wakes=None, deadline_alarm=False,
                     continuation_instructions=instructions,
                     deadline_basis="User renewed polling until stop/pause; compute lifetime checked separately")
    state.clear()
    state.update(candidate)
    return {"status": state["status"], "plan_revision": revision(state)}
