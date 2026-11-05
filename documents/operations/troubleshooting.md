# Troubleshooting

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md)

> **Purpose**: For each warning agentctl prints, say what the user sees and exactly what to type next.

Every warning goes to the terminal you ran `agentctl` from, on stderr, and each line starts `agentctl:`; none is ever
printed into a session that is about to close. A launch checks the multiplexer, then the agent, then the agent's login,
and stops at the first failure, so fixing one warning can reveal the next. A failed launch leaves no session behind and
exits with the status its class names below ([exit status](../reference/cli_reference.md)), so nothing needs cleaning
up: fix the cause and run the same command again. The exact wording of each warning is held by the oracle rows the
tests compare against, `tests/oracles/preflight.toml` for launch failures and `tests/oracles/auth_status.toml` for
login remedies.

## Multiplexer Missing

**What you see.** A warning that tmux (Linux, macOS) or psmux (Windows) was not found on PATH, exit 3, or that the one
found is older than its floor, tmux 3.2 or psmux 3.4.0, exit 4, with the install command for your OS. Every command
that drives sessions checks this, so `agentctl list` reports it too.

**What to type.** Install the multiplexer, then run the command again:

```console
$ sudo apt install tmux        # Debian, Ubuntu
$ sudo dnf install tmux        # Fedora and the RHEL family
$ sudo pacman -S tmux          # Arch
$ brew install tmux            # macOS
> winget install psmux         # Windows
```

Some distributions ship a tmux older than 3.2: Ubuntu 20.04 has 3.0a, Debian 11 has 3.1c, and Alma, Rocky and CentOS 8
have 2.7. There, install a newer tmux, for example from Homebrew, which also provides tmux on Linux, or move to a newer
release of the OS. On Windows agentctl runs `psmux` itself, never psmux's `tmux` alias, so another `tmux` on PATH, such
as MSYS2's or Cygwin's, does not count.

An unrecognised version answer is refused with that raw answer quoted in the typed diagnostic; it is never treated
as a new enough version. On an unrecognised Linux distribution, the remedy names tmux 3.2 or later and the OS package
manager without inventing an apt or dnf command. The core checks availability and prints the remedy; it does not
install a multiplexer or change its configuration.

## Agent Missing

**What you see.** A warning that `claude` or `codex` was not found on PATH, with the official install command for your
OS; exit 5.

**What to type.** Install the agent, open a new shell if the installer changed PATH, and run the command again:

```console
$ curl -fsSL https://claude.ai/install.sh | bash                                         # claude: macOS, Linux
> winget install Anthropic.ClaudeCode                                                    # claude: Windows
$ curl -fsSL https://chatgpt.com/codex/install.sh | sh                                    # codex: macOS, Linux
> powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"   # codex: Windows
```

Other official routes are `irm https://claude.ai/install.ps1 | iex` in PowerShell, `brew install --cask claude-code`,
`npm install -g @anthropic-ai/claude-code` (Node.js 22 or later), `brew install --cask codex` and
`npm install -g @openai/codex`. An npm-installed codex is a Node script, so `node` must be on PATH as well. On Windows
use a native installer: agentctl refuses the `.cmd` launchers npm creates (below).

## Windows .cmd Shim Refused

**What you see.** A warning that `claude` or `codex` resolves only to a `.cmd` or `.bat` file, with its path, and that
agentctl starts only a native `.exe`; exit 6. Windows runs a `.cmd` or `.bat` file through `cmd.exe`, which parses the
arguments a second time, so your ARGS would not reach the agent verbatim and text in them could run as commands.

**What to type.** Install the native agent with one of the Windows commands above, then check which file PATH finds
first with `where.exe codex` (or `where.exe claude`). When the `.cmd` is listed before the `.exe`, remove it or put the
native agent's directory earlier on PATH, and run the command again.

## Logged Out

**What you see.** A warning that the agent is not logged in, naming the command for you to type; exit 7. No session
was created: the login check runs before any session exists.

**What to type.** Log in yourself, in your own shell, then run the agentctl command again:

```console
$ claude auth login
$ codex login
$ codex login --device-auth    # codex on a headless or remote machine
```

`claude auth login` signs in with a Claude subscription by default; add `--console` for Anthropic Console billing or
`--sso` for single sign-on. Log in with the environment you run agentctl from: claude keeps one login per
`CLAUDE_CONFIG_DIR`, and a file-stored codex login lives under `CODEX_HOME` (default `~/.codex`), so a login made with a
different value of either is not the one agentctl checks. `codex login status` exits 1 both for "Not logged in" and for
"Error checking login status", so a codex warning that you are logged out can also mean codex could not read its
credential store; run `codex login status` to see which.

## Login-Shaped ARGS Refused

**What you see.** A warning that login commands must be run yourself, naming the appropriate command; exit 2. It covers `agentctl claude auth login`, `agentctl claude setup-token`, a `/login` argument, and
`agentctl codex login`, and nothing was started.

**What to type.** The login command in your own shell, such as `claude auth login` or `codex login`, then the agentctl
command without it. A prompt that only mentions logging in goes after a bare `--`, as in
`agentctl claude -- "explain how login works here"`; after the `--`, only a claude prompt that is `/login`, or begins
with it, is still refused.

## Auth Check Failed

**What you see.** A warning that the agent's login state could not be determined: its status probe, `claude auth status`
or `codex login status`, exited with something other than 0 (logged in) or 1 (logged out), or did not finish within
10 s; exit 8. agentctl does not treat this as logged out and does not tell you to log in again.

**What to type.** Run the probe yourself and read what it says, then fix what it points at:

```console
$ claude auth status --text
$ claude doctor
$ codex login status
```

- **An outdated agent.** claude 2.1.301 fixed sign-outs after short commands such as `claude auth status`; update with
  `claude update`, or let a native install update itself.
- **A credential store that cannot answer.** On macOS claude keeps its login in the Keychain, which can be locked in an
  SSH session; a codex configured with `cli_auth_credentials_store = "keyring"` fails when the OS keyring is
  unavailable. Unlock the store, or log in where it is available.

## Instant Exit

**What you see.** The agent's own output, relayed to your terminal, then a notice that the agent exited during startup
and its session was closed. agentctl exits with the agent's exit status, 0 included. agentctl starts the agent with your
ARGS followed by its mandatory flags, `--dangerously-skip-permissions` for claude and
`--dangerously-bypass-approvals-and-sandbox --no-daemon` for codex, before the first bare `--` if there is one, and keeps
the pane open for a short startup window, so an agent that rejects that command line shows you why.

**What to type.** Read the agent's message and fix your ARGS:

| The agent prints | Cause | What to type |
|---|---|---|
| `error: unknown option '--dangerously-skip-permissions'` | ARGS begin with a claude subcommand, such as `auth status`, which does not take the flag | Run the subcommand with `claude` directly, outside agentctl |
| `error: unexpected argument '--no-daemon' found` | ARGS begin with `exec`, a codex subcommand that rejects `--no-daemon` | Run `codex exec ...` directly, outside agentctl |
| `the argument '--ask-for-approval <APPROVAL_POLICY>' cannot be used with '--dangerously-bypass-approvals-and-sandbox'` | `-a` or `--ask-for-approval`, or `--approve-for-me`, conflicts with the bypass flag | Run again without that flag |
| `unexpected argument '--full-auto'` | A flag codex 0.166.0 does not have | Run again without it |
| `--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons` | claude was started as root or under sudo | Run agentctl as your normal user |

Any ARGS that make the agent print something and exit at once end the same way, with its output and its status.

## Prerequisite Missing in a Non-Interactive Run

**What you see.** A warning that GHC needs OS packages this host lacks, listing the exact commands that install them,
and saying that nothing was installed; the exit is non-zero. It appears when the run has no terminal to ask in and
`--assume-yes` was not given, when you decline the `[y/N]` prompt, when `--assume-yes` meets a sudo
that needs a password, and on a host whose package set agentctl has not verified, such as Arch Linux, where it names the
failed probes instead of running a package manager.

**What to type.** One of these, then run your command again:

```console
$ agentctl list                     # from a terminal: agentctl asks, then installs through sudo
$ agentctl --assume-yes list        # consent in advance; sudo -n, so passwordless sudo or root
$ sudo apt-get update && sudo apt-get install -y <packages the warning lists>
```

The prompt accepts `y` or `yes`, ignoring case and surrounding spaces; every other answer declines. The last command
is the Ubuntu and Debian form; use the commands the warning prints. On macOS the prerequisite is the Xcode Command Line
Tools. `agentctl check` requires them to be installed already; it never opens a setup dialog. Use a host with the tools
installed for automated validation. Interactive setup with `xcode-select --install` is outside the gate.

## ghcup Below the Floor

**What you see.** A warning that the ghcup agentctl found, with its path and version, is older than 0.1.50.2 or did not
answer `--numeric-version`; the exit is non-zero. agentctl never replaces or upgrades a ghcup you own.

**What to type.** Upgrade it yourself, with the ghcup the warning names, then run the command again:

```console
$ ghcup upgrade
```

## ghcup Download Failed Verification

**What you see.** A warning that the download was truncated, its SHA-256 did not match the pin, or a verified ghcup
could not be downloaded. The command exits non-zero and removes its temporary download.

**What to type.** Retry with a working network and writable ghcup destination. An occupied or changed destination
means another executable appeared after discovery; retry so agentctl gathers its version. Preserve an existing ghcup
and use its reported upgrade remedy when it is below the floor. Do not disable digest verification.

## Unsupported Platform

**What you see.** A warning naming the OS and architecture agentctl found and the platforms it supports: Linux on x86_64
or aarch64, macOS on x86_64 or arm64, and Windows on x86_64. Nothing was installed.

**What to type.** Nothing fixes this on that host: the pinned GHC and cabal are not built for it, Windows on ARM64
included. Run agentctl on a supported host.

## Native Build, Cache or Binary Identity Failed

**What you see.** A compiler diagnostic, an unreadable source or pin file, an incomplete published directory, an
unexpected core handshake, or a build-lock timeout. A binary identity mismatch names the built and published SHA-256
values and the one published directory involved. Existing published directories are retained on every failure.

**Remedy.** Fix the reported source, toolchain or filesystem error and retry the same `agentctl` command. A lock timeout
means another build still holds that digest; retry after it finishes. An identity mismatch after clearing the build
cache can result from a rebuild with different bytes. Remove only the single published directory the diagnostic names
to permit a fresh publish, as [binary identity](../engineering/binary_build.md#binary-identity) describes. No commit,
review or interactive confirmation is needed to validate the repaired checkout: run `agentctl check`.

## Session Exists, ARGS Not Applied

**What you see.** agentctl attaches you to the session it launched earlier from this folder and prints
`agentctl: api-claude is already running; the arguments given were not applied.` The agent in that session keeps the
ARGS it started with, and re-attaching skips the checks. When every pane of that session is dead, agentctl ends the
leftover session instead and launches afresh, with your ARGS.

**What to type.** To keep the session, nothing. To start the agent again with new ARGS, end the session and launch again,
using the name `agentctl list` prints; `agentctl stop` ends the agent and whatever it was doing:

```console
$ agentctl stop api-claude
$ agentctl claude --add-dir ../lib
```

## Stop Refused, Pane Forgotten or Stale

**What you see.** One of three messages:

- `agentctl: api is not a session agentctl manages; nothing was stopped.` with a non-zero exit, for a name that is
  neither a managed session nor an adopted pane;
- `agentctl: %3 is adopted, not owned. Registration removed; agentctl did not end the pane.` with exit 0, including a stale adopted registration;
- `stale` beside an adopted pane in `agentctl list` or `agentctl status`, when its pane id is gone or now belongs to
  another process, as after the multiplexer server restarted; agentctl never acts on a stale entry.

**What to type.** `agentctl list` shows the names agentctl accepts. A session or pane agentctl does not own is ended
with the multiplexer's own commands, for example `tmux kill-session -t =api`. A stale entry is cleared with
`agentctl stop %3`, and a pane that still runs under a new id is registered again with
`agentctl adopt %7 --agent claude`.

## Supervisor Already Running

**What you see.** `agentctl supervisor run` exits non-zero at once, naming the process id of the supervisor that holds
the lock. One supervisor runs per user.

**What to type.** Nothing, to keep the one that runs. To restart it with other options, stop it with Ctrl-C in its
terminal, or with `kill <pid>`, which sends SIGTERM, then start it again. Stopping a supervisor leaves every session
running.

## Watch Target Refused

**What you see.** `agentctl watch NAME` exits non-zero and leaves the watch set unchanged, because `NAME` is neither a
managed session nor an adopted pane.

**What to type.** `agentctl list` for the names agentctl accepts. To watch an agent pane agentctl did not create, adopt
it first, then watch it by its pane id:

```console
$ agentctl adopt %3 --agent codex
$ agentctl watch %3
```

## No Terminal

**What you see.** Run without a terminal, as from a script, `agentctl claude` or `agentctl codex` creates the session or
finds the existing one, prints the command that attaches to it, such as `tmux attach-session -t =api-claude`, and
exits 0 without attaching; `agentctl attach NAME` does the same.

**What to type.** The printed command, or `agentctl attach NAME`, from a terminal.

## Invalid Adopted-Pane Registry

An invalid or unsafe adopted-pane registry causes a warning and a non-zero exit without replacing its bytes.
Unknown fields or agents, duplicate pane ids, nonpositive pids and a registry path that is not an owned private
file are rejected (`tests/e2e/test_adopt.py::test_registry_rejects_invalid_state`). The registry format and private
state-directory rules are in [files and state](../reference/files_and_state.md#adopted-pane-registry).

## Related

- [installation.md](installation.md) — the first run, consent, `--assume-yes` and the login rule.
- [cli_reference.md](../reference/cli_reference.md) — every command and its exit status.
- [launch_contract.md](../architecture/launch_contract.md#failure-and-warnings) — each launch warning, its class and its exit status.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed, adopted and foreign sessions, and what `stop` may touch.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — the watch commands and the supervisor lock.
- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — prerequisites, consent, the ghcup floor and the supported platforms.
- [external_tool_facts.md](../reference/external_tool_facts.md) — the sources for every install command and agent message quoted here.
