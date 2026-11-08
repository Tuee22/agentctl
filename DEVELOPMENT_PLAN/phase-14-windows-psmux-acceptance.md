# Phase 14 — Windows and psmux acceptance

**Status**: Active
**Depends on**: [Phase 10 — Recovery supervisor](phase-10-supervisor.md)
**Host lane**: windows-psmux
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: none recorded
**Evidence covers**: `src/` `tests/` `pyproject.toml`

> **Purpose**: Confirm on Windows x86_64 with psmux what the lower phases owe Windows: the mingw64 `ghcup.exe` under
> `C:\ghcup`, real psmux behind the pane trampoline, subprocess exit codes, PATHEXT resolution, case-folded folder
> identity and UTF-8 decoding.

## Phase Objective

This phase adds no code. It closes on the same `agentctl check`, run on a host meeting the windows-psmux lane:
Windows x86_64, psmux at least 3.4.0, and native `claude.exe` and `codex.exe`, already resolvable as the host harness
observes automatically. Host setup is outside validation. Every psmux process the tests start gets an absolute,
test-owned `PSMUX_DATA_DIR` and `PSMUX_NO_WARM=1`, and teardown never ends psmux processes by image name. What this
host confirms:

- **ghcup on Windows.** With no ghcup, the bootstrap downloads `x86_64-mingw64-ghcup-0.2.6.2.exe` to
  `C:\ghcup\bin\ghcup.exe` and verifies its pinned SHA-256, with no MSYS2 bootstrap; a ghcup at or above 0.1.50.2 is
  reused untouched. GHC 9.12.4 and cabal 3.16.1.0 install with `--no-set`, and the forward-slash paths
  `ghcup whereis` prints are used as given.
- **Real psmux behind the trampoline.** The pane runs `agentctl-core pane-exec <spec>` with no `-e` value on the
  psmux command line, so the agent gets the caller's environment from the spec file and none of psmux's injected
  variables. remain-on-exit holds a pane whose agent ends inside the startup window, and because psmux reports
  `#{pane_dead_status}` as 0, the agent's exit status comes from the trampoline's status file. Exact `=NAME` targets,
  `kill-session`, capture and `send-keys -l` behave as the vocabulary declares.
- **Subprocess exit codes.** Python runs the core binary as a child and exits with its status, so every documented
  exit code reaches the user's shell unchanged.
- **PATHEXT.** psmux and the agents resolve through PATH and PATHEXT to native `.exe` files, and a `.cmd` or `.bat`
  shim earlier on PATH is refused with its remedy, because cmd.exe would re-parse its arguments.
- **Case-folded identity.** The hash form and the `@agentctl_folder` comparison case-fold the canonical path, so one
  folder reached with different letter case is one session and re-attaches.
- **UTF-8 decoding.** psmux and agent output is decoded as UTF-8 explicitly, never as the cp1252 that Python's
  subprocess uses by default on Windows.

The lane summary prints the windows-psmux EVIDENCE line only when the lane holds, and the closing agent records it as
Gate evidence. A failure, such as a psmux difference the values did not foresee, is fixed in the phase that introduced
its cause ([§ A](development_plan_standards.md#a-one-continuous-constructive-narrative)), which stales the digest, and
the run repeats.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R20 — native observer liveness detects an owned live process and accepts its reaped-pid control | `tests/oracles/lint_config.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/integration/test_guard.py::test_containment_detects_owned_leak` |
| R3 — on Windows ghcup is reused, or the pinned mingw64 ghcup.exe is downloaded to C:\ghcup and verified | `tests/oracles/pins.toml`, `tests/oracles/bootstrap_plan.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/unit/test_plan.py::test_plan_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin` |
| R7 — sessions run under real psmux through the trampoline, its status file and remain-on-exit | `tests/oracles/mux_commands.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status` |
| R6 — the handoff runs the core binary as a child and exits with its status | `tests/oracles/command_surface.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status` |
| R12.2 — agents resolve through PATHEXT to native executables and shims are refused | `tests/oracles/preflight.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/integration/test_agent_real.py::test_logged_out_by_construction` |
| R8 — the canonical folder is case-folded on Windows, so one folder is one session | `tests/oracles/session_names.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight` |
| R18 — the supervisor captures and sends through real psmux | `tests/oracles/forbidden_actions.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/e2e/test_supervisor_run.py::test_second_instance_refused` |
| R17 — native Windows console events stop the supervisor and preserve watched panes | `tests/oracles/forbidden_actions.toml` | owed: windows-psmux-acceptance | none — this phase adds no code | `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions` |

## Not Proven By This Gate

- That the recorded run took place: the evidence row's digest proves the tree is current, not that a run happened ([§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes)). — not proven by any phase.
- Windows on ARM64, for which no GHC bindist exists and which agentctl refuses. — not proven by any phase.
- The toolchain provenance the host does not have: a host with its own ghcup confirms reuse, and one without confirms the pinned mingw64 download. — not proven by any phase.
- A host whose policy forbids writing `C:\ghcup` at the drive root. — not proven by any phase.
- A human attaching to a psmux session from a real console window, which the test runner, holding no console of its own, cannot drive. — not proven by any phase.
- A logged-in launch on Windows, whose lane requires no login. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Confirms

- R20 — Windows snapshots use real owner-SID and DACL queries, preserve private spec bytes, and refuse missing or oversized files (owed by [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md)).
- R20 — native Windows observer liveness uses read-only process queries, detecting an owned live child and accepting its reaped-pid control (owed by [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md)).

- R3 — on Windows the plan selects `x86_64-mingw64-ghcup-0.2.6.2.exe` and its pinned SHA-256 for `C:\ghcup\bin\ghcup.exe`, with no MSYS2 bootstrap, and the host's provenance branch holds: an existing ghcup untouched, or the pinned one downloaded, verified and used (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).
- R7 — under real psmux the trampoline gives the agent the caller's environment with no `-e` on the psmux command line, remain-on-exit holds an instantly exiting pane, and the agent's exit status comes from the status file while `#{pane_dead_status}` reads 0 (owed by [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md)).
- R6 — Python runs the core binary as a child process and exits with its exit code unchanged (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R12.2 — claude and codex resolve through PATH and PATHEXT to native `.exe` files, and a `.cmd` or `.bat` shim is refused with its remedy (owed by [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md)).
- R8 — the hash form and folder identity case-fold the canonical path, so re-running in the same folder under different letter case re-attaches (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R18 — the supervisor's capture, `send-keys -l` and separate Enter work through real psmux, and its lock holds on Windows (owed by [Phase 10 — Recovery supervisor](phase-10-supervisor.md)).

- R17 — native Windows console events stop the supervisor and preserve watched panes without ending any managed or adopted target (owed by [Phase 10 — Recovery supervisor](phase-10-supervisor.md)).

## Sprints

### Sprint 14.1: Windows run and evidence [Active]

**Status**: Active
**Implementation**: none — this phase adds no code
**Validation tests**: `tests/unit/test_plan.py::test_plan_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`, `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/e2e/test_supervisor_run.py::test_second_instance_refused`, `tests/integration/test_guard.py::test_containment_detects_owned_leak`, `haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`, `haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`, `haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`
**Mutants**: none — this phase adds no code
**Closes**: none
**Docs to update**: none — this phase changes no document

#### Objective

Record the EVIDENCE line of a passing `agentctl check` on a Windows host with psmux.

#### Deliverables

- Native first-run preparation uses the host harness to record initial toolchain absence before provisioning; an existing toolchain confirms reuse instead, as the bootstrap provenance contract states.
- A Windows x86_64 host meeting the windows-psmux lane as `tests/harness/host.py` observes it: psmux at least 3.4.0
  and native `claude.exe` and `codex.exe`.
- One unchanged `agentctl check` run there, every psmux process under a test-owned `PSMUX_DATA_DIR` with
  `PSMUX_NO_WARM=1`.
- The lane summary's line `EVIDENCE <YYYY-MM-DD> ; windows-psmux ; agentctl check ; pass ; tree <sha256> ; <detail>`,
  copied into `**Gate evidence**`; the plan validator recomputes the digest over Evidence covers and compares the lane
  and the digest only.
- A failure fixed by rewriting the phase that introduced its cause, then a fresh run on the changed tree.

#### Validation

1. The provisioning plan's Windows rows select the mingw64 asset, its SHA-256 and `C:\ghcup\bin\ghcup.exe` —
   `tests/unit/test_plan.py::test_plan_oracle`; fails when a Windows row differs from
   `tests/oracles/bootstrap_plan.toml`; no mutant: this phase adds no code.
2. The toolchain matches its observed provenance: a reused ghcup untouched, or `ghcup.exe`'s sha256 equal to the pin —
   `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`; fails when the bytes differ from the pin; no
   mutant: this phase adds no code.
3. A private psmux namespace starts, runs the vocabulary and is torn down, the fake agent reporting the caller's
   environment — `tests/integration/test_mux_real.py::test_private_server_roundtrip`; fails when a `-e` value or an
   injected psmux variable reaches the agent; no mutant: this phase adds no code.
4. A fake agent exiting 3 inside the startup window leaves a dead pane whose status file reads 3 while
   `#{pane_dead_status}` reads 0 — `tests/integration/test_mux_real.py::test_instant_exit_status`; fails when the status
   comes from psmux; no mutant: this phase adds no code.
5. The core binary's exit code reaches the caller through the child-process handoff —
   `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`; fails when the status is lost or rewritten; no
   mutant: this phase adds no code.
6. PATHEXT resolution picks the native `.exe` and refuses a `.cmd` or `.bat` shim, here on a real Windows PATH —
   `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`; fails when a shim is accepted; no mutant: this phase adds
   no code.
7. A launch from the same folder under different letter case re-attaches to one session —
   `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`; fails when a second session appears; no mutant: this phase
   adds no code.
8. Under psmux the supervisor sends the recovery text once after the initial delay, and its lock refuses a second
   instance — `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`,
   `tests/e2e/test_supervisor_run.py::test_second_instance_refused`; fails when psmux capture or `send-keys -l`
   misbehaves or the lock does not hold; no mutant: this phase adds no code.

9. Native Ctrl+C and Ctrl+Break in a private console stop the foreground supervisor with exit 0, release its lock and preserve managed and adopted pane identities —
   `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`; fails on an ignored native stop request, a non-zero exit, a held lock or any changed target identity; no mutant: this phase adds no code.

#### Remaining Work

Run the complete gate on a Windows x86_64 host with psmux and native agent executables, and record evidence for the current covered tree.

## Remaining Work

Sprint 14.1 requires a Windows x86_64 host with psmux and native agent executables and passing gate evidence for the current covered tree.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- None.
