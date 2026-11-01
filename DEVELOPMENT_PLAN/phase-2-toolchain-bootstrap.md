# Phase 2 — Toolchain bootstrap

**Status**: Planned
**Depends on**: [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md)
**Host lane**: any-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R3, R4, R15

> **Purpose**: Make the Python layer provide GHC's OS prerequisites with consent, ghcup, and the pinned GHC and cabal,
> idempotently and without editing an rc file or changing the user's ghcup selection, and run that code path as
> check's `toolchain-ensure` step.

## Phase Objective

Provisioning is one pure function between two thin effectful edges: `src/agentctl/hostfacts.py` gathers the host as one
frozen value, `src/agentctl/bootstrap/plan.py` maps it to the ordered actions the host still needs, and
`bootstrap/prereqs.py`, `bootstrap/ghcup.py` and `bootstrap/toolchain.py` carry them out through
`src/agentctl/process.py`. [The toolchain bootstrap](../documents/engineering/toolchain_bootstrap.md) is the contract.

- **Pins.** GHC 9.12.4, cabal 3.16.1.0, ghcup 0.2.6.2 with the published SHA-256 of each of its five binaries, and the
  reuse floor 0.1.50.2, shipped as `src/agentctl/bootstrap/pins.toml` and held equal to `tests/oracles/pins.toml`.
- **Never.** No rc or profile edit, no bootstrap script, no `ghcup upgrade`, `ghcup set` or `ghcup run`, no GPG and no
  `--set`; cabal always gets `--no-set`, and GHC and cabal run by absolute path.
- **No test changes the user's toolchain.** Real ghcup runs only under a test-owned `GHCUP_INSTALL_BASE_PREFIX`, the
  spawn audit of Sprint 1.4 records and vetoes every sudo, package-manager, `xcode-select --install` and ghcup install
  spawn, and downloads come from a local HTTP server the test owns. Tests adapt to toolchain provenance alone.
- **The gate.** check gains preconditions P7 to P10 and the `toolchain-ensure` step, the code path a user's first
  command runs, which [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md)
  needs before any Haskell leg. Sprint 2.4 writes the clean-lane recipe that
  [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) runs.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R15 — GHC's OS prerequisites are probed, installed only with consent, and a non-interactive run never prompts | `tests/oracles/prerequisites.toml`, `tests/oracles/bootstrap_plan.toml` | value: the package sets and the consent outcomes per host facts; observer: the spawn audit records the vetoed package-manager argv after consent and none after a decline, beside the probe's own spawn, with a fresh nonce; owed: clean-container-acceptance; owed: macos-acceptance | `M-prereq-skip-consent`, `M-prereq-sudo-may-prompt`, `M-prereq-gmp-dropped` | `tests/unit/test_prereqs.py::test_package_sets_match_oracle`, `tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`, `tests/integration/test_prereqs_consent.py::test_non_tty_refuses_without_assume_yes` |
| R3 — an existing ghcup at or above the floor is reused, otherwise the pinned binary is downloaded and verified, and no rc file changes | `tests/oracles/pins.toml`, `tests/oracles/bootstrap_plan.toml` | value: the floor policy and each triple's pinned URL and digest; real: test-owned bytes through the real urllib into a test-owned prefix, and an existing ghcup kept byte for byte; observer: the spawn audit records only the reused ghcup's version check, with a fresh nonce; owed: clean-container-acceptance; owed: macos-acceptance; owed: windows-psmux-acceptance | `M-ghcup-skip-verify`, `M-ghcup-overwrite-existing`, `M-pins-digest-swapped` | `tests/integration/test_ghcup.py::test_sha_mismatch_refused_no_file`, `tests/integration/test_ghcup.py::test_present_ghcup_untouched`, `tests/unit/test_ghcup.py::test_pins_match_oracle` |
| R4 — GHC and cabal are installed at their pins through ghcup and the user's default selection never changes | `tests/oracles/pins.toml`, `tests/oracles/bootstrap_plan.toml` | value: no planned action carries `--set` and the cabal install carries `--no-set`; observer: the spawn audit records the vetoed install argv with a fresh nonce; real: the resolved ghc answers `--numeric-version` with its pin when the test runs it, and the default links are unchanged across `toolchain-ensure` | `M-boot-cabal-without-no-set`, `M-boot-spawn-adds-set`, `M-boot-links-unchecked` | `tests/unit/test_plan.py::test_plan_never_sets_default`, `tests/integration/test_toolchain.py::test_argv_never_sets`, `tests/integration/test_toolchain.py::test_default_links_unchanged_by_step`, `tests/integration/test_toolchain_real.py::test_resolved_ghc_reports_pin` |
| R1 — the build chain needs only pipx and its Python (contributing) | `tests/oracles/bootstrap_plan.toml` | value: the plan for a host with only python3 and pipx provisions the prerequisites, ghcup, GHC and cabal and never tmux, psmux, claude or codex, and the recipe's Stage A starts from exactly that host; owed: clean-container-acceptance | `M-boot-reinstall-present`, `M-boot-recipe-stage-a-root` | `tests/unit/test_plan.py::test_plan_oracle`, `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle` |

## Not Proven By This Gate

- A real download of the pinned ghcup from downloads.haskell.org, checked against its published SHA-256, on a host with no ghcup. — owed to [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md).
- A real apt install of the missing prerequisites through passwordless sudo after `--assume-yes`, and the build that follows. — owed to [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md).
- A first install of GHC and cabal on a pristine host, leaving no unversioned default link. — owed to [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md).
- The darwin ghcup binaries and the `xcode-select -p` probe on a Mac. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- The mingw64 `ghcup.exe` under `C:\ghcup\bin`, fetching GHC through the `curl.exe` that Windows ships. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Completing the Xcode Command Line Tools dialog, which only a person can do. — not proven by any phase.
- Installs through dnf or pacman, and the refusal on a real Arch Linux host; only the vetoed argv and the plan's values cover them. — not proven by any phase.
- A consent prompt answered at a real terminal, and a sudo that asks for a password. — not proven by any phase.
- Who built the ghcup bytes: the pin proves they equal what downloads.haskell.org published, not their authorship, and GPG verification is rejected. — not proven by any phase.
- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.

## Sprints

### Sprint 2.1: Host facts and the pure provisioning plan [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/hostfacts.py`, `src/agentctl/bootstrap/plan.py`, `src/agentctl/bootstrap/pins.toml`, `src/agentctl/check/preconditions.py`, `tests/oracles/bootstrap_plan.toml`, `tests/oracles/pins.toml`, `tests/mutants/bootstrap_plan.toml`
**Validation tests**: `tests/unit/test_plan.py::test_plan_oracle`, `tests/unit/test_plan.py::test_fully_provisioned_plan_is_empty`, `tests/unit/test_plan.py::test_plan_never_sets_default`, `tests/unit/test_ghcup.py::test_pins_match_oracle`, `tests/unit/test_hostfacts.py::test_ghcup_discovery_order`, `tests/unit/test_preconditions.py::test_toolchain_preconditions`
**Mutants**: `M-boot-reinstall-present`, `M-boot-replace-old-ghcup`, `M-boot-cabal-without-no-set`, `M-pins-digest-swapped`, `M-boot-ghcup-prefix-ignored`, `M-boot-windows-arm64-allowed`
**Closes**: none
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/quality_gate.md`, `documents/reference/external_tool_facts.md`

#### Objective

Represent the host as one frozen value, and the provisioning it needs as a pure plan, exhaustive over the supported
host states and empty once applied.

#### Deliverables

- `hostfacts.py` gathers OS family and architecture without spawning `uname`, the distribution and package manager from
  `/etc/os-release`, whether the run is root and interactive, the ghcup it finds with its `--numeric-version`, and
  whether the GHC and cabal paths recorded in `cache` answer with the pins; a provisioned host stops there.
- ghcup discovery honours `GHCUP_INSTALL_BASE_PREFIX` and `GHCUP_USE_XDG_DIRS`, then PATH, then `~/.ghcup/bin/ghcup` or
  `C:\ghcup\bin\ghcup.exe`.
- `plan.py` maps facts to ordered actions (download the pinned ghcup, install GHC, install cabal, resolve both) and
  never plans an action whose effect the facts show. A refusal with its remedy is a whole plan: Windows ARM64, which has
  no GHC, and a ghcup below 0.1.50.2 or one that does not answer, whose remedy is `ghcup upgrade`.
- No action renders `--set` or `ghcup set`, and the cabal install always carries `--no-set`.
- `tests/oracles/bootstrap_plan.toml` rows give facts, the exact actions they need and the facts those actions leave,
  over every supported platform, ghcup absent, below or at the floor, and each pin present or missing.
- `pins.toml` and `tests/oracles/pins.toml` hold each triple's ghcup URL and SHA-256, the floor and the GHC and cabal
  pins, with provenance in the published `SHA256SUMS` and decisions D-18 to D-21.
- Preconditions P7 (room for the toolchain and the cache), P8 (the pins installed, or downloads.haskell.org and
  hackage.haskell.org reachable) and P10 (a platform with a GHC bindist), each with its remedy.

#### Validation

1. Each facts row plans exactly its actions — `tests/unit/test_plan.py::test_plan_oracle`; fails when an action is
   missing, extra or reordered, or a below-floor ghcup plans a download; mutants `M-boot-reinstall-present`,
   `M-boot-replace-old-ghcup`.
2. The facts a row's actions leave plan nothing, against the control that the row's first plan is not empty —
   `tests/unit/test_plan.py::test_fully_provisioned_plan_is_empty`; fails when an answering pin is planned again;
   mutant `M-boot-reinstall-present`.
3. No planned argv carries `--set` and the cabal install carries `--no-set`, against the control that a bare host
   plans both installs — `tests/unit/test_plan.py::test_plan_never_sets_default`; fails when cabal lacks `--no-set`;
   mutant `M-boot-cabal-without-no-set`.
4. The package-data pins equal the oracle — `tests/unit/test_ghcup.py::test_pins_match_oracle`; fails when a version,
   URL or digest differs, two swapped digests included; mutant `M-pins-digest-swapped`.
5. ghcup is found by the environment, then PATH, then the default, over test-owned directories and constructed PATHs —
   `tests/unit/test_hostfacts.py::test_ghcup_discovery_order`; fails when `GHCUP_INSTALL_BASE_PREFIX` is ignored;
   mutant `M-boot-ghcup-prefix-ignored`.
6. P7, P8 and P10 pass and fail on constructed facts with their remedies —
   `tests/unit/test_preconditions.py::test_toolchain_preconditions`; fails when Windows ARM64 passes P10; mutant
   `M-boot-windows-arm64-allowed`.

#### Remaining Work

The whole sprint.

### Sprint 2.2: OS prerequisites with consent [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/prereqs.py`, `src/agentctl/hostfacts.py`, `src/agentctl/bootstrap/plan.py`, `src/agentctl/cli.py`, `src/agentctl/check/preconditions.py`, `tests/oracles/prerequisites.toml`, `tests/oracles/bootstrap_plan.toml`, `tests/mutants/prerequisites.toml`
**Validation tests**: `tests/unit/test_prereqs.py::test_package_sets_match_oracle`, `tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`, `tests/integration/test_prereqs_consent.py::test_accepted_runs_exact_argv`, `tests/integration/test_prereqs_consent.py::test_non_tty_refuses_without_assume_yes`, `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`, `tests/unit/test_preconditions.py::test_prerequisite_precondition`
**Mutants**: `M-prereq-skip-consent`, `M-prereq-sudo-may-prompt`, `M-prereq-prompt-without-tty`, `M-prereq-gmp-dropped`, `M-prereq-probe-ignores-link`
**Closes**: R15
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/quality_gate.md`, `documents/operations/installation.md`, `documents/operations/troubleshooting.md`, `documents/reference/cli_reference.md`

#### Objective

Probe GHC's OS prerequisites, install a missing set only with consent, and never prompt in a non-interactive run.

#### Deliverables

- Linux probes: `cc` links a one-line C program against `-lgmp` in a temp dir, curl or wget resolves, the CA store that
  Python's `ssl` default verify paths name exists, and make resolves; macOS probes `xcode-select -p`; Windows has no
  probe. libffi is not probed, since GHC 9.12.4 bundles it (D-21). Host facts gain the results and `--assume-yes`.
- `tests/oracles/prerequisites.toml` holds each host's set and argv (apt on Ubuntu 23 or later and Debian 13 or later,
  dnf on Fedora) from ghcup's requirement lists less libffi; apt runs `apt-get update`, then `apt-get install -y`. A
  host with no verified row, Arch Linux included, gets a refusal naming the failed probes.
- A failed probe makes the plan install the whole set in one run and probe again; a probe still failing is a typed
  error naming it, never a second install.
- Consent: the global option `agentctl --assume-yes`, which click parses and never forwards, consents with privilege
  through `sudo -n` or as root; an interactive run without it shows the commands and asks `[y/N]` on stderr, then uses
  sudo; a non-interactive run without it, check included, is a refusal that spawns nothing, prints the commands for the
  user to type and exits non-zero.
- On macOS, consent runs `xcode-select --install`, then agentctl exits non-zero, asking the user to finish the dialog.
- Precondition P9: the prerequisites are present, or `--assume-yes` was given as root or with passwordless sudo.
- Under the suite the spawn audit vetoes and records every sudo, package-manager and `xcode-select --install` spawn,
  and records the probe's compiler spawn without vetoing it.

#### Validation

1. Each host's set and argv equal their oracle row — `tests/unit/test_prereqs.py::test_package_sets_match_oracle`; fails
   when an apt set loses `libgmp-dev` or gains a libffi package; mutant `M-prereq-gmp-dropped`.
2. A declined prompt records no package-manager spawn beside the recorded probe spawn that shows the audit was live —
   `tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`; fails when a decline still runs apt;
   mutant `M-prereq-skip-consent`.
3. An accepted prompt records exactly the row's sudo and apt-get argv, in order, with the observer's nonce —
   `tests/integration/test_prereqs_consent.py::test_accepted_runs_exact_argv`; fails when the argv differs; mutant
   `M-prereq-gmp-dropped`.
4. Without a terminal or `--assume-yes` the run refuses, spawns nothing and names the commands, while the same run with
   `--assume-yes` records `sudo -n` — `tests/integration/test_prereqs_consent.py::test_non_tty_refuses_without_assume_yes`;
   fails when the run prompts or the flag yields a sudo that may prompt; mutants `M-prereq-prompt-without-tty`,
   `M-prereq-sudo-may-prompt`.
5. The probe agrees with the test's own link against `-lgmp`, and reports the compiler missing under a constructed PATH
   without one — `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`; fails when the probe
   only checks that `cc` resolves; mutant `M-prereq-probe-ignores-link`.
6. P9 passes and fails on constructed facts — `tests/unit/test_preconditions.py::test_prerequisite_precondition`; fails
   when missing prerequisites pass without `--assume-yes`; mutant `M-prereq-skip-consent`.

#### Remaining Work

The whole sprint.

### Sprint 2.3: ghcup reuse or pinned download [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/ghcup.py`, `tests/mutants/ghcup.toml`
**Validation tests**: `tests/integration/test_ghcup.py::test_present_ghcup_untouched`, `tests/integration/test_ghcup.py::test_sha_mismatch_refused_no_file`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_ghcup.py::test_no_rc_file_written`
**Mutants**: `M-ghcup-overwrite-existing`, `M-ghcup-skip-verify`, `M-ghcup-nonatomic-write`, `M-ghcup-edits-rc`
**Closes**: R3
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/operations/troubleshooting.md`, `documents/reference/external_tool_facts.md`

#### Objective

Provide ghcup as the host already has it, or as the pinned, SHA-256-verified binary, touching nothing else the user
owns.

#### Deliverables

- A found ghcup at or above 0.1.50.2 is used as it is, never replaced or upgraded; one below the floor or one that
  does not answer is the refusal whose remedy, `ghcup upgrade`, the user types.
- With no ghcup, urllib fetches `https://downloads.haskell.org/~ghcup/0.2.6.2/<triple>-ghcup-0.2.6.2`
  (`x86_64-mingw64-ghcup-0.2.6.2.exe` on Windows) into a temporary file in the destination directory and hashes it
  there; `SHA256SUMS` is never fetched at run time.
- Only a SHA-256 match is made executable (0755 on POSIX) and renamed onto `~/.ghcup/bin/ghcup`,
  `$GHCUP_INSTALL_BASE_PREFIX/.ghcup/bin/ghcup` or `C:\ghcup\bin\ghcup.exe`; a mismatch or a truncated body deletes the
  temporary file and leaves nothing at the final path.
- The download takes the pin record as a value, so a test points it at its own server with no test-only branch.
- Every ghcup spawn sets `GHCUP_SKIP_UPDATE_CHECK`; nothing edits an rc or profile file or runs the bootstrap script.
- Tests run ghcup in a test-owned `GHCUP_INSTALL_BASE_PREFIX` with `HOME` redirected, since every ghcup command but
  `--help` and `--version` rewrites its log, against a local HTTP server that logs every request.

#### Validation

1. A copy of the host's resolved ghcup in a test-owned prefix is reused: the server, live by the test's own request,
   logs no download, the audit records only its `--numeric-version`, and its bytes are unchanged —
   `tests/integration/test_ghcup.py::test_present_ghcup_untouched`; fails when agentctl downloads over it; mutant
   `M-ghcup-overwrite-existing`.
2. Correct bytes install with mode 0755, while corrupted bytes from the same server leave no final or temporary file —
   `tests/integration/test_ghcup.py::test_sha_mismatch_refused_no_file`; fails when the digest is not compared; mutant
   `M-ghcup-skip-verify`.
3. A truncated body leaves nothing at the final path, against the control that the complete body installs —
   `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`; fails when bytes land in place; mutant
   `M-ghcup-nonatomic-write`.
4. An install under a redirected `HOME` leaves every rc and profile file byte-identical, against the control that ghcup
   was installed — `tests/integration/test_ghcup.py::test_no_rc_file_written`; fails when a PATH line is appended to
   `.bashrc`; mutant `M-ghcup-edits-rc`.

#### Remaining Work

The whole sprint.

### Sprint 2.4: Pinned GHC and cabal, and the clean-lane recipe [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/toolchain.py`, `src/agentctl/check/steps.py`, `tests/harness/host.py`, `tests/lanes/clean-host.Dockerfile`, `tests/oracles/bootstrap_plan.toml`, `tests/mutants/toolchain.toml`
**Validation tests**: `tests/integration/test_toolchain.py::test_argv_never_sets`, `tests/integration/test_toolchain.py::test_whereis_paths_used_verbatim`, `tests/integration/test_toolchain.py::test_default_links_unchanged_by_step`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`, `tests/integration/test_toolchain_real.py::test_resolved_ghc_reports_pin`, `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/e2e/test_fresh_bootstrap.py::test_no_default_links`, `tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins`
**Mutants**: `M-boot-spawn-adds-set`, `M-boot-ghc-from-path`, `M-boot-links-unchecked`, `M-boot-ghcup-on-warm-run`, `M-boot-recipe-stage-a-root`
**Closes**: R4
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/quality_gate.md`, `documents/engineering/testing.md`, `documents/reference/files_and_state.md`

#### Objective

Install GHC 9.12.4 and cabal 3.16.1.0 without changing the user's selection, resolve them by absolute path, run that
code as check's `toolchain-ensure` step, and write the recipe of the clean-container lane.

#### Deliverables

- `toolchain.py` runs `<ghcup> install ghc 9.12.4` and `<ghcup> install cabal 3.16.1.0 --no-set` for a missing pin
  (exit 0 when installed, 3 on failure), then `whereis` for each (exit 30 when missing), after the install because
  ghcup handles a missing tool there only from 0.2.5.0.
- A resolved path must answer `--numeric-version` with its pin before it is recorded in `cache`; later uses run the
  recorded paths verbatim, never `ghc` or `cabal` from PATH, and a warm run repeats only those two checks.
- The `toolchain-ensure` step runs this code path between the `ty` and `fourmolu` legs, reads ghcup's unversioned
  `ghc` and `cabal` entries before and after, comparing link targets or bytes, and fails on any change.
- `tests/harness/host.py` observes toolchain provenance: agentctl-installed when the pre-bootstrap record that only the
  recipe writes is present, the user's otherwise.
- `tests/lanes/clean-host.Dockerfile` runs as a non-root user with NOPASSWD sudo. Stage A: `ubuntu:24.04` with
  `python3`, `pipx` and `sudo` only, the copied tree and the pre-bootstrap record, a `pipx install` of the copy
  without `--editable`, and `agentctl --assume-yes list`, required to end with the multiplexer-missing warning and
  status. Stage B adds tmux, git and the native agents, then `pipx install --force --editable '.[dev]'` and a plain
  `agentctl check`; the expected stages are rows of `tests/oracles/bootstrap_plan.toml`.
- `tests/e2e/test_fresh_bootstrap.py` reads filesystem facts, never a journal agentctl wrote: for an agentctl-installed
  toolchain, ghcup's SHA-256, no unversioned `ghc` or `cabal`, and `whereis` paths that report the pins; for the user's,
  a ghcup at or above the floor and no second ghcup written.

#### Validation

1. With nothing recorded the first spawn the audit vetoes is `install ghc 9.12.4`, and with GHC recorded it is
   `install cabal 3.16.1.0 --no-set` — `tests/integration/test_toolchain.py::test_argv_never_sets`; fails when an argv
   carries `--set` or cabal lacks `--no-set`; mutant `M-boot-spawn-adds-set`.
2. Every later use runs the recorded paths, also under a constructed PATH holding neither `ghc` nor `cabal` —
   `tests/integration/test_toolchain.py::test_whereis_paths_used_verbatim`; fails when ghc comes from PATH; mutant
   `M-boot-ghc-from-path`.
3. A default `ghc` link retargeted between the step's readings fails it, while unchanged links pass —
   `tests/integration/test_toolchain.py::test_default_links_unchanged_by_step`; fails when the step compares nothing;
   mutant `M-boot-links-unchecked`.
4. A warm run records the two `--numeric-version` spawns (the positive control) and no ghcup spawn —
   `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`; fails when a warm run calls
   ghcup; mutant `M-boot-ghcup-on-warm-run`.
5. The test runs the resolved ghc and cabal itself and reads 9.12.4 and 3.16.1.0 —
   `tests/integration/test_toolchain_real.py::test_resolved_ghc_reports_pin`; fails when another version answers; no
   mutant: the subject's own report is never consulted.
6. The recipe's stages equal their rows — `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`;
   fails when Stage A gains git, a compiler or tmux, a stage runs as root, or a stage's command changes; mutant
   `M-boot-recipe-stage-a-root`.
7. An agentctl-installed ghcup carries its triple's pinned SHA-256, and a user's is the one the run resolved —
   `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`; fails when the bytes differ from the pin; no
   mutant: the branch depends on the host, so no mutant names it.
8. An agentctl-installed toolchain has no unversioned `ghc` or `cabal` while the versioned entries resolve —
   `tests/e2e/test_fresh_bootstrap.py::test_no_default_links`; fails when a pin became the default; no mutant, as in 7.
9. `whereis` gives existing paths whose `--numeric-version` is the pin —
   `tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins`; fails when a pin is missing; no mutant, as in 7.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 2.1–2.4.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/python_haskell_boundary.md` — the bootstrap steps Python owns and the spawns they add: ghcup,
  the C compiler probe, and sudo with the package manager.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — host facts, the plan and its idempotence law, the probes and package
  sets, consent, ghcup reuse and the pinned download, the GHC and cabal pins, and the clean-lane recipe.
- `documents/engineering/quality_gate.md` — preconditions P7 to P10 and the `toolchain-ensure` step.
- `documents/engineering/testing.md` — toolchain provenance as an allowed adaptation, the recipe's pre-bootstrap
  record, and the audit veto of sudo, package-manager and ghcup install spawns.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — the first run's provisioning, consent and `--assume-yes`.
- `documents/operations/troubleshooting.md` — the prerequisite refusal, a ghcup below the floor and an unsupported
  platform, each with what the user types.
- `documents/reference/cli_reference.md` — the global `--assume-yes` option.
- `documents/reference/external_tool_facts.md` — the ghcup URLs and SHA-256 values, the `install` and `whereis` exit
  codes, and the bootstrap-script behaviour agentctl avoids.
- `documents/reference/files_and_state.md` — the recorded GHC and cabal paths in `cache`.

**Cross-references to add:**

- `documents/engineering/toolchain_bootstrap.md` — links `documents/engineering/binary_build.md` for what the resolved
  toolchain builds.
