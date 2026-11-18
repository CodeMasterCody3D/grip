---
name: grip-infinite
description: "Activate GRIP infinite mode in the current Codex chat when the user invokes /grip-infinite or $grip-infinite, or explicitly asks to turn it on. Questions, examples and requests to install or change this shortcut do not activate it."
---

# GRIP infinite

An actual invocation is a handoff to **activate infinite continuation in this
Codex chat** and continue its existing authorized work. Installing, discussing,
or quoting the command does not activate it. Ordinary "activate GRIP" does not
select infinite mode unless the user explicitly requested it.

Read the sibling [GRIP skill](../grip/SKILL.md) for runtime and continuation
rules. Use the existing checkout that owns the installed `codex_bridge.py`
hook; in a plugin package the bridge and `CODEX.md` are two directories above
this skill. Follow that guide's **Optional infinite mode for Codex** workflow.

1. Recover this chat's actual `CODEX_THREAD_ID`, current workspace, latest user
   decisions, authorized tools/compute, and unfinished work. A missing mission
   or finish condition is not a blocker. Do not create chats or change other
   bindings. Preserve completed tasks and the previous installation-test state.
2. Find this chat's existing Codex binding, if any. Reuse its state path. If
   infinite mode is already armed, keep it and continue the work; do not reset
   counters, replace scope, or create another worker. Otherwise pause an existing
   binding before switching modes and reconcile any pending send. With no
   binding, use a new project-local `.grip/codex-infinite.json` state file.
3. Run `codex_bridge.py --state ABSOLUTE_STATE configure-infinite` with the
   actual `--thread-id`, `--workspace`, authorized `--compute`, and
   `--instructions` covering the user's existing work and approved plans/ideas.
   No mission JSON is required. This configuration step leaves it paused.
4. Verify desktop delivery with `configure-desktop` before activation. Reuse
   existing verified settings when present, or discover the running app page
   with `desktop_predictions.mjs --list`. The local debugger must already be
   enabled. If unavailable, state that concrete setup requirement; do not quit,
   restart or patch active apps. Never fabricate successful verification.
5. Run `codex_bridge.py --state ABSOLUTE_STATE activate`, then `status`. Confirm
   `continuation_mode` is `infinite` and `continuation_active` is true. Report
   activation briefly and perform the next useful authorized action in this
   chat. Do not end with only a proposed plan or ask for routine reapproval.

Grey text is preferred. With none, review unfinished requests and existing
plans/backlogs/ideas, then act. A failed code attempt means debug and repair
that SAME task, using a different literal implementation when needed; do not
abandon it after one failure. No mission-completion or wake-count cutoff applies.
Stop/Pause, newer human input/drafts, plan mode, retained deadlines and uncertain
delivery still apply. `/grip-infinite` is an activation shortcut, not a toggle;
"Pause GRIP" and "Stop GRIP" disarm it.
