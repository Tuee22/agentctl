# Documentation Index

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Index the canonical target contracts and their implementation owners without making completion claims.

The [development plan](../DEVELOPMENT_PLAN/README.md) alone owns completion status. Pages state target
contracts and distinguish named current mechanisms from required evidence. Standing incompatible source is
recorded in [the deletion ledger](../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md); writing a stricter
contract does not prove that migration or its new gate machinery is complete. Verdict, evidence and limit terms
are defined once in
[standards § T](../DEVELOPMENT_PLAN/development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts);
pages link its clauses and never restate them.

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
| [engineering/quality_gate.md](engineering/quality_gate.md) | Gate mechanics that decide the § T verdicts: census, legs, seals, attribution, identity, receipt store and publication | [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |
| [engineering/testing.md](engineering/testing.md) | Admissible-test mechanics, native controls, mutants and isolation | [Python discipline and gate integrity](../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) |
| [operations/installation.md](operations/installation.md) | Pipx install, local source-build bootstrap and runtime prerequisites | [Python bootstrap and handoff](../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) |
| [operations/troubleshooting.md](operations/troubleshooting.md) | Typed readiness failures, preserved diagnostics and remedies | [Haskell runtime and platform policy](../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md) |
| [operations/validation_runbook.md](operations/validation_runbook.md) | Dedicated VirtualBox VM, same-checkout binding, credentials, host setup, the canonical run sequence and native Windows and Darwin runs | [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |
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
| environment model | Registered pure model of a tool, host or process environment, bound to a declared effect interpreter and anchored to ratcheted conformance rows | [§ T](../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test) |
| conformance case | Case whose expectations come only from ratcheted oracle or transcript rows and that checks a model; it alone kills the model's mutants | [§ T](../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy) |
| model mutant | Mutant of an environment model that weakens its refusals or answers, killed only by its conformance cases | [§ T](../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy) |
| run-owned resource | Temp root, process, private multiplexer server or record created under the run nonce and torn down by it | [§ Q](../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection) |
| closed list | The only resources a test may touch; everything else, including the user's agents, sessions and VMs, stays untouched | [§ Q](../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection) |
| thin native layer | The production native interpreters and adapters that alone earn native evidence beside private servers and harness provisioning | [§ L](../DEVELOPMENT_PLAN/development_plan_standards.md#l-evidence-classes-and-what-cannot-count) |
| managed session | Session created and owned by agentctl, independently of human attachment and supervision | [sessions](architecture/sessions_and_ownership.md) |
| adopted pane | Explicit external endpoint/instance access without ownership | [sessions](architecture/sessions_and_ownership.md) |
| coherent observation | One checked target snapshot with revision, text/styles, cursor/geometry and native dead state | [supervisor](architecture/supervisor_contract.md) |
| guarded submission | Server-ordered identity/activity check and one literal+Enter submission; stale or uncertain states grant no retry permission | [supervisor](architecture/supervisor_contract.md) |
| lane | A phase's declared host requirement: Linux plus at most one native family, evaluated as halves | [plan standards § N](../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes) |
| half | One separately evaluated host part of a lane: `linux`, `windows`, `macos`, `linux-clean` or `linux-live` | [T.O](../DEVELOPMENT_PLAN/development_plan_standards.md#to-output) |
| verdict | The parent-published result of one phase: `pass`, `awaiting:<half>`, `awaiting:setup:<capability>`, `awaiting:prerequisite` or `fail` | [T.V](../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict) |
| stage | The enforcement stage at which a verdict is judged, printed on its `PHASE` line | [T.W](../DEVELOPMENT_PLAN/development_plan_standards.md#tw-staged-enforcement) |
| closure | A phase together with its transitive prerequisites | [T.X](../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms) |
| owed | Native confirmation a lower phase cannot observe, assigned to a later receiver whose lane includes that family or half | [T.X](../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms) |
| applicable mutant | A corpus mutant that a phase cites whose target is owned within its closure, applicable on each half of its lane where it is a kill obligation | [T.X](../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms) |
| logged-in | An agent CLI whose status probe succeeds | [T.X](../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms) |
| unrun | A half that no verified run on a host qualifying it has evaluated; other runs print it `absent` | [T.X](../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms) |
| host provision | The hardware and the setup the user supplies with it, recorded in the plan's Validation Hosts table; it changes only selection | [Validation Hosts](../DEVELOPMENT_PLAN/README.md#validation-hosts) |
| selection line | The `selection:` line of a verified run, naming the next action on the plan | [T.D](../DEVELOPMENT_PLAN/development_plan_standards.md#td-status-and-progression) |
| phase receipt | A verified run's stored record of one phase on one half it evaluated natively, read for that half only with equal logical and prerequisite identities | [quality gate](engineering/quality_gate.md#receipt-store) |
| observer | Independent nonce-bound bytes/process/resource observation | [testing](engineering/testing.md) |
| bind-mounted checkout | The same live Windows source exposed to the dedicated VirtualBox guest through a real Linux bind mount, not a synchronized copy | [runbook](operations/validation_runbook.md#bind-the-same-checkout) |

## Related

- [documentation standards](documentation_standards.md) — governed authoring.
- [plan](../DEVELOPMENT_PLAN/README.md) — status and execution.
- [overview](../DEVELOPMENT_PLAN/00-overview.md) — requirements.
- [plan standards](../DEVELOPMENT_PLAN/development_plan_standards.md#s-contract-homes) — contract ownership.
- [components](../DEVELOPMENT_PLAN/system-components.md) — implementation inventory.
