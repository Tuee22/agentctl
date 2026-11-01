# Launch Contract

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md)

> **Purpose**: Define what `agentctl claude` and `agentctl codex` do, from the session name and the agent argv
> through preflight, failures, create-or-attach and instant exit to the pane trampoline.

## TL;DR

- `agentctl claude [ARGS...]` and `agentctl codex [ARGS...]` run the agent in a tmux (Linux, macOS) or psmux
  (Windows) session named `<base>-<agent>` after the invoking folder, or `<base>-<8 hex>-<agent>` when another
  folder holds that name; re-running in the same folder re-attaches (R7, R8).
- ARGS pass verbatim; user copies of the mandatory flags and codex's `--yolo` are removed, the flags go last or
  just before the first bare `--` (R9, R10, R11), and login-shaped ARGS are refused (R13).
- Preflight checks the multiplexer, the agent and its login before any session exists, and only it produces
  `Ready` (R12.1, R12.2). A failure leaves no session, warns on the user's own terminal and exits non-zero (R12).
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
From `/home/ana/src/api`, `agentctl claude` creates `api-claude`; from `/home/ana/work/api` it then creates
`api-fe49ec32-claude`, and running it there again re-attaches to that session. Names and decisions are compared
with the oracle rows, each hash recomputed by Python's hashlib (`tests/unit/test_session_names.py::test_session_names_match_oracle`,
`tests/unit/test_session_names.py::test_decision_rows_match_oracle`), and every generated name passes the
`SessionName` smart constructor (`haskell:agentctl-core-test/Name/always-valid`).

## Argument Assembly

`AgentCtl.Agent.Argv` builds the argv from the agent table in `AgentCtl.Agent` and the raw ARGS:

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

agentctl never runs a login command, never types a login into a REPL, and refuses login-shaped ARGS before
anything is spawned (R13):

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

`AgentCtl.Preflight` runs three checks in order, stops at the first failure, and creates nothing: no session,
no spec and no state.

1. **Multiplexer.** tmux or psmux resolves and meets its floor ([multiplexer adapter](multiplexer_adapter.md)).
2. **Agent.** `claude` or `codex` resolves on PATH to an absolute path. On Windows only a native `.exe`, found
   through PATHEXT, qualifies: a `.cmd` or `.bat` shim started through CreateProcessW has its arguments
   re-parsed by cmd.exe, which would expose verbatim ARGS to injection.
3. **Login.** `claude auth status` or `codex login status` runs by absolute path in the caller's environment,
   the one the trampoline later gives the pane, and only its exit code counts: 0 is logged in, 1 is logged out,
   and any other exit, a signal, a failure to start or no exit within 10 s is `check failed`.

Exit codes alone decide, because claude prints JSON on stdout and codex writes only to stderr in wording that
changes between versions; a usage error or a hung probe never tells a logged-in user to log in again. Success is
`Ready`, whose constructor `AgentCtl.Preflight` does not export, and `AgentCtl.Launch` creates a session only
from a `Ready`, so a launch that skips preflight does not compile.

The rows in `tests/oracles/auth_status.toml` cover exits 0, 1, 2 and 127, a signal and a timeout
(`tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`). The real CLIs, logged out by construction
(empty `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, the latter setting `cli_auth_credentials_store = "file"`, no auth
variables, `DISABLE_AUTOUPDATER=1`), exit 1 (`tests/integration/test_agent_real.py::test_logged_out_by_construction`).
With no tmux on a constructed PATH the fake agent records nothing, against the same PATH with tmux
(`tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`), and `ready_constructed.hs.txt`
constructs the private constructor as an expression and fails with `GHC-88464`, while its twin
`ready_from_preflight.hs.txt` compiles
(`tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`).

## Failure and Warnings

Warnings go to the binary's stderr, which is the user's own terminal, never into the pane, where they would
vanish with the session. Every line starts `agentctl: `, and `tests/oracles/preflight.toml` holds each line per
class and OS (`tests/unit/test_preflight.py::test_failure_warnings_match_oracle`):

| Class | Exit | Warning |
|---|---|---|
| Login-shaped ARGS | 2 | `` `auth login` is a login command, and agentctl never runs one. Type it yourself: claude auth login `` |
| Multiplexer missing | 3 | `tmux 3.2 or later is required, and none was found on PATH.`, then the install hint |
| Multiplexer below its floor | 4 | `tmux 3.1c at /usr/bin/tmux is older than 3.2, the oldest version agentctl supports.`, then the hint |
| Agent missing | 5 | `claude was not found on PATH.`, then the install hint |
| Windows shim refused | 6 | `codex resolves only to <path>\codex.cmd; agentctl starts only a native codex.exe.`, then the hint |
| Logged out | 7 | `claude is not logged in, so no session was started.`, then `log in yourself by typing: claude auth login` |
| Auth check failed | 8 | ``could not tell whether codex is logged in: `codex login status` exited 2.``, then `run it yourself to see why; no session was started.` |
| Instant exit | the agent's own | the relayed pane output, then `codex exited with status 2 during startup; its session was closed.` |
| Any other launch failure | 1 | what failed, such as both session names being held by other sessions |

| Install hint | Linux and macOS | Windows |
|---|---|---|
| multiplexer | the distribution's tmux package, for example `sudo apt install tmux`; `brew install tmux` on macOS | `winget install psmux` |
| claude | `curl -fsSL https://claude.ai/install.sh \| bash` | `winget install Anthropic.ClaudeCode` |
| codex | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` | `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 \| iex"` |

The login remedy is `claude auth login` (`--console` for Anthropic Console billing, `--sso` for single sign-on)
or `codex login` (`codex login --device-auth` on a headless or remote machine)
(`tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`); the agent-missing warning names the
hint for the host's OS (`tests/integration/test_preflight.py::test_missing_agent_names_install_hint`). Each "no
session is left behind" test pairs the absence with a positive control, the fake agent's record that the
session existed or the same run with the check passing
(`tests/e2e/test_launch.py::test_preflight_failure_leaves_nothing`).

## Create or Attach

`AgentCtl.Launch` runs these steps:

1. Refuse login-shaped ARGS and assemble the argv, both pure, before anything is spawned.
2. Resolve the multiplexer (preflight check 1), which finding a session needs.
3. Look for this folder's session ([session names](#session-names)). A **live** one is re-attached: re-attach
   skips the rest of preflight, so neither the agent nor its login is checked, and ARGS given with it are not
   applied, which agentctl says: `agentctl: api-claude is already running; the arguments given were not applied.`
   A **dead leftover**, every pane dead as remain-on-exit leaves it, is ended with `kill-session -t =NAME`, and
   the launch continues afresh.
4. Run preflight checks 2 and 3 to obtain `Ready`.
5. Run `new-session -d -s <name> -P -F '#{pane_id}' -- <binary> pane-exec <spec>` from a client whose working
   directory is the canonical folder, set the agent pane's remain-on-exit and the identity options, and only
   then write the spec, so remain-on-exit is on before the agent can start.
6. Watch the startup window ([instant exit](#instant-exit)); when the agent is alive at its end, unset
   remain-on-exit and hand over, as re-attach also does:
   - **No TTY** (standard input or output is not a terminal): print the attach command, such as
     `tmux attach-session -t =api-claude`, and exit 0, leaving the session running.
   - **`$TMUX` set:** `switch-client -t =NAME` on the server `$TMUX` names, where the session was created, since
     tmux reads `$TMUX` when given no socket; tmux refuses to attach inside its own server, and psmux blocks nesting.
   - **Otherwise:** `attach-session -t =NAME`; agentctl exits 0 when the client detaches or the session ends.

The plan is pure (`tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`), and on a private server a
re-run keeps the session and runs no second auth probe (`tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`),
a same-basename folder gets the hash form (`tests/e2e/test_launch.py::test_same_basename_other_folder_gets_hash_form`),
a dead leftover is replaced (`tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced`), and each hand-over
holds (`tests/e2e/test_launch.py::test_no_tty_prints_attach_command`,
`tests/e2e/test_launch.py::test_inside_tmux_switches_client`, `tests/e2e/test_launch.py::test_attach_under_pty`).
[Sessions and ownership](sessions_and_ownership.md) owns the identity a re-run finds.

A new session may open on claude's bypass-permissions warning, its workspace-trust dialog or codex's
directory-trust screen; each keeps the pane alive, and the user answers it after attaching. agentctl never
answers one, because accepting writes the user's settings and is the user's consent. The logged-in launch is
confirmed by [Live agent acceptance](../../DEVELOPMENT_PLAN/phase-11-live-agent-acceptance.md).

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
  directory it sits in.
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

- [multiplexer adapter](multiplexer_adapter.md) — the vocabulary, floors and session options used here.
- [sessions and ownership](sessions_and_ownership.md) — `list`, `attach` and `stop` for launched sessions.
- [python and haskell boundary](python_haskell_boundary.md) — the raw passthrough that delivers ARGS unchanged.
- [troubleshooting](../operations/troubleshooting.md) — each warning, the other install routes, what to type.
- [cli reference](../reference/cli_reference.md) — every command and its exit status.
- [files and state](../reference/files_and_state.md) — the spec and status file formats.
- [external tool facts](../reference/external_tool_facts.md) — the claude, codex, tmux and psmux facts cited.
- [Agent adapters and preflight](../../DEVELOPMENT_PLAN/phase-5-agent-adapters-and-preflight.md) — builds argv, refusals, preflight.
- [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) — builds the rest.
