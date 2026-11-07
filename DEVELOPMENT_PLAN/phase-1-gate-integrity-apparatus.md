# Phase 1 — Gate-integrity apparatus

**Status**: Done
**Depends on**: [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md)
**Host lane**: any-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R20

> **Purpose**: Make check's evidence independent, fresh and complete through request-derived oracles, named-reason mutants, a ratchet against HEAD, run-integrity guards and mechanically checked phase closure.

## Phase Objective

This phase gives the check skeleton the apparatus that bounds R20's claim. The request-derived oracles are
authored independently before product code. Every run exercises its mutants, checks
the checkout and interpreter it uses, and joins the plan's completion claims to results from that run.
[Testing](../documents/engineering/testing.md) owns the mechanics; [the quality gate](../documents/engineering/quality_gate.md)
owns the steps and configuration.

- `tests/harness/oracle.py` extends the comparison introduced in Sprint 0.2 with provenance and amendment validation;
  its expected values import nothing from the package under test.
- `src/agentctl/check/mutants.py` runs exact-once patches on scratch copies; `check/ratchet.py` compares gate data
  against HEAD; `check/writeguard.py` owns the tree snapshots, venv integrity and containment.
- `check/audit.py` observes Python process boundaries, and `check/validator/source.py` owns static source and
  configuration guards. Neither supplies a test-only branch to production code.
- `check/evidence.py`, `check/lanes.py` and `check/validator/plan.py` join fresh results to citations and evidence
  rows. No host-acceptance phase is marked complete here, and no recorded digest attests that a run happened.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R20 — expected values have independent provenance before the implementation | `tests/oracles/launch_argv.toml`, `tests/oracles/session_names.toml`, `tests/oracles/preflight.toml`, `tests/oracles/auth_status.toml`, `tests/oracles/recovery_transitions.toml`, `tests/oracles/backoff.toml` | value: row-schema, quote, provenance and import checks over minimal oracle trees | `M-oracle-quote-unchecked`, `M-oracle-subject-import-allowed` | `tests/governance/test_oracles.py::test_quote_must_match_requirement`, `tests/governance/test_oracles.py::test_loader_imports_no_subject` |
| R20 — every deliberate defect is killed for its named reason in this run | `tests/mutants/gate.toml` | real: pytester baseline and defective scratch subjects, with exact patch and reason checks | `M-mutant-any-failure-counts`, `M-mutant-survivor-accepted` | `tests/governance/test_mutants.py::test_wrong_reason_rejected`, `tests/governance/test_mutants.py::test_survivor_rejected` |
| R20 — gate data cannot weaken against HEAD and check cannot change its subject or environment | `tests/oracles/lint_config.toml` | value: append-only comparison over committed and working rows; real: temporary checkouts and disposable venvs expose changed files, refs and installed distributions; real: an owned observer pid is detected live and accepted after reaping; observer: an independent hook records snapshot reads around a failed tool; owed: windows-psmux-acceptance | `M-ratchet-allow-edit`, `M-guard-skip-ignored`, `M-guard-ref-unchecked`, `M-guard-venv-unchecked`, `M-guard-containment-blind` | `tests/governance/test_ratchet.py::test_edited_row_rejected`, `tests/integration/test_guard.py::test_ignored_write_detected`, `tests/integration/test_guard.py::test_venv_change_detected`, `tests/integration/test_guard.py::test_ref_change_detected`, `tests/integration/test_guard.py::test_containment_detects_owned_leak`, `tests/integration/test_guard.py::test_finalizers_run_after_failed_leg` |
| R20 — process boundaries, suppression bans and static legs are observed rather than asserted by the subject | `tests/oracles/lint_config.toml` | value: source and configuration choices match their negative controls; observer: spawn audit records allowed and vetoed events with fresh nonces; real: pinned tools reject copied negative fixtures | `M-audit-hook-blind-execv`, `M-guard-process-allowlist-wide`, `M-guard-noqa-blind` | `tests/integration/test_spawn_audit.py::test_all_spawn_events_recorded`, `tests/governance/test_source_guards.py::test_subprocess_import_outside_process_module`, `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture` |
| R20 — completion and evidence refer to tests and lanes of the current run | `tests/oracles/check_steps.toml` | value: closure and evidence fixtures; real: pytester manifests joined to this run's collected, executed and passed ids | `M-evidence-nonce-unchecked`, `M-evidence-missing-citation-allowed`, `M-evidence-lane-refusal-off` | `tests/governance/test_run_evidence.py::test_manifest_nonce_required`, `tests/governance/test_plan_validator.py::test_plan_cited_ids`, `tests/unit/test_lane.py::test_refusal_when_done_lane_unmet`, `tests/governance/test_gate_plugin.py::test_manifest_matches_execution` |

## Not Proven By This Gate

- That an oracle captures every interpretation of natural-language intent, beyond its recorded cases and provenance. — not proven by any phase.
- That request-derived oracles predate their implementation when that ordering has no independent historical evidence. — not proven by any phase.
- That a host-acceptance evidence row describes a run that happened; its digest proves the covered tree is current. — not proven by any phase.
- Containment of a process that crosses neither a registered observer nor a private-server boundary. — not proven by any phase.
- Native Windows observer liveness queries. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 1.1: Oracle store and request-derived oracles [Done]

**Status**: Done
**Implementation**: `tests/harness/oracle.py`, `src/agentctl/check/steps.py`, `tests/oracles/command_surface.toml`, `tests/oracles/check_legs.toml`, `tests/oracles/launch_argv.toml`, `tests/oracles/session_names.toml`, `tests/oracles/preflight.toml`, `tests/oracles/auth_status.toml`, `tests/oracles/recovery_transitions.toml`, `tests/oracles/backoff.toml`, `tests/oracles/check_steps.toml`, `tests/oracles/lint_config.toml`, `tests/governance/test_oracles.py`
**Validation tests**: `tests/governance/test_oracles.py::test_quote_must_match_requirement`, `tests/governance/test_oracles.py::test_duplicate_row_id_rejected`, `tests/governance/test_oracles.py::test_loader_imports_no_subject`, `tests/governance/test_oracles.py::test_provenance_resolves`, `tests/governance/test_oracles.py::test_empty_oracle_rejected`, `tests/governance/test_oracles.py::test_amendment_chain_resolves`
**Mutants**: `M-oracle-quote-unchecked`, `M-oracle-duplicate-allowed`, `M-oracle-subject-import-allowed`, `M-oracle-provenance-unresolved`, `M-oracle-empty-accepted`, `M-oracle-amendment-cycle-allowed`
**Closes**: none
**Docs to update**: `documents/engineering/testing.md`, `documents/reference/external_tool_facts.md`

#### Objective

Anchor expected values to the request, recorded decisions and verified tool facts before a product subject exists.

#### Deliverables

- Each TOML row has a stable id, requirement, exact quote, provenance, input and expected value, with optional
  `amends`. The quote is a substring of that requirement's quote in `00-overview.md`, whose own quote anchors to
  the preserved request. `oracles.independence` validates the schema and provenance against those homes.
- Provenance resolves to `request:R<n>`, a versioned `tool:` fact in external tool facts, or a `decision:D-<nn>`
  row in `rationale.md`; missing ids, duplicate ids and unresolved provenance fail. An amendment names a prior row
  of the same requirement, forms no cycle and leaves the prior row intact; the latest valid amendment supplies
  the effective expectation, while the whole chain remains available to the ratchet.
- `assert_oracle` imports no `agentctl` module, accepts the subject from its caller, and `assert_rows` compares every effective row
  and reports mismatches by row id; an empty file fails. An expected digest is derived from the stated rule in the
  test rather than by importing the subject's digest helper.
- Freeze argv and agent-table rows, session-name cases, preflight order and auth classifications, recovery state
  transitions and backoff bounds. The agent-table rows of `launch_argv.toml` include the `recovery_text` constants
  with provenance `decision:D-48`. The full check-step and leg shapes are specification data, including later
  capabilities; only a step whose introducing sprint is built is executable, and no not-yet-built step claims a pass.
- Freeze the co-designed lint configuration from Sprint 0.2, and validate the existing command-surface and leg
  oracle rows with the same schema. Corrections append an amendment, and using the expectations or advancing to
  product work never requires a commit or human review.

#### Validation

1. A mismatched quote fails while the same row with its requirement's exact quote passes — `tests/governance/test_oracles.py::test_quote_must_match_requirement`; fails when quote validation is omitted; mutant `M-oracle-quote-unchecked`.
2. A duplicated id fails beside a distinct-id control — `tests/governance/test_oracles.py::test_duplicate_row_id_rejected`; fails when both ids are accepted; mutant `M-oracle-duplicate-allowed`.
3. A loader importing `agentctl`, including an aliased or relative import, fails beside a standard-library-only loader — `tests/governance/test_oracles.py::test_loader_imports_no_subject`; fails when package imports are permitted; mutant `M-oracle-subject-import-allowed`.
4. Each provenance form resolves, and an unknown request, decision or tool fact yields its named violation — `tests/governance/test_oracles.py::test_provenance_resolves`; fails when an unknown source is accepted; mutant `M-oracle-provenance-unresolved`.
5. An empty oracle fails beside one row whose subject is called and compared — `tests/governance/test_oracles.py::test_empty_oracle_rejected`; fails when an empty target set passes; mutant `M-oracle-empty-accepted`.
6. A valid amendment chain selects its latest expectation, while a missing target, cycle or cross-requirement amendment fails — `tests/governance/test_oracles.py::test_amendment_chain_resolves`; fails when a cycle is accepted; mutant `M-oracle-amendment-cycle-allowed`.

#### Remaining Work

None.

### Sprint 1.2: Mutant runner and corpus [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/mutants.py`, `tests/mutants/gate.toml`, `tests/governance/test_mutants.py`, `tests/fixtures/static_negative/`
**Validation tests**: `tests/governance/test_mutants.py::test_corpus`, `tests/governance/test_mutants.py::test_wrong_reason_rejected`, `tests/governance/test_mutants.py::test_survivor_rejected`, `tests/governance/test_mutants.py::test_exact_once_required`, `tests/governance/test_mutants.py::test_operator_set_closed`, `tests/governance/test_mutants.py::test_corpus_killer_rejected`, `tests/governance/test_mutants.py::test_parameter_killers_execute_current_cases`, `tests/governance/test_mutants.py::test_baseline_must_pass`, `tests/governance/test_mutants.py::test_runner_restores_scratch_tree`
**Mutants**: `M-mutant-any-failure-counts`, `M-mutant-survivor-accepted`, `M-mutant-multiple-match-accepted`, `M-mutant-unknown-operator-accepted`, `M-mutant-baseline-unchecked`
**Closes**: none
**Docs to update**: `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`

#### Objective

Require each deliberate defect to change a passing baseline into the specific failure its record names.

#### Deliverables

- A record holds id, operator, relative target, search and replacement text, killer node ids and reason substring.
  An ordinary pytest node may select one ASCII-named parameter case; live nodes, corpus recursion and malformed
  selectors remain invalid. Every selected killer must pass its baseline and fail by name under the defect;
  a missing parameter case is a baseline failure with its node and child output. Corpus assertions render the
  complete child diagnostic for baseline and defective failures.
  Operators are exactly `delete`, `negate`, `replace-literal`, `reorder`, `widen` and `short-circuit`; an unknown
  operator, missing killer or target escaping the scratch copy fails before execution.
- The runner copies the checkout into a run-owned scratch tree, requires the search text to match exactly once,
  and applies one mutant at a time. It restores the scratch bytes in a finalizer, including after timeouts and
  failed killers, and never writes to the real checkout.
- Run every named killer on the unmodified copy first: each passes, and its output lacks the reason substring.
  Under the mutant every killer fails and its output contains that substring; a survivor, unrelated failure,
  import error, patch failure or timeout never counts as a kill.
- Seed every explicit Phase 0 mutant and this phase's mutants into capability-named corpus files. Each record
  becomes a parametrized `test_corpus` case in the ordinary pytest leg, never a cached verdict or an optional run.
  Child killer invocations run exactly the named nodes outside the whole-suite gate-plugin session and cannot
  print gate evidence or contribute ids to its manifest; naming a corpus-driver test as a killer is rejected to
  prevent recursion. The outer gate collects and executes every corpus case and verifies every result.
  This sprint activates mutation execution:
  Phase 0 closes first through its direct tests and negative controls, and every later run also re-proves that
  Done phase by executing its declared retro-mutants. No earlier closure depends on a runner that is not built.
- The runner executes Python mutants here. The record schema reserves Haskell pure-kernel targets, but their
  executable support and its real tests land in Sprint 3.1 with the toolchain and package; no unexercised Haskell
  dispatch branch or runnable record exists here.

#### Validation

1. Every record's baseline and defective run meet the contract — `tests/governance/test_mutants.py::test_corpus`; fails when a record survives or a patch cannot apply; no mutant: this is the aggregate corpus check, while the following dedicated meta-tests kill runner defects without recursion.
2. An unrelated exception with no named reason is rejected, beside a defect producing the reason — `tests/governance/test_mutants.py::test_wrong_reason_rejected`; fails when any non-zero status counts; mutant `M-mutant-any-failure-counts`.
3. A no-op mutant is rejected beside a defect killed by its test — `tests/governance/test_mutants.py::test_survivor_rejected`; fails when passing killers count as kills; mutant `M-mutant-survivor-accepted`.
4. Zero and two search matches fail while one applies — `tests/governance/test_mutants.py::test_exact_once_required`; fails when the first of several matches is patched; mutant `M-mutant-multiple-match-accepted`.
5. An unregistered operator or a corpus-driver killer is refused beside registered operators and an ordinary killer — `tests/governance/test_mutants.py::test_operator_set_closed`, `tests/governance/test_mutants.py::test_corpus_killer_rejected`; fails when an unknown operator dispatches or corpus recursion is allowed; mutant `M-mutant-unknown-operator-accepted`.
6. A failing baseline is rejected and the scratch bytes are restored after each exit path — `tests/governance/test_mutants.py::test_baseline_must_pass`, `tests/governance/test_mutants.py::test_runner_restores_scratch_tree`; fails when a pre-existing failure is credited as a kill; mutant `M-mutant-baseline-unchecked`.

#### Remaining Work

None.

### Sprint 1.3: Ratchet, write-guard and venv integrity [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/ratchet.py`, `src/agentctl/check/writeguard.py`, `src/agentctl/check/steps.py`, `src/agentctl/check/validator/source.py`, `src/agentctl/process.py`, `tests/harness/git.py`, `tests/support.txt`, `tests/oracles/forbidden_surfaces.toml`, `tests/mutants/integrity.toml`, `.gitignore`, `pyproject.toml`, `tests/oracles/lint_config.toml`, `tests/governance/test_ratchet.py`, `tests/governance/test_forbidden_surfaces.py`, `tests/integration/test_guard.py`
**Validation tests**: `tests/governance/test_ratchet.py::test_deleted_row_rejected`, `tests/governance/test_ratchet.py::test_edited_row_rejected`, `tests/governance/test_ratchet.py::test_amends_row_accepted`, `tests/governance/test_ratchet.py::test_head_adapter_real`, `tests/governance/test_ratchet.py::test_config_weakening_rejected`, `tests/governance/test_forbidden_surfaces.py::test_fixture_and_live_tree`, `tests/integration/test_guard.py::test_write_detected`, `tests/integration/test_guard.py::test_ignored_write_detected`, `tests/integration/test_guard.py::test_ref_change_detected`, `tests/integration/test_guard.py::test_venv_change_detected`, `tests/integration/test_guard.py::test_containment_detects_owned_leak`, `tests/integration/test_guard.py::test_finalizers_run_after_failed_leg`
**Mutants**: `M-ratchet-allow-edit`, `M-ratchet-allow-delete`, `M-ratchet-config-widened`, `M-guard-parallel-runner-allowed`, `M-guard-skip-ignored`, `M-guard-ref-unchecked`, `M-guard-venv-unchecked`, `M-guard-containment-blind`
**Closes**: none
**Docs to update**: `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`

#### Objective

Hold gate data to the available HEAD baseline and keep the tested tree, refs and interpreter unchanged during check.

#### Deliverables

- `ratchet.append-only` parses oracle rows, mutant records and requirement rows from HEAD with read-only git and
  compares them to the tree. Removing or editing a baseline row fails; an added amendment preserves its original.
  Tool configurations only tighten: new ignores, exclusions, weaker severities or a lower coverage floor fail.
- A repository without HEAD reports `no baseline` and checks the live schema without claiming historical
  protection. The adapter distinguishes that state from unreadable or malformed baseline data, which fails.
- `write-guard-snapshot` records path, size and SHA-256 for the entire checkout, ignored paths included, excluding
  only `.git`; it separately records HEAD, refs and packed refs. `write-guard-compare` detects additions,
  removals, changed bytes and moved refs and runs in a finalizer once a snapshot exists.
- The run re-executes with `PYTHONPYCACHEPREFIX`, tool caches and coverage output under its temp directory.
  Snapshot installed distributions in the interpreter's environment, their metadata and recorded files before and
  after the run; any installation, removal or content change fails venv integrity. Its own redirected bytecode is
  outside the compared installation, and the checkout remains covered by the tree guard.
- `containment` checks registered observer pids and owned server sockets after teardown, then reads only the user's
  server's session list to reject a session bearing the run nonce. A private-server kill requires its socket to be
  under the run directory; containment and the write comparison still execute after a failed step.
- `tree.forbidden-surfaces` rejects Makefiles, justfiles, tox/nox, pre-commit, hooks, `.github/workflows` and script
  entry surfaces alongside check. Source modules, data fixtures and the clean-host Dockerfile are classified by
  purpose rather than a loose extension ban; the gate remains the single runner.

#### Validation

1. Edited and deleted baseline rows fail while an appended `amends` row passes — `tests/governance/test_ratchet.py::test_edited_row_rejected`, `tests/governance/test_ratchet.py::test_deleted_row_rejected`, `tests/governance/test_ratchet.py::test_amends_row_accepted`; fails when a protected row is changed in place; mutants `M-ratchet-allow-edit`, `M-ratchet-allow-delete`.
2. Read-only adapters distinguish temporary repositories with and without HEAD, and weakened config fails beside identical and tightened config — `tests/governance/test_ratchet.py::test_head_adapter_real`, `tests/governance/test_ratchet.py::test_config_weakening_rejected`; fails when an added ignore is accepted; mutant `M-ratchet-config-widened`.
3. A fixture containing each forbidden surface yields its named violation, while the live tree and support fixtures are clean — `tests/governance/test_forbidden_surfaces.py::test_fixture_and_live_tree`; fails when a parallel runner is accepted; mutant `M-guard-parallel-runner-allowed`.
4. A temporary checkout's ordinary or ignored write is detected beside an unchanged run — `tests/integration/test_guard.py::test_write_detected`, `tests/integration/test_guard.py::test_ignored_write_detected`; fails when ignored paths are omitted; mutant `M-guard-skip-ignored`.
5. A ref move in a disposable repository and a distribution edit in a disposable venv fail beside their unchanged controls — `tests/integration/test_guard.py::test_ref_change_detected`, `tests/integration/test_guard.py::test_venv_change_detected`; fails when either snapshot is omitted; mutants `M-guard-ref-unchecked`, `M-guard-venv-unchecked`.
6. A registered live observer pid is detected and then terminated by the test's finalizer; its dead-pid control passes — `tests/integration/test_guard.py::test_containment_detects_owned_leak`; fails when a registered leak is ignored; mutant `M-guard-containment-blind`.

#### Remaining Work

None.

### Sprint 1.4: Spawn audit, source guards and coverage [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/audit.py`, `src/agentctl/check/validator/source.py`, `src/agentctl/check/legs.py`, `tests/harness/nonce.py`, `tests/integration/test_spawn_audit.py`, `tests/governance/test_source_guards.py`, `tests/governance/test_gate_plugin.py`, `tests/integration/test_static_legs.py`, `src/agentctl/check/preconditions.py`, `src/agentctl/check/steps.py`, `tests/mutants/source.toml`, `tests/fixtures/static_negative/audit/actor.py.txt`, `tests/integration/test_runtime_boundaries.py`, `pyproject.toml`, `tests/oracles/lint_config.toml`, `src/agentctl/check/writeguard.py`, `src/agentctl/check/gate_plugin.py`, `src/agentctl/check/validator/plan.py`, `src/agentctl/cli.py`
**Validation tests**: `tests/integration/test_spawn_audit.py::test_all_spawn_events_recorded`, `tests/integration/test_spawn_audit.py::test_forbidden_spawn_vetoed`, `tests/integration/test_spawn_audit.py::test_nonce_replay_rejected`, `tests/governance/test_source_guards.py::test_subprocess_import_outside_process_module`, `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/governance/test_source_guards.py::test_no_test_branches`, `tests/governance/test_source_guards.py::test_no_login_construction`, `tests/governance/test_source_guards.py::test_lint_config_matches_oracle`, `tests/governance/test_source_guards.py::test_live_tree_clean`, `tests/governance/test_gate_plugin.py::test_coverage_gap_fails`, `tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ruff_format_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_ignores_user_config`, `tests/integration/test_spawn_audit.py::test_windows_command_line_and_veto_policy`, `tests/integration/test_spawn_audit.py::test_audit_input_boundaries`, `tests/integration/test_spawn_audit.py::test_malformed_event_refused`, `tests/governance/test_source_guards.py::test_invalid_and_empty_source_tree`, `tests/governance/test_source_guards.py::test_invalid_config_schema`, `tests/integration/test_runtime_boundaries.py::test_process_errors_and_teardown`, `tests/integration/test_runtime_boundaries.py::test_owned_child_escalation`, `tests/integration/test_runtime_boundaries.py::test_single_run_lock_releases`, `tests/integration/test_runtime_boundaries.py::test_preconditions_real_interpreters`, `tests/integration/test_runtime_boundaries.py::test_leg_followups_and_failures`, `tests/governance/test_ratchet.py::test_ratchet_parser_boundaries`, `tests/governance/test_ratchet.py::test_corrupt_and_missing_baselines`, `tests/governance/test_ratchet.py::test_git_read_vetoes`, `tests/unit/test_identity.py::test_python_floor`, `tests/governance/test_source_guards.py::test_coverage_exception_scope`, `tests/governance/test_gate_plugin.py::test_plugin_collection_boundaries`, `tests/governance/test_mutants.py::test_mutant_input_boundaries`, `tests/governance/test_mutants.py::test_mutant_filesystem_and_baseline_failures`, `tests/integration/test_guard.py::test_snapshot_error_boundaries`, `tests/integration/test_guard.py::test_invalid_observer_registry`, `tests/integration/test_guard.py::test_record_schema`, `tests/integration/test_guard.py::test_finalizer_outcomes`, `tests/integration/test_guard.py::test_validation_failure_stages`, `tests/integration/test_guard.py::test_gate_read_and_oracle_vetoes`, `tests/integration/test_guard.py::test_ref_and_liveness_read_errors`, `tests/integration/test_runtime_boundaries.py::test_check_command_failure_paths`, `tests/integration/test_runtime_boundaries.py::test_owned_child_decoding_failure`
**Mutants**: `M-audit-hook-blind-execv`, `M-audit-veto-disabled`, `M-audit-nonce-reused`, `M-guard-process-allowlist-wide`, `M-guard-noqa-blind`, `M-guard-test-branch-allowed`, `M-guard-login-spawn-allowed`, `M-guard-config-drift-allowed`, `M-guard-coverage-floor-lowered`, `M-guard-static-leg-noop`, `M-guard-type-severity-lowered`, `M-guard-user-config-leak`
**Closes**: none
**Docs to update**: `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`, `documents/engineering/code_standards.md`

#### Objective

Observe process effects without replacing the subject and prove that source, lint, type and coverage checks fire.

#### Deliverables

- `audit.py` installs a `sys.addaudithook` observer in the subject interpreter before a test invokes it. It records
  Python spawn, exec, system and posix-spawn events with exact argv and a fresh nonce; forbidden package-manager,
  sudo, `xcode-select --install` and ghcup install events raise before execution. Harmless probes are allowed and
  recorded as controls. Exec probes run in disposable child interpreters so their event records survive exec.
  Native Windows exec/spawn probes quote their API argument vectors with CRT rules, and require both those exact
  observed vectors and the child's independently written sentinel.
- `tests/harness/nonce.py` prefixes a fresh observer nonce with the check run's nonce; a stale or wrong record is
  rejected. No subject consumes a test-switch environment variable, and tests never monkeypatch the subject.
- `src.one-process-module` examines imports and process-call forms: Python spawns only in `process.py`, and Haskell
  imports `System.Process` only in `AgentCtl.Process`. The source checks apply to Haskell once its owning phase is
  built, with no missing-source success claimed beforehand.
- `src.suppression-ban` rejects `Any`, `cast`, ignore comments, skip/xfail/importorskip, warning suppression,
  Haskell `-Wno-*`, HLint ignores and formatter-disable markers; a coverage exception requires an exact allowlisted
  path and line with a reason. `src.no-test-branches` rejects package test switches; `src.no-login-construction`
  rejects executable login argv and login keystrokes, while remedy strings naming what the user types remain valid.
- `config.pinned` compares the live ruff, ty, pytest and coverage configuration to `lint_config.toml`, including the
  narrow process-module exceptions, explicit source walks and no exclusions. The pytest leg gains 100% branch
  coverage of the package, with data outside the tree; an uncovered branch fails check.
- Run each pinned Python static leg over a copied negative fixture and its corrected twin. A type error must be an
  error, not a warning; a fake user config that downgrades it changes nothing. Each tool must report at least one
  examined file, and each validator a non-empty owned subject set.

#### Validation

1. Every supported spawn event is recorded with argv and nonce, including exec in a child, beside a harmless observed probe — `tests/integration/test_spawn_audit.py::test_all_spawn_events_recorded`; fails when exec events disappear; mutant `M-audit-hook-blind-execv`.
2. A forbidden spawn is recorded and vetoed before an executable sentinel can run, while an allowed sentinel runs — `tests/integration/test_spawn_audit.py::test_forbidden_spawn_vetoed`; fails when the forbidden sentinel executes; mutant `M-audit-veto-disabled`.
3. Replayed records fail while a fresh observer record passes — `tests/integration/test_spawn_audit.py::test_nonce_replay_rejected`; fails when the expected nonce is not checked; mutant `M-audit-nonce-reused`.
4. Each source violation produces exactly its named check, beside a legal control and the live tree — `tests/governance/test_source_guards.py::test_subprocess_import_outside_process_module`, `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/governance/test_source_guards.py::test_no_test_branches`, `tests/governance/test_source_guards.py::test_no_login_construction`, `tests/governance/test_source_guards.py::test_live_tree_clean`; fails on a broadened process allowlist, ignored suppression, test switch or login execution; mutants `M-guard-process-allowlist-wide`, `M-guard-noqa-blind`, `M-guard-test-branch-allowed`, `M-guard-login-spawn-allowed`.
5. Altered tool config fails beside its exact oracle match, and a coverage gap fails beside a covered branch — `tests/governance/test_source_guards.py::test_lint_config_matches_oracle`, `tests/governance/test_gate_plugin.py::test_coverage_gap_fails`; fails when config drifts or the floor falls; mutants `M-guard-config-drift-allowed`, `M-guard-coverage-floor-lowered`.
6. Negative lint, formatting and type fixtures fail while corrected twins pass, with the type result unchanged under a hostile user config — `tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ruff_format_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_ignores_user_config`; fails when a leg is bypassed, a type error downgraded or user config leaks in; mutants `M-guard-static-leg-noop`, `M-guard-type-severity-lowered`, `M-guard-user-config-leak`.

#### Remaining Work

None.

### Sprint 1.5: Plan closure rules, lane summary and evidence line [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/evidence.py`, `src/agentctl/check/lanes.py`, `src/agentctl/check/validator/plan.py`, `src/agentctl/check/steps.py`, `tests/harness/host.py`, `tests/governance/test_run_evidence.py`, `tests/governance/test_plan_validator.py`, `tests/unit/test_lane.py`, `src/agentctl/resources/python-startup.pth`, `pyproject.toml`, `tests/oracles/python_startup.toml`, `tests/integration/test_python_startup.py`, `src/agentctl/check/plan_data.py`, `src/agentctl/check/validator/closure.py`, `src/agentctl/check/gate_plugin.py`, `.gitattributes`, `tests/mutants/evidence.toml`
**Validation tests**: `tests/governance/test_run_evidence.py::test_manifest_nonce_required`, `tests/governance/test_run_evidence.py::test_collected_executed_passed_equal`, `tests/governance/test_run_evidence.py::test_every_mutant_has_current_case`, `tests/governance/test_plan_validator.py::test_plan_gate_integrity`, `tests/governance/test_plan_validator.py::test_plan_cited_ids`, `tests/governance/test_plan_validator.py::test_plan_cited_paths`, `tests/governance/test_plan_validator.py::test_plan_evidence_rows`, `tests/governance/test_plan_validator.py::test_plan_lanes`, `tests/governance/test_plan_validator.py::test_validator_non_vacuous`, `tests/unit/test_lane.py::test_refusal_when_done_lane_unmet`, `tests/unit/test_lane.py::test_acceptance_lane_not_refused`, `tests/unit/test_lane.py::test_evidence_printed_only_after_full_pass`, `tests/integration/test_python_startup.py::test_startup_precedes_editable_imports`
**Mutants**: `M-evidence-nonce-unchecked`, `M-evidence-missing-citation-allowed`, `M-evidence-missing-mutant-allowed`, `M-evidence-path-unchecked`, `M-evidence-digest-unchecked`, `M-evidence-lane-refusal-off`, `M-evidence-empty-target-accepted`, `M-evidence-printed-after-failure`, `M-evidence-startup-bytecode`
**Closes**: R20
**Docs to update**: `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`, `documents/documentation_standards.md`

#### Objective

Make status consequences and evidence rows depend on the current run's tests, mutants, source tree and host facts.

#### Deliverables

- `post-run-verifier` requires this run's nonce and equal collected, executed and passed pytest id sets; no skip,
  deselection or zero-test result qualifies. Each corpus record has its passing parametrized case in that manifest.
- The isolated application environment disables import bytecode through its packaged startup policy before the
  console entry imports the editable package. This keeps the covered tree independent of interpreter version and
  checkout path, including the outer command before re-execution. The gate still redirects its tool caches and
  explicit coverage data to the run directory.
- `plan.cited-ids` requires every Done sprint's cited pytest id to have passed now; Haskell ids must appear in the
  suite listing and passing tasty report once the Haskell suite exists. `plan.cited-paths` requires each Done
  sprint's Implementation paths to exist and rejects `.build/` and log citations. These closure joins activate
  here and re-check earlier Done sprints; their absence does not prevent Phase 0 from closing on its own tests.
- `plan.gate-integrity` validates every declaration's row shape, classes and bidirectional owed/Confirms join;
  executable record, killer and result joins apply from each capability's introducing sprint, with the Phase 0
  retrospective boundary at Sprint 1.2. Planned declarations cannot claim executed evidence, and a live test cannot
  be a mutation killer. `validator.non-vacuous` requires a non-empty target set
  for every applicable check; an absent subject is allowed only while its owning phase is Planned and is reported
  as not applicable rather than passed.
- `tests/harness/host.py` records observed OS and architecture with the nonce and supplies the lane evaluator. Agent,
  multiplexer, toolchain and clean-recipe observations extend it with their owning capabilities; a lane whose
  observation has no implementation is unmet, never presumed met. Tests adapt only to the allowed host states.
- `plan.lanes` uses the closed lane vocabulary and refuses an unmet lane of a Done self-verifying phase;
  acceptance lanes are reported and never demanded for an unrelated check. `lane-summary` reports its observations
  and ratchet baseline only after the earlier steps and finalizers have succeeded.
- `plan.evidence-rows` validates row shape and lane and recomputes the digest over sorted relative paths, entry kinds
  and length-prefixed bytes of every file under `src/`, `tests/` and `pyproject.toml`, ignored and untracked inputs
  included. Symlinks contribute link text and resolved bytes; unreadable or escaping inputs fail. The native POSIX
  special-file control uses a runtime-checked FIFO interface that remains type-checkable on Windows. Recording a row
  cannot stale itself because the plan is outside Evidence covers. A covered
  change reopens a Done acceptance phase and clears its evidence in the same change.
- Only a full passing run prints the EVIDENCE row for each met lane, with the literal gate `agentctl check`, the
  current UTC date, tree digest and host detail. The row proves currency, not that a run occurred. Closure and
  product implementation proceed from executable evidence without a commit, human approval or interactive step.

#### Validation

1. A stale nonce, missing executed id or failed id fails beside a matching non-empty manifest — `tests/governance/test_run_evidence.py::test_manifest_nonce_required`, `tests/governance/test_run_evidence.py::test_collected_executed_passed_equal`; fails when replayed output qualifies; mutant `M-evidence-nonce-unchecked`.
2. Every corpus record has a passing current case, and deleting one result fails — `tests/governance/test_run_evidence.py::test_every_mutant_has_current_case`; fails when a missing mutant result is ignored; mutant `M-evidence-missing-mutant-allowed`.
3. Valid row, test and path joins pass while an absent applicable killer, missing citation result, missing path or stale digest yields exactly its named violation; adding or editing an ignored covered file also stales the digest — `tests/governance/test_plan_validator.py::test_plan_gate_integrity`, `tests/governance/test_plan_validator.py::test_plan_cited_ids`, `tests/governance/test_plan_validator.py::test_plan_cited_paths`, `tests/governance/test_plan_validator.py::test_plan_evidence_rows`; fails when a citation, path or covered byte is unchecked, while Planned future declarations remain structurally valid without results; mutants `M-evidence-missing-citation-allowed`, `M-evidence-path-unchecked`, `M-evidence-digest-unchecked`.
4. An empty owned target set fails while one valid subject passes; a Planned owner reports not applicable — `tests/governance/test_plan_validator.py::test_validator_non_vacuous`; fails when an applicable empty walk passes; mutant `M-evidence-empty-target-accepted`.
5. Constructed lane facts refuse a Done mux-host phase without a multiplexer, accept it with one, and report an unmet acceptance lane without refusing — `tests/governance/test_plan_validator.py::test_plan_lanes`, `tests/unit/test_lane.py::test_refusal_when_done_lane_unmet`, `tests/unit/test_lane.py::test_acceptance_lane_not_refused`; fails when the Done lane is waived; mutant `M-evidence-lane-refusal-off`.
6. Every earlier-step and finalizer failure suppresses the evidence row, while the fully passing control prints the expected lane and digest — `tests/unit/test_lane.py::test_evidence_printed_only_after_full_pass`; fails when a row is printed after failure; mutant `M-evidence-printed-after-failure`.
7. The installed startup policy and wheel mapping match the frozen oracle, and a real child leaves no import bytecode beside a `-S` control that writes it — `tests/integration/test_python_startup.py::test_startup_precedes_editable_imports`; fails when the packaged policy changes; mutant `M-evidence-startup-bytecode`.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — oracle provenance and amendments, named-reason mutants, observer nonces,
  source guards, the ratchet and automatic closure with the available baseline's historical limits.
- `documents/engineering/quality_gate.md` — the run-integrity steps, redirected bytecode, coverage, closure joins,
  lane evaluation and the evidence line's honest limit.
- `documents/engineering/code_standards.md` — the source guards, narrow process-module rule and suppression ban.

**Operations and reference docs to create/update:**

- `documents/reference/external_tool_facts.md` — the versioned facts supporting tool-derived oracle rows.

**Cross-references to add:**

- `documents/documentation_standards.md` — the validation and enforcement-citation links into testing and the gate.
- `documents/README.md` — the testing and external-fact homes in the documentation index.
