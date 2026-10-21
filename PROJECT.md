# GRIP project

GRIP is external, opt-in orchestration for one existing OpenCode session.
It is not a model trainer, inference provider, VM allocator or extra AI worker.

## Rules

1. Preserve the user's authorized objective, selected session and compute scope.
2. Completed tasks stay done; changed evidence requires review, not replay.
3. Events and polling share one lock, binding, freshness check and dispatch gate.
4. Stop, Pause, planning mode, active tools and newer human work suppress wakes.
5. A verified whole objective closes continuation; do not manufacture more work.
6. Keep personal paths and mission data out of the public source tree.
7. Backups require the user's separately selected private repository.

## Existing implementation

- `grip.py`: CLI, session client, watcher, vault, private backup and owned rollback.
- `mission.py`: revision-checked durable tasks, dependencies and activation.
- `completion.py`: source-bound requirements, audit and independent challenge.
- `objective_watch.py`: explicit full-objective closure and eleven review questions.
- `event_hooks.py`, `stream_events.py`, `v2_control.py`: metadata-only observations
  and existing OpenCode API adapters; no prompts or tool outputs are archived.
- `progress_watch.py`: configurable project progress and fresh beacon observations.
- `plugins/grip-events.mjs`: optional bridge; controller discovery is module-relative.
- `skills/grip/SKILL.md`: generic agent instructions, not a running service.
- `tests/verify_activation.py`: fixture verification and source-drift checks.

## Portability and deployment boundaries

Linux, Python 3.10 or newer, Git, GitHub CLI and tmux are required. The optional
bridge and full verification use Node.js 18 or newer. No named developer account,
home directory, model family, hardware host or training runner is required.

Use explicit profiles for session/model/compute identity, workspace, private
backup directory and optional progress layout. Skill location and cache roots
are current-user-derived or explicitly configured; see the README.

Modes Two and Three are undefined; strategy records are not learned abilities.
Private deployment records and immutable source snapshots stay in separately
selected private storage. Removing archives from the current Git tree alone does
not remove them from older commits. The reviewed published branch now starts at
the portable-source snapshot, with restricted original backups preserved.
Do not rewrite history or migrate/restart a live mission without authorization.

Use verified GitHub no-reply commit metadata. Published source must never be used
as a destination for private mission archives, even while visibility is private.
