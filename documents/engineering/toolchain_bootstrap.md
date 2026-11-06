# Toolchain Bootstrap

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Toolchain bootstrap](../../DEVELOPMENT_PLAN/phase-2-toolchain-bootstrap.md)

> **Purpose**: State how the Python layer provides GHC's OS prerequisites with consent, ghcup, and the pinned GHC and cabal, idempotently and without changing anything the user has selected.

This page is the prose home of R3, R4 and R15 in the [requirements table](../../DEVELOPMENT_PLAN/00-overview.md#requirements).
Their data homes are `tests/oracles/pins.toml` and `tests/oracles/prerequisites.toml`, and
`tests/oracles/bootstrap_plan.toml` holds the provisioning plan. The pins ship as package data in
`src/agentctl/bootstrap/pins.toml`, which `tests/unit/test_ghcup.py::test_pins_match_oracle` holds equal to the
oracle. Every version, URL, flag and exit code below is recorded, with its verification, in
[external tool facts](../reference/external_tool_facts.md).

## The Provisioning Plan

Provisioning is one pure function between two thin effectful edges.

1. **Host facts.** `src/agentctl/hostfacts.py` gathers one frozen value: OS family and architecture, the
   distribution and its package manager (from `/etc/os-release` on Linux), whether the run is root, whether it
   is interactive, whether `--assume-yes` was given, the result of each prerequisite probe, the ghcup it finds
   with that ghcup's `--numeric-version`, and whether the pinned GHC and cabal answer at their recorded paths.
2. **The plan.** `src/agentctl/bootstrap/plan.py` maps the facts to an ordered tuple of actions: install the
   prerequisites (or request the Xcode Command Line Tools), download the pinned ghcup, install GHC, install
   cabal, resolve both paths. A refusal, carrying its reason and the remedy the user types, is a whole plan on
   its own. The plan never contains an action whose effect the facts already show.
3. **Apply.** `bootstrap/prereqs.py`, `bootstrap/ghcup.py` and `bootstrap/toolchain.py` carry out the actions
   in order, spawning only through `src/agentctl/process.py`, and stop at the first failure with a typed error.

Cold host facts gain the results of the prerequisite probes through `bootstrap/prereqs.py::observe`; the result is
another frozen value for the pure planner. Warm facts remain unchanged without a prerequisite probe
(`tests/unit/test_prereqs.py::test_observation_completes_cold_facts_and_preserves_warm_pins`).

Gathering stops early on a provisioned host. When the GHC and cabal paths recorded by the last resolution,
kept as absolute strings in `cache/toolchain-paths.toml`, answer `--numeric-version` with the pins, the facts say so and nothing
else is observed: a warm run spawns those two version checks and no ghcup, probe, package manager or network
request (`tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`). Check's
precondition P9 probes the prerequisites on its own account, because its build legs need them.

**The idempotence law.** Each row of `tests/oracles/bootstrap_plan.toml` gives host facts, the exact ordered
actions they require, and the facts of the host those actions leave; the plan of the first must equal the
actions, and the plan of the last must be empty. The rows cover the finite space exhaustively: every platform,
prerequisites present or missing, ghcup absent, below the floor or at or above it, and each pin present or
missing. `tests/unit/test_plan.py::test_plan_oracle` fails on a missing, extra or reordered action, and
`tests/unit/test_plan.py::test_fully_provisioned_plan_is_empty` on any action for a provisioned host.

The same plan runs in two places: the first command that needs a binary the current digest has not built
([binary build](binary_build.md)), and the `toolchain-ensure` step of
[the quality gate](quality_gate.md#check-steps), which runs this code path rather than a copy of it.

## OS Prerequisites

GHC's OS prerequisites are probed, never assumed. On Linux the probes are:

| Probe | Satisfied when |
|---|---|
| C compiler and linker, with `-lgmp` | `cc` resolves on PATH and links a one-line C program against `-lgmp` in a temp dir |
| curl or wget | either resolves on PATH; ghcup has no internal downloader and fetches GHC and cabal with one of them |
| CA certificates | the CA file or directory named by Python's `ssl` default verify paths exists, so the urllib download of ghcup can verify TLS |
| make | `make` resolves on PATH; GHC bindists install through configure and make |

On macOS the one probe is `xcode-select -p`, which succeeds once the Xcode Command Line Tools are installed.
Windows has no probe and no package-manager action: ghcup downloads with the `curl.exe` that Windows 10 and
later ship, and MSYS2 is needed only by Haskell packages that ship configure scripts, which the Cabal project
never depends on ([code standards](code_standards.md)).

libffi is not probed: GHC 9.12.4 bundles it ([decision D-21](../../DEVELOPMENT_PLAN/rationale.md#decisions)),
so the `libffi-dev` and `libffi8` entries of ghcup's own requirement lists are dropped from every set below.
When any probe fails, the plan installs the host's whole set in one installation transaction and probes again; a
probe that still fails is a typed error naming it, never a second install.

| Host | Package manager | Packages installed after consent |
|---|---|---|
| Ubuntu 23 or later | apt | `build-essential curl libgmp-dev libgmp10 libncurses-dev pkg-config` |
| Debian 13 or later | apt | `build-essential curl libgmp-dev libgmp10 libncurses-dev pkg-config libncurses6 libtinfo6` |
| Fedora | dnf | `gcc gcc-c++ gmp gmp-devel make ncurses ncurses-compat-libs xz perl` |
| Arch Linux | pacman | no verified set (see below) |
| macOS | none | `xcode-select --install`, a dialog only a person can complete |
| Windows | none | nothing |

The apt actions are `apt-get update` then `apt-get install -y` with the set, so a host with empty or stale
package lists still resolves it. The apt and dnf argv, consent outcomes and Arch refusal are rows of
`tests/oracles/prerequisites.toml`, anchored to versioned tool facts, the request and D-21.
The verified facts give no Arch package set, only ghcup's generic Linux list
(`curl g++ gcc gmp make ncurses realpath xz-utils pkg-config`), whose names are not package names on every
distribution. A host without a verified row, Arch Linux included, therefore gets a refusal when a probe fails:
it names the failed probes and that generic list, and runs no package manager.

## Consent

Running a package manager changes the host, so it happens only with consent, and the way consent is given
decides how privilege is obtained.

| Run | Consent | Privilege |
|---|---|---|
| Started as `agentctl --assume-yes <command>`, interactive or not | the flag | `sudo -n`, which fails rather than prompts; nothing as root |
| Interactive, without the flag: standard input and standard error are terminals | one `[y/N]` prompt on standard error showing the exact commands; only `y` or `yes`, ignoring case and surrounding whitespace, consents | `sudo`, which may ask for the user's password; nothing as root |
| Non-interactive without the flag, `agentctl check` included | none, because nothing may prompt | none: the plan is a refusal |

A decline or refusal spawns nothing, prints the exact commands for the user to type, and exits non-zero; a
`sudo -n` that needs a password is reported the same way. On macOS, consent runs `xcode-select --install`,
which needs no sudo and opens the dialog; agentctl then exits non-zero and asks the user to finish the dialog
and run the command again. `agentctl check` never prompts or opens that dialog: P9 needs existing Command Line
Tools on macOS. On Linux, P9 holds when the probes are ready or a verified package set is installable after
`--assume-yes` as root or with passwordless sudo; the privilege observation is `sudo -n true`
([preconditions](quality_gate.md#preconditions)).

```console
$ agentctl claude
agentctl: GHC needs build tools this host lacks: the C compiler and make.
agentctl: with your consent agentctl runs:
agentctl:   sudo apt-get update
agentctl:   sudo apt-get install -y build-essential curl libgmp-dev libgmp10 libncurses-dev pkg-config
agentctl: run them now? [y/N] n
agentctl: nothing was installed; run the commands above yourself, then run agentctl again.
```

No test runs a package manager, sudo or `xcode-select --install`. The spawn audit records each such spawn's argv
and vetoes it, records the probe's compiler spawn without vetoing it, and tests answer the prompt through click's
`CliRunner` input. A declined prompt must record no package-manager
spawn beside the probe spawn that shows the audit was live
(`tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`). Each approved command is attempted
individually under the hook and compared with its oracle argv and nonce, while a batch stops at its first veto
(`tests/integration/test_prereqs_consent.py::test_accepted_runs_exact_argv`),
and a non-interactive run without the flag must refuse
(`tests/integration/test_prereqs_consent.py::test_non_tty_refuses_without_assume_yes`).
The actors' PATHs contain no installer binaries, so removing a veto still cannot reach the host's package manager.
Successful command ordering and the single post-install probe are value controls; the actual apt sequence is owed
to [Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md).
The actual click dispatcher passes the global option to the check child
(`tests/integration/test_prereqs_consent.py::test_global_assume_yes_reaches_check`).

## ghcup

**Reuse.** agentctl looks for ghcup where the user's environment says it lives: first the location
`GHCUP_INSTALL_BASE_PREFIX` or `GHCUP_USE_XDG_DIRS` names, when set; then `ghcup` on PATH; then the default,
`~/.ghcup/bin/ghcup` or `C:\ghcup\bin\ghcup.exe` (`tests/unit/test_hostfacts.py::test_ghcup_discovery_order`).
On Unix, the presence of `GHCUP_USE_XDG_DIRS`, an empty value included, selects `XDG_BIN_HOME/ghcup` or
`~/.local/bin/ghcup` ahead of the ordinary prefix. Windows ignores XDG and uses `<prefix>\ghcup\bin\ghcup.exe`,
with `C:\` as its default prefix. An absent environment-selected file still permits PATH and default discovery.
A ghcup whose `--numeric-version` is at or above 0.1.50.2 is
reused as it is, never replaced or upgraded ([decision D-18](../../DEVELOPMENT_PLAN/rationale.md#decisions)),
because it is a tool the user owns. One below the floor, or one that does not answer, is a refusal whose remedy
is `ghcup upgrade`, typed by the user. `tests/integration/test_ghcup.py::test_present_ghcup_untouched` requires
an existing ghcup to cause no download and to keep its bytes.

**The pinned download.** When no ghcup exists, agentctl downloads ghcup 0.2.6.2 with Python's urllib and checks
it against the SHA-256 compiled into `pins.toml`, whose provenance is the `SHA256SUMS` file published beside the
binaries; that file is never fetched at run time.

| Host | URL | SHA-256 |
|---|---|---|
| Linux x86_64 | `https://downloads.haskell.org/~ghcup/0.2.6.2/x86_64-linux-ghcup-0.2.6.2` | `9ed5da5449b48043a0d17e767c05d2ef585e25a639bb934329496c6d2fad9cf8` |
| Linux aarch64 | `https://downloads.haskell.org/~ghcup/0.2.6.2/aarch64-linux-ghcup-0.2.6.2` | `65a5f05120288ee4f1a81d28825374b6af317456a351a586adfce90c6dc29e3b` |
| macOS x86_64 | `https://downloads.haskell.org/~ghcup/0.2.6.2/x86_64-apple-darwin-ghcup-0.2.6.2` | `e713b9f213d7da01fa4791f39e04e0892b5c5f082d5a38712281f529bab88e56` |
| macOS arm64 | `https://downloads.haskell.org/~ghcup/0.2.6.2/aarch64-apple-darwin-ghcup-0.2.6.2` | `4e521e008fe0813db6db4b91cfeebd0c44c80c68afb458ea32a1c94cf5c7cc1d` |
| Windows x86_64 | `https://downloads.haskell.org/~ghcup/0.2.6.2/x86_64-mingw64-ghcup-0.2.6.2.exe` | `94da902a2853b1de1df509d04da900a05258480759efdb4f654e66956b6f30db` |

The bytes go to a mode-0600 file in a private temporary directory under the destination directory and are hashed
as they are written in bounded chunks. An advertised Content-Length must equal the received byte count. Only a match is made
executable (mode 0755 on POSIX) and renamed onto the final path, `~/.ghcup/bin/ghcup`
(`$GHCUP_INSTALL_BASE_PREFIX/.ghcup/bin/ghcup` when the variable is set) or `C:\ghcup\bin\ghcup.exe`. A digest
mismatch or a truncated body deletes the temporary file and leaves nothing at the final path. A local HTTP
server owned by the test serves correct, corrupted and truncated bytes into a test-owned
`GHCUP_INSTALL_BASE_PREFIX` (`tests/integration/test_ghcup.py::test_sha_mismatch_refused_no_file`,
`tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`).

An occupied destination is refused before downloading and checked again before publication, preserving a file that
appears while bytes are being received. Failed requests, malformed lengths, unsupported responses and filesystem
errors are typed failures; temporary artifacts are removed on all those paths
(`tests/integration/test_ghcup.py::test_download_errors_are_typed`,
`tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`).
The HTTP connection adapter closes error responses before propagating their exception into the typed download
failure, releasing the error body's resource (`tests/integration/test_ghcup.py::test_download_errors_are_typed`).

**Never.** agentctl edits no shell rc or profile file, so the installed ghcup is not on PATH and is always
invoked by absolute path (`tests/integration/test_ghcup.py::test_no_rc_file_written`). It never runs
`ghcup upgrade`, `ghcup set` or `ghcup run`, never verifies with GPG (a second host dependency against R1),
and sets `GHCUP_SKIP_UPDATE_CHECK` on every ghcup it spawns.

```text
WRONG  curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | BOOTSTRAP_HASKELL_ADJUST_BASHRC=0 sh
RIGHT  urllib fetches the pinned 0.2.6.2 binary, and only a SHA-256 match reaches ~/.ghcup/bin/ghcup
```

The WRONG form runs a script that verifies no checksum, treats any non-empty `BOOTSTRAP_HASKELL_ADJUST_BASHRC`,
`0` included, as permission to edit rc files, and outside minimal mode runs `ghcup set ghc`, changing the
user's default compiler.

## GHC and cabal

The pins are GHC 9.12.4 and cabal 3.16.1.0. They are installed through the ghcup that the previous section
found or placed, always with the tool subcommand:

```text
<ghcup> install ghc 9.12.4
<ghcup> install cabal 3.16.1.0 --no-set
<ghcup> whereis ghc 9.12.4
<ghcup> whereis cabal 3.16.1.0
```

- **No set flag for GHC, `--no-set` for cabal.** ghcup's default is not to set the default for ghc and to set
  it for every other tool, so these two argv leave the user's `ghc` and `cabal` exactly as they were. Neither
  argv ever carries `--set`, and no `ghcup set` runs
  (`tests/unit/test_plan.py::test_plan_never_sets_default`; the spawn audit records the real argv in
  `tests/integration/test_toolchain.py::test_argv_never_sets`).
- **Idempotent installs.** `ghcup install` exits 0 for a version already installed and 3 on failure, so the
  install actions converge without reinstalling anything.
- **Resolution after install.** `ghcup whereis` prints a canonical absolute path and exits 30 when the version
  is missing. It runs only after the install, because its handling of a tool that is not installed was fixed
  only in ghcup 0.2.5.0, above the reuse floor. Every later use invokes those paths verbatim, never `ghc` or
  `cabal` from PATH (`tests/integration/test_toolchain.py::test_whereis_paths_used_verbatim`).
- **Verification.** Each resolved path must answer `--numeric-version` with its pin before it is recorded, and
  a warm run repeats exactly that check instead of calling ghcup. The test runs the resolved `ghc` itself and
  compares the answer with the oracle (`tests/integration/test_toolchain_real.py::test_resolved_ghc_reports_pin`).
- **The user's default links.** The `toolchain-ensure` step reads ghcup's unversioned `ghc` and `cabal` entries
  before and after this code path runs, comparing each link target, or its bytes where it is not a link, and
  check fails if either changed (`tests/integration/test_toolchain.py::test_default_links_unchanged_by_step`).

`bootstrap/toolchain.py` interprets the planner's actions with explicit command and prerequisite adapters. It stops
at the first failure and publishes `cache/toolchain-paths.toml` only after both absolute paths answer their pins.
The record is written with mode 0600 in a private temporary directory, then renamed into place. A failed command,
relative whereis result or wrong version leaves the existing record intact
(`tests/unit/test_toolchain.py::test_apply_sequence_and_verified_record`,
`tests/unit/test_toolchain.py::test_apply_refuses_partial_or_failed_resolution`,
`tests/unit/test_toolchain.py::test_record_atomicity_and_storage_failure`).

Selection checks cover the configured ghcup binary directory and the discovered executable's directory, including
Windows `.exe` entries. They compare after a typed provisioning failure as well as after success; an unreadable
entry is a failure (`tests/integration/test_toolchain.py::test_default_observation_failures`).

## The Clean-Lane Recipe

`tests/lanes/clean-host.Dockerfile` is the recipe of the `clean-container` lane, which
[Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md) runs on a gate
host with docker; neither agentctl nor check invokes docker. Both stages run as a non-root user with NOPASSWD
sudo, because claude refuses its bypass flag as root and because a root run would never exercise sudo.

- **Stage A** starts from `ubuntu:24.04` with only `python3`, `pipx` and `sudo` installed. It copies the tree,
  writes the pre-bootstrap record (the recipe's own statement that the host holds no ghcup, GHC or cabal, which
  agentctl never writes), runs `pipx install` on the copy without `--editable`, then `agentctl --assume-yes list`.
  That one command must
  install the apt set through `sudo -n`, download and verify the pinned ghcup, install GHC and cabal without
  setting either, build and publish the binary, and end with the multiplexer-missing warning and a non-zero
  exit, because Stage A has no tmux. The recipe requires that exit status, so a Stage A that ends any other way
  stops the build before Stage B exists.
- **Stage B** adds tmux, git and the agents' official native installers, installs the checkout with
  `pipx install --force --editable '.[dev]'`, and runs plain `agentctl check`, so the gate literal never
  changes.

The closing agent launches Stage B with `docker run --init`. Docker's init process reaps orphaned native children,
so the gate can require every observer PID to disappear after teardown, as it does on a native host. The image's
command remains `agentctl check`; child reaping is part of the container's execution environment.

The clean recipe and the gate use `tests/harness/host.py` with its standard-library-only
`tests/harness/bootstrap_origin.py` helper to record observed absence of ghcup, GHC and cabal before the first
provisioning command. This happens automatically when the observed PATH and configured prefix contain none of
those tools. This harness-owned pre-bootstrap record
contains the host, the probed prefix and a fresh nonce; the provisioning code never writes it. Existing native toolchains receive
no absence record and confirm reuse. The harness calls the toolchain agentctl-installed only with that initial
absence record and matching current prefix, and the user's otherwise; that provenance is the only thing
`tests/e2e/test_fresh_bootstrap.py` branches on. For an agentctl-installed toolchain it reads the resulting filesystem facts, never a journal
agentctl wrote: ghcup under the recorded prefix's `bin` directory (`ghcup.exe` on Windows) carries the pinned SHA-256 for its triple
(`tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`), that `bin` directory holds no unversioned `ghc`
or `cabal` while the versioned entries resolve (`tests/e2e/test_fresh_bootstrap.py::test_no_default_links`), and
`ghcup whereis` gives both pins, each answering `--numeric-version` as pinned when the test runs it
(`tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins`). For the user's toolchain it asserts the
reuse contract instead: the run resolved the user's ghcup, at or above the floor, and wrote no second one. A
value test reads the Dockerfile itself, so a recipe that installs git, a compiler or tmux in Stage A, runs as
root, or changes either stage's command fails on every host
(`tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`). The absence witness is
`state/pre-bootstrap.json`; a mismatched prefix is refused, and an existing witness is never rewritten
(`tests/integration/test_bootstrap_origin.py::test_absence_record_precedes_first_file`,
`tests/integration/test_bootstrap_origin.py::test_existing_tool_and_mismatched_witness`). A partial or previously
unobserved toolchain receives no clean-host claim: an initially absent ghcup still has to match its download pin,
and an existing ghcup has to preserve its independently observed bytes.

The current run's `bootstrap-host.json` records the binary and selection entries before provisioning. The
clean-container lane additionally requires Docker's filesystem marker and the recipe's Stage A absence observation;
native absence alone does not qualify it. Stage B's `CMD` runs a fresh plain `agentctl check` when the container starts.

## What Each Step Proves

| Step | Proven by every check run | Owed or not proven |
|---|---|---|
| Host facts and the plan | `value`: every `bootstrap_plan.toml` row and the idempotence law | none |
| Prerequisites and consent | `value`: the per-host sets and argv (`tests/unit/test_prereqs.py::test_package_sets_match_oracle`); `observer`: the audited argv after `y`, none after `n`; `real`: the probe agrees with the test's own link test (`tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`) | A real apt install after consent is owed to [Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md); real dnf and pacman installs and completing the Xcode dialog are proven by no phase |
| ghcup | `value`: the triple table; `real`: test-owned bytes through the real urllib and filesystem, and the reuse of an existing ghcup untouched | The real download from downloads.haskell.org is owed to [Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md), the darwin binaries to [macOS acceptance](../../DEVELOPMENT_PLAN/phase-13-macos-acceptance.md), and the mingw64 binary in `C:\ghcup\bin` to [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md) |
| GHC and cabal | `value`: argv with no `--set` and with cabal's `--no-set`; `observer`: the audited argv; `real`: the resolved pins answer `--numeric-version`, and the user's default links are unchanged | A first install on a pristine host is confirmed, as part of R1, by [Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md) |

## Related

- [binary_build.md](binary_build.md) — what the resolved GHC and cabal build, and where the binary goes.
- [quality_gate.md](quality_gate.md#check-steps) — the `toolchain-ensure` step and precondition P9 that run this path.
- [testing.md](testing.md#observers-and-nonces) — how the spawn audit observes and vetoes package-manager spawns.
- [external_tool_facts.md](../reference/external_tool_facts.md) — the verified ghcup, GHC, cabal and package facts cited here.
- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — why bootstrap is Python's and the binary never calls ghcup.
- [installation.md](../operations/installation.md) — what a user sees on the first run and how consent is given.
- [rationale.md](../../DEVELOPMENT_PLAN/rationale.md#rejected-alternatives) — why the bootstrap script, `--set`, `ghcup run` and GPG are rejected.
- [Toolchain bootstrap](../../DEVELOPMENT_PLAN/phase-2-toolchain-bootstrap.md) — the phase that builds this contract.
