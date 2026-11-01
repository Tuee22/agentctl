# Installation

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md)

> **Purpose**: Say how to install agentctl with pipx, what its first run does and asks, and how to upgrade it, remove it and log the agents in.

## Requirements

pipx, with the Python it runs on, is the only thing you install by hand to install and build agentctl. agentctl installs
everything else its build needs itself: the OS packages GHC requires (after asking you), ghcup, the pinned GHC and cabal,
and the core binary, which it builds from the Haskell sources bundled in its package.

| Requirement | Minimum | Why |
|---|---|---|
| Python | 3.12 | agentctl's package declares `requires-python` at least 3.12. |
| pipx | 1.4.3 | The version Ubuntu 24.04 ships. The commands on this page need nothing newer; they avoid options such as `--fetch-python`, which arrived in pipx 1.16. |
| Platform | Linux on x86_64 or aarch64; macOS on x86_64 or arm64; Windows on x86_64 | The pinned GHC and cabal are built for these; there is no Windows ARM64 build. |
| git | Only for an install from a git URL | pipx clones the repository; installing from a local copy of the source tree needs no git. |

To launch agents you also need, at run time, a terminal multiplexer and the agent CLIs: tmux 3.2 or later on Linux and
macOS, or psmux 3.4.0 or later on Windows, and `claude`, `codex` or both (the native `claude.exe` and `codex.exe` on
Windows). agentctl never installs these. It checks for them every time it launches an agent and, when one is missing,
prints the command that installs it ([troubleshooting](troubleshooting.md)).

## Install pipx

On Debian, Ubuntu and other distributions that mark their system Python as externally managed (PEP 668), install the
distribution's own pipx package; `pip install --user pipx` fails there.

```console
$ sudo apt install pipx
```

On macOS, Windows and other Linux distributions, follow pipx's installation guide,
`https://pipx.pypa.io/stable/how-to/install-pipx.html`.

pipx installs the `agentctl` command into its bin directory, `~/.local/bin` unless `PIPX_BIN_DIR` says otherwise, and
that directory must be on your PATH; pipx's guide shows how to add it. agentctl itself never edits your shell's startup
files.

## Install agentctl

No release of agentctl is published, so install it from its git repository. Replace `<owner>` with the account that
hosts the repository:

```console
$ pipx install 'agentctl @ git+https://github.com/<owner>/agentctl.git'
```

To install an exact revision, add a commit after the URL:

```console
$ pipx install 'agentctl @ git+https://github.com/<owner>/agentctl.git@<commit>'
```

On a host without git, copy the source tree there and install the copy: `pipx install <path-to-tree>`. When pipx's own
Python is older than 3.12, the install fails on `requires-python`; name a newer interpreter with `--python`:

```console
$ pipx install --python <path-to-python3.12-or-later> 'agentctl @ git+https://github.com/<owner>/agentctl.git'
```

The install puts one command on PATH, `agentctl`. Contributors who run `agentctl check` install an editable checkout
with the `dev` extra instead, `pipx install --editable '.[dev]'` (or `uv tool install --editable '.[dev]'`) from the
checkout, as [the quality gate](../engineering/quality_gate.md#preconditions) requires.

## First Run

The first command that needs the core binary, which is any command except `agentctl check` and `agentctl --help`,
provisions the toolchain and builds the binary before it runs:

1. **Platform.** agentctl reads the OS, the architecture and the package manager, and stops with a warning on a platform
   outside the table above.
2. **OS prerequisites.** On Linux and macOS it probes what GHC needs: a C compiler and linker, the GMP library
   (`-lgmp`), curl or wget, CA certificates and make. When one is missing, it shows the packages and the exact command
   and asks whether to run it. On yes it runs the verified apt or dnf package set through sudo; an unverified Linux
   distribution gets the failed probes and manual remedy instead of an automatic install. On macOS it runs
   `xcode-select --install`, whose dialog you complete before running agentctl again. On no it installs nothing and
   stops with the command for you to type.
3. **ghcup.** An existing ghcup at version 0.1.50.2 or later is used as it is, never replaced or upgraded. An older or
   non-answering ghcup produces a warning asking you to repair it; agentctl never replaces it. Only when ghcup is absent,
   agentctl downloads ghcup 0.2.6.2 from `downloads.haskell.org` and checks it against the SHA-256 published beside it;
   a mismatch installs nothing. It never runs ghcup's install script and never edits a shell startup file.
4. **GHC and cabal.** It installs GHC 9.12.4 and cabal 3.16.1.0 through ghcup without changing your default selection:
   the `ghc` and `cabal` you run, if any, stay the ones you had.
5. **The core binary.** It builds the core binary from the bundled sources and keeps it in its data directory, under a
   digest of those sources and the pins. The binary is never put on PATH; agentctl starts it for you.
6. **Your command** runs.

The first run takes time in steps 3 to 5: downloading and installing GHC, which occupies about 3.6 GB once installed,
fetching the Hackage package index and building the core binary's dependencies, which takes minutes. Those steps need
network access to `downloads.haskell.org` and `hackage.haskell.org`, and several gigabytes of free disk. Later runs find
the toolchain and the binary for the current digest and start at once. After an upgrade that changes the bundled sources
or pins, the next command builds one new binary under the new digest, and no binary is ever overwritten.

[The toolchain bootstrap](../engineering/toolchain_bootstrap.md) is the full contract for steps 1 to 4, and
[the binary build](../engineering/binary_build.md) for step 5.

## Runs Without a Terminal

agentctl never asks a question when no terminal is attached, as in a script or over `ssh host agentctl ...`. A missing
OS prerequisite is then installed only if you consent in advance with the global option `--assume-yes`, placed before
the command:

```console
$ agentctl --assume-yes list
```

With `--assume-yes` and no terminal, agentctl runs the package manager directly as root or through `sudo -n`, which
succeeds only where sudo needs no password. Without `--assume-yes` it installs nothing and stops with a warning that
lists the command to type. In a terminal, `--assume-yes` also uses root or `sudo -n`; it never supplies a password.
Without that option an interactive run asks for consent first, then ordinary sudo may ask for your password.

## Logging In

agentctl never logs an agent in. When `agentctl claude` or `agentctl codex` finds the agent logged out, it creates no
session and prints the command for you to type in your own shell:

```console
$ claude auth login
$ codex login
```

`claude auth login` signs in with a Claude subscription by default; `--console` uses Anthropic Console billing and
`--sso` single sign-on. On a headless or remote machine, codex signs in with `codex login --device-auth`. After logging
in, run the same agentctl command again.

agentctl never runs a login command, never types into an agent's REPL to log in, and refuses ARGS that would log in:
`agentctl claude auth login`, `agentctl claude setup-token`, a `/login` argument, and `agentctl codex login`. The refusal
prints the same remedy. Log in with the same environment you run agentctl from: a login made under a different
`CLAUDE_CONFIG_DIR` or `CODEX_HOME` is not the one agentctl checks.

Every session runs its agent with permission prompts bypassed: claude with `--dangerously-skip-permissions`, and codex
with `--dangerously-bypass-approvals-and-sandbox --no-daemon`. The first interactive start of claude in that mode shows
a warning dialog, and an agent may ask whether you trust a folder it has not seen. You answer both yourself, in the
session; agentctl never answers either.

## Upgrade

```console
$ pipx reinstall agentctl
```

`pipx reinstall` installs again from the spec you installed with, so an install from the git URL without a commit moves
to the repository's latest revision. To move a pinned install to another commit, install over it:

```console
$ pipx install --force 'agentctl @ git+https://github.com/<owner>/agentctl.git@<commit>'
```

The next command builds a new core binary if the upgrade changed the bundled sources or pins; ghcup, GHC and cabal are
reused as they are.

## Removal

There is no uninstall command. First stop `agentctl supervisor run` if it is running, and end each session you no
longer want with `agentctl stop NAME` while agentctl is still installed. Then uninstall the package and delete
agentctl's three per-user directories:

```console
$ pipx uninstall agentctl
$ rm -rf ~/.cache/agentctl ~/.local/share/agentctl ~/.local/state/agentctl
```

On Windows, in PowerShell, the second step is `Remove-Item -Recurse -Force "$env:LOCALAPPDATA\agentctl"`. These are the
default locations; when `XDG_CACHE_HOME`, `XDG_DATA_HOME` or `XDG_STATE_HOME` is set, delete `agentctl` under each one
instead ([files and state](../reference/files_and_state.md)). Deleting the state directory forgets adopted panes and the
watch set.

agentctl never removes anything it does not own, and these steps leave all of it in place:

- **ghcup, GHC and cabal**, which stay where ghcup keeps them. To reclaim their disk space, remove them with ghcup itself,
  for example `ghcup rm ghc 9.12.4`, and only if nothing else of yours uses that version.
- **The OS packages** it installed with your consent.
- **Your sessions**, which keep running on your tmux or psmux server.
- **The agents' credentials and configuration**, which belong to claude and codex.

## Related

- [troubleshooting.md](troubleshooting.md) — each warning a first run or a launch can print, and what to type.
- [files_and_state.md](../reference/files_and_state.md) — the default directories on each OS and what each file holds.
- [cli_reference.md](../reference/cli_reference.md) — every command, and the `--assume-yes` option.
- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — the contract behind the prerequisites, consent, ghcup and the pins.
- [launch_contract.md](../architecture/launch_contract.md) — what a launch checks and what it runs in the pane.
- [external_tool_facts.md](../reference/external_tool_facts.md) — the sources for the pipx, ghcup and agent facts used here.
