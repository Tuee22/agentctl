# Phase 12 — Clean-host bootstrap acceptance

**Status**: Done
**Depends on**: [Phase 10 — Recovery supervisor](phase-10-supervisor.md)
**Host lane**: clean-container
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: R1
**Gate evidence**: 2026-11-10 ; clean-container ; agentctl check ; pass ; tree a43319031bd088b9a0ca3be17172e492eab335d4c1044f48d8bf0287b1146ed9 ; os=Linux,arch=aarch64,baseline=a27507f2e9404d65fec401f531766533ea8226b1
**Evidence covers**: `src/` `tests/` `pyproject.toml`

> **Purpose**: Close R1 by running the two-stage clean-host recipe: from pipx alone agentctl provisions its build
> prerequisites, ghcup, GHC and cabal and builds the core binary, and the same tree then passes `agentctl check`.

## Phase Objective

This phase adds no code. Its host is the clean-container lane: the two-stage recipe `tests/lanes/clean-host.Dockerfile`,
which [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) writes and value-tests, run as a non-root user
with NOPASSWD sudo on a gate host with docker. Neither agentctl nor check runs docker: the closing agent builds and runs
the recipe, launches Stage B with `docker run --init` and copies the EVIDENCE line that Stage B's check prints.
Docker's init process reaps orphaned native children, allowing the existing PID-absence and containment assertions
to verify complete teardown. Non-root matters twice over: claude refuses
`--dangerously-skip-permissions` under root or sudo, and a root run would never exercise sudo.

- **Stage A: pipx alone.** The image is `ubuntu:24.04` with `python3`, `pipx` and `sudo` only, plus the non-root user.
  The recipe copies the tree in and writes its pre-bootstrap record, which marks the toolchain as one agentctl is about
  to install and which agentctl never writes. As that user, `pipx install` of the copy, without `--editable`, builds a
  wheel from the tree, so the packaged sources and not a checkout do the work. Then `agentctl --assume-yes list` must
  probe the GHC prerequisites and install the missing set with apt through `sudo -n`, download the pinned ghcup 0.2.6.2
  with urllib and verify its SHA-256, install GHC 9.12.4 and cabal 3.16.1.0 (cabal with `--no-set`), build the core
  binary into `cache/build/<digest>`, publish it into `data/bin/<digest>` and hand off. The binary finds no tmux and
  ends with the multiplexer-missing warning, its install command and the exit status `tests/oracles/preflight.toml`
  records; the recipe requires exactly that ending, so any other stops the build before Stage B exists.
- **Stage B: the gate.** On top of Stage A the recipe adds tmux, git and the native claude and codex, reinstalls the
  same tree with `pipx install --force --editable '.[dev]'`, and runs a plain `agentctl check` as the same user, so
  the gate literal never changes. Docker's `--init` option supplies child reaping around that command. The container
  holds no credentials, so the live tests take their logged-out branch.
- **Facts, not journals.** In that run `tests/harness/host.py` sees the recipe's record and reports an
  agentctl-installed toolchain, and `tests/e2e/test_fresh_bootstrap.py` asserts what Stage A left on disk: ghcup's
  SHA-256 against the pin, no unversioned `ghc` or `cabal`, and `ghcup whereis` paths that report the pins. It never
  reads a record agentctl wrote about itself, which would be a subject self-report.

R1 holds when both stages pass: the build chain needed only pipx and its Python, while tmux and the agent CLIs stayed
runtime prerequisites that the binary checked and named install commands for.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R1 — from pipx alone agentctl provisions the build chain and builds the binary, and only checks tmux and the agents | `tests/oracles/bootstrap_plan.toml`, `tests/oracles/pins.toml` | value: the provisioning plan for a host with only python3 and pipx, and the recipe's stages, against bootstrap_plan.toml; real: the installed ghcup digest, default-link absence and resolved GHC and cabal versions; owed: clean-container-acceptance | none — this phase adds no code | `tests/unit/test_plan.py::test_plan_oracle`, `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/e2e/test_fresh_bootstrap.py::test_no_default_links`, `tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins` |
| R3 — the pinned ghcup is downloaded with urllib and SHA-256-verified on a host with none | `tests/oracles/pins.toml` | owed: clean-container-acceptance | none — this phase adds no code | `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin` |
| R15 — missing GHC prerequisites are really installed through apt once consent is given | `tests/oracles/prerequisites.toml` | owed: clean-container-acceptance | none — this phase adds no code | `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer` |

## Not Proven By This Gate

- That the recorded run took place: the evidence row's digest proves the tree is current, not that a run happened ([§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes)). — not proven by any phase.
- Prerequisite installs through dnf or pacman, since the clean lane is Ubuntu 24.04 only. — not proven by any phase.
- A consent prompt answered at a terminal, and a sudo that asks for a password; Stage A consents through `--assume-yes` with passwordless sudo. — not proven by any phase.
- An install from a published git tag or source archive, which needs a release the user publishes. — not proven by any phase.
- A fresh bootstrap on the Linux architecture the gate host does not have; one run proves one of x86_64 and aarch64. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Confirms

- R1 — on a host with only `python3`, `pipx` and `sudo`, a non-editable `pipx install` and `agentctl --assume-yes list` provision the prerequisites, ghcup, GHC and cabal, leave no unversioned `ghc` or `cabal` on that pristine host, build the core binary and end with the multiplexer-missing warning and exit status, after which Stage B's plain `agentctl check` passes (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).
- R3 — on a host with no ghcup, the pinned ghcup 0.2.6.2 is downloaded from downloads.haskell.org with urllib and its SHA-256 equals the published pin (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).
- R15 — the missing GHC prerequisites are really installed with apt through passwordless sudo once `--assume-yes` consents, the probe and the test's own link against `-lgmp` then agree, and the build that follows succeeds (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).

## Sprints

### Sprint 12.1: Two-stage clean-host run and evidence [Done]

**Status**: Done
**Implementation**: none — this phase adds no code
**Validation tests**: `tests/unit/test_plan.py::test_plan_oracle`, `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/e2e/test_fresh_bootstrap.py::test_no_default_links`, `tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins`, `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`
**Mutants**: none — this phase adds no code
**Closes**: R1
**Docs to update**: none — this phase changes no document

#### Objective

Run both stages of the clean-host recipe and record the EVIDENCE line of Stage B's passing `agentctl check`.

#### Deliverables

- Stage A, built from `tests/lanes/clean-host.Dockerfile` on a gate host with docker: `ubuntu:24.04` with `python3`,
  `pipx` and `sudo` only, a non-root user with NOPASSWD sudo, and the recipe's pre-bootstrap record.
- As that user, a non-editable `pipx install` of the copied tree, then `agentctl --assume-yes list`, which provisions
  the prerequisites, ghcup, GHC and cabal, builds and publishes the core binary, hands off, and ends with the
  multiplexer-missing warning and the exit status of `tests/oracles/preflight.toml`.
- Stage B: tmux, git and the native claude and codex added, `pipx install --force --editable '.[dev]'` of the same
  tree, and a plain `agentctl check` as the same user, launched using `docker run --init`.
- Stage B's lane summary reports clean-container met and prints
  `EVIDENCE <YYYY-MM-DD> ; clean-container ; agentctl check ; pass ; tree <sha256> ; <detail>`, which the closing agent
  copies into `**Gate evidence**`; the plan validator recomputes the digest over Evidence covers and compares the lane
  and the digest only.
- A failure fixed by rewriting the phase that introduced its cause, then both stages rebuilt and rerun.

#### Validation

1. The provisioning plan for a host with only `python3` and `pipx` installs the prerequisites, ghcup, GHC and cabal in
   order and never tmux, psmux, claude or codex — `tests/unit/test_plan.py::test_plan_oracle`; fails when a row's
   actions differ from `tests/oracles/bootstrap_plan.toml`; no mutant: this phase adds no code.
2. The recipe's stages equal their oracle rows, Stage A holding no git, compiler or tmux and neither stage running as
   root — `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`; fails when the recipe drifts from
   the lane it claims; no mutant: this phase adds no code.
3. The ghcup Stage A installed carries the SHA-256 `tests/oracles/pins.toml` pins for its triple —
   `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`; fails when its bytes differ from the pin; no
   mutant: this phase adds no code.
4. ghcup's bin dir holds no unversioned `ghc` or `cabal` after the fresh install, while the versioned entries resolve
   — `tests/e2e/test_fresh_bootstrap.py::test_no_default_links`; fails when a pin was installed as the default; no
   mutant: this phase adds no code.
5. `ghcup whereis` gives existing paths for GHC 9.12.4 and cabal 3.16.1.0 whose `--numeric-version` is the pin —
   `tests/e2e/test_fresh_bootstrap.py::test_whereis_paths_report_pins`; fails when a pin is missing or another version
   answers; no mutant: this phase adds no code.
6. After Stage A's install the prerequisite probe and the test's own link against `-lgmp` agree that the prerequisites
   are present — `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`; fails when the
   install left a prerequisite missing that the probe misses; no mutant: this phase adds no code.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- None.
