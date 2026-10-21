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

## Portability and safety

All personal paths and project layout are discovered or explicitly configured.
Private mission/vault data belongs in a user-selected private backup repository,
not the public software repository. No default model provider, remote machine,
training dataset, GPU or advisory service is selected by this contract.

Modes Two and Three remain undefined and are refused. Strategy descriptions do
not confer trained model abilities. Physical deployment, sensing, extra workers,
new compute, spending or public publishing require separate current authorization.
