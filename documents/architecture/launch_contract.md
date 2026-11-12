# Launch Contract

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Agent preflight and launch](../../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md)

> **Purpose**: Define what `agentctl claude` and `agentctl codex` do, from the session name and the agent argv
> through preflight, failures, create-or-attach and instant exit to the pane trampoline.

## TL;DR

- `agentctl claude [ARGS...]` and `agentctl codex [ARGS...]` run the agent in a tmux (Linux, macOS) or psmux
  (Windows) session named `<base>-<agent>` after the invoking folder, or `<base>-<8 hex>-<agent>` when another
  folder holds that name; re-running in the same folder re-attaches (R7, R8).
- ARGS pass verbatim; user copies of the mandatory flags and codex's `--yolo` are removed, the flags go last or
  just before the first bare `--` (R9, R10, R11), and login-shaped ARGS are refused (R13).
- Haskell checks the requested user-installed agent early, ensures the host backend through its runtime plan,
  and validates authentication before creating a session. Only successful preflight produces `Ready`. A failed
  new launch leaves no new session and reports its reason on the invoking terminal.
- The pane runs `agentctl-core pane-exec <spec>`: the agent's argv, working directory and environment travel in
  a 0600 spec file, never on the multiplexer's command line.

## Session Names

`AgentCtl.Session.Name` derives the name as a pure function whose rows are in `tests/oracles/session_names.toml`.

1. The canonical folder is the realpath of the invoking working directory, symlinks resolved.
2. The base is its last component: each character outside `[A-Za-z0-9_-]` becomes `-`, runs of `-` collapse to
   one `-` and runs of `_` to one `_` (so no name contains `__`, psmux's namespace separator), and a leading
   `-` is removed. A base that sanitises to nothing, such as the filesystem root's, is `folder`.
3. The plain name is `<base>-<agent>`; the hash form is `<base>-<h>-<agent>`, where `<h>` is the first 8
   lowercase hex digits of the SHA-256 of the canonical path's UTF-8 bytes, case-folded first on Windows.

tmux format-expands the `-s` value, uses `:` and `.` as target separators, and has treated them differently
across versions (refused before 3.2, rewritten to `_` from 3.2, kept from 3.7a); a whitelisted name is stored
exactly as computed on every version and can never run a command. A session is this folder's when
`@agentctl_owner` is `agentctl`, `@agentctl_agent` names the agent and `@agentctl_folder` decodes to the
canonical folder, compared case-folded on Windows. The first row that applies decides:

| Situation | Result |
|---|---|
| `=<plain>` exists and is this folder's | re-attach to it |
| `=<hash>` exists and is this folder's | re-attach to it |
| `=<plain>` does not exist | create `<plain>` |
| `=<hash>` does not exist | create `<hash>` |
| both names belong to other sessions | refuse, naming the session that holds the hash form |

A session agentctl does not own, or another folder's, never matches, so launch never attaches to it or ends it.
Windows compares session names case-folded while preserving the selected session's actual spelling for attachment;
missing owner, agent or folder options always make a session foreign. The pure naming module uses the shared
closed identity in `AgentCtl.Agent.Types`, which `AgentCtl.Agent` re-exports, without importing the mux IO adapter.
From `/home/ana/src/api`, `agentctl claude` creates `api-claude`; from `/home/ana/work/api` it then creates
`api-fe49ec32-claude`, and running it there again re-attaches to that session. Names and decisions are compared
with the oracle rows, each hash recomputed by Python's hashlib (`tests/unit/test_session_names.py::test_session_names_match_oracle`,
`tests/unit/test_session_names.py::test_decision_rows_match_oracle`), and every generated name passes the
`SessionName` smart constructor (`haskell:agentctl-core-test/Name/always-valid`).

## Argument Assembly

`AgentCtl.Agent.Argv.launchArgv` builds the argv from the closed agent table in `AgentCtl.Agent` and the raw ARGS.
The table also owns executable names, auth argv, login remedies and variants, OS install hints and literal recovery
text; `tests/unit/test_agent_table.py::test_agent_table_matches_oracle` checks every field on every OS family:

| Agent | Mandatory flags, in order | Removed before the first bare `--` |
|---|---|---|
| claude | `--dangerously-skip-permissions` | `--dangerously-skip-permissions` |
| codex | `--dangerously-bypass-approvals-and-sandbox` `--no-daemon` | those two, and `--yolo` |

1. The argv is the absolute executable path preflight resolved, then ARGS verbatim and in order: empty
   strings, newlines, a trailing `;`, `#{...}` and `$(...)` included. No shell ever reads them.
2. Before the first bare `--`, every element equal to a mandatory flag or its alias is removed, because codex
   exits 2 on a repeated flag and `--yolo` is an alias of its bypass flag. Nothing after the `--` is removed:
   both CLIs read what follows it as positional, so a prompt saying `--yolo` is the user's text.
3. The mandatory flags go immediately before the first bare `--`, or at the end when there is none.
4. Nothing else changes, and no subcommand or flag table exists: an argv the agent rejects is reported by the
   agent itself, through [instant exit](#instant-exit).

| Invocation | Agent argv after the executable |
|---|---|
| `agentctl claude --model opus` | `--model opus --dangerously-skip-permissions` |
| `agentctl claude --model opus -- 'fix --verbose'` | `--model opus --dangerously-skip-permissions -- 'fix --verbose'` |
| `agentctl codex --yolo resume --last` | `resume --last --dangerously-bypass-approvals-and-sandbox --no-daemon` |
| `agentctl codex -- --yolo` | `--dangerously-bypass-approvals-and-sandbox --no-daemon -- --yolo` |

```text
WRONG  claude --model opus -- fix the tests --dangerously-skip-permissions
RIGHT  claude --model opus --dangerously-skip-permissions -- fix the tests
```

After `--` both CLIs read every token as positional, so the WRONG argv hands the flag over as prompt text and
claude starts without bypass mode: R10 fails while the session looks normal. The oracle rows
(`tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`) and the property
`haskell:agentctl-core-test/Argv/user-order-and-single-flags` hold these rules, and
`tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags` checks that the installed CLIs
know each mandatory flag while rejecting a nonce-named one.

## Login Refusals

`AgentCtl.Agent.Argv.checkedArgv` applies the login refusal before calling the pure assembly kernel. Launch uses
this checked operation before preflight. Its error renderer returns exit 2 with the primary login remedy and
does not repeat user arguments: agentctl refuses login-shaped ARGS before anything is spawned (R13):

| Agent | Refused when ARGS contain | The user types instead |
|---|---|---|
| claude | before the first bare `--`: an element `setup-token`, or an element `auth` followed by an element `login` | the same command in their own shell, such as `claude auth login` |
| claude | anywhere: an element that is `/login` or begins with `/login` and whitespace | `claude auth login` |
| codex | before the first bare `--`: an element `login` | `codex login`, or `codex login --device-auth` on a headless or remote machine |

With no flag table agentctl cannot tell which element is the subcommand once options precede it, so it refuses
the shape anywhere before the first bare `--`; a prompt goes after the `--`. `auth status`, `logout` and a
prompt that mentions logging in pass (`tests/unit/test_auth_status.py::test_login_shaped_args_refused`), and no
source constructs a login command or login keystrokes (`src.no-login-construction`).

```text
WRONG  preflight finds claude logged out, and agentctl runs `claude auth login` or sends `/login` to the pane
RIGHT  preflight finds claude logged out, and agentctl prints `claude auth login` as the remedy and exits 7
```

The request makes logging in the user's own discrete command: a spawned login opens a browser flow and stores
credentials on the user's behalf, and keystrokes into the REPL are the path it rules out. With the fake agent as
both agents, a preflight records one auth-status probe and no login
(`tests/integration/test_agent_auth_probe.py::test_preflight_never_runs_login`).

## Preflight

`AgentCtl.Preflight` interprets a pure closed program over native host facts, agent discovery, authentication
and the Haskell runtime dependency plan. The runtime is described by
[the multiplexer adapter](multiplexer_adapter.md#resolution-and-version-floors). Python does not search for,
install or launch the multiplexer or agent.

Before any runtime mutation, Linux must identify itself as Debian with exact `ID=debian`; the Windows path
requires its supported native architecture. Unsupported platform facts produce an immediate named refusal.
A live session eligible for reattachment uses its existing qualified backend and follows
[create or attach](#create-or-attach); it does not reinstall an agent or repeat authentication.

For a genuinely new launch, the selected Claude or Codex executable is checked before expensive backend
preparation. Agentctl never installs either agent, an agent package manager, or an authentication state.
A missing selected CLI produces an actionable user-installation message; the other CLI is irrelevant to that
launch. Session listing, attachment and stopping do not require either CLI merely to inspect existing work.

Agent discovery resolves PATH in order to one absolute executable. On Windows a `.cmd` or `.bat` shim is
refused rather than reparsed by cmd.exe or skipped in favor of a later candidate. Only a native executable
qualifies. Relative search entries are interpreted against the caller's absolute working directory. The
selected path is retained throughout the operation.

The authentication status probe runs by that absolute path in the environment the trampoline gives the
agent. Its actual exit status decides readiness; a nonzero usage error, signal, invalid operation or timeout
is a check failure, not evidence that the user is logged out. The status-only runner drains both streams as
bytes, so diagnostic encoding does not manufacture an authentication failure. Login commands are never run.

The runtime planner reuses a qualified backend or prepares the missing one under explicit consent. Debian
uses APT-managed tmux. Windows Haskell obtains private Rust/Cargo and native build capabilities and builds a
qualified psmux under the private artifact root. The consent envelope comes from the handoff, separately
from ARGS; privilege does not imply consent. A declined plan, unavailable privilege, pending reboot, source
verification failure or build failure returns a named error and creates no agent session.

`Ready` combines the validated agent, authentication result, backend artifact/profile and current namespace.
Its constructor remains private. The creation path accepts only that capability and revalidates the target
namespace before mutation. No spec or session is published while a prerequisite is unready. A failed install
cannot become a fallback to an arbitrary PATH psmux.

## Failure and Warnings

Every runtime failure is a typed Haskell result rendered on the invoking terminal. Messages identify the
failed capability and an actionable remedy without echoing secret environment values or arbitrary user
arguments. Their exit codes and exact expected forms belong to `tests/oracles/preflight.toml` and
[the CLI reference](../reference/cli_reference.md).

| Failure family | Required behavior |
|---|---|
| Unsupported Linux distribution or architecture | Fail before runtime installation or session mutation |
| Selected agent missing | Name that CLI and the user-owned installation remedy; run no agent installer |
| Native Windows executable unavailable | Name the refused shim and required native CLI |
| Logged out | Name the discrete login command for the user; run no login flow |
| Authentication probe unavailable or indeterminate | Report the probe failure without asserting logout |
| Runtime dependency unready | Identify denied consent, privilege, reboot, verification, build or qualification reason |
| Backend or server incompatible | Identify actual artifact/server and unavailable operation; do not silently substitute |
| Agent instant exit | Relay captured startup output and the actual agent exit status |
| Other launch failure | Report the cause and clean up only resources this launch created |

A missing tmux can be remedied by Haskell's authorized Debian provisioning plan. A missing Windows backend
can be remedied by Haskell's authorized private source-build plan. A generic system psmux installation
instruction is not a substitute for that qualification workflow.

Failure controls pair refusal with a successful native twin and independently observed resource state.
The missing-agent path establishes that no package-manager, Rust, psmux-build or agent-install operation
occurred; the declined provisioning path establishes that no session exists. Refusal tests inspect the
reason, not merely a nonzero exit that could conceal an unexpected traceback.

## Create or Attach

`AgentCtl.Launch` first checks the raw login shape and calculates the canonical folder and candidate names.
Haskell validates the runtime platform. Read-only discovery of an accepted existing backend then looks for
this folder's live owned session. A valid match reattaches without agent installation or authentication;
ARGS are not reapplied, and the command explains that they were not applied.

If a new launch is needed, early agent/authentication checks and the runtime ensure described by
[preflight](#preflight) produce `Ready`. A dead owned leftover can be replaced only after its complete identity
is checked. A foreign session, a stale name now held by another instance, or an external adoption is never
cleanup for a new launch.

Creation uses the checked session name, the absolute pane trampoline and an unpredictable private spec
path. The creating client runs in the canonical folder. Launch sets the agent pane's temporary remain-on-exit
and owned metadata before releasing the spec, so startup failure remains observable. It then observes the
startup window and hands control to the correct backend:

- Without terminal input/output, print `agentctl attach NAME` and leave the live session running. This command
  preserves private Windows routing and backend identity instead of asking the user to find a psmux binary.
- From a compatible attached client in the same backend namespace, use the backend's checked switch operation.
- Otherwise open a foreground client by the qualified absolute executable against the exact namespace.

A system psmux pane does not count as being inside agentctl's private Windows registry merely because `TMUX`
is set. Namespace identity decides whether switching is possible. A cross-namespace attach does not end the
user's current client, rewrite global aliases, or migrate any running server.

The private Windows registry and qualified client/server compatibility table are described by
[sessions and ownership](sessions_and_ownership.md). Replacing the artifact used for new sessions never
restarts an existing one. Legacy sessions retain visible compatibility diagnostics and do not authorize
unsupported automated recovery.

A new agent may wait at a workspace-trust, permissions or login-related dialog. Agentctl neither answers it
nor sends a prompt to clear it. Native live validation observes the fixed live-acceptance folder with
updating disabled and no input; it cannot infer every classifier's correctness from an idle startup screen.

## Instant Exit

remain-on-exit turns an agent that ends at once into a dead pane instead of a vanished session. The startup
window is a fixed 2 s, a constant of `AgentCtl.Launch` counted from the moment the spec is written. When
`#{pane_dead}` turns 1 inside it, launch captures the pane (`capture-pane -p -J -t %<id> -S -100`) and prints
the output on stderr, reads the status (`#{pane_dead_status}`, or 128 plus `#{pane_dead_signal}`, on tmux; the
trampoline's status file on psmux), ends the session with `kill-session -t =NAME`, prints
`agentctl: codex exited with status 2 during startup; its session was closed.` and exits with that status, 0
included. So an agent's own rejection reaches the user in the installed version's words: `agentctl codex exec
'x'` relays "unexpected argument '--no-daemon' found" and exits 2, `agentctl claude auth status` relays "unknown
option '--dangerously-skip-permissions'" and exits 1, and claude started as root relays its refusal of bypass
mode. The trampoline's own failures arrive the same way; an agent that exits after the window ends its session
as tmux ends any pane, under the user's own remain-on-exit setting. The relay is shown with a fake agent that
prints a nonce line and exits 3 (`tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`),
and the real agents' rejections inside the window by running the trampoline directly with logged-out claude and
codex (`tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`); a real rejection
relayed through `agentctl` itself needs a logged-in agent and is proven by no phase.

A closed terminal can precede child accounting. When tmux has no published status, the process runner reads that
backend's server pid and sends SIGCHLD to request normal child reaping, then the observer continues waiting for the
actual status. This handles libutempter's temporary signal-handler replacement without sending pane input or
changing the required exit status. psmux continues reading the trampoline's private status file.

## The Pane Trampoline

The pane command is `agentctl-core pane-exec <spec>`, both paths absolute, run by `AgentCtl.PaneExec`;
[files and state](../reference/files_and_state.md) owns the spec's format.

- **Location and contents.** Launch writes the spec into `<state>/launch/`, mode 0700, as a mode 0600 file with
  a fresh, unpredictable name, through a temporary file renamed into place. It holds the agent argv, absolute
  executable first, the canonical folder and the caller's complete environment.
- **Order.** The trampoline waits for its spec, which launch writes only after remain-on-exit and the identity
  options are set. A spec missing after 30 s makes the trampoline say why and exit non-zero, leaving a dead pane
  that the next launch replaces.
- **Refusal.** A spec that is not a regular file, is not owned by the invoking user, or is more permissive than
  0600 in a directory more permissive than 0700 is refused; on Windows it takes the access rules of the per-user
  directory it sits in. Native owner-SID and DACL observations establish Windows privacy; reparse points, null
  DACLs and unsupported ACE forms are refused. The bounded snapshot and the common access model are defined in
  [files and state](../reference/files_and_state.md#launch-specs).
- **Lifetime.** The trampoline deletes the spec right after reading it; a launch whose pane never started
  deletes its own, and nothing else reads one.
- **Environment.** The agent gets the caller's environment from the spec, except `TERM`, `TMUX` and
  `TMUX_PANE`, which the trampoline keeps from the pane because they describe the pane, not the caller.
- **POSIX.** The trampoline changes to the folder and calls `execve`, so `#{pane_pid}` is the agent and
  `/proc/<pane_pid>/cmdline` on Linux holds its argv; an npm-installed codex shows as `node` running `codex.js`.
- **Windows.** The trampoline runs the agent as a child in the folder, writes its exit status atomically to a
  status file beside the spec, and exits with it, because psmux reports `#{pane_dead_status}` as 0 always. A
  status file written after the startup window has no reader, and the next launch removes it.

No user text therefore reaches tmux or psmux parsing, environment values stay off its command line, and preflight and the agent see the
same environment rather than the one the server started with, and the exit status is reliable on both
multiplexers. `pane-exec` is the one command run without Python's handoff, and these rules are its authority.
The fake agent records the oracle argv, the canonical folder as its working directory and the caller's
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` (`tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`), and a
folder named `#(touch <sentinel>)` runs nothing (`tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`).

## Related

- [multiplexer adapter](multiplexer_adapter.md) — runtime qualification, provisioning and session options used here.
- [sessions and ownership](sessions_and_ownership.md) — `list`, `attach` and `stop` for launched sessions.
- [python and haskell boundary](python_haskell_boundary.md) — the raw passthrough that delivers ARGS unchanged.
- [troubleshooting](../operations/troubleshooting.md) — each warning, the other install routes, what to type.
- [cli reference](../reference/cli_reference.md) — every command and its exit status.
- [files and state](../reference/files_and_state.md) — the spec and status file formats.
- [external tool facts](../reference/external_tool_facts.md) — the claude, codex, tmux and psmux facts cited.
- [Agent preflight and launch](../../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md) — builds argv, refusals, preflight and launch.
