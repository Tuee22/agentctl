# System Components

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Inventory target capabilities, paths, tools and private resources with a single substantive phase owner.

This inventory describes the artifacts built by each owner's contract; a Planned path is a deliverable, not a
claim that the file already exists. The [ledger](legacy_tracking_for_deletion.md) records standing incompatible
shapes. The executable ownership manifest independently censuses every present file, shared dependency and
test. A consumer inherits the owning capability's input identity; moving a phase number does not rename its API.

## Python Package

Python owns bootstrap, transport and developer-gate infrastructure. Product/runtime provisioning belongs to
Haskell. The strict functional doctrine applies equally to application, gate, tests and boundary declarations.
No external standards library or checker is a dependency.

| Capability | Paths | Responsibility | Owning phase |
|---|---|---|---|
| Gate ownership/report model | `src/agentctl/check/phase_reports.py`, `steps.py`, `evidence.py`, `lanes.py`, `validator/`, `tests/oracles/phase_ownership.toml` | Complete present census, phase/prerequisite input closures, shared integrity and independent lane receipts | [Phase 0 — Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Source doctrine and native type boundaries | `src/agentctl/check/validator/`, `tests/governance/test_python_discipline.py`, `tests/oracles/python_discipline.toml`, `stubs/` | Local strict functional controls, native stub conformance, module roles and first-party migration | [Phase 1 — Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Python process and result edge | `src/agentctl/process.py`, `result.py`, `tests/integration/test_python_boundaries.py` | One Python spawner, typed outcomes, literal argv, borrowed native handles and finite immutable values | [Phase 1 — Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Bootstrap facts and source build | `src/agentctl/bootstrap/`, `hostfacts.py`, `paths.py`, `src/agentctl/haskell/` | Only work necessary to obtain Haskell; verified pins, source-only packaging, digest builds and atomic publication | [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Click and typed transport | `src/agentctl/cli.py`, `bootstrap/handoff.py`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs` | Raw command tail, separate consent, protocol and roots; permanent pipx entry point | [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |

## Haskell Package

All Haskell modules live under the bundled source project and are built through the application-owned path.
Additional path fragments in the inventory refer to that same tree, never an independently callable public binary.

| Capability | Paths | Responsibility | Owning phase |
|---|---|---|---|
| Native runtime effects | `src/agentctl/haskell/src/AgentCtl/Process.hs`, `Native.hs`, `native_fs.c`, `native_process.c`, `native_stop.c` | One Haskell spawner, bounded UTF-8 effects, actual filesystem/identity facts and native stop observation | [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Haskell platform/provisioning foundation | `src/agentctl/haskell/src/AgentCtl/Host.hs`, `Provision.hs`, `Provision/Artifact.hs`, `Paths.hs` | Runtime host policy, consent/privilege plans, private roots, immutable artifact identity and readiness | [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Debian mux and trampoline | `src/agentctl/haskell/src/AgentCtl/Provision/Tmux.hs`, `Mux.hs`, `Mux/Command.hs`, `Mux/Tmux.hs`, `Mux/Types.hs`, `PaneExec.hs`, `PaneExec/Spec.hs` | APT preparation, qualified backend interface, exact targeting and private argv/environment specs | [Phase 4 — Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Agent boundary and launch | `src/agentctl/haskell/src/AgentCtl/Agent/`, `Preflight.hs`, `Launch.hs`, `Session/Name.hs` | External-agent discovery only, status authentication, folder identity, flags, safe startup and reattachment | [Phase 5 — Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Sessions and adoption | `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `Adopt.hs`, `Session/Identity.hs` | Instance/endpoint ownership, exact commands and external adoption without ownership | [Phase 6 — Session management and adoption](phase-6-session-management-and-adoption.md) |
| Observation and capability guard | `src/agentctl/haskell/src/AgentCtl/Observe/`, `Mux/Guarded.hs`, `tests/harness/guarded_input.py` | Coherent native snapshots, true wrapping, class/fingerprint kernels and proven server-ordered submission | [Phase 7 — Pane observation and classification](phase-7-pane-observation-and-classification.md) |
| Recovery and supervisor | `src/agentctl/haskell/src/AgentCtl/Recovery/`, `Supervisor/`, `Supervisor.hs` | Pure transitions, finite timing, safe conditional delivery, typed uncertainty, locks/logs and non-destructive stop | [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md) |
| Base independent fake agent/private mux | `src/agentctl/haskell/app/FakeAgent.hs`, `tests/harness/tmux.py` | Strict closed-handle byte/process observer and private endpoint teardown required by mux tests | [Phase 4 — Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Public launch observer | `tests/harness/launch.py` | Through-stack argv/environment/lifecycle observation, built on the base observer | [Phase 5 — Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Scripted supervisor observer extension | `src/agentctl/haskell/app/ScriptedAgent.hs`, `fake_signals.c`, `tests/harness/supervisor_signals.py` | Generation/acknowledgement frame/input/stop receipts extending the already usable base observer | [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md) |
| Windows native toolchain/source preparation | `src/agentctl/haskell/src/AgentCtl/Provision/Windows.hs`, `Rust.hs`, `Source.hs`, `Psmux.hs`, `src/agentctl/haskell/resources/psmux/` | Actual MSVC/SDK resource/link probes, isolated Rust roots, trusted archive/patches, local Cargo build | [Phase 9 — Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) |
| Qualified private psmux adapter | `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `resources/psmux/patches/`, `tests/integration/test_psmux_*.py` | Memory/control/capture/identity/guarded-input qualification of exact native artifacts; private coexistence | [Phase 10 — Windows backend qualification](phase-10-windows-backend-qualification.md) |

## Test Apparatus

Implementation ownership follows the lower contract that supplies a test or observer. Acceptance consumes
its actual native receipt; it does not own or add test code.

| Resource | Implementation owner | Native acceptance consumer |
|---|---|---|
| `tests/integration/test_wsl_binding.py`, phase-report/host-lane schema controls | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Linux clean/live/WSL receipt |
| `tests/integration/test_release_install.py` | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Final installed-package receipt |
| `tests/integration/test_owned_resources.py` | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Native Windows resource receipt |
| Clean recipe and `tests/integration/test_clean_runtime.py` | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Linux clean-host receipt |
| `tests/live/test_live_launch.py` | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Linux authenticated live receipt |
| `tests/live/test_live_classification.py` | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Linux authenticated live receipt |
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
| WSL2, Debian, cgroup/mount tools | Dedicated Linux validation environment, actual capacity and same-checkout proof | [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) |
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
