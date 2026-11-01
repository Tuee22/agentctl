# Multiplexer Adapter

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Multiplexer adapter](../../DEVELOPMENT_PLAN/phase-4-multiplexer-adapter.md)

> **Purpose**: Define how the core binary finds tmux or psmux, the one typed vocabulary it drives them with,
> how it targets sessions and records their identity, and the isolation under which tests run the real
> multiplexer.

## TL;DR

- The binary drives tmux on Linux and macOS (at least 3.2) and psmux on Windows (at least 3.4.0, always as
  `psmux.exe`). It resolves the multiplexer once per command to an absolute path and checks the floor before
  anything else (R12.1).
- Every action is a value of the closed vocabulary in `AgentCtl.Mux.Command`, rendered to argv by the pure
  `AgentCtl.Mux.Tmux` or `AgentCtl.Mux.Psmux` and run by `AgentCtl.Process`, the one runner. The vocabulary
  has no `kill-server`, no respawn and no command that takes a shell string.
- Sessions are targeted as `=NAME` and agent panes by their `%id`. Managed identity lives in the session
  options `@agentctl_owner`, `@agentctl_agent`, `@agentctl_folder` and `@agentctl_pane`, on the user's normal
  server.
- No user text reaches multiplexer parsing: the pane command is the pane trampoline, and the agent's argv,
  working directory and environment travel in its spec file.
- Tests run the real multiplexer only in a scope they own: `TMUX_TMPDIR` with `TMUX` unset for tmux,
  `PSMUX_DATA_DIR` with `PSMUX_NO_WARM=1` for psmux.

## Resolution and Version Floors

`AgentCtl.Mux` looks up `tmux` on PATH on Linux and macOS, and `psmux.exe` through PATH and PATHEXT on Windows.
It never uses `tmux.exe` or `pmux.exe`, the aliases psmux ships: `tmux.exe` is also the name of MSYS2, Cygwin
and WSL tmux, and psmux's alias reports psmux's own version in tmux's format (psmux 3.3.8 answers
`tmux 3.3.8`), so a tmux floor read through it would judge the wrong program.

The version comes from `-V`. tmux prints `tmux <version>`, such as `tmux 3.4` or `tmux 3.2a`; psmux prints
`psmux <major>.<minor>.<patch> (<commit> <date>)`. A string the parser does not recognise is refused, and the
warning quotes it.

| Multiplexer | Floor | Why this floor |
|---|---|---|
| tmux | 3.2 | Every behaviour this contract uses is present by 3.2: exact `=` targets (2.1), direct execution of a pane command of two or more arguments (documented by 2.9), and remain-on-exit with `#{pane_dead}` and `#{pane_dead_status}`. The floor admits Ubuntu 22.04, Debian 12 and EL 9 and their successors, which ship 3.2a or newer, and refuses Ubuntu 20.04's 3.0a, Debian 11's 3.1c and EL 8's 2.7. |
| psmux | 3.4.0 | Quote-aware handling of paths containing spaces in the pane command (arrived in 3.3.9 and 3.4), `-L` honoured over `$TMUX` (3.3.7), and a bare `kill-server` that ends only its own namespace (3.3.8). The trampoline's paths sit under the user's profile, which can contain spaces. |

Resolution and the floor are the first check of [preflight](launch_contract.md#preflight), and every command
that drives sessions runs them too; the warnings, remedies and exit codes of a missing or too-old multiplexer
are in [failure and warnings](launch_contract.md#failure-and-warnings). The accepted and refused version
strings are rows of `tests/oracles/mux_commands.toml`, and a missing multiplexer is tested by running the
subject under a constructed PATH that lacks it, never by inspecting the host.

## The Typed Vocabulary and the One Runner

`AgentCtl.Mux.Command` is closed: a value names one multiplexer action, `AgentCtl.Mux.Tmux` and
`AgentCtl.Mux.Psmux` render it as argv with pure functions, and `AgentCtl.Process`, the only importer of
`System.Process` (`src.one-process-module`), runs it and decodes the output as UTF-8, never the locale
encoding; [the supervisor contract](supervisor_contract.md) owns what becomes of a capture. The adapter issues
one command per invocation and never chains commands with `;`.

| Action | tmux argv | Used by |
|---|---|---|
| create the agent session | `new-session -d -s <name> -P -F '#{pane_id}' -- <binary> pane-exec <spec>` | launch |
| does the session exist | `has-session -t =<name>` | launch, sessions |
| read sessions, options and panes | `list-sessions -F <format>`, `show-options -t =<name>`, `list-panes -s -t =<name> -F <format>` | launch, `list`, `status` |
| read pane state | `display-message -p -t %<id> '#{pane_pid} #{pane_dead} #{pane_dead_status} #{pane_dead_signal}'` | launch, `status`, the supervisor |
| set identity | `set-option -t =<name> @agentctl_<key> <value>` | launch |
| hold or release a dead pane | `set-option -p -t %<id> remain-on-exit on`, then `set-option -p -u -t %<id> remain-on-exit` | launch |
| capture | `capture-pane -p -J -t %<id> -S -<lines>` | launch, `status`, the supervisor |
| type text literally | `send-keys -l -t %<id> -- <text>` | the supervisor |
| submit | `send-keys -t %<id> Enter` | the supervisor |
| attach or switch | `attach-session -t =<name>`, `switch-client -t =<name>` | launch, `attach` |
| end a session | `kill-session -t =<name>` | launch cleanup, `stop` |

There is no value for `kill-server`, `kill-pane`, `respawn-pane`, `respawn-window`, `run-shell`, `if-shell`,
`pipe-pane`, `source-file`, a global `set-option -g`, or any command that takes a shell string. Production code
therefore cannot end the user's server, the supervisor cannot restart a process (R19), and no user setting
outside agentctl's own sessions and agent panes can change. Each rendering is a row of
`tests/oracles/mux_commands.toml`, compared as a value, and any argv difference fails:

```toml
[[render]]
action = "kill-session"
session = "api-claude"
tmux = ["kill-session", "-t", "=api-claude"]
psmux = ["kill-session", "-t", "=api-claude"]
provenance = "tool:tmux 3.4 tmux.1 target-session"
```

## Targets and Session Options

Every session target is `=NAME`, an exact match. Without the `=`, tmux tries a session id, the exact name, a
prefix and then an fnmatch pattern, so `has-session -t api` succeeds when only `api-v2` exists and
`kill-session -t api` can end it. Names never contain `.` or `:`, the target separators, because the name
whitelist excludes them. [Create or attach](launch_contract.md#create-or-attach) uses these targets for the
re-attach and `switch-client`, and [sessions and ownership](sessions_and_ownership.md) for `kill-session -t =NAME`,
the only command that ends anything.

Panes are targeted by `%id`. A session target resolves to the active pane of the current window, which is
the user's choice once they split a window, so every capture and send names the agent pane's id, the one
`new-session -P -F '#{pane_id}'` printed.

Sessions live on the user's normal server (psmux's default namespace on Windows), so `tmux ls`, the user's
key bindings and the status line see them. agentctl passes no `-L` or `-S`: tmux's own rule chooses the server, the socket named in `$TMUX` when it
is set and the default socket otherwise. Launch writes the identity of each managed session as session
options:

| Option | Value |
|---|---|
| `@agentctl_owner` | `agentctl`; the session is managed |
| `@agentctl_agent` | `claude` or `codex` |
| `@agentctl_folder` | the canonical folder path, base64url-encoded without padding from its UTF-8 bytes |
| `@agentctl_pane` | the agent pane's `%id` |

Options live and die with their session, so they never describe a session that has ended, and a server
restart takes them away together with the pane ids they name. The folder is the one user-derived string that
identity needs; encoding it draws the value from the same `[A-Za-z0-9_-]` set as session names, so no
multiplexer parsing rule can touch it, and `list` decodes it for display. agentctl sets no option on a session
it does not own, never sets a global option, and holds remain-on-exit at pane scope only during the startup
window, then unsets it so that the user's own setting applies again.

## Format Expansion, Separators and the Trampoline

tmux applies its own parsing to parts of its command line:

- **Format expansion.** The `-s` and `-c` values of `new-session` are format-expanded: `#(cmd)` runs `cmd`
  with `/bin/sh`, `##` becomes `#`, and short aliases such as `#S`, `#H` and `#D` are substituted. A folder
  named `#(touch x)` passed to `-c` runs a command.
- **The `;` separator.** An argv element ending in an unescaped `;` ends the tmux command there; the `;` is
  stripped and the rest of argv starts a new tmux command. An element that is exactly `;` is dropped.
- **Silent exec failure.** A pane command of two or more elements is exec'd directly with no shell, and a
  failed exec calls `_exit(1)` and prints nothing, so the session simply disappears.
- **The server's environment.** A pane gets the environment the server started with plus the
  `update-environment` variables, not the caller's. `-e` values are not expanded, but they sit on the client's
  argv, where other processes can read them.

The adapter removes each hazard instead of escaping it:

- `-s` receives only whitelisted names ([session names](launch_contract.md#session-names)).
- `-c` is never passed. The `new-session` client runs with the canonical folder as its working directory, which
  tmux takes as the start directory, and the trampoline sets the agent's working directory from its spec.
- The pane command is exactly three agentctl-generated elements: the absolute path of the published binary,
  `pane-exec` and the absolute spec path. Neither path ends in `;`, and no element carries user text.
- No `-e` is passed: the caller's environment travels in the 0600 spec, so environment values stay off the multiplexer command line and the pane
  sees the caller's environment rather than the server's.
- The trampoline reports its own failures in the pane before it exits, and instant-exit capture relays them,
  so no failure is silent.
- Option values are whitelisted words, base64url text or pane ids, and the only text ever typed is the
  supervisor's per-agent constant, sent with `send-keys -l`, which types characters instead of reading key
  names.

```text
WRONG  new-session -d -s api-claude -c '/home/ana/#(touch x)' -- /usr/bin/claude fix; --dangerously-skip-permissions
RIGHT  new-session -d -s api-claude -P -F '#{pane_id}' -- <binary> pane-exec <spec>
```

The WRONG form runs `touch x` while expanding `-c`, ends the tmux command at `fix;` so that claude starts
without its mandatory flag and the flag becomes a failing tmux command, and leaves the agent's argv readable on
the tmux client's command line. The RIGHT form gives tmux nothing to expand, split or expose.
[The pane trampoline](launch_contract.md#the-pane-trampoline) owns the spec file rules.

## psmux Differences

| Topic | psmux behaviour | Consequence for the adapter |
|---|---|---|
| Server model | One server process per session, reached over loopback TCP with an auth key; registry files under `~\.psmux\`, the `.port` file written last as the readiness beacon | After `new-session`, poll `has-session` with a bounded timeout instead of sleeping |
| Namespaces | `-L` becomes a file prefix, `<ns>__<session>` | Session names never contain `__` |
| Exit status | `#{pane_dead_status}` always returns 0 | The trampoline runs the agent as a child and writes a status file |
| `#{pane_pid}` | The pane's own process | The trampoline, which waits for the agent |
| `=` targets | Stripped on `has-session`, matching tmux's exact match; undocumented elsewhere | Rendered as `=NAME` everywhere; confirmed on Windows |
| `;` chains | Commands before an unknown command have already run | Irrelevant: the adapter never chains |
| `-c` | Whether it is format-expanded is undocumented | Never passed |
| Claude settings | `claude-code-fix-tty` and `claude-code-force-interactive` (which sets `CLAUDE_CODE_FORCE_INTERACTIVE=1`) are on by default, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set when absent, and a pwsh `claude` function adds `--teammate-mode tmux` | The trampoline gives the agent the caller's environment and a direct argv, so neither the variables nor the function reach it; agentctl leaves the user's psmux options alone |
| Nesting | Blocked inside psmux; panes carry `TMUX` and `TMUX_PANE` | `switch-client`, as with tmux |
| `kill-server` | Since 3.3.8 a bare form ends only the default namespace | Never used in production |

## Isolation

Production code has no isolation switch: it never passes `-L` or `-S`, and `src.no-test-branches` rejects any
test-only path. Tests isolate it from outside, through the environment, as
[testing](../engineering/testing.md#isolation) records in full:

- **tmux.** `TMUX_TMPDIR` points at a short test-owned directory, mode 0700, because tmux refuses a socket
  directory with permissions for others, and `TMUX` is unset, so the subject's normal server is a private
  server under the run dir. The socket path stays within 100 bytes (precondition P6), since Unix socket paths
  are limited to about 104 bytes on macOS and 108 on Linux.
- **kill-server.** Only `tests/harness/tmux.py` runs it, and only after asserting that the socket lies under
  the run dir. A developer's shell is commonly inside the default server, so a bare `kill-server` would end the
  user's sessions.
- **psmux.** Every psmux process gets an absolute, test-owned `PSMUX_DATA_DIR`, which gives it its own registry
  and server guard, and `PSMUX_NO_WARM=1`, which disables pre-spawned warm servers. Teardown never runs
  `taskkill /im psmux.exe`, which would end the user's psmux too.
- **The observer.** `agentctl-fake-agent`, copied into a temp bin as `claude` or `codex`, records argv, working
  directory, environment keys, the multiplexer session and the run's nonce, and either exits at once or stays
  running.

Against a real private server the tests show an instant exit held by remain-on-exit, `=ab` ending `ab` but not
`ab-c`, the elements `x;`, `#{pane_id}` and `#(id)` arriving verbatim, and the pane environment equalling the
caller's when the server started with a different one. The `containment` check step fails when a private
server or an observer pid is still alive, or when a session carrying the run's nonce exists on the user's
server. Real psmux runs only on a Windows host, and macOS tmux only on a Mac; until then psmux rendering is
proven as values.

## Related

- [launch contract](launch_contract.md) — the session names, the pane trampoline and the failure warnings.
- [sessions and ownership](sessions_and_ownership.md) — how `list`, `attach` and `stop` read these options.
- [supervisor contract](supervisor_contract.md) — the captures and literal sends made through this vocabulary.
- [python and haskell boundary](python_haskell_boundary.md) — why only the binary drives the multiplexer.
- [testing](../engineering/testing.md#isolation) — the isolation recipes these tests use.
- [external tool facts](../reference/external_tool_facts.md) — the verified tmux and psmux facts cited here.
- [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md) — where real
  psmux behaviour is confirmed.
- [Multiplexer adapter](../../DEVELOPMENT_PLAN/phase-4-multiplexer-adapter.md) — the phase that builds this
  adapter.
