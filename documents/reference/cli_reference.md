# CLI Reference

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md)

> **Purpose**: List every agentctl command with its arguments, what it does and its exit status.

`agentctl` is the only command you run. `check` runs in agentctl's Python layer; every other command passes, with its
arguments untouched, to the core binary, which agentctl builds and starts for you and which you never call directly.
Each command below names the phase that builds it, and the plan's
[status table](../../DEVELOPMENT_PLAN/README.md#current-phase-status) records which of those phases are built.

## Global Options

Global options go before the command; after the command, every token belongs to it.

| Option | Meaning | Owning phase |
|---|---|---|
| `--assume-yes` | Consents in advance to installing missing OS prerequisites. A run without a terminal installs directly as root or through `sudo -n` with passwordless sudo; it never prompts. Example: `agentctl --assume-yes list`. | [Toolchain bootstrap](../../DEVELOPMENT_PLAN/phase-2-toolchain-bootstrap.md) |
| `--help` | `agentctl --help` lists the commands, and `agentctl <command> --help` describes one. After `claude` or `codex`, `--help` is one of the ARGS and goes to the agent. | [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |

## Names

`NAME` below is a name exactly as `agentctl list` prints it: a managed session's name, such as `api-claude`, or an
adopted pane's id, such as `%3`. A managed session is named `<folder>-<agent>` after the folder it was launched from,
and a different folder with the same name gets `<folder>-<8 hex digits>-<agent>`
([session names](../architecture/launch_contract.md#session-names)). Every command works on one multiplexer server:
the one `$TMUX` names when it is set, otherwise your default server.

## Commands

| Command | Arguments | What it does | Owning phase |
|---|---|---|---|
| `agentctl claude [ARGS...]` | `ARGS`: passed to claude verbatim | Launches claude for the current folder in a tmux (Linux, macOS) or psmux (Windows) session named `<folder>-claude`, after checking the multiplexer, claude and claude's login, then attaches you to it. claude gets `ARGS` with `--dangerously-skip-permissions` at the end, or immediately before the first bare `--`; copies of that flag before the `--` are dropped. When the folder's session is alive, it re-attaches without the checks and says that `ARGS` were not applied. Login-shaped `ARGS` (`auth login…`, `setup-token`, a `/login` prompt) are refused. | [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| `agentctl codex [ARGS...]` | `ARGS`: passed to codex verbatim | The same for codex, in `<folder>-codex`, with `--dangerously-bypass-approvals-and-sandbox --no-daemon` placed the same way; copies of those flags and of `--yolo` before the `--` are dropped. `login…` is refused. | [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| `agentctl list` | none | One row per managed session, then one per adopted pane: name or pane id, agent, folder (managed sessions only), whether the agent's pane is alive (`stale` for an adopted pane that failed revalidation), and whether a client is attached. Sessions agentctl neither manages nor adopted are not listed. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| `agentctl status [NAME]` | `NAME`, optional; without it, the managed sessions launched from the current folder | The `list` facts plus the agent pane's id and pid and, for a dead pane, its exit status; the screen class read from the pane ([Pane observation and classification](../../DEVELOPMENT_PLAN/phase-8-pane-observation-and-classification.md)); and the watch state, `watched` or `paused` ([Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md)). | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| `agentctl attach NAME` | `NAME`: a managed session | Attaches your terminal to the session; inside tmux it switches your client instead, and without a terminal it prints the attach command and exits 0. It changes nothing on the session, and an adopted pane is refused. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| `agentctl stop NAME` | `NAME` | A managed session ends, with the agent in it. An adopted pane is forgotten and keeps running, with a notice saying so. Anything else is refused and left untouched. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| `agentctl adopt PANE --agent AGENT` | `PANE`: a pane id such as `%3`; `AGENT`: `claude` or `codex` | Registers a pane agentctl did not create, without taking ownership; it then appears in `list` under its id and can be watched, and agentctl never ends it. A pane that does not exist, belongs to a managed session or is already adopted is refused. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| `agentctl watch NAME` | `NAME` | Adds the session or pane to the watch set that `supervisor run` observes. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl unwatch NAME` | `NAME` | Removes it from the watch set; the session and its pane are not touched. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl pause NAME` | `NAME` | Keeps the watch entry, suspends captures and recovery decisions, and drops an open incident. `resume-watch` takes a fresh baseline before detecting new failures. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl resume-watch NAME` | `NAME` | Clears the pause. It resumes supervision, not the agent's goal. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl logs NAME` | `NAME` | Prints, in log order, the supervisor's records for exactly that target: every observation, decision, attempt and result, and every notification. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl supervisor run [OPTIONS]` | the timing options below | Runs the recovery supervisor in the foreground over the watch set until SIGINT (Ctrl-C) or SIGTERM. Nothing starts it for you, one runs at a time, and stopping it leaves every session running. It never switches models, restarts a crashed agent or sends login input, and its notifications go to its stderr and to the log. | [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| `agentctl check` | none | Runs the quality gate over the checkout agentctl is installed from: every step and leg, the entire test suite included. It needs an editable install of that checkout with the `dev` extra, and it never prompts. | [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |

`agentctl supervisor run` takes these timing options and reads no configuration file:

| Option | Default | Meaning |
|---|---|---|
| `--poll-seconds` | `5` | Seconds between captures of each watched pane |
| `--initial-delay-seconds` | `30` | The backoff delay before the first recovery attempt |
| `--max-delay-seconds` | `900` | The longest any backoff delay grows |
| `--multiplier` | `2` | The factor by which each backoff delay exceeds the one before |
| `--jitter-fraction` | `0.2` | The random spread applied to each delay, as a fraction of it |

The contracts behind these rows are in [the launch contract](../architecture/launch_contract.md),
[sessions and ownership](../architecture/sessions_and_ownership.md), [the supervisor contract](../architecture/supervisor_contract.md)
and [the quality gate](../engineering/quality_gate.md).

This table is joined both ways against the code by
`tests/integration/test_command_surface.py::test_cli_reference_joins_click_and_handshake`: every command in click's
command list, and every command in the core binary's handshake command list, has a row here, and every row whose owning
phase the status table records as built is in click's list and, except `check`, in the handshake list.

## Exit Status

`agentctl claude` and `agentctl codex` exit with the status of their outcome
([failure and warnings](../architecture/launch_contract.md#failure-and-warnings)):

| Status | Outcome |
|---|---|
| `0` | Your client detached, or the session ended; without a terminal, the session exists and its attach command was printed |
| `1` | Any other launch failure, such as both of the folder's names being held by other sessions |
| `2` | Login-shaped `ARGS` refused |
| `3` | Multiplexer missing |
| `4` | Multiplexer older than its floor |
| `5` | Agent missing |
| `6` | Windows `.cmd` or `.bat` shim refused |
| `7` | Agent logged out |
| `8` | Auth check failed |
| The agent's own status | The agent exited during the startup window; its output is shown first and its session closed ([instant exit](../architecture/launch_contract.md#instant-exit)) |

After the startup window the multiplexer client does not carry the agent's exit status, so a launch that attached exits
0 however the agent later ends.

Every other command exits 0 when it did what its row says, and non-zero with a warning on stderr when it failed or
refused ([troubleshooting](../operations/troubleshooting.md)). In particular, `stop` exits 0 for a managed session and for
an adopted pane; `logs` exits non-zero when the target has no records; `supervisor run` exits 0 on SIGINT or SIGTERM and
non-zero while another supervisor holds the lock; and `check` exits 0 only when every step and leg ran and passed. A
first run that cannot provision the toolchain or build the core binary, such as one meeting a missing prerequisite
without consent, exits non-zero before the command itself runs.

## Related

- [troubleshooting.md](../operations/troubleshooting.md) — each warning a command can print, and what to type.
- [installation.md](../operations/installation.md) — installing agentctl, the first run and `--assume-yes`.
- [files_and_state.md](files_and_state.md) — the files these commands read and write.
- [launch_contract.md](../architecture/launch_contract.md) — the full contract of `claude` and `codex`.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed sessions, adopted panes and their commands.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — what `supervisor run` observes, decides and sends.
- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — how every command but `check` reaches the core binary.
