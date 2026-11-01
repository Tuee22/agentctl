# Sessions and Ownership

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md)

> **Purpose**: Define which sessions agentctl manages, which panes it only adopts, how it identifies each, and
> what `list`, `status`, `attach`, `stop` and `adopt` may do to them.

## TL;DR

- A **managed** session is one that `agentctl claude` or `agentctl codex` created. Its identity lives in its
  `@agentctl_*` session options, so it exists exactly as long as the session does, and no file lists it.
- An **adopted** pane is a pre-existing pane the user registers with `agentctl adopt %N --agent claude|codex`.
  It is recorded in the adopted registry under `state` and is never owned: `stop` forgets it and leaves it
  running (R17.1).
- Everything else is **foreign**: agentctl lists none of it and touches none of it.
- `list`, `status`, `attach`, `stop` and `adopt` work with no supervisor running (R16). A session ends only
  through `kill-session -t =NAME` on a managed session, and agentctl never runs `kill-server`.

## Managed, Adopted and Foreign

| Kind | How it arises | Identity | Addressed as |
|---|---|---|---|
| Managed | launch created it | session options on the live server | its session name, such as `api-claude` |
| Adopted | `agentctl adopt %N --agent claude\|codex` | an entry in the adopted registry | its pane id, such as `%3` |
| Foreign | any other session or pane | none | not addressable; commands naming it refuse |

Every command talks to one server, the one tmux itself chooses: the server named in `$TMUX` when it is set,
otherwise the user's default server. A pane id is unique only within its server, so `%3` always means the
pane `%3` on that server.

## Identity

**Managed sessions.** Launch writes `@agentctl_owner` (`agentctl`), `@agentctl_agent`, `@agentctl_folder` and
`@agentctl_pane` when it creates the session ([multiplexer adapter](multiplexer_adapter.md)), and every
command reads them from the live server; nothing caches them. Options live and die with the session, so a
session the user ends with tmux, or one lost to a server restart, simply stops being listed. The same options
let launch find a folder's session and re-attach ([create or attach](launch_contract.md#create-or-attach)).

**Adopted panes.** The adopted registry is `<state>/adopted.json`, rewritten atomically (a temporary file
renamed into place); [files and state](../reference/files_and_state.md) owns its format. Each entry holds the
server's endpoint identity in the `socket` field, the pane id, the pid of the pane's first process at adoption and
the agent. The adapter supplies a tmux socket path or an opaque psmux identity containing the namespace and
addressed server; Windows need not have a filesystem socket. Every use revalidates the entry: its endpoint must
name the live server the command talks to, and the pane id must exist
there with the recorded pid. An entry whose server is gone, whose pane id is missing or whose pid differs,
because the server restarted and reused the id, is **stale**: `list` and `status` show it as stale, nothing
captures from or sends to it, and `stop` forgets it. A restart that reuses both the id and the pid for another
process on the same socket is not detected, because the socket, pane id and pid are all revalidation compares.

`#{pane_current_command}` is a hint, never proof of what runs in a pane: `list` shows it beside an adopted pane,
and `adopt` takes the agent from `--agent` rather than guessing it from the process name.

## The Commands

- **`list`** prints one row for each managed session on the server, then one for each adopted pane: its name
  or pane id, the agent, the folder (decoded from `@agentctl_folder`; managed sessions only), whether the agent's
  pane is alive (`stale` for an adopted entry that failed revalidation) and whether a client is attached;
  adopted panes are marked adopted. Foreign sessions are not listed.
- **`status [NAME]`** prints the same facts for one session or pane, plus the agent pane's id and pid and, for a
  dead pane, its exit status. With no argument it reports the managed sessions launched from the current folder,
  both agents included. A name that is neither managed nor adopted is refused with a non-zero exit.
  [Pane observation and classification](../../DEVELOPMENT_PLAN/phase-8-pane-observation-and-classification.md)
  adds the screen class, from a capture this `status` run takes, classified by the agent `@agentctl_agent`
  names or, for an adopted pane, the agent recorded at adoption;
  [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) adds the watch state, `watched` or
  `paused`, and watching never takes ownership.
- **`attach NAME`** takes a managed session and hands the terminal to it the way launch does:
  `attach-session -t =NAME`, `switch-client -t =NAME` when `$TMUX` is set, or, with no TTY, the printed attach
  command and exit 0. It changes nothing on the session. An adopted pane or a foreign session is refused; the
  multiplexer's own commands reach it.
- **`stop NAME`** depends on the kind:
  - a managed session ends with `kill-session -t =NAME`, its agent pane included, and the command exits 0;
  - an adopted pane, stale or not, is forgotten and nothing else happens; agentctl prints
    `agentctl: %3 is adopted, not owned. Registration removed; agentctl did not end the pane.` and exits 0;
  - anything else is refused with a non-zero exit, and nothing is touched:
    `agentctl: api is not a session agentctl manages; nothing was stopped.`
- **`adopt PANE --agent claude|codex`** reads the pane's `#{pane_pid}` and records the entry. It refuses with a
  non-zero exit, recording nothing, when the pane does not exist, belongs to a managed session, or is already
  adopted. It sets no option, sends no key and ends nothing: adopting a pane transfers no ownership.

## What Each Command May Touch

| Action | Managed | Adopted | Foreign |
|---|---|---|---|
| `list`, `status` | yes | yes, revalidated | no |
| `attach` | yes | refused | refused |
| set session options | launch, at creation only | never | never |
| capture and send, once watched | the supervisor, at the agent pane | the supervisor, after revalidation | never |
| `kill-session -t =NAME` | `stop`, and launch cleaning up its own failed launch | never | never |
| `kill-server` | never | never | never |

`kill-server` is not in the typed vocabulary at all, so no production path can end the user's server, and
the exact `=NAME` target means `stop api` can never reach `api-claude`. The decisions behind this table are pure
and their rows are in `tests/oracles/session_ownership.toml`
(`tests/unit/test_sessions_values.py::test_list_rows_match_oracle`,
`tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`,
`tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle`). The real tests run on a private server beside a
foreign session the harness creates as their control:

- `list` shows the managed sessions and not the harness's own, which the harness's `list-sessions` does show
  (`tests/e2e/test_sessions.py::test_list_shows_only_managed`), and `status` reports a dead pane with its exit
  status and defaults to the current folder (`tests/e2e/test_sessions.py::test_status_reports_dead_pane`,
  `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`);
- `stop` ends only the named managed session, refuses the foreign one and never prefix-matches
  (`tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`,
  `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session`,
  `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`);
- `attach` attaches or switches under a PTY and prints its command without one
  (`tests/e2e/test_sessions.py::test_attach_and_switch_under_pty`,
  `tests/e2e/test_sessions.py::test_attach_without_tty_prints_command`);
- after `stop %N` the adopted pane is alive with the same pid and its entry is gone, its session carrying no
  agentctl option (`tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`), and a server restarted under
  the test, whose new pane reuses the id with another pid, leaves the entry stale and never acted on
  (`tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`).

## Independence from the Supervisor

Being managed or adopted, being watched and being attached by a human are independent. Attaching changes
neither ownership nor supervision, unwatching never ends the agent, and stopping the supervisor never ends a
managed or adopted session; [the supervisor contract](supervisor_contract.md) owns those last two rules (R17).

Session management never needs the supervisor. Every command here reads the session options and the adopted
registry directly, and the supervisor is a foreground process that nothing starts automatically, so sessions
stay listable, attachable and stoppable whether or not one is running.

## WRONG and RIGHT

```text
WRONG  stop api-claude runs: kill-session -t api-claude
RIGHT  stop api-claude runs: kill-session -t =api-claude
```

Without the `=`, a target that matches no session exactly falls back to prefix and pattern matching, so after
`api-claude` has ended the WRONG command ends `api-claude2`.

```text
WRONG  stop %3, on an adopted pane, runs: kill-pane -t %3
RIGHT  stop %3 removes the registry entry, says %3 is still running, and exits 0
```

The pane predates agentctl and belongs to the user; adopting it registered the pane and transferred nothing,
so ending it would kill a process agentctl never owned (R17.1).

```text
WRONG  launch records each managed session in a registry file, and list reads that file
RIGHT  launch writes the @agentctl_* options, and list reads them from the live server
```

A file keeps listing a session after the user ends it with tmux or the server restarts, so `list` shows
ghosts and `stop` aims at names that may now belong to another session.

## Related

- [launch contract](launch_contract.md) — how managed sessions are named, created and re-attached.
- [multiplexer adapter](multiplexer_adapter.md) — the session options, `=NAME` targets and the missing
  `kill-server`.
- [supervisor contract](supervisor_contract.md) — watching managed sessions and adopted panes, and R17.
- [files and state](../reference/files_and_state.md) — the adopted registry's format.
- [cli reference](../reference/cli_reference.md) — the syntax and exit codes of these commands.
- [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md) — where psmux pane
  ids and options are confirmed.
- [Session management and adoption](../../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) — the
  phase that builds these commands.
