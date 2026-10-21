# Operations reference

Detailed configuration and operating rules for GRIP. For an introduction and setup overview, see the [README](README.md).

**Generalized Repetitive Improvement Proxy**

An external, opt-in improvement workflow for an already-authorized project. It
resumes one existing OpenCode session after a genuinely completed idle turn,
keeps a content-addressed code vault, journals each experiment, and pushes its
source/evidence checkpoints to a private GitHub repository.

GRIP is orchestration, not a model trainer or an application feature. Compute,
model/data formats and transport stay with the selected project's existing tools.
Large weights/data stay in the project's verified artifact stores; GitHub keeps
source, run records and exact artifact receipts.

## Portable setup

GRIP is user- and project-agnostic. It has no fixed home directory, checkout,
provider/model, hardware address or personal project layout. Current support is
**Linux**, Python 3.10 or newer, Git, authenticated GitHub CLI, tmux and an existing
compatible OpenCode session. Linux process identity and UNIX sockets are required;
Windows/macOS support is not claimed. Node.js 18 or newer is needed for the optional
JavaScript bridge and its tests. No Python third-party packages are required.

From your GRIP checkout:

```bash
export GRIP_ROOT="$PWD"
python3 "$GRIP_ROOT/grip.py" --state "$GRIP_ROOT/runtime/unused.json" install-skill
```

This installs instructions for the **current user**, without activating anything.
To choose a different agent's skill directory, pass `--target PATH` or set
`GRIP_SKILL_PATH` to its absolute skill filename. Wake prompts also accept a
profile-specific `skill_path`. Use the same selected location when installing
and configuring the watcher.

The optional bridge derives the controller from its own file location, including
checkout paths with spaces. If you copy the bridge elsewhere, explicitly set its
`controllerPath` option or `GRIP_CONTROLLER` to the actual controller filename.
`python` / `GRIP_PYTHON` selects its interpreter. The default is `python3` on PATH.
Python and the bridge share `GRIP_CACHE_DIR`, or `XDG_CACHE_HOME/grip`, or the current
user's `.cache/grip` directory. Use **absolute** environment paths and the same
environment for the watcher and bridge; different cache roots do not share bindings.

### Private backup storage is separate from this public source repository

Create or choose your own **private** GitHub repository and clone it into a separate
directory. Set these profile fields to its actual values:

```json
{
  "backup_directory": "REPLACE_WITH_ABSOLUTE_PRIVATE_GIT_CHECKOUT",
  "github_repo": "YOUR_OWNER/YOUR_PRIVATE_REPOSITORY",
  "backup_branch": "YOUR_CHECKED_OUT_BACKUP_BRANCH"
}
```

These are template values, not runnable defaults. JSON paths must be real absolute
paths: shell variables and `~` inside a profile are not generally expanded. Discover
the real session/server/provider/model and project authorization before filling the
remaining required fields below. Never paste credentials into the profile.

The backup directory must be the Git repository root with the expected `origin`.
Omitting `backup_branch` selects its currently checked-out branch; detached HEAD
or a configured branch mismatch is refused. GRIP stages only `code_vault` and
`projects` there, verifies private visibility before pushing, and checks the remote
commit. It never creates or selects another user's GitHub account or compute host.
Legacy profiles without `backup_directory` retain checkout-local storage, but
backups into a public remote are always refused. Do not change a live mission's
backup directory without explicitly migrating its existing vault and records.

Personal archives, deployment evidence and local mission state are ignored in the
source tree. The published branch history was replaced with the reviewed portable
source snapshot to exclude earlier private deployment archives. Original history
is retained only in restricted backups; previously downloaded copies and hosting
caches cannot be recalled by replacing a branch.

Use your verified GitHub no-reply email for public-source commits. Audit reachable
history, not just the latest file tree, before changing repository visibility.

### Project-specific progress is opt-in

`watchdog --snapshot PATH` reads your project's beacon. It does not assume a model,
training runner or progress-file directory. Select your actual layout with repeated
`--progress-glob` (workspace-relative JSON patterns), `--progress-field` (material
fields, not heartbeat timestamps), and `--source-path` (explicit source filenames).
The beacon's default schema is `grip_progress_beacon_v1`; `--snapshot-schema` can
select your own. It supplies `now` as Unix seconds and may supply `busy`,
`job_lease_alive`, `job_run_id`, `job_progress`, `idle_since` and `worker_log.bytes`.
Missing, stale or mismatched beacons never establish a safe-to-abort idle machine.
Existing deployments using other schemas/layouts must select those explicitly
before restarting; this release does not rewrite live profiles or restart watchers.

## Cycle

1. Read current authority, best checkpoint, queue and evidence.
2. Record a falsifiable primary hypothesis and an opposite/mirror hypothesis.
3. Bank the working source **before** editing.
4. Run one bounded packet with a positive and a breaking control.
5. Save weights/results, explain the change and check its actual outputs.
6. Bank the iteration, then keep or roll back only its owned files.
7. Try at least three distinct justified variants before parking a method;
   rotate methods and revisit with new evidence. Infrastructure errors and user
   stops are not scientific attempts. Never blindly repeat a deterministic error.

## Commands

## Unified idle watchdog and authorized objective

Tool-finish, completed-turn and session-idle events notify the existing watcher.
They never dispatch independently. Its UNIX notification socket and fallback poll
share one locked gate, persisted final-turn checks, freshness recheck and dedup key.
An idle hint cannot clear real running tools or manufacture a completed turn.
Both native and optional plugin events retain source timestamps when supplied.
The optional plugin remains metadata-only; no extra timer or AI worker is added.

Each continuation carries the eleven-question review: full objective, remaining
work/blocker, recovery without unnecessary questions, concrete fix, measured
improvement, user intent, regressions/permissions, authorized research, authorized
project-authorized advice, actual evidence, and necessary in-scope gaps. These questions grant
no new compute, research authority, agents or spending. Stop/Pause and Plan win.

New missions get an explicit objective guard (default scope `milestone`). A manifest
may set `project_objective`, `project_done_when` and `scope_kind: project|milestone`.
Repeated activation preserves that scope; legacy missions are not silently migrated.
For an existing mission, explicitly migrate with current authority:

`goal --objective TEXT --done-when TEXT --scope project|milestone --note AUTHORITY --revision N`

The goal is the latest closure scope; it does not rewrite old task or model history.
All tasks done means objective review remains pending, not mission complete.
Use `goal-review --result satisfied|unfinished|blocked --note TEXT --evidence RELATIVE.json --revision N`.
`unfinished` records actual gaps; add the genuinely necessary tasks, never reset old
ones. `blocked` suppresses the whole objective even if tasks remain ready. To clear
an evidenced blocker, record an explicit unfinished review or a revised goal; a wake
cannot bypass it. Paused missions remain paused throughout administrative edits.

Satisfied proof must exactly match `objective`, `done_when`, `scope`, and the current
`objective_signature` returned by status, list `questions_reviewed: [1,2,3,4,5,6,7,8,9,10,11]`,
and have literal `passed: true` plus nonempty all-true `checks`. All tasks must be
complete and the iteration banked; Mode1 also requires its verified spec audit and
separate challenge. Actual Mode1 source/task/review changes, or changed/missing
closure proof, invalidate closure without resetting completed tasks. Configure a
Mode1 source-bound spec for source invalidation; legacy task-only missions have no
implicit source inventory. A JSON claim still needs evidence inspection, not trust.
Verified closure suppresses further continuation; GRIP is not an endless polish loop.

## Mode 1: complete the agreed project, not just the task list

October20 opt-in additions preserve legacy missions. Configure a source-bound
spec with `spec --file RELATIVE.json --revision N`; it names `mode: 1`, existing
`source_paths`, and requirements with unique `id` and measurable `done_when`.
Use `add-task --id ID --content TEXT --done-when TEXT --depends-on ID --revision N`
for a genuinely missing in-scope dependency; it cannot replace completed work.

`review --stage requirement|audit|challenge --result pass|fail --note TEXT
--evidence RELATIVE.json --revision N [--requirement ID]` records actual evidence.
Passing reports require literal `passed: true` and nonempty all-true `checks`.
Whole-spec reports must list every requirement ID in `coverage`. Passing audit
grants provisional green, not completion. A separate challenge needs different
evidence bytes and named `scenarios`. Failure preserves evidence and returns to
repair; changed scoped source invalidates old requirement/audit/challenge proofs.
These reports still require human/AI inspection: the CLI cannot certify arbitrary
software correctness from a JSON claim. Modes2/3 remain undefined and refused.

`bind-hooks` binds this exact session and enables a read-only native event observer
inside its one watcher. It uses the discovered native `event.subscribe` SSE route
on the exact bound server (not an unrelated default CLI service) and strips all
events down to matching-session tool/turn/agent metadata.
No raw tool inputs/outputs or other sessions' data are stored. Notifications wake
the same locked eligibility check; polling is the fallback when events are missed.
Plan mode blocks normal and watchdog dispatch. Tool completion alone is not idle.
The optional V2 plugin in `plugins/grip-events.mjs` provides the same observations;
loading that plugin is not required when native events are available. Do not reload
every user's location merely to install a hook into one active session.

`SPEC_MODE1.md` records the generic orchestration contract;
`reasoning_modes.json` records reasoning strategies and future deployment boundaries.
Those strategy specifications are not claims of trained model abilities or AGI.

`python3 grip.py --state /absolute/path/state.json status`

`python3 grip.py --state /absolute/path/state.json activate --mission /absolute/path/mission.json [--profile /absolute/path/profile.json]`

Direct "activate the GRIP skill" or "get a grip would ya, I can't do this while
I sleep" means recover the current chat/project decisions, reconcile this plan,
and run this activation command. Quoted examples, questions, setup instructions
and deferred requests do not activate anything. Read the WHOLE user message:
"finish X, then Y" records Y as a dependent task; it does not interrupt X.
See `skills/grip/SKILL.md` for the agent-side handoff/recovery instructions.

Activation checks the real session, saves progress, then starts/reuses one named
tmux watcher with a verified PID/start-time/argument receipt. `--configure-only`
saves a plan without starting it. Repeat activation cannot reset completed or
in-progress tasks, replace the scope, clear the active iteration or duplicate
the watcher. It does not start a model, create another agent or allocate a VM.

`python3 grip.py --state /absolute/path/state.json checkpoint --note 'baseline'`

`python3 grip.py --state /absolute/path/state.json begin --family FAMILY --hypothesis TEXT --mirror TEXT --change TEXT --file RELATIVE_PATH --estimate-seconds 300`

`python3 grip.py --state /absolute/path/state.json finish --iteration ID --verdict better|same|worse|failed --reason TEXT --evidence RELATIVE_PATH [--best RELATIVE_PATH --metric-contract CONTRACT]`

`python3 grip.py --state /absolute/path/state.json rollback --iteration ID`

`python3 grip.py --state /absolute/path/state.json task --id TASK --status pending|in_progress|waiting|blocked|completed|parked --note TEXT --revision CURRENT [--evidence relative/report.json]`

Durable missions require the current plan revision on task edits and saved
evidence on completion. Each update is locked/atomic. Completed tasks are
terminal unless explicitly reopened with `--reopen` and a reason; their old
evidence stays in history and a new completion needs new evidence. Running or
waiting work takes precedence over new work. Dependencies control readiness.
With an objective guard, all tasks completed leads to objective review; only the
full verified goal becomes complete, suppressing both normal and watchdog wakes.
Unmigrated legacy missions retain their existing completion policy.
A blocked queue is not silently called done.
Wake prompts tell the agent to read the current revision, inspect existing
jobs/artifacts, and reconcile interrupted completion rather than repeat it.
The controller does not itself prove that arbitrary test output means success:
the agent still reads results against each task's declared finish condition.

Legacy `schedule` now preserves completed/running tasks and the dispatch lease;
it cannot replace a durable mission. Use activate/task, not a whole-state rewrite.

## Mission and connection files

An activation mission is JSON with `schema: 1`, stable `mission_id`, `workspace`,
`session_id`, `session_directory`, `objective`, `done_when`,
`continuation_instructions`, nonempty `context_refs`, and ordered `tasks`.
Each task has a stable `id`, `content`, `status`, measurable `done_when` and
optional `depends_on` IDs. An initially completed task also supplies `evidence`
as a list of relative saved-report paths. Activation records their hashes/sizes.
Never store full raw conversations, secrets or model payloads in these files.

A NEW state additionally needs an explicit `--profile`. It supplies the existing
OpenCode `server_url` (owned loopback only), `server_secret_file` (path, never its
contents), exact `session_id`/`session_directory`, `provider_id`/`model_id`,
project `workspace`/`project_id`, `compute_target`, `source_roots`, private
`github_repo` (and a separate `backup_directory` as described above), `poll_seconds`, `idle_grace_seconds`, `maximum_packet_seconds`,
`deadline` and `deadline_basis`. A null deadline needs explicit until-stopped
authority in its basis; activation preserves the selected scheduling policy.
Use real discovered values and the current user's permissions, not another
project's profile or guessed session/model/runtime IDs. An existing state cannot
be rebound by supplying a replacement profile. The user keeps the same chat.

Skill installation: `install-skill` preserves a different installed file by
default. After reviewing it, `install-skill --replace-sha256 OLD_SHA256` vaults
the exact old bytes and installs the current source atomically. Installation
does not activate a mission. Existing TUI skill metadata may require a restart;
the explicit skill and poller prompt remain readable without model inference.

Best pointers are per family/metric contract; promoting a pulse experiment never
replaces the selected downstream model. Distinct causal changes, not repeated
identical failures, count toward a method's minimum attempt target. Queue updates
use the locked CLI rather than rewriting a state file under the running poller.

`python3 grip.py --state /absolute/path/state.json tick [--dry-run]`

`python3 grip.py --state /absolute/path/state.json watch`

`python3 grip.py --state /absolute/path/state.json pause|resume`

Run `serve` and `watch` in named tmux sessions. Do not use `tmux attach`.
The poller never launches a new VM or a helper agent. It targets the configured
existing session and provider/model. A separate loopback server can load that
persisted session; final-turn and fresh-message checks prevent concurrent turns.

## Verification and limits

Unit tests use fake sessions and temporary repositories, never a model/GPU.
Run `python3 tests/verify_activation.py NEW_EVIDENCE_DIRECTORY` from the checkout
for source-bound Python and JavaScript checks, including relocation, current-user
cache/skill paths, separate backup storage, arbitrary backup branches, configurable
progress layouts and refusal to push private mission data to a public remote.
Live verification separately checks server/session identity, active/busy
suppression, private remote visibility, matching pushed commit and actual wake
acknowledgements. An API acknowledgement is not proof the next agent completed
useful work; heartbeat records those stages separately.

The agent host must remain powered/connected and its credentials/quota must work.
Deadline, explicit pause/stop, permission blocks and unreachable services are
recorded and alarmed. Healthy remote jobs are not killed to make a poller look busy.
Rollback refuses concurrent user changes; it never runs git reset/restore on the
working project. New/changed skill discovery in an existing TUI needs restart;
GRIP's wake prompt explicitly reads the skill without depending on that cache.
