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

Personal historical files are ignored and retained in restricted local backups,
including exact pre-edit source snapshots. The authorized publication cleanup
replaced reachable branch history with the reviewed portable source tree and
no-reply commit metadata. Application/source bytes were preserved; no live mission
or existing watcher was migrated or restarted by that history replacement.

Do not push old backup refs or archives into the source repository. Old public
clones and hosting caches are not proven erased by a branch replacement.
