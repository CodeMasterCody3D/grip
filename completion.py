"""Opt-in Mode1: source-bound requirements, provisional green and challenge.

No inference, tools or permission grants. Evidence is a retained claim to review,
not a proof that every possible real-world behavior was exercised.
"""
import copy
import hashlib
import json
from pathlib import Path


def selected(state):
    return state.get("operating_mode") == 1


def fingerprint(state):
    root = Path(state["workspace"]).resolve()
    values = {}
    for relative in state.get("completion", {}).get("source_paths", []):
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError("Completion source escapes workspace")
        values[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def invalidate(state, note, *, requirements=False):
    gate = state.get("completion")
    if not selected(state) or not gate:
        return
    if gate.get("audit") or gate.get("challenge"):
        gate.setdefault("history", []).append({"audit": gate.pop("audit", None),
            "challenge": gate.pop("challenge", None), "reason": note})
    gate["phase"] = "repair"
    if requirements:
        for item in gate["requirements"]:
            if item.get("evidence"):
                item.setdefault("history", []).append(item.pop("evidence"))
            item.update(status="pending", note=note)


def sync(state):
    if not selected(state) or not state.get("completion"):
        return
    current = fingerprint(state)
    if current != state["completion"]["source_fingerprint"]:
        invalidate(state, "Scoped source changed; recheck requirements", requirements=True)
        state["completion"]["source_fingerprint"] = current


def configure(state, spec, receipt):
    if spec.get("mode") != 1:
        raise ValueError("Only Mode1 is defined; Modes2/3 need user-selected policies")
    if state.get("completion"):
        raise ValueError("Existing completion spec preserved; do not replace its scope silently")
    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("Spec needs measurable requirements")
    ids = [item.get("id") for item in requirements]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Unique requirement IDs required")
    if any(not isinstance(item.get("done_when"), str) or not item["done_when"].strip() for item in requirements):
        raise ValueError("Each requirement needs done_when")
    paths = spec.get("source_paths")
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p for p in paths):
        raise ValueError("Spec needs explicit source_paths for stale-proof detection")
    candidate = copy.deepcopy(state)
    candidate["operating_mode"] = 1
    candidate["completion"] = {"spec": receipt, "phase": "implementing", "source_paths": paths,
        "requirements": [{"id": item["id"], "done_when": item["done_when"], "status": "pending"}
                         for item in requirements]}
    candidate["completion"]["source_fingerprint"] = fingerprint(candidate)
    if any(not (Path(candidate["workspace"]) / p).is_file() for p in paths):
        raise ValueError("Scoped source files must exist before specification binding")
    state.clear(); state.update(candidate)
    return state["completion"]


def review(state, *, stage, passed, note, evidence, report, requirement=None):
    if not selected(state) or not state.get("completion"):
        raise ValueError("Configure a Mode1 spec first")
    candidate = copy.deepcopy(state)
    sync(candidate)
    gate = candidate["completion"]
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Review needs an evidence-backed explanation")
    if passed:
        checks = report.get("checks") if isinstance(report, dict) else None
        if not isinstance(report, dict) or report.get("passed") is not True or not isinstance(checks, dict) or not checks or any(v is not True for v in checks.values()):
            raise ValueError("Passing proof needs literal passed=true and nonempty all-true checks")
    if stage == "requirement":
        item = next((r for r in gate["requirements"] if r["id"] == requirement), None)
        if item is None:
            raise ValueError("Unknown spec requirement")
        invalidate(candidate, "Requirement reviewed: " + requirement)
        if item.get("evidence"):
            item.setdefault("history", []).append(item["evidence"])
        item.update(status="passed" if passed else "failed", note=note, evidence=evidence)
    elif stage in ("audit", "challenge"):
        if any(t["status"] != "completed" for t in candidate["tasks"]):
            raise ValueError("Whole-spec review requires all in-scope tasks complete; blocked is not done")
        if any(r["status"] != "passed" for r in gate["requirements"]):
            raise ValueError("Whole-spec review requires every requirement verified")
        if passed and set(report.get("coverage", [])) != {r["id"] for r in gate["requirements"]}:
            raise ValueError("Whole-spec evidence must cover every requirement ID")
        if stage == "challenge":
            audit = gate.get("audit", {})
            if gate["phase"] != "provisional_green" or not audit.get("passed"):
                raise ValueError("Challenge requires provisional green from a passing audit")
            if evidence["sha256"] == audit["evidence"]["sha256"]:
                raise ValueError("Challenge needs separate evidence, not reused audit bytes")
            if passed and (not report.get("scenarios") or not isinstance(report["scenarios"], list)):
                raise ValueError("Challenge must name outside-happy-path scenarios")
        if not passed:
            invalidate(candidate, stage + " failed: " + note, requirements=True)
            gate.setdefault("history", []).append({"stage": stage, "passed": False,
                "note": note, "evidence": evidence})
        else:
            gate[stage] = {"passed": True, "note": note, "evidence": evidence,
                           "source_fingerprint": gate["source_fingerprint"]}
            gate["phase"] = "provisional_green" if stage == "audit" else "verified"
    else:
        raise ValueError("Unknown review stage")
    state.clear(); state.update(candidate)
    return state["completion"]


def next_action(state):
    if not selected(state):
        return None
    gate = state.get("completion")
    if not gate:
        kind, content = "recover-spec", "Recover user intent, inspect/test existing work and establish measurable spec; do not invent requirements."
    else:
        if any(t["status"] != "completed" for t in state["tasks"]):
            return None
        if any(r["status"] != "passed" for r in gate["requirements"]):
            kind, content = "repair", "Inspect unverified/failed requirements; add necessary scoped gap tasks and verify them; completed components stay done."
        elif gate["phase"] == "provisional_green":
            kind, content = "challenge", "Provisional green only: exercise real end-to-end use, boundary cases and recovery; seek counterexamples with separate evidence."
        elif gate["phase"] == "verified":
            return None
        else:
            kind, content = "audit", "Audit the WHOLE agreed spec and actual workflows, not just the last component; retain coverage/evidence/limitations."
    return {"id": "grip:" + kind, "status": "pending", "content": content,
            "done_when": "Use spec/review/add-task CLI with retained real evidence; no automatic self-certification", "governance": True}
