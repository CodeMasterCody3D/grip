# Change log

## Portable public distribution

- Removed personal controller paths from the hook bridge and skill. The bridge
  discovers its checkout and accepts explicit controller/interpreter overrides.
- Added current-user/XDG cache selection and configurable skill installation.
- Added a separate private backup checkout and configurable/current Git branch;
  public backup destinations remain refused.
- Made progress layout, fields, source paths and beacon schema profile-selected.
- Replaced deployment-specific public notes with generic project contracts.
- Excluded personal archives/evidence from the current public source tree while
  retaining local files and immutable history. Older commits are not rewritten.
- Added relocation, cache, skill, storage, branch and public-backup regression tests.

## October20 — current-project activation and durable progress

- Added direct/casual handoff instructions, with discussion/quoted/deferred
  examples explicitly excluded from activation. Read full messages and honor
  "finish this, then that" ordering through task dependencies.
- Added `activate --mission` (explicit profile for a new state), same-session
  identity checks, single tmux watcher startup/reuse and PID/start/argv receipts.
  Configure-only and installation do not start work. No new AI/VM allocation.
- Added durable task IDs/finish conditions/dependencies, in_progress/waiting/
  blocked states, evidence-backed completion, revision rejection and explicit
  reopening with archived evidence. Completed and blocked queues suppress wakes.
- Fixed legacy schedule resetting completed tasks and clearing dispatch ownership.
  Wake/watchdog prompts reload current progress and recover jobs/results instead
  of treating an old reminder as a new project assignment.
- Reviewed install replacement requires the old skill digest and vaults it first.
- Existing dirty controller/progress watchdog source was vaulted/preserved.
  Verification uses temporary repositories and real tmux against a fake HTTP
  session on the rig: no model inference, paid runtime or GitHub writes.

## Initial implementation — October15,2026

- Added named GRIP skill, single-session idle proxy, private backup and
  content-addressed before/after source vault.
- Added bounded packet estimates/deadline, evidence journal, owned-file rollback,
  stop/pause, freshness and final-turn checks. No new runtime or helper agent.
- Baseline GNU AI snapshot pushed and remote commit verified.

## Pre-arm refinements

- Extended tests caught an old global-best implementation remaining after a
  partial source patch. Corrected to per-family/metric-contract pointers, leaving
  the selected downstream model untouched. Failed behavior existed only in
  temporary unit fixtures; earlier wave measurements remain valid.
- Repeated identical changes do not exhaust a method's distinct-attempt target.
- Queue changes have a locked task CLI; evidence content is vaulted, not merely
  named. User-edit/conflict and vault-corruption rollback checks are fail-closed.
- Preserved initial controller sources in the vault and Git history.
- Made continuation prompts profile-driven for reuse across projects,while the
  GNU AI mission retains its own compute/model/scope rules. Accepted wakes get
  a durable receipt; a transient receipt-push failure preserves acceptance state
  rather than risking a duplicate. Added pinned-model positive dispatch tests.
