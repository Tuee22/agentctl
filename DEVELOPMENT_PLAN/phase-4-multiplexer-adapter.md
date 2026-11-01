# Phase 4 — Multiplexer adapter

**Status**: Planned
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
| R12.1 — the binary checks that tmux 3.2 or later (Linux, macOS) or psmux 3.4.0 or later (Windows) is available | `tests/oracles/mux_commands.toml` | value: version, floor, resolution-candidate and remedy cases through agentctl-core-eval; real: resolution under a constructed PATH without the multiplexer, and of the host's multiplexer against its floor; owed: macos-acceptance | `M-mux-floor-3-1`, `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os` | `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable` |
| R7 — the agent runs in a multiplexer pane exactly as its spec says (contributing) | `tests/oracles/mux_commands.toml` | real: rendered commands run against a private tmux server with the trampoline as the pane command; observer: the fake agent records argv, folder, environment keys, session and the nonce; owed: windows-psmux-acceptance | `M-mux-shell-joined-command`, `M-mux-spec-drops-environment`, `M-mux-bare-target` | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling` |
| R12 — an agent that exits at once leaves a dead pane holding its exit status for launch to relay (contributing) | `tests/oracles/mux_commands.toml` | value: where each multiplexer's dead-pane status is read; real: remain-on-exit set before the spec is written holds a fake agent that exits 3 as a dead pane reporting 3; observer: the fake agent's record with the nonce shows the agent ran | `M-mux-remain-on-exit-off`, `M-mux-psmux-status-from-pane` | `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`, `tests/integration/test_mux_real.py::test_instant_exit_status` |

## Not Proven By This Gate

- Real psmux: sessions through ConPTY, `=NAME` on commands other than `has-session`, the `has-session` readiness poll, PATHEXT resolution of `psmux.exe`, and the trampoline's status file. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Homebrew tmux on macOS, meeting its floor and driving private servers within macOS's socket-path limit. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- `attach-session` and `switch-client` from a real terminal inside the user's own server, which no test touches. — not proven by any phase.
- tmux versions other than the one the run observes: the 3.2 floor rests on tmux's recorded changes, and only the host's tmux runs. — not proven by any phase.
- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.

## Sprints

### Sprint 4.1: Resolution, version floors and session names as values [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux.hs`, `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Name.hs`, `src/agentctl/haskell/app/`, `src/agentctl/check/preconditions.py`, `tests/oracles/mux_commands.toml`, `tests/mutants/mux.toml`
**Validation tests**: `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `tests/unit/test_mux_values.py::test_session_name_oracle`, `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable`, `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`, `tests/unit/test_preconditions.py::test_socket_path_length`
**Mutants**: `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`, `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os`, `M-mux-name-allows-double-underscore`, `M-mux-socket-length-unchecked`
**Closes**: R12.1
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/engineering/quality_gate.md`, `documents/operations/troubleshooting.md`, `documents/reference/external_tool_facts.md`

#### Objective

Find the host's multiplexer by absolute path, hold it to its floor, and make a valid session name a value only the
smart constructor can produce.

#### Deliverables

- `AgentCtl.Process` gains its first operation: run an absolute executable with an explicit argv, environment and
  timeout, decoding its output as UTF-8; `src.one-process-module` now sees its Haskell subject.
- `AgentCtl.Mux` looks up `tmux` on PATH on Linux and macOS and `psmux.exe` through PATH and PATHEXT on Windows, never
  `tmux.exe` or `pmux.exe`, then runs `-V` through the runner and parses `tmux <version>`, such as `3.4` or `3.2a`, or
  `psmux <major>.<minor>.<patch> (<commit> <date>)`; an unrecognised string is refused and quoted.
- The floors are tmux 3.2 and psmux 3.4.0. A missing or too-old multiplexer is a typed failure with the host's remedy:
  the tmux package of the host's package manager on Linux, `brew install tmux` on macOS, `winget install psmux` on
  Windows.
- `AgentCtl.Session.Name` exports `SessionName` without its constructor; the smart constructor accepts only
  `[A-Za-z0-9_-]`, never empty, never with a leading `-`, never with `__`. Deriving a name from a folder is not here.
- `tests/oracles/mux_commands.toml` holds the version, resolution and remedy rows with `tool:` provenance; the
  constructor's rows are those of `tests/oracles/session_names.toml`, frozen in Sprint 1.1.
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
   mutant: an effect, and Haskell mutants target pure kernels.
6. The host's multiplexer resolves to an absolute path whose version meets the floor —
   `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`; fails when the runner mis-decodes `-V` output; no
   mutant, as in item 5.
7. A socket path of 101 bytes fails P6 and one of 100 passes — `tests/unit/test_preconditions.py::test_socket_path_length`;
   fails when the length is not checked; mutant `M-mux-socket-length-unchecked`.

#### Remaining Work

The whole sprint.

### Sprint 4.2: Typed command vocabulary, the one runner and the pane trampoline [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Command.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Tmux.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/PaneExec.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `tests/oracles/mux_commands.toml`, `tests/mutants/mux.toml`
**Validation tests**: `tests/unit/test_mux_values.py::test_render_oracle`, `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`, `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`, `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`
**Mutants**: `M-mux-bare-target`, `M-mux-shell-joined-command`, `M-mux-render-psmux-alias`, `M-mux-remain-on-exit-off`, `M-mux-psmux-status-from-pane`, `M-mux-spec-mode-unchecked`, `M-mux-spec-drops-environment`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/launch_contract.md`, `documents/engineering/code_standards.md`, `documents/reference/files_and_state.md`

#### Objective

Express every multiplexer action as a typed value with a pure rendering per multiplexer, run it through the one runner,
and make the pane run the trampoline rather than the agent's own argv.

#### Deliverables

- `AgentCtl.Mux.Command` holds the actions of the adapter's table: create the agent session
  (`new-session -d -s <name> -P -F '#{pane_id}' -- <binary> pane-exec <spec>`), `has-session`, `list-sessions` with a
  format, pane state through `display-message`, an `@agentctl_<key>` session option, pane-scoped `remain-on-exit` on
  and unset, `capture-pane`, `send-keys -l` and a separate Enter, `attach-session`, `switch-client` and `kill-session`.
- No value exists for `kill-server`, `kill-pane`, `respawn-pane`, `respawn-window`, `run-shell`, `if-shell`,
  `pipe-pane`, `source-file`, a global `set-option` or any shell string, and one command runs per invocation, never
  chained with `;`.
- Session targets render only from a `SessionName`, as `=NAME`; pane targets as the `%id` that `new-session` printed.
  `AgentCtl.Mux.Psmux` always invokes `psmux`.
- A dead pane's status is read from `#{pane_dead_status}`, or 128 plus `#{pane_dead_signal}` for a signal, on tmux,
  and from the trampoline's status file on psmux, whose `#{pane_dead_status}` is always 0.
- `AgentCtl.Process` interprets these values with the resolved multiplexer, an explicit environment and a timeout; on
  psmux it polls `has-session` with a bounded timeout after `new-session`.
- `AgentCtl.PaneExec`, the one command the binary runs without Python's handoff, waits up to 30 s for its spec,
  refuses one that is not a regular file of the invoking user or is wider than 0600 in a directory wider than 0700,
  deletes it after reading, and keeps the pane's `TERM`, `TMUX` and `TMUX_PANE`.
- Through `AgentCtl.Process` the trampoline changes to the spec's folder and calls `execve` on POSIX, or on Windows
  runs the agent as a child, writes its exit status to the status file atomically and exits with it; its own failure
  is printed in the pane before it exits. Its spec codec covers argv, folder, environment and the status path.
- `agentctl-core-eval` gains the render, dead-status, spec-codec and spec-acceptance subjects.

#### Validation

1. Every vocabulary value renders to its row for tmux and psmux — `tests/unit/test_mux_values.py::test_render_oracle`;
   fails on any argv difference, such as a bare session target, a pane command joined into one string or psmux called
   by its alias; mutants `M-mux-bare-target`, `M-mux-shell-joined-command`, `M-mux-render-psmux-alias`,
   `M-mux-remain-on-exit-off`.
2. Each multiplexer reads a dead pane's status where its row says —
   `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`; fails when psmux trusts `#{pane_dead_status}`; mutant
   `M-mux-psmux-status-from-pane`.
3. Spec modes, owners and file kinds are accepted or refused as their rows say —
   `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`; fails when a 0644 spec or a 0755 directory is
   accepted; mutant `M-mux-spec-mode-unchecked`.
4. Decoding an encoded spec returns it unchanged for argv holding `--`, the empty string, `x;`, `#{pane_id}`, `$(id)`
   and newlines, folders with spaces and `#`, and arbitrary environments —
   `haskell:agentctl-core-test/PaneExec/spec-round-trip`; fails when a variable or an empty element is lost; mutant
   `M-mux-spec-drops-environment`.
5. `pane-exec` on a spec naming an executable that exits 3 deletes the spec and exits 3, by `execve` on POSIX and
   through the status file on Windows, against the control that the spec existed when it started —
   `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`; fails when the spec survives or the
   status is lost; no mutant: an effect, and Haskell mutants target pure kernels.
6. On POSIX a 0644 spec, or one in a 0755 directory, is refused with a message and its program never runs, while the
   same spec at 0600 in a 0700 directory runs it — `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`;
   fails when the refusal is skipped; mutant `M-mux-spec-mode-unchecked`.

#### Remaining Work

The whole sprint.

### Sprint 4.3: Real isolated-server behaviour and the fake agent [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/app/`, `tests/harness/tmux.py`, `tests/mutants/mux.toml`
**Validation tests**: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`, `tests/integration/test_mux_real.py::test_containment_sees_leftover_server`, `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`, `tests/integration/test_fake_agent.py::test_record_carries_nonce`
**Mutants**: `M-mux-harness-kills-foreign-socket`, `M-mux-fake-record-drops-nonce`
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
  starts the private server itself with `-f /dev/null`, and runs `kill-server` only after asserting that the socket
  lies under the run dir; for psmux it sets an absolute `PSMUX_DATA_DIR` under the run dir and `PSMUX_NO_WARM=1`, and
  never ends psmux processes by image name.
- The real tests render each action through `agentctl-core-eval` and run it through the harness against the private
  server, with the trampoline as the pane command and the fake agent as the agent; the test writes each spec itself,
  and the spec's argv carries the observer's nonce as one argument.
- The `containment` step of Sprint 1.3 meets real tmux: a private server left alive, or a nonce-carrying session on
  the server it scans, fails it.

#### Validation

1. On a private server whose environment lacks a variable the caller sets, the fake agent records exactly the spec's
   argv, `x;`, `#{pane_id}`, `#(id)`, `$(id)`, `--`, the empty string and a newline included, the spec's folder, that
   variable among its keys, and the nonce, and on POSIX its pid is `#{pane_pid}` —
   `tests/integration/test_mux_real.py::test_private_server_roundtrip`; fails when an element is changed, split or
   dropped, a shell wraps the agent, or the pane gets the server's environment; mutants `M-mux-shell-joined-command`,
   `M-mux-spec-drops-environment`.
2. With remain-on-exit set on the pane before the spec is written, a fake agent that exits 3 at once leaves a dead pane
   whose status reads 3 (from the status file on psmux), against the control that a fake agent that stays running
   leaves a live pane — `tests/integration/test_mux_real.py::test_instant_exit_status`; fails when the pane vanishes or
   its status is lost; mutant `M-mux-remain-on-exit-off`.
3. `kill-session -t =ab` ends `ab` and leaves `ab-c` running, against the control that `ab` existed —
   `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`; fails when the target loses its `=`;
   mutant `M-mux-bare-target`.
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

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 4.1–4.3.

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
