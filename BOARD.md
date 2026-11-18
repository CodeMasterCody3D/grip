# GRIP board

## Claude Code binding built and live -- November 1, 2026

- Cody, 3:44 PM: "make sure the grip skill can use the python script to hook intoo the claude harness like how the claude-mem does.
  this would make it so the grip side for cluade can work and you can continue training captureing data and info so we can make a
  better trainer and i learn at the same time". Until now GRIP could wake only OpenCode sessions (its loopback server).
- New file `claude_bridge.py` (no GRIP file edited): one `hook` command for every Claude Code hook event (stdin JSON, like claude-mem),
  feeding GRIP's own event kinds into the mission state and a metadata-only observation log (`claude_observations.jsonl`: tool, purpose or
  file, ok / failed, seconds; never command text, output or prompt text); a Stop gate that sends the turn back with GRIP's wake prompt
  while a task is actionable and no waiter is armed (never on a stop-hook continuation, plan mode, pause, deadline, wake budget, or a turn
  with no tool work since the last block); `wait`, the wake, run as a Claude Code background task (exits with the wake prompt when its
  `--until` check passes or the heartbeat elapses); `init` (mission.activate, schema 1), `bind`, `unbind`, `status`, `observations`,
  `install-hooks` (merges into a settings file, keeps the old one beside it, idempotent).
- Tests: `tests/test_claude_bridge.py`, 7 pass (unbound silent; events + metadata-only log; human stop pauses; gate continues once and
  never spins; armed waiter lets the session stop and wakes on its condition; paused mission refuses; install keeps existing hooks).
- Live: mission `runtime/heal27-opd-1101` bound to Claude session 5f10507f (onebit-forge, the 27B healing run on cody-a100-heal27);
  hooks installed in onebit-forge/.claude/settings.local.json; tool events observed live (tool_start / tool_end, 2.8 s measured).
- Not done: a Claude Code plugin package (hooks.json) for install-anywhere; user-wide install (one flag: --settings ~/.claude/settings.json).
- 5:58 PM FALLBACK (Cody: "add a fall back feature to have you occasionally check on it just in case its failed silently"):
  `wait --health "<check>" --health-strikes 3` -- a shell health check every poll; 3 failures in a row wake the session at once
  with the check's output (8 tests pass). Plus an independent Claude Code scheduled check-in (CronCreate, every ~20 min while idle)
  that re-runs status + the health check and re-arms a dead waiter or poller -- it does not depend on any watcher process.

## Task-first GRIP update installed — October 26, 2026

- Installed the reviewed task-first controller, objective prompt, skill instructions
  and matching operations/project/test files from `improvement/task-first-workflow`.
  Wake messages now prioritize existing work, decision-relevant checks, independent
  workload backup cadence and brief next-action/wait updates. Completed task history
  and full evidence blobs no longer accumulate in wake previews.
- Each replaced source file matched the branch's published-main base beforehand;
  unrelated existing edits were preserved. Exact pre-update source, installed skill
  and private mission snapshots are retained outside the repository.
- Used the installer's reviewed-hash replacement to update the installed skill.
  Gracefully reloaded four PID/start-verified paused watchers and one existing
  standby. No activation, resume, dispatch, training, model backup or cleanup ran.
- Verified all seven deployed file hashes against the reviewed branch, installed
  skill equality, new prompt generation without dispatch, fresh paused heartbeats
  and unchanged tasks, goals, revisions, completion, active-iteration and wake fields.
  Reused the branch's nine passing focused checks rather than repeat the suite.
- All four missions remain paused. Trainer storage/retention behavior is unchanged;
  this installation does not resolve a project's storage blocker or demonstrate
  improved training throughput. No source commit, merge or public push was made.
- Private deployment evidence: `~/.cache/grip-update/20261026-211012-task-first/`.

## Website project emblems published October 24

- Reused the supplied lab emblem already embedded on the website beside all six
  project names. Icons are 40-pixel contained images, decorative to screen readers;
  project names, descriptions, links and filter metadata remain unchanged.
- Headless Chrome desktop and mobile checks verified six loaded logos, exact
  dimensions and no horizontal overflow. Project-section screenshots visually
  reviewed; initial CLI screenshots were unsuitable, replaced by CDP captures.
- Website main commit 6e40f6a09c71b0fae6bd86cdafb41fbbf803570b changes only
  index.html. Normal push, remote tip and GitHub bytes verified. Pages run
  40114998537 succeeded; fresh live HTTP 200 confirms the logo update.
- Evidence and publication receipt: /home/cody/.cache/grip-site-publish-20261023-193326/
  project-logos-layout-checks.json and website-project-logos-publication.json.
  No GRIP source, mission, service, model job or unrelated browser session changed.

## Website Discord links published October 23

- Added the supplied Discord invite to the main navigation and as a footer icon
  immediately beside GitHub; all other website bytes preserved.
- Website main commit 27fd3c7323ff9985bb28eaf176b81b65224a4230 normally pushed
  and remote tip verified. Pages run 40046758287 succeeded. Fresh live HTTP 200
  response contains exactly two invite links in the requested locations.
- Receipt: /home/cody/.cache/grip-site-publish-20261023-193326/website-discord-publication.json.
  No GRIP source, runtime, mission or services changed.

## Main publication verified October 23

- Published the approved caption beneath the logo to GitHub main in commit
  22f30d7ab14886985470910f1d59de6a6aaa9646. Normal fast-forward push and
  independently fetched GitHub README bytes verified.
- This PC's running GRIP processes use /home/cody/grip/grip.py. That checkout
  is on main with older ancestry and preserved local edits, not a caption
  branch. All 35 previously published files exist locally; controller, plugin,
  skill and tests match published main. Only README and local Board differed.
- All 22 saved release source hashes match; prior passing 155 Python and four
  hook checks remain applicable. No test rerun or controller update needed.
- Published from a clean main clone rather than pushing the running checkout's
  older history. No service restart, private-state publication or history rewrite.
- Website main commit fe1f7b49938d64d04633af4d5d62bbc044f16447 changes only
  “Built here. Taking shape here.” to “Built here. Shaped here.” and retains
  “Project directory”. Remote commit and content verified. Pages deployment
  40045712516 succeeded; a fresh live-page request verified the new tagline.
- Publication receipts and exact pre-edit snapshots are outside the public
  tree in /home/cody/.cache/grip-site-publish-20261023-193326. Previous video
  and benchmark evidence preserved; no GRIP video production started.

## Logo caption added October 23

- Added the user's approved six-finger joke immediately beneath the README logo:
  “Tell your AI to get a GRIP.”, the extra-finger action, and “Extra GRIP.
  Obviously.” The image and all other README content are unchanged.
- Preserved existing worktree edits and exact pre-edit documentation snapshots
  outside the public source tree. Documentation-only edit; no activation,
  watcher/service changes, video production, commit or push.

## Public visibility approved October 22

- The user explicitly requested making GRIP public again. GitHub visibility is
  now public, independently verified through an unauthenticated metadata request.
- A fresh read-only mirror scan covered all reachable refs, including the
  documentation branch and pull-request refs. No scanner detections or private
  deployment archive paths were found. No release assets or Actions artifacts
  were present in the preflight metadata.
- Existing source commits and history were unchanged. The separately selected
  private backup repositories remain private. No mission, watcher, service or
  installed skill was restarted or migrated for this visibility change.
- This publication does not certify unknown-format secrets, unavailable hosting
  caches or earlier external copies. The existing source/private-runtime boundary
  remains required even while the source repository is public.

## Interrupted completion and standby reliability repair

- Root cause: a terminal iteration was written before lease release, retries
  rejected that terminal record, and the returned backup commit was never saved
  into a durable finish receipt. Clearing the flag alone did not fix this.
- Completion now seals its request, verifies evidence/vault and private-bank
  proof, persists a receipt, deduplicates the attempt, and reconciles the lease.
  Interrupted retries preserve source work and reuse an already verified bank.
- Explicit legacy recovery banks the before-state and checks the original bound
  session, idle ownership and exact record hash. It preserves pauses and task/goal
  blockers. A separate evidence-backed review can release only a repaired
  infrastructure blocker; genuine prerequisites and completed work remain intact.
- Passive standby owns no dispatch path. It restarts only a proven-dead primary
  through serialized startup, the exclusive primary lease and shared state lock.
  Live hangs, uncertain ownership and unknown dispatch acceptance require
  investigation. Pending dispatch intent is persisted before server contact to
  prevent replay after an ambiguous acceptance/crash.
- The standby fault test exposed lost process identity on dead-owner inspection;
  dead receipts now retain their ownership evidence without claiming liveness.
- Passive health observation does not block behind a stuck dispatch lock; an
  action still requires the same nonblocking gate. A held lock is investigated,
  never bypassed. The corrected monitor was reloaded without restarting its busy
  primary chat or changing mission flags.
- The final source-bound suite passed 155 Python tests and four hook checks,
  with zero failures, errors, skips or source drift. It includes real Git-bank
  proof, crash-boundary injection and actual tmux/fake-server failover. No model
  inference or project tests were repeated by this suite.
- The saved blocked completion was privately verified and reconciled; a repeated
  recovery retained one attempt and created no duplicate backup commit. Its
  already-authorized preparation task is pending again. Genuine model/runtime
  prerequisites stay blocked. One primary and one passive standby are live for
  that deployment. Its busy chat remains protected rather than force-cleared.
- General reasoning, Build and engineering, and Creation Mode are investigation
  procedures, not learned capabilities. Modes Two and Three remain undefined.
- This bounded controller repair is not completion of the underlying project or
  proof of permanent unattended reliability. The repair source and requested
  README/banner are published on main; private recovery receipts remain separate.

## Local service-restart address repair

- Reproduced rejection when the service advertised a wildcard listener while its
  client remained on the same loopback port. This was a representation mismatch,
  not a need to move the session or copy credentials.
- Added strict local endpoint comparison, plus listener-to-loopback conversion for
  explicit adoption. Remote endpoints and actual port changes remain refused.
- All 133 Python tests passed, including the reproduced regression, negative URL
  cases, session-adoption failure and preservation of paused/completed work.
- Verified four existing session/directory bindings with read-only requests and
  reloaded only their GRIP watchers. Their tasks and active/paused/blocked states
  were preserved. OpenCode, model jobs and unrelated services were not restarted.
- Fresh heartbeats no longer report the endpoint mismatch; native tool events are
  observed for the current chat. Historical errors remain as diagnostic history.
- This repairs the connection blocker; it does not force an autonomous wake or
  clear separate human-takeover, paused or blocked conditions.
- Adopted the user-selected documentation branch's README and banner as exact
  files, without importing its Git history. Its operations reference retains the
  technical documentation and now includes the mobile/listener address repair.

## Portable public distribution

- Controller discovery is checkout-relative rather than a personal home path.
- Skill installation, user cache and separate private backup storage are configurable.
- Progress paths, material fields and beacon schemas belong to the user's profile.
- Private backup branches are selected by configuration or the actual checkout.
- Public source excludes personal vaults, mission archives and deployment evidence.
- Historical records are preserved in restricted backups. Authorized publication
  hygiene replaced the remote branch history with the reviewed portable snapshot.
- Git author/committer metadata uses a verified GitHub no-reply identity.
- A fresh remote clone of the sanitized source snapshot passed the secret scan.

## Verification

The relocated-checkout release passed 127 Python checks and four JavaScript checks
with zero failures, skips or source drift. It ran in a checkout path containing
spaces; its actual tmux lifecycle uses a fake session, not model inference.

Fixture tests use fake sessions and temporary repositories. The portability suite
checks changed home/cache/skill locations, paths with spaces, private storage,
branch selection, public-backup refusal and configured progress layouts.
Run the source-bound verifier for evidence for your exact checkout.

## Boundaries

No live session, model mission, storage migration or watcher restart is part of
this public-source cleanup. Existing deployment configuration remains its owner's
responsibility. Model capability or sustained unattended reliability is not implied
by passing controller fixtures. Modes Two and Three remain undefined.

Replacing published history cannot recall older clones or guarantee deletion of
hosting caches. Keep source and private backups separate regardless of visibility.
