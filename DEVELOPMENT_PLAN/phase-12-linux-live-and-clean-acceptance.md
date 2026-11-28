# Phase 12 — Linux live and clean acceptance

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-live-clean
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: R1, R25
**Gate evidence**: none recorded
**Evidence covers**: phase input closure and verified prerequisite receipts

> **Purpose**: Debian clean-host and logged-in agent acceptance, with a dedicated Debian VirtualBox VM for Linux evidence on a Windows host.

## Phase Objective

Debian clean-host and logged-in agent acceptance, with a dedicated Debian VirtualBox VM for Linux evidence on a Windows host. Actual preparation occurs before the noninteractive gate and is bound to its subject; a copied checkout or commit cannot bridge host and guest state, and the clean container's byte-identical tree of the bound checkout counts only as D-142 bounds it.

This phase's verdict evaluates the `linux-clean` and `linux-live` halves ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)): the two-stage clean Debian bootstrap runs on `linux-clean`, and the checkout binding and logged-in no-input acceptance run on `linux-live`. Clean state is observed under the run nonce, never asserted by a hand-written fact; while a half's capability is absent, its probe reports absence, that half prints `absent` and the verdict is at best `awaiting:setup:<capability>`. Every cited artifact is owned within closure(12) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), and each acceptance node is implemented in a module of the lower phase that owns its contract; a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. This phase consumes the clean-host recipe of [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) unchanged, needs no Windows-toolchain code and receives the clean and logged-in confirmations that lower phases owe it, each paired with one Confirms line.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R25 — Dedicated VirtualBox and checkout binding | `tests/oracles/requirements.toml` | observer: nonce-bound guest binding, mount, census and capacity observations | none — closure-owned mutants with all their killers follow P0-18 | `tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`, `tests/integration/test_virtualbox_binding.py::test_capacity_and_dependency_receipt` |
| R1 — Two-stage clean Debian bootstrap | `tests/oracles/requirements.toml` | real: actual clean toolchain, build and APT tmux preparation on the `linux-clean` half | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land, and closure-owned mutants with all their killers follow P0-18 | `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux` |
| R1 — Logged-in no-input live acceptance | `tests/oracles/requirements.toml` | real: logged-in agent launch, screen classes and supervision without input on the `linux-live` half | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land, and closure-owned mutants with all their killers follow P0-18 | `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A logged-in observation proves what the installed agent CLI rendered without input, never agent-internal readiness ([T.C](development_plan_standards.md#tc-ceiling) C5).

## Confirms

The `linux-clean` and `linux-live` halves confirm each lower item that an ordinary Linux run cannot observe; a logged-out refusal never stands in for logged-in evidence. Each item is discharged on its half only when the evidence citations of its source row pass natively there and satisfy [T.E](development_plan_standards.md#te-unspoofable-test) at this phase's stage, alongside this phase's own acceptance rows (D-159).

- R15 — the genuine production preparation receipt on the `linux-clean` half (owed by [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)).
- R12.1 — clean APT tmux preparation through the unchanged clean-host recipe (owed by [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)).
- R7 — logged-in no-input live launch (owed by [Agent preflight and launch](phase-5-agent-preflight-and-launch.md)).
- R18.1 — logged-in live screen classes (owed by [Pane observation and classification](phase-7-pane-observation-and-classification.md)).
- R18 — the live supervisor never sends input (owed by [Recovery and supervisor](phase-8-recovery-and-supervisor.md)).

## Sprints

### Sprint 12.1: Dedicated VirtualBox and checkout binding [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`, `tests/integration/test_virtualbox_binding.py::test_capacity_and_dependency_receipt`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: R25
**Docs to update**: migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Dedicated VirtualBox and checkout binding supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

When using Windows, use an agentctl-only Debian VirtualBox VM sized with host headroom, observed CPU/memory/swap/disk capacity and all Linux dependencies. Bind mount the live Windows checkout into its Linux workspace; verify mountinfo, source identity and bidirectional nonce visibility, including uncommitted/untracked state. Native Debian uses its own corresponding host identity. This sprint runs on the `linux-live` half, where the guest binding nodes of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) execute as portable nodes on the bound checkout ([T.X](development_plan_standards.md#tx-terms)), and consumes that guest binding check; in the clean container's run of the `linux-clean` half they claim no binding, and the kills and coverage that only the bound checkout reaches come from the guest's current verified run ([T.V](development_plan_standards.md#tv-verdict), D-168); it needs no Windows-toolchain code. Once P0-18 lets a row cite mutants owned within its closure, each Gate Integrity row of this phase cites them with every killer.

#### Validation

For the VirtualBox route require a real bind mount and fail a symlink, copy, stale guest tree or different HEAD/content pairing. The mount's permission-change, lock, case and symlink behavior is recorded as a mount fact, never as a qualification prerequisite. Native Debian records its direct checkout identity and requires no Windows machine. Observe allocations and available capacity with host headroom; cross-project isolation proof is not a prerequisite. Do not change other VMs or existing sessions.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 12.2: Two-stage clean Debian bootstrap [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/probes/container_runtime.py`
**Validation tests**: `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land, and closure-owned mutants with all their killers follow P0-18
**Closes**: R1
**Docs to update**: migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Two-stage clean Debian bootstrap supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Stage A records absent toolchains and tmux, installs Python build prerequisites through the real bootstrap and prepares tmux through Haskell under explicit consent. Stage B runs the unchanged noninteractive gate with package-manager vetoes. Isolated agent installation is host preparation; application code never installs agent CLIs. The `linux-clean` half runs in a clean Debian container of the agent-installed container runtime in the dedicated guest; this sprint consumes `tests/lanes/clean-host.Dockerfile`, the clean-host recipe of [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md), unchanged (D-142). This phase's host-declared probe for `setup:container-runtime` reports absence while the runtime is absent, leaving this phase at best `awaiting:setup:container-runtime`. The guest run that builds the container evaluates that probe; the container run natively evaluates only the `linux-clean` half, which it qualifies from the clean state it observes under its own nonce, never from that probe, and there the guest binding nodes claim no shared-folder binding (D-164). The container is built after binding from a byte-identical copy of the bound checkout, with no edit before its gate finishes; its logical identity equals that of the guest's stored receipts, it never substitutes for the bind mount, and its receipts enter the guest store through the receipt-store import of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) (D-142). The planned mutant `M-clean-tmux-preparation-unreprobed` is named here until its corpus row lands ([§ C](development_plan_standards.md#c-honest-completion-tracking)): it accepts Stage A's APT tmux preparation without re-probing the installed tmux, and `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux` kills it. Its every killer is declared to the `linux-clean` half, so it is a kill obligation only on that half and this phase owns it ([T.K](development_plan_standards.md#tk-kill) K6, [T.M](development_plan_standards.md#tm-adequacy) M1, D-168); once P0-18 lands, the R1 clean row also cites the closure-owned mutants that its portable `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin` kills.

#### Validation

Require actual native toolchain/build and tmux preparation receipts bound to source inputs and host, then full owned tests and immutable warm reuse. Clean state is observed under the run nonce. A fabricated JSON receipt without matching executable/observed state fails; what a stored receipt proves is bounded by [T.C](development_plan_standards.md#tc-ceiling) C3.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 12.3: Logged-in no-input live acceptance [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/probes/agents_logged_in.py`
**Validation tests**: `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land, and closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Logged-in no-input live acceptance supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use existing logged-in Linux agents only in the fixed live-acceptance folder with updates disabled and no answered dialogs. Agent credentials reach the dedicated guest through transient read-only VirtualBox shared folders of the host `.claude` and `.codex` folders: only `~/.claude/.credentials.json` and `~/.codex/auth.json` are symlinked, the guest keeps its own writable `~/.claude.json` and settings, binaries are never mounted and the host stays the single writer of refreshed tokens. When the status probe fails or the tokens desynchronize, those two files are copied with mode 0600 instead, the choice is recorded in host facts and host originals stay intact (D-141). This phase's host-declared probe for `setup:agents-logged-in` reports absence while no logged-in agent is available, leaving this phase at best `awaiting:setup:agents-logged-in`. Logged-out controls remain tested but do not qualify the `linux-live` half. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-live-launch-screen-unclassified`, `M-live-screen-class-misread` and `M-live-supervisor-input-sent`, which `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes` and `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends` respectively kill on a logged-in agent. Each has only killers declared to the `linux-live` half, so it is a kill obligation only on that half and this phase owns it while its target stays with its lower owner ([T.K](development_plan_standards.md#tk-kill) K6, [T.M](development_plan_standards.md#tm-adequacy) M1, D-168); those killers launch agents only in `<state>/live-acceptance/` and send no input.

Live acceptance runs only on the bound dedicated guest (D-179). This phase owns the live-starting modules, including `tests/live/test_live_launch.py` and `tests/harness/live.py`, moved here from their earlier owners. Agent probes run only on that guest; every live node is collected and executed on every run and asserts the branch its sealed qualification requires, and a qualifying run requires an observer record of the installed agent from each live node (P0-37). Live inputs (the guest's real home, agent configuration and credentials, and `<state>/live-acceptance`) reach only live nodes. At most five live mutants of this phase's own comparison code, declared wholly to `linux-live`, are killed only on that half, each kill one live session, and the half runs only on the triggers that need it. Replaying the agent-CLI transcript rows of [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) against the installed agents confirms that model here. Planned mutants, named here until their corpus rows land: `M-live-refusal-branch-accepted`, `M-live-observer-record-missing-accepted`.

#### Validation

Observe real agent processes, exact launch configuration and safe classes without sending prompts. A missing logged-in capability remains unmet and cannot become a passing live receipt through a documented fixture or manual confirmation.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 12.1–12.3.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
