# GRIP maintainer handoff

Read the project rules, README and Mode One specification before changes.
Reuse the existing controller, task/goal gates, private vault and event dispatcher.

The public repository contains portable software and generic tests, not an active
mission. Recover runtime state only from the current user's selected profile.
Never adopt an old session, model, endpoint, compute host or project by example.

Private backup storage can be separate from the software checkout. Moving existing
storage requires an explicit migration of its vault and records; do not change a
live profile or restart an owned watcher merely to install a software update.
Public remotes remain invalid backup destinations.

Portability verification passed 127 Python and four JavaScript checks, without
failures, skips or source drift, from a relocated checkout whose path has spaces.
This proves fixture coverage for that release, not a new live deployment.

Personal historical files are ignored and retained locally, including pre-edit
source snapshots. Old Git commits still contain historical deployment material;
the portable-source cleanup does not rewrite or erase that history.
