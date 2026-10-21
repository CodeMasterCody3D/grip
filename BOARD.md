# GRIP board

## Portable public distribution

- Controller discovery is checkout-relative rather than a personal home path.
- Skill installation, user cache and separate private backup storage are configurable.
- Progress paths, material fields and beacon schemas belong to the user's profile.
- Private backup branches are selected by configuration or the actual checkout.
- Public source excludes personal vaults, mission archives and deployment evidence.
- Historical records are preserved locally; Git history is not rewritten.

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
