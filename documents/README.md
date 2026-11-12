# Documentation Index

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Index the canonical target contracts and their implementation owners without making completion claims.

The [development plan](../DEVELOPMENT_PLAN/README.md) alone owns completion status. Pages state target
contracts and distinguish named current mechanisms from required evidence. Standing incompatible source is
recorded in [the deletion ledger](../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md); writing a stricter
contract does not prove that migration or its new gate machinery is complete.

## Pages

| Page | Canonical topic | Owning phase |
|---|---|---|
| [documentation_standards.md](documentation_standards.md) | Prose structure, contract homes and evidence honesty | [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |
| [architecture/python_haskell_boundary.md](architecture/python_haskell_boundary.md) | Minimal Python bootstrap, typed consent and raw Haskell handoff | [Python bootstrap and handoff](../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) |
| [architecture/multiplexer_adapter.md](architecture/multiplexer_adapter.md) | Qualified Debian/native backends, private Windows source build and identity | [Debian tmux and multiplexer](../DEVELOPMENT_PLAN/phase-4-debian-tmux-and-multiplexer.md) |
| [architecture/launch_contract.md](architecture/launch_contract.md) | External agent checks, raw flags, launch/reattach and failures | [Agent preflight and launch](../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md) |
| [architecture/sessions_and_ownership.md](architecture/sessions_and_ownership.md) | Instance identity, management and explicit external adoption | [Session management and adoption](../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| [architecture/supervisor_contract.md](architecture/supervisor_contract.md) | Coherent observation, guarded input, recovery and uncertainty | [Recovery and supervisor](../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| [engineering/code_standards.md](engineering/code_standards.md) | Strict Python doctrine, migration and Haskell source discipline | [Python discipline and gate integrity](../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) |
| [engineering/toolchain_bootstrap.md](engineering/toolchain_bootstrap.md) | Bootstrap versus Haskell runtime toolchain preparation and consent | [Haskell runtime and platform policy](../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md) |
| [engineering/binary_build.md](engineering/binary_build.md) | Source packaging, immutable build identity and publication | [Python bootstrap and handoff](../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) |
| [engineering/quality_gate.md](engineering/quality_gate.md) | Complete execution, phase/lane reports and overall verdict | [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |
| [engineering/testing.md](engineering/testing.md) | Independent evidence, native controls, mutants and containment | [Python discipline and gate integrity](../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) |
| [operations/installation.md](operations/installation.md) | Pipx install, local source-build bootstrap and runtime prerequisites | [Python bootstrap and handoff](../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) |
| [operations/troubleshooting.md](operations/troubleshooting.md) | Typed readiness failures, preserved diagnostics and remedies | [Haskell runtime and platform policy](../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md) |
| [operations/validation_runbook.md](operations/validation_runbook.md) | Dedicated WSL2, same-checkout binding, resources and native acceptance | [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |
| [reference/cli_reference.md](reference/cli_reference.md) | Public commands, consent, capability status and exit outcomes | [Recovery and supervisor](../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| [reference/files_and_state.md](reference/files_and_state.md) | Private caches, artifacts, registry, receipts and lock lifetimes | [Haskell runtime and platform policy](../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md) |
| [reference/external_tool_facts.md](reference/external_tool_facts.md) | Versioned primary-source facts and verification scope | [Python discipline and gate integrity](../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) |

## Glossary

| Term | Meaning | Home |
|---|---|---|
| bootstrap | Python work needed to obtain the source-built Haskell application | [boundary](architecture/python_haskell_boundary.md) |
| runtime preparation | Haskell-owned host/backend/toolchain readiness before actual session work | [toolchain](engineering/toolchain_bootstrap.md) |
| candidate artifact | Build-verified immutable output without behavioral backend admission | [build](engineering/binary_build.md) |
| qualified backend | Exact client/server/profile identity with the required behavior proven on its native host | [multiplexer](architecture/multiplexer_adapter.md) |
| managed session | Session created and owned by agentctl, independently of human attachment and supervision | [sessions](architecture/sessions_and_ownership.md) |
| adopted pane | Explicit external endpoint/instance access without ownership | [sessions](architecture/sessions_and_ownership.md) |
| coherent observation | One checked target snapshot with revision, text/styles, cursor/geometry and native dead state | [supervisor](architecture/supervisor_contract.md) |
| guarded submission | Server-ordered identity/activity check and one literal+Enter submission; stale or uncertain states grant no retry permission | [supervisor](architecture/supervisor_contract.md) |
| lane | Required actual Linux and optional native-family capability observations for a phase | [quality gate](engineering/quality_gate.md) |
| phase receipt | Current complete owned/prerequisite input and execution evidence for one phase/lane | [quality gate](engineering/quality_gate.md) |
| observer | Independent nonce-bound bytes/process/resource observation | [testing](engineering/testing.md) |
| bind-mounted checkout | The same live Windows source exposed through a real Linux bind mount, not a synchronized copy | [runbook](operations/validation_runbook.md) |

## Related

- [documentation standards](documentation_standards.md) — governed authoring.
- [plan](../DEVELOPMENT_PLAN/README.md) — status and execution.
- [overview](../DEVELOPMENT_PLAN/00-overview.md) — requirements.
- [plan standards](../DEVELOPMENT_PLAN/development_plan_standards.md#s-contract-homes) — contract ownership.
- [components](../DEVELOPMENT_PLAN/system-components.md) — implementation inventory.
