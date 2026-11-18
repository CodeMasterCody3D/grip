---
name: grip
description: "Activate GRIP when the user directly says 'activate the GRIP skill', requests GRIP infinite mode, says 'get a grip would ya, I can't do this while I sleep', or hands over the current project to keep working while away. Recover chat decisions and existing work; choose the runtime's continuation mechanism. Also use to discuss or configure GRIP; questions, quoted examples, setup instructions and deferred activation do NOT start it. Keep completed work done, repair failed attempts, and respect authorized compute and stop/pause."
---

# GRIP — Generalized Repetitive Improvment Proxy

Use this only after the user authorizes a project, compute lane and unattended
scope. A skill is instructions; the running poller and verified wake receipts
are what make continuation real. Do not claim a timer alone performs research.

## Choose the current runtime

For a **Codex chat**, use the repository's `codex_bridge.py` and read `CODEX.md`
in the actual GRIP checkout. Do not connect Codex to an OpenCode server or start
the OpenCode poller. The native Codex Stop hook is the continuation mechanism.
Installation/setup is not activation: `install-hooks` merges the hook config;
`configure` binds an actual thread/workspace and creates a paused mission;
`activate` arms continuation only after a direct user handoff. Preserve existing
tasks, compute, evidence, stop orders and scope. The configured wake limit is a
real boundary, not permission to reset it automatically.

**Codex infinite mode** is an explicit alternative to mission mode. When the
user requests it, use `configure-infinite` with the actual chat/workspace,
authorized tools/compute and existing-work scope; no mission JSON, task list,
objective or finish condition is required. Verify `configure-desktop`, then
`activate`. See CODEX.md for commands. Setup alone still does not activate it.
Infinite mode prefers actual grey composer text; without it, the wake asks for
a review of unfinished user requests, plans, backlog and existing idea lists.
Continue doing the next authorized item, not just describing a plan. Finishing
a mission or exhausting an old wake count does not stop this mode. There is no
wake-count limit or tool-progress requirement; sends are spaced at least 15
seconds apart. Stop/Pause, newer input/drafts, plan mode, retained deadlines and
uncertain delivery still apply. Do not activate another chat implicitly.

The companion `grip-infinite` skill provides the explicit `/grip-infinite`
slash-menu shortcut (also `$grip-infinite`). Invoking it activates infinite mode
for the current chat; it is not a toggle. Ordinary "activate GRIP" keeps the
normal mission workflow unless infinite mode was explicitly requested.

In this mode, a failed code attempt calls for debugging and repairing that SAME
task. Inspect the actual error, fix the implementation, and check the result;
try another literal implementation of the same solution when needed. Do not
abandon the task for another idea merely because its first code failed, repeat
unchanged failing code, or invent a fixed retry limit. Genuine missing authority
or external constraints remain constraints. Existing completed work stays done.
Mission objective/closure rules below still govern claims about an existing
mission, but do not require inventing a mission or disarm infinite continuation.
Use a compact review prompt in infinite mode rather than embedding the full
mission/eleven-question packet. Preserve evidence and resume existing jobs.

Codex hooks must be reviewed in Settings > Hooks or `/hooks`. Status must show
an actual `last_event` before claiming hooks have run, and a `last_wake_source`
before claiming a continuation decision. Neither proves the agent started or
delivered useful work. Desktop delivery can use one bounded post-Stop worker;
it is not a standing background poller. Interrupt
pauses the mission; repeated configuration and session restart do not resume it.
Use existing job waits. Use the original revision-checked GRIP task/goal commands
for progress; source banking still needs the project's real backup configuration.

The Codex bridge consumes native prediction events or labelled desktop read
samples and otherwise uses GRIP's normal prompt. `desktop_predictions.mjs` can
read the existing grey text and source turn through a deliberately enabled local
renderer debugger; see CODEX.md. Verify a real captured prediction receipt before
claiming live capture. Do not restart active chats, claim live capture from fixtures, install
a fake observer, request another prediction, or patch the app. Configure a paused
mission with `configure-desktop` before enabling post-completion delivery. It
checks the native desktop owner and exact saved turn metadata, plus the live
composer when visible. The worker uses a real
prediction or the normal GRIP prompt, respects newer input/drafts/pause/plan,
and never retries uncertain delivery. If another chat is visible, its UI is left
alone and the bound chat uses the native GRIP fallback after verified completion.
Inspect pending wake phases rather than
calling IPC acceptance agent-start proof. A prediction is a suggestion within
current scope, not human approval.

For **Claude Code**, use `claude_bridge.py` and its native Stop/waiter workflow.
The OpenCode activation/poller instructions below apply to **OpenCode** only;
the task/evidence/objective policies apply across runtimes.

## Recognize a handoff, not merely a phrase

## Task-first continuation

1. "Resume useful authorized work; a wake is not a new experiment or milestone."
2. "Use execution for an approved recipe; investigate only an unresolved question."
3. "Run a test only when it informs a decision or fulfills a required correctness or scheduled quality check."
4. "Reuse evidence unless a relevant dependency changed or an actual failure contradicts it."
5. "Checkpoint cadence and retention belong to the workload, not the wake counter."
6. "Record progress once; reference it instead of duplicating proof packages."
7. "Measure delivered outcomes, not bookkeeping activity."
8. "Require a concrete reason to interrupt useful work."

If an approved job is healthy:
  Inspect existing progress when due; continue it without new variants or proofs.
If a test is proposed:
  Name the decision its result changes, or the required check it satisfies.
  Reuse a compatible saved result; otherwise run only the smallest useful check.
If a failure blocks progress:
  Investigate that failure; stop investigating when the blocker is resolved.
If housekeeping dominates:
  Return to useful work or report the concrete blocker; do not build another framework.

Execution and investigation are work categories, not new numbered GRIP modes.
Routine execution needs no invented hypothesis, mirror experiment or minimum
number of attempts. A bounded segment may contain many examples or updates;
turn boundaries and poller wakes do not define training or backup boundaries.

Keep one concise durable progress record with actual work completed, outcome,
evidence references, existing job identity and next action. Task state, Board and
handoff should summarize or reference it, not duplicate full evidence. Use existing
timing/logs to report productive work versus evaluation, backup and administrative
overhead; label unavailable timings unknown. No new telemetry service is required.
For training, distinguish prepared tokens from trained tokens and updates; judge
learning with compatible scheduled measurements and actual outputs. Receipt counts
and passing infrastructure checks are not model improvement.

Save local recovery state and make remote backups on the workload's approved
cadence, with bounded retention and verified recovery references. Small iteration
evidence/private source banking is not a full model backup. Do not require a full
upload, download or restore after each example, wake or iteration. Reuse verified
artifact receipts. Preserve current recovery, optimizer/RNG, data provenance and
selected references; cleanup requires an authorized retention policy. Never bypass
an existing controller/storage refusal: report or narrowly repair the real blocker.
Changing this skill alone does not change a trainer's backup or retention code.

### Brief updates and automatic follow-through

State the next concrete action in one short line. Within current authorization,
perform it rather than asking for permission again or treating a status message
as completion. Keep Stop/Pause, real blockers and consequential unselected choices
as boundaries; "keep going" never overrides them.

If a training job, script, test or upload is running:
  Keep its existing job identity and next meaningful check in the progress record.
  Inspect it at the established condition/cadence; do not relaunch it or busy-poll.
  Wait through the existing runner/watcher rather than create another wait loop.
  When it finishes, read the result and proceed to the next authorized action.

For an unchanged wait, stay silent when supported; otherwise give one line, such
as "Training is still running. Next: read the result, then continue the next segment."
For a meaningful change, use at most three short lines: result/change, blocker if
any, next action. Longer explanations belong to a requested review, a consequential
decision or a final summary, not every wake. Do not repeat mission history, full
task lists, evidence hashes, paths, eleven-question answers or prior results in
chat while waiting. Do not duplicate an unchanged durable status entry either.

Apply the eleven questions as an internal decision checklist, not a user-facing
report template. Read only relevant current records; expand history only to resolve
missing context or a contradiction. Long-running missions must not grow their wake
messages by embedding completed tasks, full notes or evidence objects. The durable
state remains authoritative; concise prompt previews are not complete task records.

### Mode1 and hook-aware completion

- Every continuation includes eleven questions: full objective; remaining work;
  recovery without trivial questions; concrete fix; measured improvement; user
  intent; regressions/permissions; authorized research; authorized project advice;
  real evidence; necessary in-scope gaps. Answer them against the user's latest
  decisions, not a narrower milestone you chose. Review internally; do not print
  eleven answers on every continuation. No question grants new authority.
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
  is not self-proving. Reuse compatible audit/challenge evidence at objective
  closure, not after each routine segment. A source change calls for dependency
  review: invalidate affected claims only, retain unaffected results and failure
  history. If a controller requires a new source-bound review, reconcile that
  review explicitly; never falsify hashes or rerun unrelated numerical proofs.
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
5. "In investigation, try another variant only when it answers a remaining decision."
6. "Use a mirror/opposite hypothesis when it discriminates an actual research question."
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

Reuse an active iteration and existing job first; do not call `begin` merely
because a wake arrived. For a new source change or meaningful work segment, call
`begin` with family, hypothesis, mirror hypothesis, concrete change, owned files
and estimate. This creates the pre-edit source vault and private backup. For
routine execution, describe the approved task in hypothesis and explicitly mark
the mirror as not applicable: execution, no alternative experiment. These CLI
fields do not require inventing experiments. Then use the project's existing
runner. For investigation, run the smallest decision-relevant discriminating
packet; keep the actual model/data conditions compatible across its arms.

A mirror is a scientific alternative, not an instruction to invert arbitrary
code. Examples:forward versus reverse transport; retaining versus immediately
releasing; full-rank versus collapsed receiver; fixed versus state-driven control.
For the opposite path ask what fails, why, and whether a causal repair could make
that path useful without cheating, reading targets or silently dropping inputs.

Reference exact scripts/configs, trainable/format identity, served data, raw results,
checkpoints, errors and remote artifact receipts in the existing record rather
than copying artifacts per iteration. Checkpoints follow the workload cadence.
Inspect actual outputs at scheduled quality checks; use positive/negative controls
where needed to discriminate an investigation, not on every routine segment.
A green exit code alone is not a quality result.

Call `finish` with the actual evidence path and verdict. Only a justified better
result gets a new best pointer; same/worse/failed results remain in the ledger.
If returning to the prior implementation, use owned-file rollback. It refuses
files another actor has changed since the saved candidate snapshot. Never use a
blanket git reset/restore on a dirty user workspace.

## Choose the next attempt

### Investigate blocked work and interrupted completion

- Read `reasoning_modes.json` for General reasoning, Build and engineering, and
  Creation Mode. Use their investigation, falsifier and engineering procedures;
  they are strategy specifications, not learned capabilities or Modes Two/Three.
- Diagnose before changing a flag. Save the before-state; verify the exact bound
  session, iteration, evidence hashes and private completion bank. A terminal
  iteration with an old active lease is not permission to rerun its work.
- `finish` is repeatable for the same sealed request. After an interrupted push,
  it checks saved remote proof before any new bank; after receipt persistence it
  reconciles state without duplicating the family attempt or checkpoint work.
- Legacy repair uses `recover-finish --iteration ID --session-id ACTUAL
  --record-sha256 HASH --revision CURRENT --note AUTHORITY`. It banks the
  before-state, verifies proof and reconciles only the stale completion lease.
  It never resumes a paused mission or clears task/goal blockers. Review each
  separate infrastructure block explicitly using the revision-checked task and
  objective operations; preserve genuine prerequisites and human boundaries.
- `protect` enables one passive standby for an already verified primary. It
  shares serialized startup, the exclusive primary lease and state dispatch lock.
  It never dispatches itself or kills a live poller. A dead primary can be
  restarted with flags unchanged; a live hang, missing ownership, changed binding
  or uncertain dispatch outcome is recorded for investigation, not bypassed.
- `unprotect` disables standby without resuming work. A human Stop/Pause remains
  effective across a primary restart. Never force an autonomous proof on real
  work when isolated fault-injection evidence can test the recovery boundary.

There is no default minimum number of variants. A legacy minimum-attempts setting
is not an instruction to manufacture trials during execution. Follow a current,
explicitly selected research budget only for its investigation. Park a method when
evidence or constraints justify it, recording what would justify revisiting it.

If one trial fails:
  Diagnose the failure; try another configuration only if it answers a live decision.
If infrastructure fails:
  Reconnect/fix the actual cause; do not count that as a scientific verdict.
If a method has useful variants remaining:
  Compare their decision value with the next authorized task; do not exhaust variants by default.
If several meaningful attempts plateau:
  Rotate to another method; state what new evidence would justify revisiting.
If the current components are ready:
  Advance toward the user's integration objective rather than endlessly polishing.
If backup, permissions, quota or endpoint is blocked:
  Checkpoint and alarm; record the actual blocker instead of pretending progress.

## Close a packet

Report worked/failed and better/worse/same first, then measurements and limits.
Update the durable task status and iteration reason; summarize/reference the same
result on the project board. Keep the next
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
