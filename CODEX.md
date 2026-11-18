# GRIP in Codex

The Codex bridge uses native lifecycle hooks. It needs Python 3.10+ and Linux,
but no OpenCode server, tmux poller, new model, API key or desktop patch.
Existing OpenCode and Claude missions are separate and unchanged.

## Install without activating

From the GRIP checkout:

```sh
python3 codex_bridge.py install-hooks
python3 grip.py --state runtime/unused.json install-skill
cp -R skills/grip-infinite "$HOME/.agents/skills/"
```

The first command merges seven handlers into `$CODEX_HOME/hooks.json` (normally
`~/.codex/hooks.json`), preserves other hooks, and backs up an existing file
before changing it. Repeat installation adds no duplicates. It never changes
hook trust or binds/activates a chat. The installed skill updater requires the
existing skill digest if replacing a different installed version; use its
`--replace-sha256` option only after reviewing that version.
The copy exposes the companion `grip-infinite` skill in the slash menu. Run it
once when that destination is absent; review an existing skill before replacing
it. Use a regular directory: the inspected build did not discover a linked
shortcut folder, but native `skills/list` confirmed the regular installation as
enabled without errors. A plugin installation discovers both packaged skills
automatically, so it does not need this copy.

Review the GRIP commands in **Settings > Hooks** or **Review hooks** in the
desktop composer; the CLI equivalent is **`/hooks`**. Codex skips untrusted
hooks. Already-loaded threads may need a normal reopen/restart before new
hook definitions are discovered. Do not globally reload active chats.

The optional portable `plugin.json`, compatibility `.codex-plugin/plugin.json`,
and `hooks/hooks.json` package the same bridge and skill for a local plugin.
Choose either plugin hooks or the direct user hook installation to avoid
registering the same bridge twice. The runtime gate also deduplicates wakes.

## Configure one chat, then activate on handoff

Recover the actual current thread ID from `CODEX_THREAD_ID`, its workspace,
authorized compute and existing mission. Do not copy another chat's binding.
Use GRIP's schema-1 mission JSON: `mission_id`, `objective`, `done_when`,
`continuation_instructions`, nonempty `context_refs`, and tasks with stable
`id`, `content`, `done_when`, `status`, optional `depends_on`, and saved evidence
for completed tasks. Keep the full agreed project objective in `project_objective`
and `project_done_when` when applicable; the default objective scope is a milestone.

```sh
python3 codex_bridge.py --state /absolute/project/.grip/codex-state.json configure \
  --mission /absolute/project/.grip/mission.json \
  --thread-id ACTUAL_THREAD_ID --workspace /absolute/project \
  --compute 'The compute and tools authorized for this project' --max-wakes 20
python3 codex_bridge.py --state /absolute/project/.grip/codex-state.json status
```

Configuration leaves a new mission paused. Only after the user hands over the
current work, run:

```sh
python3 codex_bridge.py --state /absolute/project/.grip/codex-state.json activate
```

Activation arms the next native Stop event; it does not itself start an idle
chat or send a message. The active chat uses its existing model and permissions.
Use the original `grip.py --state ... task/add-task/goal/goal-review` operations
to record progress and completion with revision/evidence checks. `begin` and
`finish` still need the project's separately configured private backup lane;
the Codex binding does not invent or configure that lane. If it is absent, use
the project's authorized edit/verification workflow and record task evidence;
do not pretend a private source bank exists.

```sh
python3 codex_bridge.py --state /absolute/project/.grip/codex-state.json pause
python3 codex_bridge.py unbind --thread-id ACTUAL_THREAD_ID
```

A leading `stop`, `pause`, `cancel`, or `hold on` message (optionally starting
with `please`) pauses the mission. Codex's Interrupt hook pauses it immediately.
Normal session restart and repeated configuration preserve that pause. Removing
a binding makes the global hook inert for that chat without deleting its state.

## Optional infinite mode for Codex

Type **`/grip-infinite`**, select the `grip-infinite` skill from the slash menu,
and send it to activate infinite mode in that chat. **`$grip-infinite`** and
**"Turn on GRIP infinite mode for this chat"** also work. Ordinary "activate
GRIP" selects the normal mission workflow unless infinite mode was requested.
This hands over existing work without requiring a mission or finish condition.
Adding/installing the feature alone does not arm any chat. If a newly installed
skill has not appeared yet, reopen the skill menu; Codex normally detects new
skills automatically. The skill uses these commands with the
actual chat ID, project and authorized scope:

```sh
python3 codex_bridge.py --state /absolute/project/.grip/codex-infinite.json configure-infinite \
  --thread-id ACTUAL_THREAD_ID --workspace /absolute/project \
  --compute 'The existing authorized local tools and compute' \
  --instructions 'Continue this project: repair unfinished work, then execute existing approved plans and ideas.'
python3 codex_bridge.py --state /absolute/project/.grip/codex-infinite.json configure-desktop \
  --endpoint http://127.0.0.1:9222 --target-id SELECTED_CODEX_PAGE_ID \
  --node /absolute/existing/node
python3 codex_bridge.py --state /absolute/project/.grip/codex-infinite.json activate
```

The renderer debugger must already be running as described below. Activation
arms the next Stop event in this existing chat; it does not send an initial
message to an idle chat. No mission JSON, objective, task list, or completion
review is required. The scope and tools fields retain the user's authorization.
The mode has **no wake-count cap**, and completed tasks, completed missions or
text-only turns do not end it. `status` reports `continuation_mode: infinite`,
`continuation_active`, and `maximum_wakes: null`. The wake counter remains a
metric. Existing task/goal evidence is preserved, and can still be updated with
the usual revision-checked task commands; mission completion and mode activation
are separate state.

After each turn, GRIP prefers the actual grey composer suggestion for that
exact turn. If none appears during the grace window, it sends a compact review
prompt: double-check the user's requests and unfinished work, inspect existing
plans, TODO/backlog and idea lists, then execute the next authorized item. It
continues reviewing even when no task is currently listed; it must report an
empty backlog honestly rather than manufacture work. Sends are spaced at least
15 seconds apart, without a retry/wake-count cutoff.

Both paths first resume the current work. **A failed code attempt means debug
and repair that same task.** Inspect the error, fix the implementation, and run
the relevant check. If necessary, try a different literal implementation of the
same code/solution. One failed attempt is not a reason to give up, ask for routine
approval, or abandon it for another idea. Each repair should use the failure
evidence rather than repeat unchanged failing code. There is no arbitrary fixed
number of code attempts. This is programmed continuation guidance, not a promise
that every implementation can be repaired or that instructions train the model.

Stop/Pause and Interrupt still disarm the mode. Planning mode, newer human input,
a human draft, real permission constraints and uncertain message delivery remain
guards. A private-interface failure is recorded rather than risking duplicate
messages. Each post-turn worker exits within 60 seconds; the next actual turn's
Stop creates the next worker. There is no independent app-crash watchdog.

For an already-bound chat, pause it and use its **existing state path** with
`configure-infinite`; do not create a second binding. This preserves completed
work, saved receipts, accumulated wake counts, and any previously authorized
deadline. A retained deadline still applies. An unresolved pending send must be
reconciled before changing mode. To return to bounded mission mode, pause and
`configure --mission ...` with that same state path; no progress is reset.
Use `pause` or `unbind` as above when finished.

Codex lists enabled skills in its slash menu and also accepts explicit `$` skill
mentions: [official slash-command documentation](https://learn.chatgpt.com/docs/reference/slash-commands).

## Bounded mission continuation behavior

On Stop, only an active, identity-matched mission with actionable work can wake.
Planning mode, a reached deadline, an exhausted wake budget, blocked/completed
work, duplicate Stop delivery, or no tool/task progress since the last wake
suppresses continuation. Continued turns may continue again after real progress,
subject to the same limits. Concurrent events share GRIP's state lock. A locked
or failed hook lets the chat stop and emits a short diagnostic; it does not
claim a wake was sent. Status distinguishes observed hooks from a wake decision.

The native-only hook has no background watchdog. It cannot restart a crashed
app, wake a chat after hook trust prevented execution, or resume an idle job
just because a timer elapsed. Keep using a project's existing wait mechanism.
With a verified desktop binding, Stop launches one bounded post-turn worker.

## Composer predictions and post-turn delivery

Codex's generated app-server protocol contains `thread/prediction/updated` with
`threadId`, `sourceTurnId`, and a completed/failed result. An upstream integration
that actually receives that event can forward the JSON to:

```sh
python3 codex_bridge.py ingest-prediction < event.json
```

The consumer stores only predictions for an explicitly bound chat and a turn
already observed by its hooks. Stop prefers a nonempty completed prediction for
that exact turn, received in the last 120 seconds. Empty, failed, stale, absent,
or different-turn predictions use GRIP's normal continuation prompt. Predictions
are wrapped as generated suggestions within the existing authorization, not as
new human instructions. A new prompt invalidates the cache.

The inspected desktop build (Codex CLI 0.167.0-alpha.4.1) generates/caches the
prediction privately after turn completion, whereas Stop runs before that
completion. There is no prediction field in the documented Stop input. The
app runs its server over private stdio and exposes no daemon control socket in
this installation. The protocol event's existence is not proof that the private
composer service emits it.

Code inspection located a direct read path: the visible ProseMirror editor's
`cumberbatch$` plugin retains `{ prediction: { text, sourceTurnId, ... } }`, and
the corresponding displayed widget is `[data-cumberbatch] .cumberbatch-content`.
`desktop_predictions.mjs` reads that existing state through Electron's renderer
debugger. It does not ask the model for a suggestion, modify the editor, accept
the prediction, press keys, read credentials, or send a chat message. It checks
an exact source turn before returning text and declines capture if a draft or
composition is present. The metadata reader searches the composer's React
controller references and verifies that the editor view owns the exact composer
DOM node. This read path has been verified in the running app: it captured the
displayed suggestion `check capture` with the exact source-turn ID for the
preceding response. Ingested samples are labelled `desktop_composer_cdp`.

### Restart when you are ready

`scripts/launch-codex-debug.sh` starts this installed app with renderer debugging
on `127.0.0.1:9222`. It refuses to start while Codex is already running and never
stops existing processes. Quit the app normally after other work finishes, then
run the launcher and reopen the chat you want to inspect. This opens a local
debugging interface while that app run lasts; launch Codex normally to return
to an ordinary run. The executable and port can be chosen with `GRIP_APP_BIN`
and `GRIP_DEBUG_PORT`.

After restarting, use Node 22+ (this installation also bundles a suitable Node
at `/usr/lib/chatgpt/resources/cua_node/bin/node`):

```sh
node desktop_predictions.mjs --endpoint http://127.0.0.1:9222 --list
node desktop_predictions.mjs --endpoint http://127.0.0.1:9222 \
  --target-id SELECTED_CODEX_PAGE_ID --visible-text
node desktop_predictions.mjs --endpoint http://127.0.0.1:9222 \
  --target-id SELECTED_CODEX_PAGE_ID --source-turn EXACT_COMPLETED_TURN_ID
```

For a bound mission with an observed turn, `--state /absolute/codex-state.json`
supplies its thread and turn IDs. Add `--ingest` to pass a captured suggestion
to the bridge. This command is a read probe, not a standing watcher.
The first live check can use `--visible-text` to read the rendered grey text
without internal metadata. This mode never invents a source turn and cannot
ingest a suggestion for automatic use.

The reader supports a bounded `--watch-seconds 300 --out /absolute/capture.json`
check so it can observe the prediction after the current response finishes.
It reads only and does not send a follow-up. The output distinguishes waiting,
capture, and timeout; a working debugger connection alone is not capture proof.

### Connect post-turn delivery for a paused mission

Choose the Codex app page from `--list`:

```sh
python3 codex_bridge.py --state /absolute/codex-state.json configure-desktop \
  --endpoint http://127.0.0.1:9222 --target-id SELECTED_CODEX_PAGE_ID \
  --node /absolute/existing/node --prediction-wait-seconds 12
```

This verifies the desktop thread owner and reads only that chat's saved turn
metadata; it also verifies the live composer identity when that chat is visible.
It sends no input and does not activate the mission. Activate through the
usual explicit handoff when ready. The native Stop hook then reserves one wake
and lets the response finish. `codex_desktop.py` waits for the exact chat to
become idle, then reads its real prediction. A suggestion received during the
grace window is included in the GRIP continuation; otherwise the normal GRIP
prompt is used. Delivery uses the app's existing-thread IPC route, inherits
its model/permissions, and does not insert or delete composer text.

The worker exits within 45 seconds in mission mode (60 in infinite mode). A human draft in the bound chat, newer
input, interrupt/pause, planning mode, unsupported context or changed mission
stops the wake. If a different chat is visible, the worker uses the normal GRIP
fallback for the bound chat through native IPC and leaves the visible chat alone.
It waits for the exact source turn's completed status and timestamp in the
local history projection, reading `turn_id`, `status` and `completed_at` only.
It reads no message content. A newer or failed/interrupted turn suppresses the
wake; a missing or changed private history schema fails closed.
Input and pause markers are written independently of the state lock.
Immediately before sending, both UI and mission/input freshness are checked
again. Sending is not atomic with future human input at the desktop server;
the native admission route remains responsible for handling an input that
arrives after dispatch starts.

Pending state records waiting, dispatching, IPC acceptance and a matching
continuation turn's first native tool event separately. A timeout or unexpected
app response after dispatch is `delivery_unknown`, and is never retried.
If a later native input/tool event carries that exact sealed wake token in a
new turn, GRIP reconciles it to `agent_started` while retaining the earlier
delivery phase for audit. The native sender accepts `TurnStartResponse.turn.id`
as well as supported sent/queued UI wrappers.
Duplicate Stop deliveries cannot create a second pending worker. The desktop
IPC and React-controller interfaces are private and version-sensitive; changed
shapes fail closed. Predictions can be read when the bound chat is visible;
the normal fallback supports background work. Other chats remain inert unless
separately bound and activated.

### Verified installation result

On the inspected Linux desktop build, the real grey suggestion `check capture`
was read with its exact originating turn ID. A separate one-wake native Stop
test then delivered the normal GRIP fallback to the same existing chat and
started an agent turn with the matching wake token. The temporary test was
paused and unbound after that single continuation. No other chat was changed.

Prediction selection, input/draft/pause/plan guards, background fallback,
native framing, uncertainty handling and receipt reconciliation also have
isolated tests. The live send used the fallback; the prediction-specific send
choice was fixture-tested and uses the same verified transport. This is a
private-interface integration for the inspected build, not a compatibility
promise for future desktop updates.

## Verification

```sh
python3 -m unittest discover -s tests -p test_codex_bridge.py -v
python3 -m unittest discover -s tests -p test_codex_desktop.py -v
node --test tests/test_desktop_predictions.mjs
```

These tests cover the real bridge command through stdin/stdout, including
prediction/fallback selection, concurrency, pause/interruption, scope, budgets,
malformed input, idempotent installation, preserved mission progress, and infinite
mode across successive text-only turns after completion and old budget exhaustion.
Infinite-mode tests verify prediction/review selection, same-task repair guidance,
spacing and human/transport guards. They
do not make model calls or send messages to real chats.

Release behavior references: [OpenAI Hooks](https://learn.chatgpt.com/docs/hooks),
[Composer Predictions](https://learn.chatgpt.com/docs/features/composer-predictions),
and [Plugin packaging](https://developers.openai.com/plugins/build/plugins).
