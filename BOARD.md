# GRIP board

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
  proof of permanent unattended reliability. Source changes are local pending
  publication; private recovery receipts are banked separately.

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
