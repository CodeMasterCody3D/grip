# Portable-release verification

The relocated-checkout release passed 127 Python checks and four JavaScript
checks with zero failures, errors, skips or source drift. Its checkout path
contained spaces. Tests use temporary repositories and fake sessions, including
real tmux watcher startup/reuse/cleanup; no model or paid compute was used.

Coverage includes activation/progress protection, whole-objective closure,
Stop/Plan/freshness/deduplication, event observations, current-user cache and
skill locations, separate private storage, configurable backup branches, path
quoting, configurable progress schemas/layouts and public-backup refusal.

Run `python3 tests/verify_activation.py NEW_EVIDENCE_DIRECTORY` for a source-bound
report for your checkout. Reports record exact source hashes and test output;
personal deployment records are not part of the public distribution.

The natural-language scenarios here are review cases, not measured model-trigger
accuracy. Fixture success does not prove a real autonomous handoff, model-quality
improvement, sustained reliability or unattended readiness for your installation.
Verify actual session identity, watcher heartbeat, wake/start/useful-work receipts,
private backup and the authorized objective separately before unattended use.
