# Files and State

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md)

> **Purpose**: Say where agentctl keeps its per-user files on each operating system and the format of every file it writes there.

## Directories

agentctl keeps what it writes for you in three per-user directories. Its Python layer decides all three and passes them
to the core binary, which computes none ([the Python/Haskell boundary](../architecture/python_haskell_boundary.md)).

| Directory | Holds | Override, on every OS | Linux and macOS default | Windows default |
|---|---|---|---|---|
| `cache` | Build trees and the pinned Haskell style tools | `XDG_CACHE_HOME` | `~/.cache/agentctl` | `%LOCALAPPDATA%\agentctl\cache` |
| `data` | Published core binaries | `XDG_DATA_HOME` | `~/.local/share/agentctl` | `%LOCALAPPDATA%\agentctl\data` |
| `state` | Launch specs, the adopted-pane registry, the watch set, the decision log, locks and the live-test folder | `XDG_STATE_HOME` | `~/.local/state/agentctl` | `%LOCALAPPDATA%\agentctl\state` |

- An override applies on every OS, macOS and Windows included, whenever it is an absolute path, and the directory is
  then `agentctl` under it; a relative value is ignored. No other variable moves these directories, which is also how
  tests give agentctl private ones.
- macOS uses the same layout as Linux rather than `~/Library`, as cabal does, so one rule covers both and no path
  carries a space.
- Deleting `cache` while no agentctl command runs costs a rebuild; deleting `data` removes every published binary, and
  the next command builds the current one; deleting `state` forgets adopted panes, the watch set and the decision log.

Some things agentctl sets up live elsewhere: ghcup, GHC and cabal stay where ghcup keeps them
([the toolchain bootstrap](../engineering/toolchain_bootstrap.md)); sessions live on your tmux or psmux server; and the
agents keep their own configuration and credentials, such as `~/.claude`, `~/.claude.json` and `~/.codex`. Each run
of `agentctl check` adds a run directory under the system temporary directory, described at the end of this page.

## Layout

```text
<cache>/
  build/<digest>/          the build tree for one digest of the bundled Haskell sources and pins
  cabal/                   the private CABAL_DIR: configuration, package index and store
  tools/<pin-digest>/      the pinned fourmolu and hlint, used only by agentctl check
<data>/
  bin/<digest>/            the core binary built for that digest; never overwritten
<state>/
  launch/                  mode 0700: launch specs, each mode 0600 and gone once its pane starts
  adopted.json             the adopted-pane registry
  watch.json               the watch set
  supervisor.jsonl         the decision log, notify records included
  locks/
    check.lock             held by agentctl check
    supervisor.lock        held by agentctl supervisor run
  live-acceptance/         the fixed folder live tests start the real agents in
```

A change to the bundled sources or the pins gives a new digest and so a new path, which is why an old binary never runs
for new sources and nothing is replaced in place. [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)
builds `cache` and `data`, as [the binary build](../engineering/binary_build.md) describes; the build of one digest runs
under a lock inside its own build tree.

## Launch Specs

[Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) reserves one spec path in
`<state>/launch/` before creating a session, then publishes the spec atomically after remain-on-exit and identity
options are set. The session's pane runs the core binary's
`pane-exec` command, the pane trampoline, with the spec's path as its only argument. The trampoline waits for the spec to appear, reads it,
deletes it, and then becomes the agent through `execve` (Linux, macOS) or starts the agent as a child process (Windows).

The spec is the one place the launching shell's environment is written, and it is on no command line: the pane's command
line carries only the spec's path. The directory is mode 0700 and each spec mode 0600 on Linux and macOS; on Windows they
take the access rules of the per-user directory they sit in. A launch that fails before its pane starts deletes its spec.

```json
{
  "argv": ["/home/me/.local/bin/claude", "--add-dir", "../lib", "--dangerously-skip-permissions"],
  "cwd": "/home/me/src/api",
  "env": {"HOME": "/home/me", "PATH": "/home/me/.local/bin:/usr/bin:/bin"}
}
```

| Field | Holds |
|---|---|
| `argv` | The agent's absolute path, then its arguments: your ARGS with the mandatory flags in place |
| `cwd` | The canonical folder the session was launched from |
| `env` | The complete environment of the `agentctl` command that launched it |

On Windows the trampoline also writes the agent's exit status to a status file beside the spec, which instant-exit
capture reads, because psmux reports the status of every dead pane as 0.

## Adopted-Pane Registry

[Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) keeps
`<state>/adopted.json`, the panes `agentctl adopt` registered. Managed sessions are not in it: each one's identity lives
in its own session options, `@agentctl_agent`, `@agentctl_folder` and `@agentctl_owner`, so the multiplexer server is
the only record of them and none outlives its session.

```json
{"panes": [{"socket": "/tmp/tmux-1000/default", "pane": "%3", "pid": 48213, "agent": "codex"}]}
```

| Field | Holds |
|---|---|
| `socket` | The adapter's opaque, stable server endpoint identity: a tmux socket path, or the psmux namespace and addressed server identity; compared at every use |
| `pane` | The multiplexer's pane id, which is also the pane's name in `agentctl list` |
| `pid` | The process id of the pane's first process when it was adopted |
| `agent` | `claude` or `codex`, as `--agent` gave it |

The field name does not require a filesystem socket on Windows; the adapter owns the endpoint's representation.
Every use compares the recorded endpoint with the addressed server and requires the pane id to exist there with its
recorded pid. An absent server, socket mismatch, missing pane or different pid makes the entry stale: agentctl reports
it as stale and never captures from or sends to it. A server restart that reuses the socket, pane id and pid is not
detected. `agentctl stop` on an adopted pane removes its entry and leaves the pane running.

## Watch Set

[Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) keeps `<state>/watch.json`, what `supervisor run`
observes, keyed by name:

```json
{"watched": {"api-claude": {"paused": false}, "%3": {"paused": true}}}
```

`agentctl watch` adds an entry, `pause` and `resume-watch` set and clear `paused`, and `unwatch` removes the entry; none
of them touches the session. The supervisor reads the file on every poll, so a change takes effect while it runs.
A paused entry produces no pane capture or machine step and drops its open incident. The first capture after watch,
resume or supervisor start establishes a baseline whose existing errors count as handled.

## Decision Log

[Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) appends to `<state>/supervisor.jsonl`, one JSON
object per line, from the one supervisor that holds the supervisor lock. Every record has these fields:

| Field | Holds |
|---|---|
| `time` | When it happened, in UTC, as ISO 8601 |
| `run` | The supervisor run's fresh identifier, shared by that run's records |
| `target` | The session or pane name, as `agentctl list` prints it |
| `agent` | `claude` or `codex` |
| `kind` | `observation`, `decision`, `attempt`, `result` or `notify` |

| Kind | Records |
|---|---|
| `observation` | Every capture of an unpaused watched pane, unchanged screens included: class, fingerprint and machine state |
| `decision` | One step of the recovery state machine: states before and after, and the rule and action chosen |
| `attempt` | A send offered to the guard: recovery text, pre-send class and fingerprint, and outcome `sent`, `aborted` or `failed` |
| `result` | One incident's closure: `recovered`, `ended`, `not-acknowledged`, `unresolved` or `escalated`; an unchanged screen never counts as recovery |
| `notify` | A notification, also printed on the supervisor's stderr, whose level rises as failures repeat |

The rows of `tests/oracles/log_records.toml` fix each kind's required fields. Decisions are flushed before their effects;
attempts record the guard or send outcome as soon as it is known, and results are flushed at incident closure.
`agentctl logs NAME` prints NAME's records. Deleting the file while no supervisor runs loses the history and nothing else.

## Locks

Each lock is a file under `<state>/locks/` on which its holder keeps an operating-system file lock for as long as it
runs, so the lock is released when the holder exits, even after a crash. The file holds the holder's process id as text,
which a command that finds the lock taken prints in its warning.

| Lock | Held by | Effect | Owning phase |
|---|---|---|---|
| `check.lock` | `agentctl check` | One check runs at a time per user; a second exits non-zero (precondition P5) | [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |
| `supervisor.lock` | `agentctl supervisor run` | One supervisor runs at a time per user; a second exits non-zero | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |

## Live-Test Folder

`<state>/live-acceptance/` is the fixed folder in which the live tests of `agentctl check` start the real agents when
they are logged in, so any record an agent keeps per folder, such as claude's workspace trust, concerns that folder
alone. Live tests
send no input there and answer no dialog. [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md)
introduces it.

## Check Run Directory

`agentctl check` creates a fresh directory for each run, named `agentctl-check-` with a random suffix, under the system
temporary directory (`TMPDIR` on Linux and macOS), and removes it when the run ends. It holds what the run writes outside
the checkout:

- the bytecode of check and every child it starts, through `PYTHONPYCACHEPREFIX`, so nothing is compiled into the tree;
- the sockets of private tmux servers, through `TMUX_TMPDIR`, or psmux's registry, through `PSMUX_DATA_DIR`, on Windows;
- the empty configuration home the Python tools run with, so no user-level configuration reaches them;
- the run's nonce, and the node ids the test session collected and executed.

The directory stays short enough that a private tmux socket path inside it is at most 100 bytes (precondition P6); when
the system temporary directory is too deep, set `TMPDIR` to a shorter one. Nothing in it is read by a later run, so no
test outcome or mutant kill outlives the run that produced it. A run that is killed leaves its directory behind, and
deleting it is safe once no check is running. [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md)
creates it, and [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) adds the bytecode
prefix.

## Related

- [installation.md](../operations/installation.md) — removing these directories when you remove agentctl.
- [cli_reference.md](cli_reference.md) — the commands that read and write these files.
- [launch_contract.md](../architecture/launch_contract.md#the-pane-trampoline) — the trampoline that consumes each launch spec.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed identity in session options, and adoption.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — what the supervisor observes, decides and logs.
- [binary_build.md](../engineering/binary_build.md) — the digest, the build cache and atomic publish.
- [quality_gate.md](../engineering/quality_gate.md#preconditions) — preconditions P5 and P6 that rest on the lock and the run directory.
