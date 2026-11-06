# Phase 13 — macOS acceptance

**Status**: Done
**Depends on**: [Phase 10 — Recovery supervisor](phase-10-supervisor.md)
**Host lane**: macos
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: 2026-11-05 ; macos ; agentctl check ; pass ; tree ab7b56b948ad3702d59bea67ea3f6be4d9c94721bc5ab169507cdfdaf0f0b30e ; os=Darwin,arch=arm64,baseline=e7022baea09ae021d7f3780078d07dade9ea8556
**Evidence covers**: `src/` `tests/` `pyproject.toml`

> **Purpose**: Confirm on a Mac with the Xcode Command Line Tools and Homebrew tmux what the lower phases owe macOS:
> the darwin ghcup asset, Keychain-keyed `CLAUDE_CONFIG_DIR` isolation, the exec handoff and real Homebrew tmux.

## Phase Objective

This phase adds no code. It closes on the same `agentctl check`, run on a host meeting the macos lane: Darwin,
`xcode-select -p` succeeding, tmux at least 3.2, and agent-host. Existing host capabilities are observed automatically;
GUI setup is outside validation, and check never runs or waits for `xcode-select --install`. Tests adapt only to the OS
family, the multiplexer kind, the login state and the toolchain provenance, so the darwin run is the same suite taking
its darwin branches. What this host confirms:

- **The darwin ghcup asset.** The provisioning plan selects `x86_64-apple-darwin-ghcup-0.2.6.2` or
  `aarch64-apple-darwin-ghcup-0.2.6.2` for the host's architecture with its pinned SHA-256, as values on every host;
  here a ghcup at or above 0.1.50.2 is reused untouched, or with none the pinned asset is downloaded and verified.
  GHC 9.12.4 and cabal 3.16.1.0 then build the core binary host-native.
- **The Xcode probe.** The prerequisite probe reads `xcode-select -p` succeeding as the C toolchain present, so the
  plan installs nothing.
- **Keychain-keyed isolation.** On macOS claude keeps its credentials in the Keychain under an entry keyed to
  `CLAUDE_CONFIG_DIR`, so the logged-out-by-construction tests, with an empty `CLAUDE_CONFIG_DIR`, see claude logged
  out even when the user's own login sits in the Keychain. No test reads or writes the Keychain.
- **The exec handoff.** Python hands off to the core binary with `execve`, so the binary keeps agentctl's process,
  terminal and exit status on Darwin as on Linux.
- **Homebrew tmux.** The launch and multiplexer tests run against Homebrew's tmux on private servers whose socket
  paths stay within macOS's shorter limit, which precondition P6 holds to at most 100 bytes. macOS has no `/proc`, so
  the argv evidence there is the fake agent's record.

The lane summary prints the macos EVIDENCE line only when the lane holds, and the closing agent records it as Gate
evidence. A failure is fixed in the phase that introduced its cause
([§ A](development_plan_standards.md#a-one-continuous-constructive-narrative)), which stales the digest, and the run
repeats.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R3 — on Darwin ghcup is reused at or above the floor, or the pinned darwin asset is downloaded and verified | `tests/oracles/pins.toml`, `tests/oracles/bootstrap_plan.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/unit/test_ghcup.py::test_pins_match_oracle`, `tests/unit/test_plan.py::test_plan_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin` |
| R15 — on a Mac the prerequisite probe is `xcode-select -p` | `tests/oracles/prerequisites.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer` |
| R13 — an empty CLAUDE_CONFIG_DIR isolates claude from the user's Keychain login | `tests/oracles/auth_status.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/integration/test_agent_real.py::test_logged_out_by_construction` |
| R6 — the handoff to the core binary is execve on Darwin | `tests/oracles/command_surface.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`, `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary` |
| R7 — agentctl claude and agentctl codex launch into a Homebrew tmux session on Darwin | `tests/oracles/mux_commands.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last` |
| R12.1 — Homebrew tmux resolves, meets its floor and drives private servers | `tests/oracles/mux_commands.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/integration/test_mux_real.py::test_private_server_roundtrip` |
| R17 — native Darwin SIGINT and SIGTERM stop the supervisor and preserve watched panes | `tests/oracles/forbidden_actions.toml` | owed: macos-acceptance | none — this phase adds no code | `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions` |

## Not Proven By This Gate

- That the recorded run took place: the evidence row's digest proves the tree is current, not that a run happened ([§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes)). — not proven by any phase.
- Completing the Xcode Command Line Tools dialog, which only a person can do. — not proven by any phase.
- The macOS architecture the host does not have: one run confirms one of x86_64 and arm64. — not proven by any phase.
- The toolchain provenance the host does not have: a Mac with its own ghcup confirms reuse, and one without confirms the pinned darwin download. — not proven by any phase.
- The pinned ghcup download through a python.org Python whose certificate store was never installed, where urllib fails certificate verification. — not proven by any phase.
- A logged-in launch on macOS, whose lane requires no login and which has no `/proc` for the argv check. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Confirms

- R20 — Darwin snapshots preserve private spec bytes and native owner/mode facts, and missing or oversized files fail (owed by [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md)).
- R3 — on Darwin the plan selects the darwin ghcup 0.2.6.2 asset for the host's architecture and its pinned SHA-256, and the host's provenance branch holds: an existing ghcup at or above 0.1.50.2 untouched, or the pinned asset downloaded, verified and used (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).
- R15 — on a Mac the prerequisite probe is `xcode-select -p`, its verdict agrees with the test's own independent check, and with the Command Line Tools present the plan installs nothing (owed by [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)).
- R13 — with an empty `CLAUDE_CONFIG_DIR`, `claude auth status` exits 1 although the user's own login may be in the Keychain, because the Keychain entry is keyed to the config dir (owed by [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md)).
- R6 — on Darwin Python hands off with `execve`, so the warm passthrough's only spawn is the binary's execve and its exit status is the command's (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R7 — `agentctl claude` and `agentctl codex` launch into a Homebrew tmux session on Darwin, the fake agent recording the final argv in place of `/proc` (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R12.1 — Homebrew's tmux resolves on PATH, meets the 3.2 floor and runs the private-server tests within macOS's socket-path limit (owed by [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md)).

- R17 — native Darwin SIGINT and SIGTERM stop the supervisor and preserve watched panes without ending any managed or adopted target (owed by [Phase 10 — Recovery supervisor](phase-10-supervisor.md)).

## Sprints

### Sprint 13.1: macOS run and evidence [Done]

**Status**: Done
**Implementation**: none — this phase adds no code
**Validation tests**: `tests/unit/test_ghcup.py::test_pins_match_oracle`, `tests/unit/test_plan.py::test_plan_oracle`, `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`, `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`, `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`, `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`, `haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`, `haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`
**Mutants**: none — this phase adds no code
**Closes**: none
**Docs to update**: none — this phase changes no document

#### Objective

Record the EVIDENCE line of a passing `agentctl check` on a Mac that meets the macos lane.

#### Deliverables

- Native first-run preparation uses the host harness to record initial toolchain absence before provisioning; an existing toolchain confirms reuse instead, as the bootstrap provenance contract states.
- A Darwin host meeting the macos lane as `tests/harness/host.py` observes it: `xcode-select -p` succeeds, tmux at
  least 3.2 from Homebrew, and claude and codex resolvable.
- One unchanged `agentctl check` run there, with the darwin values, the Xcode probe, Homebrew tmux and the
  Keychain-backed claude under test.
- The lane summary's line `EVIDENCE <YYYY-MM-DD> ; macos ; agentctl check ; pass ; tree <sha256> ; <detail>`, copied
  into `**Gate evidence**`; the plan validator recomputes the digest over Evidence covers and compares the lane and
  the digest only.
- A failure fixed by rewriting the phase that introduced its cause, then a fresh run on the changed tree.

#### Validation

1. The pins hold each darwin triple's asset name and SHA-256 — `tests/unit/test_ghcup.py::test_pins_match_oracle`;
   fails when a darwin row differs from `tests/oracles/pins.toml`; no mutant: this phase adds no code.
2. The plan's darwin rows choose reuse or the pinned download by the host's ghcup —
   `tests/unit/test_plan.py::test_plan_oracle`; fails when a darwin row's actions differ from
   `tests/oracles/bootstrap_plan.toml`; no mutant: this phase adds no code.
3. This Mac's toolchain matches its provenance: a reused ghcup is the one the run resolved, or the downloaded one
   carries the darwin pin — `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`; fails when the bytes
   differ from the pin; no mutant: this phase adds no code.
4. The `xcode-select -p` probe's verdict agrees with the test's own independent check —
   `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`; fails when the two disagree; no
   mutant: this phase adds no code.
5. `claude auth status` with an empty `CLAUDE_CONFIG_DIR`, the auth variables removed and `DISABLE_AUTOUPDATER=1`
   exits 1 — `tests/integration/test_agent_real.py::test_logged_out_by_construction`; fails when the Keychain login
   leaks into the isolated config; no mutant: this phase adds no code.
6. The handoff mode for Darwin is execve — `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`; fails when
   Darwin is given the child mode; no mutant: this phase adds no code.
7. On a digest hit the warm passthrough's only spawn is the binary's execve —
   `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`; fails when Darwin spawns a
   child or rebuilds; no mutant: this phase adds no code.
8. `claude` and `codex` from a temp folder create the oracle-named Homebrew tmux session, and the fake agent records
   the final argv — `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`; fails when the session or
   the argv differs from its oracle row; no mutant: this phase adds no code.
9. A private Homebrew tmux server starts under a short `TMUX_TMPDIR`, runs the vocabulary and is torn down —
   `tests/integration/test_mux_real.py::test_private_server_roundtrip`; fails when the socket path exceeds its limit
   or a rendered command misbehaves; no mutant: this phase adds no code.

10. Native SIGINT and SIGTERM stop the foreground supervisor with exit 0, release its lock and preserve managed and adopted pane identities —
   `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`; fails on an ignored native stop request, a non-zero exit, a held lock or any changed target identity; no mutant: this phase adds no code.

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
