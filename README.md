# GRIP

## Tell your AI to get a GRIP.

**Keep the mission moving. Make every improvement prove itself.**

GRIP helps your AI coding agent follow through on the work you've already agreed to do. When a compatible OpenCode session finishes a turn and becomes idle, GRIP checks whether authorized work remains and, when eligible, prompts that same session to continue.

It keeps the objective, task history, source checkpoints, and experiment evidence together so the agent can pick up where it left off, test its changes, and work toward a verifiable finish.

**GRIP** stands for **Generalized Repetitive Improvement Proxy**.

[Get started](#get-started) · [How it works](#how-it-works) · [Commands](#everyday-commands) · [Operations reference](OPERATIONS.md)

## What does GRIP do?

An agent can finish a response while the larger project still has work left to do. GRIP adds a structured continuation workflow around your existing session.

| Capability | What it means for your project |
| --- | --- |
| **Continue eligible idle sessions** | Prompt the same agent to take the next authorized step after its turn has actually finished. |
| **Keep track of the mission** | Preserve the objective, task dependencies, completed work, blockers, and supporting evidence. |
| **Checkpoint before changes** | Save working source in a vault indexed by content hashes before an experiment begins. |
| **Record each experiment** | Track the hypothesis, change, measured result, and decision to keep or roll back the iteration. |
| **Back up source and evidence** | Push checkpoints and run records to your own private GitHub repository. |
| **Review the actual finish condition** | For missions using the objective guard, require an evidenced objective review after the task list is complete. |

GRIP coordinates the workflow. Your existing agent, model provider, project tools, and compute do the work. It does not train a model itself, start another AI worker, or allocate a machine.

## How it works

You define the mission: **what to accomplish, what counts as done, and what the agent is allowed to do.** GRIP binds that mission to one existing OpenCode session and starts or reuses a single background watcher.

1. **Check the session.** Wait for a completed turn and genuine idle state. A tool finishing by itself is not enough.
2. **Read the current mission.** Check remaining tasks, dependencies, blockers, checkpoints, and evidence.
3. **Continue eligible work.** Prompt the same session to take the next step within the agreed scope.
4. **Run a bounded experiment.** The agent states a testable hypothesis and an alternative explanation, saves the baseline, makes a change, and tests it.
5. **Record the outcome.** Save the results, checkpoint the iteration, and keep or roll back the files it owns.
6. **Review completion.** For objective-guarded missions, check the agreed finish condition before closing the mission and suppressing further continuation.

For example, a bug-fix mission might require the agent to reproduce a failure, checkpoint the source, test a repair, and save regression evidence. If it finishes a turn before those steps are complete, GRIP can prompt it to continue the remaining eligible work.

**You stay in control.** Pause, stop, Plan mode, permission limits, and configured deadlines take precedence. A blocked mission is not treated as finished, and a continuation prompt grants no new authority or spending.

## Requirements

Current support is **Linux** with:

- Python **3.10+**
- Git and an authenticated GitHub CLI (`gh`)
- `tmux`
- An existing compatible **OpenCode** session
- A separate **private GitHub repository** for mission backups

The optional JavaScript bridge and its tests require **Node.js 18+**. The Python controller has no third-party package dependencies.

GRIP currently relies on Linux process identity and UNIX sockets. Windows and macOS support is not claimed.

## Get started

### 1. Install the agent instructions

From your GRIP checkout:

```bash
export GRIP_ROOT="$PWD"
python3 "$GRIP_ROOT/grip.py" --state "$GRIP_ROOT/runtime/unused.json" install-skill
```

This installs the GRIP skill for the current user. **Installation does not activate a mission.**

For a custom skill location, use `--target PATH` or `GRIP_SKILL_PATH`. See the [installation details](OPERATIONS.md#portable-setup).

### 2. Prepare your mission and connection profile

A **mission** describes the objective, finish conditions, tasks, and context the agent needs. A **profile** identifies the existing OpenCode session, project workspace, model/provider, backup repository, and scheduling limits.

Use the real values from your environment. Paths in these files must be absolute where required; `~` and shell variables inside JSON are not generally expanded. Store credential file paths rather than credential contents.

Prepare a separate checkout of your private backup repository. The public GRIP source repository is not the destination for private mission records.

Read the [mission and profile fields](OPERATIONS.md#mission-and-connection-files), [private backup setup](OPERATIONS.md#private-backup-storage-is-separate-from-this-public-source-repository), and [agent handoff instructions](skills/grip/SKILL.md) before activating.

### 3. Activate GRIP

Replace the example paths with your actual files:

```bash
python3 "$GRIP_ROOT/grip.py" \
  --state /absolute/path/state.json \
  activate \
  --mission /absolute/path/mission.json \
  --profile /absolute/path/profile.json
```

A new state requires `--profile`. For an existing state, omit it: that state already owns its session binding.

Activation verifies the session, saves the mission, and starts or reuses its watcher when actionable work is available. Add `--configure-only` to save and verify the configuration without starting the watcher.

In a compatible agent session with the skill installed, explicitly asking the agent to **activate GRIP** tells it to recover the current project decisions and perform this setup using your actual environment. Mentioning GRIP in a question or quoting an activation phrase does not activate it.

## Everyday commands

Run these from the GRIP checkout after configuring a mission. Replace the state path with your own.

| Action | Command |
| --- | --- |
| View mission and watcher status | `python3 grip.py --state /absolute/path/state.json status` |
| Pause the mission | `python3 grip.py --state /absolute/path/state.json pause` |
| Resume the mission | `python3 grip.py --state /absolute/path/state.json resume` |
| Preview continuation eligibility | `python3 grip.py --state /absolute/path/state.json tick --dry-run` |
| Save a source checkpoint | `python3 grip.py --state /absolute/path/state.json checkpoint --note 'baseline'` |

For experiment commands, task updates, event binding, progress monitoring, and objective reviews, see the [operations reference](OPERATIONS.md).

## What counts as done?

For new missions, GRIP uses an **objective guard**: completing every task leads to an objective review, rather than automatically declaring the whole mission complete. The review must match the current objective and include the required saved evidence. Legacy missions retain their existing completion policy until explicitly migrated.

Optional **Mode 1** adds requirements tied to specific source files, a whole-spec audit, and a separate challenge review. Changes to the scoped source invalidate earlier proofs so they must be checked again.

These checks enforce the review workflow; they cannot establish software correctness just because a JSON report says `passed: true`. The agent or reviewer still needs to inspect the evidence.

See the [Mode 1 specification](SPEC_MODE1.md) and [completion rules](OPERATIONS.md#unified-idle-watchdog-and-authorized-objective).

## Checkpoints, privacy, and recovery

- **Source and run records** go to your configured private backup repository. GRIP verifies private visibility before pushing and checks the remote commit.
- **Large weights and datasets** stay in your project's verified artifact stores. GitHub keeps source, records, and artifact receipts.
- **Rollback is scoped to the iteration's owned files.** It refuses conflicting user changes and does not run `git reset` or `git restore` on the working project.
- **Completed tasks and evidence survive reactivation.** Repeated activation does not reset the mission or duplicate its watcher.
- **Event observation stores session metadata.** It does not store raw tool inputs/outputs or other sessions' data.

The host must stay powered and connected, and your provider credentials and quota must remain available. GRIP cannot guarantee that an agent will solve a task; it provides the continuation, checkpointing, and review structure around the attempt.

## Verification

From the checkout, use a new output directory for verification evidence:

```bash
python3 tests/verify_activation.py /absolute/path/new-evidence-directory
```

The checks use fake sessions and temporary repositories, without a model or GPU. They cover source-bound Python and JavaScript behavior, portable paths, backup configuration, and refusal to push private mission data to a public remote. The JavaScript checks require Node.js.

Live deployment needs separate verification of the actual session, busy-state suppression, backups, and observed continuation. An API acknowledgement alone does not prove the agent completed useful work.

## Documentation

| Document | Purpose |
| --- | --- |
| [Operations reference](OPERATIONS.md) | Detailed configuration, commands, scheduling, completion rules, and deployment limits |
| [Agent skill](skills/grip/SKILL.md) | Activation, handoff, and recovery instructions for the agent |
| [Mode 1 specification](SPEC_MODE1.md) | Requirements, audits, and challenge reviews |
| [Bridge guide](BRIDGE.md) | Optional bridge documentation |
| [Changelog](CHANGELOG.md) | Recorded changes |

---

**A firm grip on the goal. Progress with proof.**
