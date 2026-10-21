# GRIP Mode One contract

Mode One completes the current user's agreed objective within their existing
authority. It applies to any project, not a specific model, account or machine.
Each deployment supplies its own objective, finish condition, scope, spec and
session/compute/backup profile. No example grants execution permission.

## Rules

1. The user's full objective, not the last completed component, defines the work.
2. Recover decisions and inspect existing work before adding necessary tasks.
3. Tool completion is not final-turn completion; never overlap continuations.
4. Events and fallback polling share one binding, lock and deduplication gate.
5. Completed tasks stay done; a new in-scope gap gets its own dependency/task.
6. Finishing the task queue does not automatically close the full objective.
7. Passing a whole-spec audit grants provisional green, not final completion.
8. A separate challenge must pass; failures preserve history and return to repair.
9. Inferred work and undefined modes never enlarge permissions.
10. Stop, Pause, planning mode and newer human input take priority.
11. Investigate before acting; clear only flags proven stale by owned saved proof.
12. Standby and primary share one dispatch gate; standby has no independent prompt path.
13. Interrupted completion must be repeatable without replaying work or duplicating attempts.

## Observable acceptance

The event adapter observes only matching-session tool/turn/agent/interruption
metadata. It does not store raw prompts, tool arguments or tool outputs. Actual
session identity, watcher process identity, fresh heartbeat and wake stages must
be distinguished from installation or an API acknowledgement.

Busy tools, unfinished turns, planning, human stop/takeover, stale observations
and duplicate completed turns suppress dispatch. Missed notifications fall back
to persisted message/tool state, never blind execution.

Requirements have stable IDs and measurable finish conditions. Evidence is
source-bound and invalidates when its scoped inputs change. An audit covers the
whole spec. A separate challenge uses different evidence and named failure/boundary
scenarios. Literal passing JSON is a gate, not self-proving software correctness.

Full-goal closure matches the exact recorded objective, scope, current signature
and all eleven review questions. Completed tasks and a banked iteration are
prerequisites; Mode One also requires the verified spec audit and challenge.
Blocked objectives suppress wakes without being declared completed.

## Reliability recovery acceptance

Back up before reconciliation. Verify bound session/directory, revision, terminal
record hash, evidence/vault integrity and private completion-bank ancestry. Reject
unknown ownership, changed evidence or conflicting outcomes. Recovery of a lease
does not clear a human pause or genuine task/goal prerequisite; infrastructure-only
release requires a separate explicit evidence-backed review.

Inject failure after terminal preparation, after backup acceptance and after finish
receipt persistence but before state save. Retrying must retain one attempt and
reuse verified saved work. Unknown prompt acceptance is an investigation blocker,
not permission to send again. A live-but-unhealthy primary is not proof of death.

Fault tests must verify a standby can recover a proven-dead primary through the
same startup/primary/state locks without dispatching independently, unpausing a
mission or reopening completed work. Test on fake sessions, not by interrupting
real model work. Observe live monitoring separately from a real autonomous wake.

Apply General reasoning, Build and engineering, and Creation Mode as the existing
investigation specifications. Report programmed procedures and measured evidence;
do not claim trained capabilities or add policy for undefined operating modes.

## Portability and safety

All personal paths and project layout are discovered or explicitly configured.
Private mission/vault data belongs in a user-selected private backup repository,
not the public software repository. No default model provider, remote machine,
training dataset, GPU or advisory service is selected by this contract.

Modes Two and Three remain undefined and are refused. Strategy descriptions do
not confer trained model abilities. Physical deployment, sensing, extra workers,
new compute, spending or public publishing require separate current authorization.
