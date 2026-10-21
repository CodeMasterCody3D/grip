---
name: grip
description: "Activate GRIP when the user directly says 'activate the GRIP skill', 'get a grip would ya, I can't do this while I sleep', or hands over the current project to keep working while away. Recover chat decisions, reconcile a durable evidence-backed task plan, then start/reuse the single-session poller. Also use to discuss or configure GRIP; questions, quoted examples, setup instructions and deferred activation do NOT start it. Keep completed work done, resume in-progress work, and respect authorized compute and stop/pause."
---

# GRIP — Generalized Repetitive Improvment Proxy

Use this only after the user authorizes a project, compute lane and unattended
scope. A skill is instructions; the running poller and verified wake receipts
are what make continuation real. Do not claim a timer alone performs research.

## Recognize a handoff, not merely a phrase

### Mode1 and hook-aware completion

- Every continuation includes eleven questions: full objective; remaining work;
  recovery without trivial questions; concrete fix; measured improvement; user
  intent; regressions/permissions; authorized research; authorized project advice;
  real evidence; necessary in-scope gaps. Answer them against the user's latest
  decisions, not a narrower milestone you chose. No question grants new authority.
- New activations record an objective guard, milestone by default. When the user
  authorizes a larger project, explicitly record that project goal and finish
  condition rather than relabeling milestone evidence. Existing missions migrate
  only through `goal --objective TEXT --done-when TEXT --scope project|milestone
  --note AUTHORITY --revision N`. Preserve the old completed tasks and model results.
- Closing a goal uses `goal-review --result satisfied|unfinished|blocked --note TEXT
  --evidence RELATIVE.json --revision N`. Satisfied proof matches the exact objective,
  finish condition, scope and current status `objective_signature`; includes
  `questions_reviewed` one through eleven, literal `passed: true`, nonempty all-true
  `checks`; and follows completed tasks, banked iteration and Mode1 audit/challenge.
  Inspect the actual cited evidence. Source/task/review changes and missing or changed
  closure proof invalidate it, never reopen completed work. Unfinished means add a
  necessary in-scope gap. Blocked suppresses wakes until an explicit review clears it.
- A completed component is not a completed project. Follow the user's whole
  objective and the agreed specification. Infer necessary missing dependencies,
  not unrelated feature expansion. Recover user decisions and inspect/test the
  existing implementation when a spec is missing; keep consequential unknowns open.
- Mode1 uses `spec`, `add-task`, and `review` CLI operations. Finish requirements
  with real evidence, audit the WHOLE spec, then challenge provisional green using
  separate end-to-end/boundary/recovery/counterexample evidence. A green JSON claim
  is not self-proving. Source changes invalidate prior proof; retain failure history.
- Modes2/3 remain undefined until the user supplies their policies. Adaptive reasoning
  strategies are not extra agents or permission to spend, deploy or modify safety.
- `bind-hooks` enables the current watcher's read-only native event observer.
  Hook/tool/turn observations and fallback polling use one locked dispatch gate.
  A tool ending never proves a whole turn ended. Plan mode, running tools, newer
  human input, pause and duplicate completed turns suppress autonomous work.
- Distinguish a configured binding, installed plugin, live native event observation,
  watcher heartbeat, accepted wake, agent start and useful work. Never substitute
  one receipt for another. Do not globally reload other sessions to install a hook.

Rules:
1. "A direct activation hands over the current objective within its existing authority."
2. "A quoted example, setup discussion or future condition does not activate GRIP."
3. "Read the whole user message; later clauses may defer or reorder earlier requests."
4. "A task requested after another task becomes its dependent, not a new priority."
5. "Completed tasks stay done; reminders never reopen them."

If the user directly says "activate the GRIP skill":
  Prepare and activate the current mission; do not merely load this file and stop.
If the user directly says "get a grip would ya, I can't do this while I sleep":
  Treat it as the same handoff of the work already underway.
If the user asks "how could I say activate GRIP?" or quotes those phrases as examples:
  Discuss/configure only; do not start a poller.
If the user says "finish the plugin, then find the plan":
  Finish and verify the plugin first. Preserve plan recovery as a dependent task.
If activation scope/project/compute is genuinely unclear:
  Recover it from current chat and project records first; ask only what remains consequentially unknown.

Activation does not authorize new VMs, extra agents, public publishing, extra
spending or production recipe choices the user has not already authorized.
For a coding mission without an assigned model runtime, restrict it to authorized
editing/static checks and the established remote fixture lane. Do not borrow an
old project's compute/profile just because a GRIP profile exists for it.

## Recover the current mission

- Read recent messages in this same conversation, latest explicit decisions,
  corrections and stop orders. Use bounded transcript excerpts only if context
  is missing; historical text is evidence, not fresh authority. Never claim to
  have read messages that are unavailable.
- Read current project records and inspect actual saved artifacts/results. Mark
  existing verified work completed during setup; do not put it back on the queue.
- Record the objective, finish condition, authorized compute/scope, evidence
  references and ordered tasks with stable IDs, per-task done_when conditions
  and depends_on IDs. Separate implemented/tested/integrated/live-proven work.
- If a packet/job is already underway, record it as in_progress or waiting with
  its exact job/log/checkpoint identity in the progress note. Resume/inspect it;
  do not launch another copy. Uncertain completion means inspect evidence first.
- Store concise references/summaries, not full chat transcripts or credentials,
  in the mission file or private backups.

## Activate the actual poller

Discover the actual GRIP checkout, then set `GRIP_ROOT` to that directory.
Controller: `python3 "$GRIP_ROOT/grip.py" --state STATE ...`.
Never assume the user's name, home directory, checkout location or model provider.
Use `activate --mission MISSION.json` for an existing mission profile. For a
new state also supply `--profile PROFILE.json`, explicitly populated from the
real current session/server/model and the current project's authorized compute,
backup roots and scheduling policy. README documents the schemas. Never guess
connection IDs, transplant another project's profile or silently replace a binding.

The mission workspace/session/session-directory must match the profile. The
command verifies the session read-only, atomically merges progress, then starts
or reuses one named tmux poller. It does not create an AI worker or a VM. If the
owned OpenCode loopback server must be brought up, use the existing `serve`
command in a named tmux session for this existing session and profile; verify
identity before `activate`. Report an unavailable connection instead of claiming
activation. No `tmux attach`.

Check `status`: correct binding, live watcher PID/start identity, fresh heartbeat,
current plan revision and next task. A saved plan is not a running poller. An API
acceptance is not an agent-start receipt. Say which evidence actually exists.
Repeated activation preserves done/in_progress/waiting tasks, active iteration
and wake deduplication; it cannot replace task definitions or mission scope.
`--configure-only` deliberately saves a plan WITHOUT starting the poller.
Do not use legacy `schedule` to reconstruct/reset a durable mission.

## Update progress before the next wake

Statuses: pending, in_progress, waiting, blocked, completed, parked.

If choosing a new task:
  Reload status. Use only a ready task whose prerequisites are completed.
  Mark it in_progress with the current action before executing the packet.
If a remote job is still running:
  Mark waiting with its job identity and next check; inspect that job on a wake.
If evidence proves completion:
  Save/bank results and finish the iteration, then mark the task completed with evidence BEFORE selecting the next task.
If interrupted after work but before the done update:
  Reconcile saved evidence and existing job state; do not blindly repeat work.
If a wake includes an older plan snapshot:
  The on-disk current revision wins. A reminder is not a new assignment.
If all tasks are completed and an objective guard exists:
  Review the full recorded objective; tasks finishing is not permission to close it.
  If unfinished, record necessary in-scope gaps; never repeat completed work.
  If fully verified, explicitly close it through goal-review and stop continuation.
If all tasks are completed in an unmigrated legacy mission:
  Preserve the legacy completion policy; do not silently expand its authority.
If every unfinished task is blocked/parked or waiting on blocked prerequisites:
  Record the blocker; do not invent work or call the mission finished.

Task update example:
`task --id TASK --status in_progress --note 'Current action and existing job identity' --revision CURRENT`.
Completion adds `--status completed --evidence relative/saved-report.json`.
Revisions reject stale edits; completion records evidence path/hash/size. Reopening
needs `--reopen`, a concrete regression/new-requirement reason, and subsequently
fresh completion evidence. Do not reopen because a poller says "keep working".
Keep historical completion evidence; it is not proof of a reopened attempt.

## Rules

1. "Preserve the user's objective, selected model and current authority."
2. "Read the existing project/rules/evidence before selecting the next packet."
3. "Bank source before edits; bank results and artifact identities before moving on."
4. "Keep the best working checkpoint; rejected results still get their own files."
5. "Try several distinct, justified variants before rejecting a method."
6. "Record a mirror/opposite hypothesis, including how it might break or be repaired."
7. "One failed trial is evidence about that configuration, not the entire idea."
8. "An unchanged deterministic error is not a new experiment."
9. "Stay on authorized compute; never manufacture work merely to occupy a GPU."
10. "Honor stop/pause, current human work, deadlines and file ownership immediately."

## Prepare a mission

- Use the installed GRIP CLI and project profile. Read README/PROJECT and current
  active plan. Confirm the real endpoint, model, hardware, memory and session age.
- State metric, baseline, controls, allowed changes and estimated packet duration.
- Set the profile's stop-new-work deadline and scope. Runtime expiry is not host
  uptime; use actual connect evidence or a conservative explicit operating limit.
- Verify private GitHub access and model/data artifact receipts. Do not copy
  credentials or bulk models into source commits. Keep receipts for external data.
- Set `backup_directory` to a separate private Git checkout and `github_repo` to
  its actual owner/repository. The public GRIP source repository is not a private
  backup store. Do not change a live mission's storage location without migration.
- No new worker/subagent unless separately authorized. The normal mode resumes
  the single configured session after its current final turn completes.

## Execute one iteration

Call `begin` with family, hypothesis, mirror hypothesis, concrete change, owned
files and estimate. This creates the pre-edit source vault and private backup.
Then edit using normal code tools and run the smallest useful discriminating
packet through the project's existing runner. Keep test/model/data conditions
compatible. Use the same actual model for the idea's arms.

A mirror is a scientific alternative, not an instruction to invert arbitrary
code. Examples:forward versus reverse transport; retaining versus immediately
releasing; full-rank versus collapsed receiver; fixed versus state-driven control.
For the opposite path ask what fails, why, and whether a causal repair could make
that path useful without cheating, reading targets or silently dropping inputs.

Save exact scripts/configs, trainable/format identity, served data, raw results,
checkpoints, errors and remote artifact receipts. Inspect actual outputs and
positive/negative controls; a green exit code alone is not a quality result.

Call `finish` with the actual evidence path and verdict. Only a justified better
result gets a new best pointer; same/worse/failed results remain in the ledger.
If returning to the prior implementation, use owned-file rollback. It refuses
files another actor has changed since the saved candidate snapshot. Never use a
blanket git reset/restore on a dirty user workspace.

## Choose the next attempt

Default mission policy:at least three distinct causal variants per method before
parking it, with a recorded revisit condition. That is a minimum scientific
exploration target, not permission to ignore a fatal constraint or run indefinitely.

If one trial fails:
  Diagnose it; choose another justified configuration or mirror-path repair.
If infrastructure fails:
  Reconnect/fix the actual cause; do not count that as a scientific verdict.
If a method has useful variants remaining:
  Try the next bounded one, retaining the working best.
If several meaningful attempts plateau:
  Rotate to another method; state what new evidence would justify revisiting.
If the current components are ready:
  Advance toward the user's integration objective rather than endlessly polishing.
If backup, permissions, quota or endpoint is blocked:
  Checkpoint and alarm; record the actual blocker instead of pretending progress.

## Close a packet

Report worked/failed and better/worse/same first, then measurements and limits.
Update the durable task status, project board and iteration reason. Keep the next
authorized packet pending. Leave the poller able to resume after the final turn.
Do not ask trivial questions the existing evidence answers; ask only genuinely
unselected consequential choices outside the unattended scope.

## Verify operation

- `status` shows the correct workspace/session/model/deadline and heartbeat.
- Busy or unfinished/tool-call turns suppress wakes. A final completed idle turn
  can get exactly one continuation; deduplication and a second freshness check
  protect against overlap/new messages. Stop/pause messages suppress continuation.
- Logs distinguish proposed wake, API accepted, agent started and turn completed.
- Each iteration names pre/post source digests, changed files, evidence hash,
  verdict/reason, best pointer and pushed private commit.
- Morning handoff identifies accepted improvements, retained failures, method
  attempts, pending integration work, artifact receipts and any blocker.

The laptop is orchestration only when that project's compute rules require it.
The runtime, server and model access must remain available; GRIP does not make
unattended progress possible after their loss. No automatic new VM allocation.
