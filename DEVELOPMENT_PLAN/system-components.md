# System Components

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Inventory target capabilities, paths, tools and private resources with a single substantive phase owner.

This inventory describes the artifacts built by each owner's contract; a Planned path is a deliverable, not a
claim that the file already exists. The [ledger](legacy_tracking_for_deletion.md) records standing incompatible
shapes. The executable ownership manifest independently censuses every present file, shared dependency and
test. A consumer inherits the owning capability's input identity; moving a phase number does not rename its API.
Each numbered phase document is owned by the phase it describes; the common plan structure and shared
governance contracts belong to governance. A later phase document is not an earlier phase's owned source.
Documents under `documents/` belong to the phase named in their `Owning phase` metadata; later consumers
inherit that owner's current identity through the declared prerequisite chain.
The root agent policies, Git checkout settings, common plan files, and shared source/test/plan directory
entries are governance inputs consumed by the gate for every phase.
Oracle data homes named by requirements are owned by their earliest substantive implementation phase;
later phases that close requirements using the same file are declared consumers. The bootstrap plan and
prerequisite oracles originate in Python bootstrap and are also consumed by the relevant later contracts.
Legacy mutant files whose targets all have the same declared owner belong to that owner. Mixed-target
files need an explicit shared-input migration; a filename prefix is not proof of their ownership.

## Python Package

Python owns bootstrap, transport and developer-gate infrastructure. Product/runtime provisioning belongs to
Haskell. The strict functional doctrine applies equally to application, gate, tests and boundary declarations.
No external standards library or checker is a dependency.

| Capability | Paths | Responsibility | Owning phase |
|---|---|---|---|
| Gate ownership/report model | `src/agentctl/check/ownership.py`, `source_ownership.toml`, `phase0_mutant_ownership.toml`, `phase_reports.py`, `steps.py`, `evidence.py`, `lanes.py`, `validator/`, `tests/oracles/phase_ownership.toml`, `tests/oracles/execution_evidence.toml` | Complete present census, phase/prerequisite input closures, shared integrity and independent lane receipts | [Phase 0 — Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Gate execution and integrity | `pyproject.toml`, `src/agentctl/__init__.py`, `src/agentctl/check/__init__.py`, `audit.py`, `coverage_hosts.py`, `coverage_hosts.toml`, `gate_plugin.py`, `legs.py`, `plan_data.py`, `preconditions.py`, `ratchet.py`, `mutants.py`, `mutant_report.py`, `writeguard.py`, `tests/harness/oracle.py`, `tests/mutants/phase.toml`, `tests/mutants/evidence.toml`, `tests/mutants/governance_preconditions.toml`, `tests/mutants/governance_identity.toml`, `tests/mutants/governance_native_controls.toml`, `tests/mutants/governance_style.toml`, `tests/mutants/governance_toolchain.toml`, `tests/mutants/governance_packaging.toml`, `tests/mutant_relocations.toml` (when needed), `tests/oracles/check_steps.toml` | Complete execution observations, protected baseline and shared checkout integrity | [Phase 0 — Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Bootstrap legacy mutation corpus | `tests/mutants/passthrough.toml` | Protected bootstrap mutation records and unresolved lower-phase killer separation | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Native process mutation corpus | `tests/mutants/capture_phase3.toml`, `tests/mutants/launch_phase3.toml`, `src/agentctl/check/native_mutant_ownership.toml` | Protected native process mutation records and unresolved killer separation | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Multiplexer mutation corpus | `tests/mutants/mux.toml`, `tests/mutants/capture_phase4.toml`, `tests/mutants/sessions_phase4.toml` | Protected mux mutation records and unresolved killer separation | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Launch mutation corpus | `tests/mutants/launch.toml`, `tests/mutants/mux_phase5.toml`, `tests/mutants/passthrough_phase5.toml` | Protected launch mutation records | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Session mutation corpus | `tests/mutants/sessions.toml` | Protected session mutation records | [Session management and adoption](phase-6-session-management-and-adoption.md) |
| Observation mutation corpus | `tests/mutants/capture.toml` | Protected observation mutation records | [Pane observation and classification](phase-7-pane-observation-and-classification.md) |
| Windows qualification mutation corpus | `tests/mutants/mux_phase10.toml`, `src/agentctl/check/psmux_mutant_ownership.toml` | Protected Windows backend mutation records | [Windows backend qualification](phase-10-windows-backend-qualification.md) |
| Source doctrine and native type boundaries | `src/agentctl/check/validator/`, `tests/governance/test_python_discipline.py`, `tests/oracles/python_discipline.toml`, `stubs/` | Local strict functional controls, native stub conformance, module roles and first-party migration | [Phase 1 — Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Python process and result edge | `src/agentctl/foundation_process.py`, `process.py`, `result.py`, `tests/integration/test_python_boundaries.py` | One Python spawner, typed outcomes, literal argv, borrowed native handles and finite immutable values | [Phase 1 — Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Bootstrap facts and source build | `src/agentctl/bootstrap/`, `hostfacts.py`, `paths.py`, `src/agentctl/haskell/` | Only work necessary to obtain Haskell; verified pins, source-only packaging, digest builds and atomic publication | [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Native gate readiness and build checks | `src/agentctl/check/haskell.py`, `haskell_mutants.py`, `identity.py`, `prerequisites.py`, `style.py`, `toolchain.py` | Pinned toolchain, native build, identity and style observations | [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Click and typed transport | `src/agentctl/cli.py`, `bootstrap/handoff.py`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs` | Raw command tail, separate consent, protocol and roots; permanent pipx entry point | [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |

## Haskell Package

All Haskell modules live under the bundled source project and are built through the application-owned path.
Additional path fragments in the inventory refer to that same tree, never an independently callable public binary.

| Capability | Paths | Responsibility | Owning phase |
|---|---|---|---|
| Native runtime effects | `src/agentctl/haskell/src/AgentCtl/Process.hs`, `Native.hs`, `native_fs.c`, `native_process.c`, `native_stop.c` | One Haskell spawner, bounded UTF-8 effects, actual filesystem/identity facts and native stop observation | [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Haskell platform/provisioning foundation | `src/agentctl/haskell/src/AgentCtl/Host.hs`, `Provision.hs`, `Provision/Artifact.hs`, `Paths.hs` | Runtime host policy, consent/privilege plans, private roots, immutable artifact identity and readiness | [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Debian mux and trampoline | `src/agentctl/haskell/src/AgentCtl/Provision/Tmux.hs`, `Mux.hs`, `Mux/Command.hs`, `Mux/Tmux.hs`, `Mux/Types.hs`, `PaneExec.hs`, `PaneExec/Spec.hs` | APT preparation, qualified backend interface, exact targeting and private argv/environment specs | [Phase 4 — Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Agent boundary and launch | `src/agentctl/haskell/src/AgentCtl/Agent.hs`, `Agent/`, `Preflight.hs`, `Launch.hs`, `Session/Name.hs` | External-agent discovery only, status authentication, folder identity, flags, safe startup and reattachment | [Phase 5 — Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Sessions and adoption | `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `Adopt.hs`, `Session/Identity.hs` | Instance/endpoint ownership, exact commands and external adoption without ownership | [Phase 6 — Session management and adoption](phase-6-session-management-and-adoption.md) |
| Observation and capability guard | `src/agentctl/haskell/src/AgentCtl/Observe/`, `Mux/Guarded.hs`, `tests/harness/guarded_input.py` | Coherent native snapshots, true wrapping, class/fingerprint kernels and proven server-ordered submission | [Phase 7 — Pane observation and classification](phase-7-pane-observation-and-classification.md) |
| Recovery and supervisor | `src/agentctl/haskell/src/AgentCtl/Recovery/`, `Supervisor/`, `Supervisor.hs` | Pure transitions, finite timing, safe conditional delivery, typed uncertainty, locks/logs and non-destructive stop | [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md) |
| Base independent fake agent/private mux | `src/agentctl/haskell/app/FakeAgent.hs`, `tests/harness/tmux.py`, `tests/harness/tmux_fixtures.py` | Strict closed-handle byte/process observer and private endpoint teardown required by mux tests | [Phase 4 — Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Public launch observer | `tests/harness/launch.py` | Through-stack argv/environment/lifecycle observation, built on the base observer | [Phase 5 — Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Scripted supervisor observer extension | `src/agentctl/haskell/app/ScriptedAgent.hs`, `fake_signals.c`, `tests/harness/supervisor_signals.py` | Generation/acknowledgement frame/input/stop receipts extending the already usable base observer | [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md) |
| Windows native toolchain/source preparation | `src/agentctl/haskell/src/AgentCtl/Provision/Windows.hs`, `Rust.hs`, `Source.hs`, `Psmux.hs`, `src/agentctl/haskell/resources/psmux/` | Actual MSVC/SDK resource/link probes, isolated Rust roots, trusted archive/patches, local Cargo build | [Phase 9 — Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) |
| Qualified private psmux adapter | `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `resources/psmux/patches/`, `tests/integration/test_psmux_*.py` | Memory/control/capture/identity/guarded-input qualification of exact native artifacts; private coexistence | [Phase 10 — Windows backend qualification](phase-10-windows-backend-qualification.md) |

## Test Apparatus

Implementation ownership follows the lower contract that supplies a test or observer. Acceptance consumes
its actual native receipt; it does not own or add test code.

| Resource | Implementation owner | Native acceptance consumer |
|---|---|---|
| `tests/conftest.py`, `tests/harness/host.py`, `isolation.py`, `workspace.py`, `git.py`, `nonce.py`, shared test scaffolding and `tests/fixtures/static_negative/` except the ready fixtures | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Shared collection and static controls; native fixtures are imported by consuming test modules and mixed-purpose modules remain ledgered |
| `tests/harness/binary.py`, `bootstrap.py`, `bootstrap_origin.py`, `evaluate.py`, `haskell.py`, `haskell_fixtures.py`, `http.py`, `passthrough.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Bootstrap transport and build controls; later launch imports remain ledgered for separation |
| `tests/harness/agents.py`, `live.py`, `tests/fixtures/static_negative/ready_constructed.hs.txt`, `ready_from_preflight.hs.txt` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Agent launch controls; later session imports remain ledgered for separation |
| `tests/harness/sessions.py` | [Session management and adoption](phase-6-session-management-and-adoption.md) | Session controls; later screen imports remain ledgered for separation |
| `tests/harness/supervisor.py`, `supervisor_barrier.py`, `supervisor_cases.py` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Supervisor controls |
| `tests/unit/test_check_steps.py`, `test_steps_records.py`, `test_steps_census.py`, `test_coverage_hosts.py`, `test_steps_integrity.py`, `test_identity.py`, `test_lane.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Gate ordering, checkout identity and lane controls |
| `src/agentctl/haskell/test/TestSource.hs`, `tests/unit/test_cli.py`, `test_digest.py`, `test_ghcup.py`, `test_handoff.py`, `test_haskell_gate.py`, `test_hostfacts.py`, `test_paths.py`, `test_style_tools.py`, `test_toolchain.py`; `tests/integration/test_binary_boundaries.py`, `test_bootstrap_origin.py`, `test_build_boundaries.py`, `test_hostfacts.py`, `test_style_cache.py`, `test_toolchain_real.py`; `tests/governance/test_style_config.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Bootstrap, native readiness and tool configuration controls |
| `tests/integration/test_fake_agent.py`, `test_tmux_harness.py` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Independent fake and private server controls |
| `tests/integration/test_agent_argv_real.py`, `test_agent_real.py`; `tests/unit/test_launch_plan.py` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Agent boundary and native launch controls |
| `tests/unit/test_sessions_values.py`, `tests/e2e/test_sessions.py` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Session ownership controls; owned at their earliest mutant consumer, with later session consumers retained |
| `tests/unit/test_toolchain_gate.py`, `tests/integration/test_haskell_legs.py`, `test_haskell_style_legs.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Native gate-leg killers shared with bootstrap; owned at their earliest mutant consumer |
| `tests/integration/test_capture_real.py`, `tests/e2e/test_launch.py`, `tests/unit/test_mux_values.py` | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Native process killers shared with later mux, launch and observation consumers; independent earlier controls remain ledgered |
| `tests/harness/terminal.py`, `tests/integration/test_command_surface.py`, `tests/e2e/test_passthrough_argv.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Mixed transport and command-surface controls; later launch fixtures remain ledgered for separation |
| `tests/e2e/test_status_screen.py` | [Session management and adoption](phase-6-session-management-and-adoption.md) | Status-screen killer shared with observation |
| `src/agentctl/check/binding_challenge.py`, `binding_inventory.py`, `binding_peer.py`, `binding_protocol.py`, `binding_wsl.py`, `binding_transport.py`, `binding_transaction.py`, `wsl_registration.py`, `wsl_budget.py`, `wsl_cgroup.py`, `wsl_mount.py`, `wsl_tree.py`, `wsl_monitor.py`, `wsl_host_sample.py`, `wsl_guest_sample.py`, `tests/integration/test_binding_challenge.py`, `test_binding_inventory.py`, `test_binding_host.py`, `test_binding_peer_cleanup.py`, `test_binding_protocol.py`, `test_binding_transaction.py`, `test_wsl_storage_observation.py`, `test_wsl_encoding.py`, `test_wsl_cgroup_observation.py`, `test_wsl_tree_observation.py`, `test_wsl_host_sample.py`, `test_wsl_guest_sample.py`, `test_virtualbox_binding.py`, `src/agentctl/check/virtualbox_binding.py`, `virtualbox_bind.py`, `tests/governance/test_binding_peer.py`, `test_binding_transport.py`, `test_binding_wsl.py`, `test_wsl_registration.py`, `test_wsl_mount.py`, `test_wsl_budget.py`, `test_wsl_monitor.py`, `test_wsl_host_sample.py`, `test_wsl_guest_sample.py`, `test_ownership_manifest.py`, phase-report/host-lane schema controls | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Linux clean/live and Windows-hosted VM binding observations |
| `src/agentctl/check/virtualbox_guest.py`, `virtualbox_guest_protocol.py`, `virtualbox_sessions.py`, `virtualbox_key_observe.py`, `virtualbox_ssh_key.py`, `virtualbox_listener.py`, `virtualbox_observe.py`, `virtualbox_storage.py`, `virtualbox_snapshot.py`, `virtualbox_inventory.py`, `virtualbox_capacity.py`, `virtualbox_guest_capacity.py`, `tests/governance/test_virtualbox_guest_capacity.py`, `test_virtualbox_capacity.py`, `test_virtualbox_inventory.py`, `test_virtualbox_snapshot.py`, `test_virtualbox_storage.py`, `test_process_image.py`, `test_virtualbox_host.py`, `test_virtualbox_guest.py`, `tests/integration/test_virtualbox_observe.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Diagnostic guest values and nonce exchange; authenticated VM binding remains open |
| `tests/governance/test_phase_reports.py`, `test_plan_validator.py`, `test_gate_plugin.py`, `test_run_evidence.py`, `test_release_receipts.py`, `test_mutants.py`, `test_oracles.py`, `test_forbidden_surfaces.py`, `test_ratchet.py`, `test_ratchet_refusals.py`, `test_source_guards.py`, `tests/integration/test_guard.py`, `test_runtime_boundaries.py`, `test_spawn_audit.py`, `tests/unit/test_check_legs.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | All current phase and integrity verdicts; source doctrine extends these shared guards |
| `tests/fixtures/docs_negative/`, `tests/harness/trees.py`, `tests/governance/test_doc_validator.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Documentation and plan integrity controls |
| `tests/fixtures/bootstrap/`, `tests/fixtures/haskell/` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Bootstrap and native-build edge controls |
| `tests/fixtures/screens/`, `tests/fixtures/terminal/`, `tests/harness/screens.py`, `tests/governance/test_screen_fixtures.py` | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Classification, capture and fixture-provenance controls |
| `src/agentctl/check/governance_mutant_ownership.toml` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Partial legacy governance mutation ownership declarations |
| `src/agentctl/check/bootstrap_mutant_ownership.toml`, `tests/mutants/bootstrap_startup.toml`, `tests/mutants/bootstrap_plan.toml`, `tests/mutants/build_cache.toml`, `tests/mutants/style_legs.toml`, `tests/mutants/toolchain.toml`, `tests/mutants/haskell_build.toml` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Partial bootstrap mutation ownership declarations |
| `src/agentctl/check/agent_mutant_ownership.toml` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Partial agent mutation ownership declarations |
| `src/agentctl/check/sessions_mutant_ownership.toml`, `tests/mutants/classify_status.toml` | [Session management and adoption](phase-6-session-management-and-adoption.md) | Partial session mutation ownership declarations |
| `src/agentctl/check/supervisor_mutant_ownership.toml` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Partial supervisor mutation ownership declarations |
| `src/agentctl/check/observation_mutant_ownership.toml`, `tests/mutants/observation_status.toml` | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Partial classification mutation ownership declarations |
| `src/agentctl/pin_values.py`, `src/agentctl/check/process_identity.py`, `tests/unit/test_preconditions.py`, `tests/integration/test_socket_preconditions.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Shared pin values, socket preconditions and bootstrap readiness consumers |
| `tests/integration/test_host_mux_probe.py` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Host multiplexer qualification |
| `tests/integration/test_mux_resolution.py` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Opaque session-name constructor boundary |
| `tests/unit/test_prereqs.py`, `test_prerequisite_readiness.py`, `tests/integration/test_prereqs_consent.py`, `test_prereqs_real.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Prerequisite and consent controls |
| `tests/unit/test_agent_resolution.py`, `test_agent_table.py`, `test_auth_status.py`, `test_preflight.py`, `tests/integration/test_preflight.py`, `test_ready_opaque.py` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Agent resolution, authentication and readiness controls |
| `tests/unit/test_adopt_values.py` | [Session management and adoption](phase-6-session-management-and-adoption.md) | Nonownership and adoption controls |
| `tests/unit/test_supervisor_values.py`, `test_watch_values.py` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Supervisor and watch transition controls |
| `src/agentctl/haskell/test/NameTests.hs` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Native session-name controls |
| `src/agentctl/haskell/test/ObserveTests.hs` | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Native observation and classification controls |
| `src/agentctl/haskell/test/RecoveryTests.hs` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Native recovery and backoff controls |
| Native project metadata, shared test entry and evaluator | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Application-owned build and native test routing; the ledger tracks remaining cross-phase coupling |
| `src/agentctl/haskell/test/ProcessTests.hs`, `MuxTests.hs`, `SpecTests.hs`, `state_fixture.c` | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Native effects controls, also consumed by Debian mux tests |
| `src/agentctl/haskell/test/MuxFixture.hs` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Private mux test fixture |
| `src/agentctl/haskell/test/AgentFixture.hs`, `AgentTests.hs` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Native agent-boundary controls |
| `src/agentctl/haskell/test/SupervisorTests.hs`, `ConsoleFixture.hs`, `console_fixture.c` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Supervisor and native console observation controls |
| `tests/integration/test_release_install.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Final installed-package receipt |
| `tests/integration/test_owned_resources.py` | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Native Windows resource receipt |
| Clean recipe, `tests/mutants/linux_clean_recipe.toml`, `src/agentctl/check/linux_mutant_ownership.toml` and `tests/integration/test_clean_runtime.py` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Linux clean-host receipt |
| `tests/live/test_live_launch.py` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Linux authenticated live receipt |
| `tests/live/test_live_classification.py` | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Linux authenticated live receipt |
| `tests/live/test_live_supervision.py` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Existing no-input supervision observation; the separately planned acceptance receipt remains outstanding |
| `tests/live/test_live_supervisor.py` | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Linux authenticated live receipt |
| Native psmux/profile identity and compatibility controls | [Windows backend qualification](phase-10-windows-backend-qualification.md) | Native Windows application receipt |
| `Provision/Darwin.hs`, `tests/integration/test_darwin_runtime.py` | [macOS acceptance](phase-13-macos-acceptance.md) | The same additive native macOS contract |
| `tests/governance/test_release_receipts.py` | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Final current-receipt join |

## Acceptance Evidence Implementation Owners

Acceptance consumes tests already implemented by a lower owner; an acceptance-only missing test is unmet
evidence and is repaired at that lower owner, never implemented invisibly in the no-code phase.

| Test resource | Implementation owner | Acceptance consumer |
|---|---|---|
| phase reports, release-receipt validators, host-lane schema and WSL binding controls | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Linux/WSL and final receipt join |
| source-only package/installed-resource controls | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Final installed-package acceptance |
| native owned-resource/cleanup controls | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Native Windows application acceptance |
| clean Haskell/APT preparation receipt controls | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Clean Debian acceptance |
| no-input authenticated agent launch observers | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Linux live acceptance |
| no-input live class observers | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Linux live acceptance |
| no-input live supervisor observers | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Linux live acceptance |
| running server/profile/artifact identity controls | [Windows backend qualification](phase-10-windows-backend-qualification.md) | Native Windows application acceptance |

## External Tools

| Tool | Invoker and policy | Owner |
|---|---|---|
| pipx and Python | User supplies installation interface/interpreter; runtime package remains pure Python plus source resources | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| ghcup, GHC, cabal | Python bootstrap verifies pins, uses absolute paths and never changes user defaults | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| ruff, ty, coverage, pytest | Python-owned development gate, all source/tests, no alternative runner | [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| fourmolu, HLint | Application-owned pinned native quality tools | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| APT and tmux | Haskell Debian readiness and consented outer preparation; package managers vetoed inside tests | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| rustup, Rust, Cargo | Haskell private Windows roots and explicit pinned native tools; no user default/PATH edits | [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) |
| MSVC linker and Windows SDK/resource compiler | Haskell actual capability probes and explicit consent/elevation preparation | [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) |
| psmux source and patches | Haskell source acquisition, build and behavioral qualification; no system executable fallback | [Windows backend qualification](phase-10-windows-backend-qualification.md) |
| claude, codex | User-installed; Haskell resolves requested agent and probes status, never installs/logs in | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| VirtualBox, Debian, workload and mount tools | Dedicated Linux validation environment, actual capacity and same-checkout proof; existing WSL- and Hyper-V-specific controls require migration | [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) |
| Darwin CLT and existing Homebrew | Native setup readiness and consented Haskell tmux plan; check opens no dialogs | [macOS acceptance](phase-13-macos-acceptance.md) |

## Per-User Directories

Python supplies bootstrap cache/data/state roots. Haskell derives owned runtime subdirectories from those
explicit roots. The canonical detailed layout is [files and state](../documents/reference/files_and_state.md).
Immutable binary/artifact directories contain version/digest identity; the private psmux registry remains stable
across revisions. Rust/Cargo/cache/temp paths are private. Native short build roots outside these parents are
registered with their nonce and verified absolute cleanup boundary, never silently excluded from containment.

WSL Linux build/state/storage remains in its dedicated Linux filesystem; the source path is the required bind
mount of the live Windows checkout. Native host and guest can read the same inputs but never run concurrent
write-guarded checks against a changing tree.

## Cross-Layer Invariant Owners

| Invariant | Single owner |
|---|---|
| Per-user bootstrap roots | Python paths; Haskell validates/derives only owned children |
| Runtime distribution policy | Haskell host policy; Python only knows platform facts needed to obtain Haskell |
| Global consent and raw tail | Typed handoff contract; Click tail remains literal |
| Build/cache publication | Shared immutable input identity, per-artifact locks and atomic publish contract |
| Multiplexer readiness and agent presence | Haskell provisioning/preflight, with agents always external |
| Native capability authorization | Actual running server identity/profile, never client banner alone |
| Phase closure | Complete canonical gate report over owned/prerequisite input closure |
| Host/WSL source identity | Observed bind mount plus pre-guard bidirectional nonce/census |

## Related

- [overview](00-overview.md) — architecture and requirements.
- [standards](development_plan_standards.md) — ownership and receipt rules.
- [ledger](legacy_tracking_for_deletion.md) — standing incompatible implementations.
- [documents](../documents/README.md) — contract homes.
- [files and state](../documents/reference/files_and_state.md) — private layouts.
