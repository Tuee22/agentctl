# Phase 4 — Multiplexer adapter

**Status**: Done
**Depends on**: [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md)
**Host lane**: mux-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R12.1

> **Purpose**: Give the core binary one typed, version-checked way to drive tmux or psmux, the pane trampoline that
> keeps user text off the multiplexer's command line, and the fake agent through which later phases observe what
> reached the agent.

## Phase Objective

[The multiplexer adapter](../documents/architecture/multiplexer_adapter.md) is the contract, and
[the pane trampoline](../documents/architecture/launch_contract.md#the-pane-trampoline) owns the spec rules.

- **Resolution and floors (R12.1).** `AgentCtl.Mux` resolves tmux on Linux and macOS, at least 3.2, or `psmux.exe` on
  Windows, at least 3.4.0 and never through its `tmux.exe` alias, once per command, and a missing or too-old
  multiplexer is a typed failure carrying the remedy for the host's OS.
- **One vocabulary, one runner.** `AgentCtl.Mux.Command` is a closed set of actions with no `kill-server`, respawn or
  shell-string value, rendered by the pure `AgentCtl.Mux.Tmux` and `AgentCtl.Mux.Psmux`; `AgentCtl.Process`, the only
  importer of `System.Process`, runs every spawn and exec in the binary. Sessions are targeted as `=NAME` from a
  `SessionName` and panes by `%id`.
- **The trampoline.** The pane command is always `agentctl-core pane-exec <spec>`, so argv, folder and environment
  travel in a 0600 spec file and no user text, and no secret, reaches tmux or psmux parsing.
- **Sessions on the user's normal server.** Production passes no `-L` or `-S`; tests reach a private server through
  `TMUX_TMPDIR`, or `PSMUX_DATA_DIR` with `PSMUX_NO_WARM=1`, set up by `tests/harness/tmux.py`.
- **The proof.** Every rendering is a `value` row of `tests/oracles/mux_commands.toml` on every host; real private tmux
  servers and `agentctl-fake-agent` show the behaviour on this lane; the folder-derived name and the launch that uses
  all of this come from [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R12.1 — the binary checks that tmux 3.2 or later (Linux, macOS) or psmux 3.4.0 or later (Windows) is available | `tests/oracles/mux_commands.toml` | value: version, floor, resolution-candidate and remedy cases through agentctl-core-eval; real: constructed missing and present paths, the native host's version, and an independent nonce-bound lane observation; owed: macos-acceptance | `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`, `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os` | `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable`, `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`, `tests/integration/test_mux_resolution.py::test_host_probe_and_constructed_absence` |
| R8 — a multiplexer name can only be constructed from safe ASCII (contributing) | `tests/oracles/session_names.toml` | value: independent constructor acceptance cases through the native evaluator; real: a checked-name caller compiles while an external constructor caller fails at its named diagnostic | `M-mux-name-allows-double-underscore`, `M-mux-name-constructor-exported` | `tests/unit/test_mux_values.py::test_session_name_oracle`, `tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private` |
| R20 — bounded command effects use explicit argv, environment, UTF-8 and a finite deadline (contributing) | none — native child output, status and timeout markers are observed directly | real: the native test executable receives literal argv and environment, emits Unicode and invalid bytes, exits nonzero and reaches a controlled timeout | none — these native effects have direct two-sided controls | `haskell:agentctl-core-test/ProcessReal/utf8-argv-environment-and-status`, `haskell:agentctl-core-test/ProcessReal/line-endings-preserved`, `haskell:agentctl-core-test/ProcessReal/missing-and-relative-executables`, `haskell:agentctl-core-test/ProcessReal/invalid-utf8-is-refused`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`, `haskell:agentctl-core-test/ProcessReal/timeout-after-streams-close` |
| R20 — private Unix socket paths fit the common byte bound (contributing) | none — the 100-byte boundary and its Unicode twin are explicit independent values | value: 100 bytes pass and 101 bytes fail | `M-mux-socket-length-unchecked` | `tests/unit/test_preconditions.py::test_socket_path_length` |
| R20 — spec bytes and access facts come from a bounded native snapshot (contributing) | `tests/oracles/mux_commands.toml` | value: independent mode, owner and kind cases and a codec round-trip; real: an owned private file yields its exact bytes, while missing and oversized files fail; owed: macos-acceptance; owed: windows-psmux-acceptance | `M-mux-spec-mode-unchecked`, `M-mux-spec-drops-environment`, `M-mux-spec-mode-unchecked-at-boundary` | `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`, `haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`, `haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`, `tests/integration/test_pane_exec.py::test_unsafe_spec_refused` |
| R7 — the agent runs in a multiplexer pane exactly as its spec says (contributing) | `tests/oracles/mux_commands.toml` | value: independent command-rendering and spec-codec cases; real: rendered commands run against a private tmux server with the trampoline as the pane command; observer: the fake agent records argv, folder, environment keys, session and the nonce; owed: windows-psmux-acceptance | `M-mux-shell-joined-command`, `M-mux-render-psmux-alias`, `M-mux-spec-drops-environment`, `M-mux-bare-target`, `M-mux-spec-decode-drops-environment`, `M-mux-bare-target-at-boundary` | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`, `tests/unit/test_mux_values.py::test_render_oracle`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated` |
| R12 — an agent that exits at once leaves a dead pane holding its exit status for launch to relay (contributing) | `tests/oracles/mux_commands.toml` | value: where each multiplexer's dead-pane status is read and when native reaping is requested; real: remain-on-exit set before the spec is written holds an actual exit 3 as a dead pane reporting 3 beside a live-pane control; observer: a held fake child closes its streams and a spawn audit releases it only after a repeated status query | `M-mux-remain-on-exit-off`, `M-mux-psmux-status-from-pane`, `M-mux-dead-before-status`, `M-mux-reap-policy-inverted` | `tests/unit/test_mux_values.py::test_render_oracle`, `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`, `tests/unit/test_mux_values.py::test_reap_policy_oracle`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status` |
| R20 — native process boundaries reject extra spawn owners and test controls (contributing) | none — independent forbidden source examples have allowed twins | value: C, header and Haskell examples exercise the complete source walk | `M-mux-native-exec-scope-unchecked`, `M-mux-foreign-exec-owner-unchecked`, `M-mux-native-suppressions-unchecked`, `M-mux-native-test-branches-unchecked` | `tests/governance/test_source_guards.py::test_native_process_boundary`, `tests/governance/test_source_guards.py::test_native_controls_and_walk` |
| R20 — private server cleanup refuses a foreign endpoint (contributing) | none — two disposable native servers provide owned and foreign scope controls | real: the harness kills its own server and refuses the second server outside its scope | `M-mux-harness-kills-foreign-socket` | `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket` |
| R7 — the fake agent binds its record to the current run (contributing) | none — a fresh nonce and the started process pid are independent observations | observer: the native fake agent records literal argv and environment keys, and missing and replayed nonces fail | `M-mux-fake-record-drops-nonce` | `tests/integration/test_fake_agent.py::test_record_carries_nonce` |

## Not Proven By This Gate

- Real psmux: sessions through ConPTY, `=NAME` on commands other than `has-session`, the `has-session` readiness poll, PATHEXT resolution of `psmux.exe`, and the trampoline's status file. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Homebrew tmux on macOS, meeting its floor and driving private servers within macOS's socket-path limit. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- Native Darwin spec snapshots and owner/mode observations. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- Native Windows spec snapshots, owner-SID and DACL privacy observations. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- `attach-session` and `switch-client` from a real terminal inside the user's own server, which no test touches. — not proven by any phase.
- tmux versions other than the one the run observes: the 3.2 floor rests on tmux's recorded changes, and only the host's tmux runs. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 4.1: Resolution, version floors and session names as values [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux.hs`, `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Name.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/check/preconditions.py`, `src/agentctl/check/steps.py`, `src/agentctl/check/haskell.py`, `tests/harness/host.py`, `tests/oracles/mux_commands.toml`, `tests/oracles/session_names.toml`, `tests/mutants/mux.toml`, `tests/unit/test_mux_values.py`, `tests/integration/test_mux_resolution.py`, `tests/unit/test_haskell_gate.py`, `tests/unit/test_preconditions.py`, `tests/integration/test_guard.py`
**Validation tests**: `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `tests/unit/test_mux_values.py::test_session_name_oracle`, `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable`, `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`, `tests/unit/test_preconditions.py::test_socket_path_length`, `tests/integration/test_mux_resolution.py::test_socket_directory_inspection`, `tests/integration/test_mux_resolution.py::test_host_probe_and_constructed_absence`, `tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private`, `haskell:agentctl-core-test/ProcessReal/utf8-argv-environment-and-status`, `haskell:agentctl-core-test/ProcessReal/line-endings-preserved`, `haskell:agentctl-core-test/ProcessReal/missing-and-relative-executables`, `haskell:agentctl-core-test/ProcessReal/invalid-utf8-is-refused`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`, `haskell:agentctl-core-test/ProcessReal/timeout-after-streams-close`, `tests/unit/test_haskell_gate.py::test_xml_requires_actual_nonempty_cases`, `tests/unit/test_haskell_gate.py::test_native_evidence_must_be_fresh_and_complete`
**Mutants**: `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`, `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os`, `M-mux-name-allows-double-underscore`, `M-mux-socket-length-unchecked`, `M-mux-name-constructor-exported`
**Closes**: R12.1
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/engineering/quality_gate.md`, `documents/engineering/code_standards.md`, `documents/engineering/testing.md`, `documents/operations/troubleshooting.md`, `documents/reference/external_tool_facts.md`, `documents/reference/files_and_state.md`

#### Objective

Find the host's multiplexer by absolute path, hold it to its floor, and make a valid session name a value only the
smart constructor can produce.

#### Deliverables

- `AgentCtl.Process` gains its first operation: run an absolute executable with an explicit argv, environment and
  timeout, decoding its output as UTF-8. Executable components link the threaded runtime so process waits permit
  deadline delivery; `src.one-process-module` now sees its Haskell subject.
- `AgentCtl.Mux` looks up `tmux` on PATH on Linux and macOS and `psmux.exe` through PATH and PATHEXT on Windows, never
  `tmux.exe` or `pmux.exe`, then runs `-V` through the runner and parses `tmux <version>`, such as `3.4` or `3.2a`, or
  `psmux <major>.<minor>.<patch> (<commit> <date>)`; an unrecognised string is refused and quoted.
- The floors are tmux 3.2 and psmux 3.4.0. A missing or too-old multiplexer is a typed failure with the host's remedy:
  the tmux package of the host's package manager on Linux, `brew install tmux` on macOS, `winget install psmux` on
  Windows.
- `AgentCtl.Session.Name` exports `SessionName` without its constructor; the smart constructor accepts only
  `[A-Za-z0-9_-]`, never empty, never with a leading `-`, never with `__`. Deriving a name from a folder is not here.
- `tests/oracles/mux_commands.toml` holds independent version, resolution and remedy rows. Tool facts cite their
  verified `tool:` source; chosen floors and fallback policy cite D-57. Provenance amendments preserve prior rows
  and expectations, and comparisons select every effective row. Constructor acceptance appends independent D-07
  cases to `tests/oracles/session_names.toml` without changing its frozen folder-derivation cases.
- `agentctl-core-eval` gains the version-floor, resolution-candidate, remedy and session-name subjects.
- Precondition P6: the private tmux socket path under the run dir is at most 100 bytes.

#### Validation

1. `tmux 3.1c` and `psmux 3.3.8` are refused, `tmux 3.2`, `tmux 3.2a`, `tmux 3.4` and `psmux 3.4.0` accepted, and an
   unknown string refused — `tests/unit/test_mux_values.py::test_version_floor_oracle`; fails when 3.1c passes or 3.2a
   fails; mutants `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`.
2. Each OS family's candidates are `tmux`, or `psmux.exe` through PATHEXT and never an alias —
   `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`; fails when Windows accepts `tmux.exe`; mutant
   `M-mux-tmux-alias-on-windows`.
3. Each OS family gets its remedy row — `tests/unit/test_mux_values.py::test_remedy_oracle`; fails when Windows is told
   to use brew; mutant `M-mux-remedy-wrong-os`.
4. `api-claude` is accepted and `a__b`, `-a`, `a.b`, `a b` and the empty name refused —
   `tests/unit/test_mux_values.py::test_session_name_oracle`; fails when `__` is accepted; mutant
   `M-mux-name-allows-double-underscore`.
5. Under a constructed PATH linking every allowed executable but the multiplexer, resolution is the typed failure with
   its remedy, while the same PATH with the multiplexer linked in resolves —
   `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable`; fails when a missing multiplexer passes; no
   mutant: direct native missing/present controls.
6. The host's multiplexer resolves to an absolute path whose version meets the floor —
   `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`; fails when the runner mis-decodes `-V` output; no
   mutant, as in item 5.
7. A socket path of 101 bytes fails P6 and one of 100 passes — `tests/unit/test_preconditions.py::test_socket_path_length`;
   fails when the length is not checked; mutant `M-mux-socket-length-unchecked`.
8. A caller of the smart constructor compiles while an external constructor caller fails with `GHC-01928` —
   `tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private`; fails when the constructor
   is exported; mutant `M-mux-name-constructor-exported`.
9. Native process controls hold for UTF-8, literal argv, explicit environment, exit status, absent executables and
   timeouts — `haskell:agentctl-core-test/ProcessReal/utf8-argv-environment-and-status`, `haskell:agentctl-core-test/ProcessReal/line-endings-preserved`,
   `haskell:agentctl-core-test/ProcessReal/missing-and-relative-executables`,
   `haskell:agentctl-core-test/ProcessReal/invalid-utf8-is-refused`,
   `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`,
   `haskell:agentctl-core-test/ProcessReal/timeout-after-streams-close`; fails when bytes use locale decoding, argv
   enters a shell, failures become success or a process wait blocks deadline delivery after output closes; no
   mutant: native effect controls with a monotonic elapsed-time bound.
10. The native lane observation is nonce-bound and agrees with an independent version call, while the same PATH
    without the native tool is unmet — `tests/integration/test_mux_resolution.py::test_host_probe_and_constructed_absence`;
    fails when an absent or unusable executable qualifies the lane; no mutant: native two-sided observation.
11. Run-directory ownership selects the predicted Unix socket endpoint and an unavailable directory fails, while
    Windows needs no Unix endpoint — `tests/integration/test_mux_resolution.py::test_socket_directory_inspection`;
    fails when a filesystem error is ignored; no mutant: native filesystem controls.
12. Real native case groups record real evidence and pure groups record value evidence, and forged classes fail the
    current-run join — `tests/unit/test_haskell_gate.py::test_xml_requires_actual_nonempty_cases`,
    `tests/unit/test_haskell_gate.py::test_native_evidence_must_be_fresh_and_complete`; fails when the group convention
    or manifest classes are ignored; no mutant: two-sided evidence controls.

#### Remaining Work

None.

### Sprint 4.2: Typed multiplexer command vocabulary [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Command.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Tmux.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `src/agentctl/haskell/app/Eval.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `tests/unit/test_mux_values.py`, `tests/oracles/mux_commands.toml`, `tests/mutants/mux.toml`
**Validation tests**: `tests/unit/test_mux_values.py::test_render_oracle`, `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`
**Mutants**: `M-mux-bare-target`, `M-mux-shell-joined-command`, `M-mux-render-psmux-alias`, `M-mux-remain-on-exit-off`, `M-mux-psmux-status-from-pane`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`

#### Objective

Express the adapter's closed action vocabulary and dead-status policy as pure values with one rendering per multiplexer.

#### Deliverables

- `AgentCtl.Mux.Command` holds create, has-session, list-sessions, show-options, list-panes, pane state, identity
  options, pane-scoped remain-on-exit on and unset, capture, literal text, Enter, attach, switch and kill-session.
- No value exists for kill-server, kill-pane, respawn, run-shell, if-shell, pipe-pane, source-file, a global option
  or a shell string. A rendering contains one action, never a separator chain.
- Session targets render from an opaque `SessionName` as `=NAME`; opaque pane ids contain `%` and ASCII digits.
  Identity keys are closed and opaque values contain only the safe ASCII alphabet of D-58.
- Creation renders the published binary, `pane-exec` and the generated spec path as separate arguments. No user
  argv, environment or working-directory option reaches multiplexer parsing. Psmux renders `psmux.exe`.
- Tmux dead status uses a positive signal as 128 plus that signal, otherwise its nonnegative exit status. Psmux
  uses its spec status file exclusively. Missing or negative status is unavailable.
- The JSONL evaluator compares rendering and dead-status subjects to independent oracle rows.

#### Validation

1. Every action renders exactly to its tmux and psmux rows, including paths with spaces and native Windows paths —
   `tests/unit/test_mux_values.py::test_render_oracle`; fails when a target is bare, the trampoline is shell-joined,
   an alias is selected or remain-on-exit is off; mutants `M-mux-bare-target`, `M-mux-shell-joined-command`,
   `M-mux-render-psmux-alias`, `M-mux-remain-on-exit-off`.
2. Forbidden actions, malformed targets, unsafe identity values and nonpositive capture lengths are refused beside
   every valid action — `tests/unit/test_mux_values.py::test_render_oracle`; fails when invalid input decodes as an
   action; no mutant: independent negative rows.
3. Exit codes, signals and unavailable statuses follow each multiplexer source rule —
   `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`; fails when psmux trusts pane status; mutant
   `M-mux-psmux-status-from-pane`.

#### Remaining Work

None.

### Sprint 4.3: Private launch-spec codec and native snapshot [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/PaneExec/Spec.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/native_fs.c`, `src/agentctl/haskell/src/AgentCtl/native_utf8.h`, `src/agentctl/haskell/test/SpecTests.hs`, `src/agentctl/haskell/test/Main.hs`, `src/agentctl/haskell/app/Eval.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `tests/oracles/mux_commands.toml`, `tests/mutants/mux.toml`, `tests/unit/test_mux_values.py`, `src/agentctl/check/validator/source.py`, `tests/governance/test_source_guards.py`
**Validation tests**: `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `haskell:agentctl-core-test/PaneExec/pane-environment`, `haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`, `haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`, `haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`, `tests/governance/test_source_guards.py::test_native_process_boundary`, `tests/governance/test_source_guards.py::test_native_controls_and_walk`
**Mutants**: `M-mux-spec-mode-unchecked`, `M-mux-spec-drops-environment`, `M-mux-native-exec-scope-unchecked`, `M-mux-native-suppressions-unchecked`, `M-mux-native-test-branches-unchecked`, `M-mux-foreign-exec-owner-unchecked`
**Closes**: none
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/engineering/code_standards.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`

#### Objective

Establish one private spec snapshot boundary: its codec, pure access policy and real native filesystem observations.
The native ABI is infrastructure for this boundary, spanning its small Haskell and C modules together.

#### Deliverables

- The spec codec holds literal argv, the canonical folder, the complete caller environment and the status path.
  Environment-bearing records have no Show instance.
- The pure access policy requires a regular file and directory owned by the invoking user, file permissions no
  wider than 0600 and directory permissions no wider than 0700. Independent cases cover modes, owners and kinds.
- A small C ABI reads native metadata and snapshots the opened regular file, with a bounded size. POSIX opens the
  parent and then the file relative to its descriptor, refusing symbolic links. Windows checks real owner SIDs and
  DACLs, refusing reparse points; it never substitutes emulated POSIX ownership for Windows security.
- Haskell has no CPP and the Cabal components are unconditional. Native C sources compile with warnings as errors;
  the native platform selects its actual system APIs within the C ABI.
- Source guards cover C and headers, limit native exec to its adapter and its Haskell owner, and reject native
  shell/spawn APIs, warning suppressions and test-control branches.
- The evaluator gains spec-codec and spec-acceptance subjects. Native tests observe private snapshots and missing
  files, and the pure codec test preserves adversarial argv and arbitrary environments.

#### Validation

1. Mode, owner and file-kind cases match independent expectations —
   `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`; fails when a 0644 file or 0755 directory passes;
   mutant `M-mux-spec-mode-unchecked`.
2. Encoding and decoding preserve argv with empty elements, `--`, `x;`, format expressions and newlines, folders
   with spaces and `#`, the environment and status path — `haskell:agentctl-core-test/PaneExec/spec-round-trip`;
   fails when an environment value is lost; mutant `M-mux-spec-drops-environment`.
3. A real private file yields its bytes and native access facts, and missing or oversized files yield typed errors beside
   that successful control — `haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`,
   `haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`,
   `haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`; fails when metadata, reads or bounds are fabricated; no
   mutant: native filesystem effects.
4. Pane variables replace their caller values and server-only variables stay absent beside retained caller variables —
   `haskell:agentctl-core-test/PaneExec/pane-environment`; fails when pane identity or the caller environment is lost;
   no mutant: explicit two-sided value controls.

5. Native process scope, binding ownership, suppressions and test controls reject negative examples beside legal
   exec and file-read controls — `tests/governance/test_source_guards.py::test_native_process_boundary`,
   `tests/governance/test_source_guards.py::test_native_controls_and_walk`; fails when native code bypasses the
   source boundary; mutants `M-mux-native-exec-scope-unchecked`, `M-mux-native-suppressions-unchecked`,
   `M-mux-native-test-branches-unchecked`, `M-mux-foreign-exec-owner-unchecked`.

#### Remaining Work

None.

### Sprint 4.4: Native process interpretation and the pane trampoline [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Types.hs`, `src/agentctl/haskell/src/AgentCtl/Mux.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Command.hs`, `src/agentctl/haskell/src/AgentCtl/native_process.c`, `src/agentctl/haskell/src/AgentCtl/PaneExec.hs`, `src/agentctl/haskell/app/Core.hs`, `tests/integration/test_pane_exec.py`, `src/agentctl/bootstrap/build.py`, `src/agentctl/haskell/test/MuxTests.hs`, `src/agentctl/haskell/test/SpecTests.hs`
**Validation tests**: `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`, `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`, `tests/integration/test_pane_exec.py::test_background_binary_errors`, `tests/integration/test_pane_exec.py::test_malformed_spec_preserved`, `tests/integration/test_pane_exec.py::test_exec_failure_is_visible`, `tests/integration/test_pane_exec.py::test_delayed_spec_published_atomically`, `tests/integration/test_pane_exec.py::test_missing_spec_times_out`, `haskell:agentctl-core-test/ProcessReal/foreground-exit-status`, `haskell:agentctl-core-test/SpecReal/status-file-validation`, `haskell:agentctl-core-test/ProcessReal/closed-parent-input`
**Mutants**: `M-mux-spec-mode-unchecked-at-boundary`, `M-mux-spec-decode-drops-environment`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/launch_contract.md`, `documents/engineering/code_standards.md`, `documents/reference/files_and_state.md`, `documents/engineering/binary_build.md`

#### Objective

Establish the native process lifetime boundary and consume the private spec through the pane trampoline.
The infrastructure spans the shared type module, process bindings, native execution ABI and core entry point.

#### Deliverables

- `AgentCtl.Process` interprets typed commands through the resolved multiplexer, explicit environment and a
  deadline; psmux creation polls has-session with a bounded deadline.
- `pane-exec` is the one core command accepted without Python's handoff. It waits up to 30 s for a spec, refuses
  unsafe access or malformed content, deletes an accepted spec after reading and keeps the pane's TERM, TMUX and
  TMUX_PANE values.
- The trampoline changes to the spec folder and calls execve through AgentCtl.Process on POSIX. Windows runs an
  inherited-stream child, atomically writes its exit status to the status path and exits with it. Trampoline
  failures print in the pane and exit nonzero.
- No user text passes through shell assembly or multiplexer parsing, and environment values appear on no command
  line. The native execution ABI performs the real OS operation and exposes no test switch.

#### Validation

1. A spec naming an executable that exits 3 exists before invocation, is deleted, and the invocation exits 3; the
   POSIX pid is preserved and Windows writes status —
   `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`; fails when the spec survives,
   a shell wraps the program or its status or caller environment is lost; mutant `M-mux-spec-decode-drops-environment`; native pid/status controls remain two-sided.
2. Unsafe POSIX file and directory modes are refused with a message and the program never runs, beside the same
   private spec that runs successfully — `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`; fails when
   access validation is bypassed; mutant `M-mux-spec-mode-unchecked-at-boundary`.
3. Malformed JSON, invalid program values and unsafe status paths fail without deleting the source or executing the
   program — `tests/integration/test_pane_exec.py::test_malformed_spec_preserved`; fails when an invalid source is
   consumed or the status path aliases the spec; no mutant: explicit native negative controls beside item 1.
4. The application-owned background boundary starts a working binary and refuses supplied input, unknown targets
   and an unavailable cwd — `tests/integration/test_pane_exec.py::test_background_binary_errors`; fails when an
   internal execution bypasses the shared resolver or cannot be reaped; no mutant: native two-sided controls.
5. A missing native executable produces a visible failure after consuming a valid spec, and Windows publishes its
   failure status — `tests/integration/test_pane_exec.py::test_exec_failure_is_visible`; fails when exec fails
   silently; no mutant: native failure beside the working program of item 1.
6. A delayed atomic spec publication runs its program, while a spec absent for the real thirty-second deadline
   times out visibly — `tests/integration/test_pane_exec.py::test_delayed_spec_published_atomically`,
   `tests/integration/test_pane_exec.py::test_missing_spec_times_out`; fails when waiting is absent or unbounded;
   no mutant: native timing controls.
7. Foreground programs leave their started markers and preserve exit 0 and exit 3 —
   `haskell:agentctl-core-test/ProcessReal/foreground-exit-status`; fails when inherited-stream execution is
   fabricated or loses status; no mutant: native two-sided controls.
8. Private status files accept nonnegative exit codes and reject negative values, booleans, malformed JSON and
   relative paths — `haskell:agentctl-core-test/SpecReal/status-file-validation`; fails when missing or invalid
   status becomes success; no mutant: native file controls.
9. Closing the parent stdin still permits a nested bounded command with exact binary output, beside the open-input
   control — `haskell:agentctl-core-test/ProcessReal/closed-parent-input`,
   `haskell:agentctl-core-test/ProcessReal/line-endings-preserved`; fails when native pipe allocation reuses a closed
   standard descriptor incorrectly; no mutant: native descriptor controls.

#### Remaining Work

None.

### Sprint 4.5: Real isolated-server behaviour and the fake agent [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/app/`, `tests/harness/tmux.py`, `tests/mutants/mux.toml`, `tests/integration/test_mux_real.py`, `tests/integration/test_tmux_harness.py`, `tests/integration/test_fake_agent.py`, `src/agentctl/haskell/test/MuxFixture.hs`, `src/agentctl/haskell/test/Main.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/native_process.c`, `tests/conftest.py`, `tests/support.txt`
**Validation tests**: `tests/unit/test_mux_values.py::test_reap_policy_oracle`, `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`, `tests/integration/test_mux_real.py::test_containment_sees_leftover_server`, `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`, `tests/integration/test_fake_agent.py::test_record_carries_nonce`, `tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status`
**Mutants**: `M-mux-reap-policy-inverted`, `M-mux-harness-kills-foreign-socket`, `M-mux-fake-record-drops-nonce`, `M-mux-bare-target-at-boundary`, `M-mux-dead-before-status`
**Closes**: none
**Docs to update**: `documents/engineering/testing.md`, `documents/architecture/multiplexer_adapter.md`

#### Objective

Show the vocabulary and the trampoline working against a real tmux server the test owns, through an observer that
records what reached the agent.

#### Deliverables

- `agentctl-fake-agent`, a cabal executable outside suite routing, is copied into a temp bin as `claude` or `codex`
  (`.exe` on Windows); it writes one record of its argv, working directory, environment keys (never values), the
  multiplexer session it runs in, its pid and the nonce into a directory the test names, then exits at once with a
  configured status or stays running.
- `tests/harness/tmux.py` makes `TMUX_TMPDIR` a short 0700 directory under the run dir, unsets `TMUX` and `TMUX_PANE`,
  owns the private foreground server with `-D -f /dev/null`, and runs `kill-server` only after asserting that the socket
  lies under the run dir; for psmux it sets an absolute `PSMUX_DATA_DIR` under the run dir and `PSMUX_NO_WARM=1`, and
  never ends psmux processes by image name.
- The real tests render each action through `agentctl-core-eval` and run it through the harness against the private
  server through the test-only native command fixture, invoking the production interpreter. Independent raw
  clients observe the server, with the trampoline as the pane command and the fake agent as the agent; the test writes each spec itself,
  and the spec's argv carries the observer's nonce as one argument.
- The `containment` step of Sprint 1.3 meets real tmux: a private server left alive, or a nonce-carrying session on
  the server it scans, fails it.

- A dead tmux pane with no published status requests normal child reaping through the native runner. The runner
  reads the backend's server pid and sends only SIGCHLD after validating it as positive and bounded. psmux retains
  its status-file path. Neither this request nor status polling sends pane input or weakens the deadline.

#### Validation

1. On a private server whose environment lacks a variable the caller sets, the fake agent records exactly the spec's
   argv, `x;`, `#{pane_id}`, `#(id)`, `$(id)`, `--`, the empty string and a newline included, the spec's folder, that
   variable among its keys, and the nonce, and on POSIX its pid is `#{pane_pid}` —
   `tests/integration/test_mux_real.py::test_private_server_roundtrip`; fails when an element is changed, split or
   dropped, a shell wraps the agent, or the pane gets the server's environment; no new mutant: the pure rendering
   and codec mutants are killed by their declared controls in Sprints 4.2–4.4.
2. With remain-on-exit set on the pane before the spec is written, a fake agent that exits 3 at once leaves a dead pane
   whose status reads 3 (from the status file on psmux), against the control that a fake agent that stays running
   leaves a live pane — `tests/integration/test_mux_real.py::test_instant_exit_status`; fails when the pane vanishes or
   its status is lost; no new mutant: the remain-on-exit rendering mutant has its declared Sprint 4.2 killer.
3. `kill-session -t =ab` ends `ab` and leaves `ab-c` running, against the control that `ab` existed —
   `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`; after ab ends, subject queries
   and another kill for ab must fail while ab-c stays alive; fails when the target loses its `=`;
   mutant `M-mux-bare-target-at-boundary`.
4. The containment step fails while a private server under the run dir is alive or a session carrying the nonce exists
   on the server it scans, and passes once the harness has killed them —
   `tests/integration/test_mux_real.py::test_containment_sees_leftover_server`; fails when the scan is blind; no mutant:
   the scan's mutants belong to Sprint 1.3.
5. The harness refuses to kill a server whose socket lies outside the run dir, against the control that it kills its
   own — `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`; fails when the socket path
   is not asserted; mutant `M-mux-harness-kills-foreign-socket`.
6. A fake-agent record without the run's nonce is rejected, while the record of a direct run carries the nonce and the
   argv it was given — `tests/integration/test_fake_agent.py::test_record_carries_nonce`; fails when a nonce-less
   record is accepted; mutant `M-mux-fake-record-drops-nonce`.

7. A nonce-bound fake child closes all streams while staying alive. The status observer keeps querying and a spawn
   audit releases that child only on a later query, after which its published status must be 3 —
   `tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status`; fails when a closed
   terminal is mistaken for a published exit status; mutant `M-mux-dead-before-status`.

8. The reap policy requests only a dead tmux pane whose status is missing, while alive panes, known statuses and
   psmux never request it — `tests/unit/test_mux_values.py::test_reap_policy_oracle`; fails when the missing-status
   predicate is inverted; mutant `M-mux-reap-policy-inverted`.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/multiplexer_adapter.md` — resolution and floors, the vocabulary and its renderings, targets
  and session options, the hazards the trampoline removes, psmux's differences, and the isolation tests run under.
- `documents/architecture/launch_contract.md` — the pane trampoline's spec rules, waiting, refusal and status file,
  which this phase builds and launch uses.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — private tmux servers and the kill-server guard, psmux isolation, and the fake
  agent's record with its nonce.
- `documents/engineering/quality_gate.md` — precondition P6.
- `documents/engineering/code_standards.md` — `AgentCtl.Process` as the one runner and the vocabulary's missing values.

**Operations and reference docs to create/update:**

- `documents/operations/troubleshooting.md` — a missing or too-old multiplexer, with the install command per OS.
- `documents/reference/external_tool_facts.md` — the tmux and psmux facts behind the floors and the renderings.
- `documents/reference/files_and_state.md` — the spec file and the Windows status file.

**Cross-references to add:**

- `documents/architecture/multiplexer_adapter.md` — links `documents/architecture/launch_contract.md` for the spec rules.
