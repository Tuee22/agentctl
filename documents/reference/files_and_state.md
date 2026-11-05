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
  toolchain-paths.toml     the absolute GHC and cabal paths from resolution, preserved as returned
  build/<digest>/          the build tree for one digest of the bundled Haskell sources and pins
    build.lock             native advisory lock shared by build and binary identity
  cabal/                   the private CABAL_DIR: configuration, package index and store
  tools/<pin-digest>/      the pinned fourmolu and hlint, used only by agentctl check
<data>/
  bin/<digest>/            the core binary built for that digest; never overwritten
  locks/<digest>.publish.lock  native advisory lock serialising publication
<state>/
  launch/                  mode 0700: launch specs, each mode 0600 and gone once its pane starts
  adopted.json             the adopted-pane registry
  watch.json               the watch set
  supervisor.jsonl         the decision log, notify records included
  locks/
    check.lock             held by agentctl check
    supervisor.lock        held by agentctl supervisor run
    watch.lock             serialises watch intent updates and pre-send checks
  live-acceptance/         the fixed folder live tests start the real agents in
```

The style pin digest length-prefixes each name and version, in the order `ghc`, `fourmolu`, `hlint` and
`ghc_lib_parser`, then hashes those fields with SHA-256. A compiler, tool or parser constraint change selects a new
directory. Builds use the private Cabal store and `cache/build/style-<pin-digest>`; both executable files are
verified in a private staging directory before the directory is published. An existing directory is verified and
reused, and a damaged one fails without being overwritten
(`tests/unit/test_style_tools.py::test_style_identity_and_install_arguments`,
`tests/integration/test_style_cache.py::test_tools_publish_together_and_keep_existing`,
`tests/integration/test_style_cache.py::test_incomplete_or_wrong_version_tools_refused`).

A change to the bundled sources or the pins gives a new digest and so a new path, which is why an old binary never runs
for new sources and nothing is replaced in place. [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)
builds `cache` and `data`, as [the binary build](../engineering/binary_build.md) describes; the build of one digest runs
under a lock inside its own build tree. Publication has a separate lock under `data/locks/`; temporary staging
directories under `data/bin/` are removed, while published digest directories remain immutable
(`tests/integration/test_build_cache.py::test_waiter_uses_published_winner`,
`tests/integration/test_binary_boundaries.py::test_publication_failures_never_replace_existing`).

The toolchain path record has exactly the string fields `ghc` and `cabal`. Each path is absolute and its spelling
is preserved. Warm runs check both executables with `--numeric-version`; a malformed record reports its cache
remedy, and a path that no longer answers at its pin requires resolution again
([toolchain bootstrap](../engineering/toolchain_bootstrap.md)).
Both paths are verified before a mode-0600 temporary record is atomically published. A failed install or resolution
keeps the prior file intact (`tests/unit/test_toolchain.py::test_record_atomicity_and_storage_failure`).
Compiler probes use a private temporary directory and remove their C source and link output afterward. Ordinary
commands use the cache; check gives P9 a workspace inside its own run directory.

The independent host harness owns `state/pre-bootstrap.json`, an initial absence witness containing the host,
configured ghcup path and nonce. The provisioning code never writes it. It is created automatically only when the
observed tools are absent and is never rewritten. A different host or prefix fails its validation; it cannot certify
a pristine host by itself (`tests/integration/test_bootstrap_origin.py::test_existing_tool_and_mismatched_witness`).

## Launch Specs

[Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) reserves one spec path in
`<state>/launch/` before creating a session, then publishes the spec atomically after remain-on-exit and identity
options are set. The session's pane runs the core binary's
`pane-exec` command, the pane trampoline, with the spec's path as its only argument. The trampoline waits for the spec to appear, reads it,
deletes it, and then becomes the agent through `execve` (Linux, macOS) or starts the agent as a child process (Windows).

Each reservation is an unpredictable private directory named `<session>.launch-<random>` under `launch/`, holding
`spec.json` and its matching `status.json`. A successful launch leaves spec deletion to the trampoline. Later
launches remove completed status directories for that session; POSIX also removes its empty reservation directories.
Only those exact owned artifacts are removed, and a directory with other files is left alone.

The spec is the one place the launching shell's environment is written, and it is on no command line: the pane's command
line carries only the spec's path. The directory is mode 0700 and each spec mode 0600 on Linux and macOS; on Windows they
take the access rules of the per-user directory they sit in. A launch that fails before its pane starts deletes its spec.

```json
{
  "argv": ["/home/me/.local/bin/claude", "--add-dir", "../lib", "--dangerously-skip-permissions"],
  "cwd": "/home/me/src/api",
  "env": {"HOME": "/home/me", "PATH": "/home/me/.local/bin:/usr/bin:/bin"},
  "status": "/home/me/.local/state/agentctl/launch/unique.status.json"
}
```

| Field | Holds |
|---|---|
| `argv` | The agent's absolute path, then its arguments: your ARGS with the mandatory flags in place |
| `cwd` | The canonical folder the session was launched from |
| `env` | The complete environment of the `agentctl` command that launched it |
| `status` | The absolute status-file path reserved beside this spec; Windows publishes the agent's exit status here |

On Windows the trampoline also writes the agent's exit status to a status file beside the spec, which instant-exit
capture reads, because psmux reports the status of every dead pane as 0.
The status file is a JSON integer published by renaming a private temporary file. Its path must share the spec's
canonical parent and must not alias the spec. Malformed specs and invalid program values are refused before the
source is removed.

The native snapshot reads at most 32 MiB from the opened spec and refuses a larger file. Linux and macOS inspect
the opened parent directory and file, reject final symbolic links and retain owner and mode facts from those
descriptors. Windows inspects real owner SIDs and DACLs, rejects reparse points, and treats access limited to the
current user, LocalSystem and builtin Administrators as private. A null DACL, other effective allow entries or an
unsupported ACE form is refused. The common policy applies the equivalent private-file and directory permissions;
Windows ownership is never inferred from emulated POSIX ids.

## Adopted-Pane Registry

[Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) keeps
`<state>/adopted.json`, the panes `agentctl adopt` registered. Managed sessions are not in it: each one's identity lives
in its own session options, `@agentctl_agent`, `@agentctl_folder` and `@agentctl_owner`, so the multiplexer server is
the only record of them and none outlives its session.
The `@agentctl_status` option carries the private trampoline status-file path for reporting a retained dead psmux
pane's exit status; it does not add a managed-session registry.

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
For psmux it is a JSON-array string containing `psmux`, its reported namespace and its stable session id. The registry
has exactly one `panes` array; entries have exactly the fields above, positive pids, valid pane ids and known agents.
Duplicate pane ids and malformed or unsafe files are refused without rewriting their bytes. Publication writes a
0600 temporary file beside the target and renames it into place. Native preparation verifies the application state
root's ownership and ordinary directory kind, refuses a final link and makes that root private before publication.
It preserves existing child files and their permissions; the [native state controls](../engineering/code_standards.md#haskell)
describe that boundary. Registry refusal and publication are exercised by
`tests/e2e/test_adopt.py::test_registry_rejects_invalid_state` and
`tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`.
Every use compares the recorded endpoint with the addressed server and requires the pane id to exist there with its
recorded pid. An absent server, socket mismatch, missing pane or different pid makes the entry stale: agentctl reports
it as stale and never captures from or sends to it. A server restart that reuses the socket, pane id and pid is not
detected. `agentctl stop` on an adopted pane removes its entry and leaves the pane running.

## Watch Set

[Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) keeps `<state>/watch.json`, what `supervisor run`
observes, keyed by name:

```json
{"revision": 2, "watched": {"api-claude": {"paused": false, "revision": 1}, "%3": {"paused": true, "revision": 2}}}
```

`agentctl watch` adds an entry, `pause` and `resume-watch` set and clear `paused`, and `unwatch` removes the entry; none
of them touches the session. The supervisor reads the file on every poll, so a change takes effect while it runs. Effective changes advance the registry revision and the affected entry's revision; repeats preserve both. A pause and resume between polls therefore still establish a new baseline, while another target's change does not reset this one.
A paused entry produces no pane capture or machine step and drops its open incident. The first capture after watch,
resume or supervisor start establishes a baseline whose existing errors count as handled.

Watch and resume require a current managed session or validated adopted pane. Pause and unwatch can disable an
existing stale entry. An absent unwatch is a repeat notice, and repeated commands leave the file byte-identical.
The registry uses the same owned private snapshot and atomic replacement boundary as the adopted-pane registry
(`tests/e2e/test_watch_commands.py::test_watch_refuses_foreign_target`).

## Decision Log

[Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) appends to `<state>/supervisor.jsonl`, one JSON
object per line, from the one supervisor that holds the supervisor lock. Every record has these fields:

| Field | Holds |
|---|---|
| `time` | When it happened, in UTC, as ISO 8601 |
| `run` | The supervisor run's fresh identifier, shared by that run's records |
| `target` | The session or pane name, as `agentctl list` prints it |
| `agent` | `claude` or `codex`; `unknown` only for a disappearance notification when startup cannot resolve an old watch entry |
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
Decision states describe the proposed pure step; an aborted or failed attempt does not commit a recovery-sent
state. Observations contain the class, fingerprint and state, never captured text. The reader tolerates only an
unterminated in-flight suffix while the supervisor holds its lock; after release that suffix is corruption.
The writer validates existing history before it can append. Native appends check the opened file's ownership,
private permissions, regular-file kind and single link, without following a final link. They preserve existing
bytes and flush before returning. Log snapshots allow the writer's append handle and read the initial-length
prefix; they do not inherit the launch-spec reader's 32 MiB limit. The launch-spec reader retains that bound and
its stronger exclusion and growth checks.
`agentctl logs NAME` prints NAME's records. Deleting the file while no supervisor runs loses the history and nothing else.

## Locks

Each holder keeps an operating-system advisory file lock until scope exit or process exit. The check and supervisor
locks live under `<state>/locks/` and hold the holder's process id as text for refusal diagnostics. Build and publication
locks live beside their owned caches, contain no pid, and wait for at most 30 minutes on contention. Other kernel errors
fail immediately (`tests/integration/test_binary_boundaries.py::test_native_lock_contention_timeout_and_exception_release`,
`tests/integration/test_binary_boundaries.py::test_native_lock_spawn_hash_and_publication_race_controls`).

| Lock | Held by | Effect | Owning phase |
|---|---|---|---|
| `check.lock` | `agentctl check` | One check runs at a time per user; a second exits non-zero (precondition P5) | [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |
| `supervisor.lock` | `agentctl supervisor run` | One supervisor runs at a time per user; a second exits non-zero | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `watch.lock` | watch commands and supervisor pre-send checks | Reloads and updates watch intent in one critical section, waiting at most five seconds | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `<cache>/build/<digest>/build.lock` | native build and binary identity | Serialises work on one digest and rechecks the publish after waiting | [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) |
| `<data>/locks/<digest>.publish.lock` | binary publication | Serialises publication without changing existing digest directories | [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) |

Supervisor and watch locks use POSIX `flock` or Windows `LockFileEx`, not the presence of a PID file. They refuse
linked, foreign, non-regular or non-private entries. These lock files are retained after release and updated in
place while the handle owns the lock; replacing or unlinking their inode would break exclusion. A leading newline
reserves byte zero for the Windows byte-range lock, followed by the decimal PID and a newline, so another handle
can read the PID without reading the locked byte. A contender racing initial PID publication may report an unknown
holder, but cannot acquire the held lock. Watch updates hold `watch.lock` across reload, transition and atomic
publication of `watch.json`; concurrent commands preserve every change.

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
- the run's nonce, the node ids the test session collected and executed, and nonce-bound observer records under `observers/`;
- `bootstrap-host.json`, the independent binary digest and default-selection entries observed before provisioning;
- `mux-host/mux-host.json`, the independent multiplexer path, version, qualification and current nonce; its probe
  uses an owned home and, on Windows, an owned psmux registry with warm servers disabled;
- the source, ref and installed-distribution snapshots that the integrity finalizers compare.

The directory stays short enough that a private tmux socket path inside it is at most 100 bytes (precondition P6); when
the system temporary directory is too deep, set `TMPDIR` to a shorter one. Nothing in it is read by a later run, so no
test outcome or mutant kill outlives the run that produced it. A run that is killed leaves its directory behind, and
deleting it is safe once no check is running. [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md)
creates it and redirects child bytecode into it; [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) compares the guarded tree and interpreter around the run.

## Related

- [installation.md](../operations/installation.md) — removing these directories when you remove agentctl.
- [cli_reference.md](cli_reference.md) — the commands that read and write these files.
- [launch_contract.md](../architecture/launch_contract.md#the-pane-trampoline) — the trampoline that consumes each launch spec.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed identity in session options, and adoption.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — what the supervisor observes, decides and logs.
- [binary_build.md](../engineering/binary_build.md) — the digest, the build cache and atomic publish.
- [quality_gate.md](../engineering/quality_gate.md#preconditions) — preconditions P5 and P6 that rest on the lock and the run directory.
