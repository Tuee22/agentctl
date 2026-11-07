# Phase 8 — Pane observation and classification

**Status**: Done
**Depends on**: [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md)
**Host lane**: agent-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R18.1

> **Purpose**: Capture each pane's screen, normalise it, fingerprint its error block, classify it per agent onto the closed screen-class vocabulary over fixtures with recorded provenance, and show the class in `status`.

## Phase Objective

This phase gives the binary eyes. `AgentCtl.Observe.Capture` reads a pane through the typed
vocabulary of [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md),
`AgentCtl.Observe.Normalize` turns the capture into comparable text, `AgentCtl.Observe.Fingerprint`
identifies normalised error content conservatively, and `AgentCtl.Observe.Classify.Claude` and
`AgentCtl.Observe.Classify.Codex` map a screen onto exactly one class: `IdlePrompt`, `Working`,
`ApprovalDialog`, `PartialInput`, `TrustDialog`, `BypassWarning`, `LoginScreen`, `Overloaded`,
`UsageLimit`, `AuthError`, `ContextExhausted`, `Exited` or `Unknown`. Everything after the capture
is pure, so a screen is a value and its class is a function of it.

- Precedence is part of the classifier: a dead pane is `Exited` whatever it shows; a dialog, partial
  input or work in progress dominates any error still in scrollback; an error class means the error
  is the latest output and the agent's input prompt below it is empty. A screen matching nothing is
  `Unknown`, and nothing is ever sent to an `Unknown` screen.
- Fixtures under `tests/fixtures/screens/<agent>/<class>/<id>.txt` carry a provenance sidecar:
  `captured`, through a capture `AGENTS.md` sanctions, with the agent's version and the capture
  command, or `documented`, with the URL of the official docs or changelog it reproduces. The
  sidecar names an evidence span, which must occur verbatim in the fixture. A class backed only by
  `documented` fixtures is listed below as not proven.
- Fingerprints feed the fingerprint gating of R18.3, which closes in
  [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md); the supervisor
  of [Phase 10 — Recovery supervisor](phase-10-supervisor.md) is the first code that acts on a
  class.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18.1 — screens are classified per agent, distinguishing transient overload from usage limits, authentication errors, context exhaustion and crashes | `tests/fixtures/screens/` | value: agentctl-core-eval classifier cases over every fixture and every precedence pair; observer: native capture round-trip, visual twins and changed-cursor retry on a private multiplexer server; real: unattended live launch or refusal and screen classification; owed: live-agent-acceptance | `M-classify-usage-limit-as-overload`, `M-classify-auth-error-as-overload`, `M-classify-context-as-overload`, `M-classify-overload-over-approval`, `M-classify-ignore-partial-input`, `M-classify-overload-over-working`, `M-classify-dead-pane-by-text`, `M-classify-placeholder-as-partial`, `M-classify-placeholder-ignores-style`, `M-classify-placeholder-ignores-cursor`, `M-capture-ignore-cursor-change`, `M-classify-status-stale-capture`, `M-classify-status-other-agent` | `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Classify/dead-pane-is-exited`, `haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence`, `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`, `tests/integration/test_capture_real.py::test_capture_keeps_prompt_visuals`, `tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`, `tests/e2e/test_status_screen.py::test_screen_column_shows_fixture_class`, `tests/e2e/test_status_screen.py::test_screen_column_uses_the_agents_classifier`, `tests/live/test_live_classification.py::test_live_screen_classes` |
| R18.3 — errors are fingerprinted so stale scrollback never re-triggers | `tests/fixtures/screens/` | value: equal normalised error content retains its fingerprint despite redraw or position, while changed error content changes it | `M-capture-fingerprint-constant`, `M-capture-fingerprint-includes-redraw` | `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`, `haskell:agentctl-core-test/Fingerprint/different-error-differs` |

## Not Proven By This Gate

- Live classification of logged-in claude and codex screens as `TrustDialog`, `BypassWarning` or `IdlePrompt`. — owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md).
- Live `IdlePrompt` classification when the user has not already trusted the fixed live folder, since the live screen is then a dialog that nothing answers. — not proven by any phase.
- Real `Overloaded`, `UsageLimit`, `AuthError` and `ContextExhausted` screens, which no lane can produce on demand; their classes rest on fixtures, and a class whose fixtures are all `documented` is consistent with its docs, not with a real screen. — not proven by any phase.
- `Working`, `ApprovalDialog` and `PartialInput` screens that are not `captured` fixtures, since capturing them needs prompts that spend the user's quota. — not proven by any phase.
- Capture through a real psmux, with its UTF-8 decoding and line joining. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Screens or renderings outside the declared fixtures and live observations. — not proven by any phase.
- Recovery from a nonempty-looking suggestion without recognizable faint styling and stable cursor evidence; ambiguous text remains partial input. — not proven by any phase.
- Distinguishing a genuine identical error recurrence from stale text: content-only fingerprints deliberately suppress both once handled in the supervisor run, even after intervening work. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 8.1: Capture, normalisation and fingerprints [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/Capture.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Normalize.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Fingerprint.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Command.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Tmux.hs`, `tests/oracles/mux_commands.toml`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `tests/fixtures/terminal/utf8-and-wrap.txt`, `tests/mutants/capture.toml`, `tests/integration/test_capture_real.py`
**Validation tests**: `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`, `tests/integration/test_capture_real.py::test_capture_keeps_prompt_visuals`, `tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`, `haskell:agentctl-core-test/Normalize/idempotent`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`, `haskell:agentctl-core-test/Fingerprint/different-error-differs`
**Mutants**: `M-capture-no-join`, `M-capture-locale-decoding`, `M-capture-ignore-cursor-change`, `M-capture-normalise-not-idempotent`, `M-capture-fingerprint-constant`, `M-capture-fingerprint-includes-redraw`
**Closes**: none
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/architecture/multiplexer_adapter.md`, `documents/reference/external_tool_facts.md`, `documents/engineering/testing.md`

#### Objective

Turn a pane into a comparable screen value and fingerprint its normalised error content, retaining
identity across redraws and repeated identical text without claiming an unobserved occurrence offset.

#### Deliverables

- `AgentCtl.Observe.Capture` issues `capture-pane -p -J -S -<n>` for a bounded tail through the typed
  vocabulary and `AgentCtl.Process`, decodes the output as UTF-8 explicitly, and reads the pane's
  dead state with it, so `Exited` never depends on text. It also records an ANSI-styled, unjoined viewport and cursor
  geometry between matching native snapshots, retrying changes within the existing capture deadline.
- `AgentCtl.Observe.Normalize` is pure: it normalises line endings, strips trailing spaces, drops
  trailing blank lines and keeps the bounded tail; normalising twice equals normalising once.
- `AgentCtl.Observe.Fingerprint` is pure: a fingerprint is the SHA-256 of the normalised error block alone,
  so a redraw, scrolling or identical text emitted again keeps it. Changed error content gives a new one.
  A typed error block keeps its preceding and following text for inspection, while hashing consumes its content
  alone. No absolute history offset is inferred from a bounded capture. The supervisor's handled set suppresses
  repeated identical content for that target and run, accepting missed identical recurrences as its conservative limit.
- `agentctl-fake-agent` gains a fixture mode that prints one screen fixture and then blocks, so a
  private-server pane shows a fixture exactly as an agent would leave it. A test-owned render file releases playback
  after an independent client has resized the window; a separate terminal-control fixture guarantees wrapped UTF-8
  transport coverage without representing a real agent screen.
- `agentctl-core-eval` gains the normalisation and fingerprint subjects.

#### Validation

1. Every fixture printed by the fake agent in a private-server pane narrower than its longest line captures and normalises to the fixture's text as the test normalises it in Python — `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`; fails when wrapped lines are not joined or non-ASCII text is decoded by locale; mutants `M-capture-no-join`, `M-capture-locale-decoding`.
2. For generated screens, normalising twice equals normalising once — `haskell:agentctl-core-test/Normalize/idempotent`; fails when a second pass changes the text; mutant `M-capture-normalise-not-idempotent`.
3. A fixture's error block keeps its fingerprint when redrawn, moved within the bounded capture, or repeated with different surrounding lines; changing the error block is the positive control that the subject reads its input — `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`; fails when the fingerprint includes surrounding output or a relative position; mutant `M-capture-fingerprint-includes-redraw`.
4. Distinct normalised error blocks yield their independently computed SHA-256 values, and reusing one block gives the same value — `haskell:agentctl-core-test/Fingerprint/different-error-differs`; fails when the subject returns a constant fingerprint; mutant `M-capture-fingerprint-constant`.

5. Native faint text at the starting cursor is distinguished from identical ordinary draft text with that cursor at Home — `tests/integration/test_capture_real.py::test_capture_keeps_prompt_visuals`; fails when styled rows or cursor facts are lost; no mutant: native faint/plain twins bind actual viewport evidence.
6. A native cursor change released after the first facts query requires a fresh pair of matching snapshots, with the stable native capture as its positive control — `tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`; fails when mismatched snapshots are accepted; mutant `M-capture-ignore-cursor-change`.

#### Remaining Work

None.

### Sprint 8.2: Claude and codex screen classifiers [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/Classify.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Classify/Input.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Classify/Claude.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Classify/Codex.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `tests/fixtures/screens/`, `tests/harness/screens.py`, `tests/support.txt`, `tests/mutants/classify.toml`, `tests/unit/test_screen_classes.py`, `tests/governance/test_screen_fixtures.py`
**Validation tests**: `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Classify/dead-pane-is-exited`, `haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence`, `tests/governance/test_screen_fixtures.py::test_every_fixture_has_provenance`
**Mutants**: `M-classify-usage-limit-as-overload`, `M-classify-auth-error-as-overload`, `M-classify-context-as-overload`, `M-classify-overload-over-approval`, `M-classify-ignore-partial-input`, `M-classify-overload-over-working`, `M-classify-dead-pane-by-text`, `M-classify-placeholder-as-partial`, `M-classify-placeholder-ignores-style`, `M-classify-placeholder-ignores-cursor`
**Closes**: R18.1
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`

#### Objective

Classify every screen of each agent onto one closed class, telling transient overload apart from
every failure that a recovery text cannot fix.

#### Deliverables

- One classifier per agent maps a normalised screen and the pane's dead state onto exactly one
  class of the closed vocabulary; the classes are a closed type, so a classifier that omits one does
  not compile.
- Precedence: `Exited` for a dead pane; then `TrustDialog`, `BypassWarning`, `ApprovalDialog` and
  `LoginScreen`; then `PartialInput`; then `Working`; then `Overloaded`, `UsageLimit`, `AuthError` or
  `ContextExhausted` when that error is the latest output above an empty input prompt; then
  `IdlePrompt`; otherwise `Unknown`.
- Transient overload is the only error class a recovery text may answer. `UsageLimit`, `AuthError`
  and `ContextExhausted` are distinct classes, and a crash is `Exited`, so none of them can be read
  as `Overloaded`.
- `tests/fixtures/screens/<agent>/<class>/<id>.txt` holds at least one fixture for each class and
  agent, the directory naming the expected class; each has a provenance sidecar, `captured` with
  the agent version and capture command or `documented` with its URL, and an evidence span.
- Precedence pairs are fixture pairs that differ only in the dominating element, such as an overload
  error in scrollback above an approval dialog, above typed input and above a working indicator.
- `agentctl-core-eval` gains both classifiers as subjects.

#### Validation

1. Every fixture classifies as its directory names, for its own agent — `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`; fails when a usage-limit, authentication-error or context-exhaustion fixture reads as `Overloaded`; mutants `M-classify-usage-limit-as-overload`, `M-classify-auth-error-as-overload`, `M-classify-context-as-overload`.
2. In every precedence pair the dominating element decides the class, and the twin without it classifies as the error — `tests/unit/test_screen_classes.py::test_precedence_pairs`; fails when an error in scrollback outranks an approval dialog, typed input or work in progress; mutants `M-classify-overload-over-approval`, `M-classify-ignore-partial-input`, `M-classify-overload-over-working`.
3. A dead pane classifies as `Exited` even when its last text is an idle prompt, and the same text in a live pane classifies as `IdlePrompt` — `haskell:agentctl-core-test/Classify/dead-pane-is-exited`; fails when the class is read from text alone; mutant `M-classify-dead-pane-by-text`.
4. Every fixture has a complete sidecar whose provenance is `captured` or `documented` with its fields, whose evidence span occurs verbatim in the fixture, and whose class directory is in the closed vocabulary, while a fixture copied into a temp tree without its sidecar is reported — `tests/governance/test_screen_fixtures.py::test_every_fixture_has_provenance`; fails when a fixture lacks provenance or its span is not in its text; no mutant: it checks fixture data rather than a subject.

5. An explicit faint suggestion at the starting cursor is empty, while ordinary text at Home, a moved cursor, missing or conflicting visual data and a whitespace draft remain partial input — `haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence`; fails when text alone, a color number or the cursor alone certifies emptiness; mutants `M-classify-placeholder-as-partial`, `M-classify-placeholder-ignores-style`, `M-classify-placeholder-ignores-cursor`.

#### Remaining Work

None.

### Sprint 8.3: Screen column in status and live classification [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Capture.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Classify/Agent.hs`, `src/agentctl/haskell/app/FakeAgent.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `tests/harness/live.py`, `tests/harness/sessions.py`, `tests/support.txt`, `tests/mutants/classify_status.toml`, `tests/e2e/test_status_screen.py`, `tests/live/test_live_classification.py`, `tests/live/test_live_launch.py`
**Validation tests**: `tests/e2e/test_status_screen.py::test_screen_column_shows_fixture_class`, `tests/e2e/test_status_screen.py::test_screen_column_uses_the_agents_classifier`, `tests/live/test_live_classification.py::test_live_screen_classes`
**Mutants**: `M-classify-status-stale-capture`, `M-classify-status-other-agent`
**Closes**: none
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/cli_reference.md`, `documents/engineering/testing.md`

#### Objective

Show each managed session's live class in `status`, and classify real agents' screens where a live
host allows it, without sending them anything.

#### Deliverables

- `status` captures and classifies each managed session's pane at the moment it runs, with the
  classifier of the agent its `@agentctl_agent` option names, and shows the class in a screen
  column; an adopted pane uses the agent recorded at adoption.
- The column is computed from a capture taken by that `status` run, never from an earlier one.
- `tests/live/test_live_classification.py` runs in the fixed live folder under the real `state` dir
  with `DISABLE_AUTOUPDATER=1` and the per-invocation codex ARGS `-c check_for_update_on_startup=false` on a private server and branches on each agent's login state: logged
  in, each capture classifies as `TrustDialog`, `BypassWarning` or `IdlePrompt`, and as `IdlePrompt`
  only where the user has already trusted the folder; logged out, the launch is refused with its
  remedy. It never sends input or answers a dialog.
- `tests/live/test_live_launch.py` gains the same class check for its logged-in branch, so a pane
  that is alive but shows an unexpected screen fails the live launch.

#### Validation

1. Managed sessions whose fake agents print one fixture of each class show that class in the screen column, and each fake's record carries the run's nonce — `tests/e2e/test_status_screen.py::test_screen_column_shows_fixture_class`; fails when the column reuses a capture from before the fixture changed; mutant `M-classify-status-stale-capture`.
2. A codex session printing a codex-only fixture shows its codex class, while the claude classifier on the same screen yields another class — `tests/e2e/test_status_screen.py::test_screen_column_uses_the_agents_classifier`; fails when status classifies with the other agent's classifier; mutant `M-classify-status-other-agent`.
3. The live branch for each agent holds as Deliverables state — `tests/live/test_live_classification.py::test_live_screen_classes`; fails when a logged-in screen classifies as anything else; no mutant: no mutant names a live test as its killer, so none runs against a real agent.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` — capture and normalisation, the fingerprint and what it covers, the closed screen classes with their precedence, and the provenance rule that leaves a `documented`-only class not proven.
- `documents/architecture/sessions_and_ownership.md` — the screen column of `status` and the classifier each target uses.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — screen fixtures and their sidecars, the sanctioned-capture rule, the fake agent's fixture mode, and the live classification rules.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — the screen column of `status` and its values.
- `documents/reference/external_tool_facts.md` — styled viewport flags, cursor geometry and documented prompt suggestions, with native observations distinguished from source facts.

**Cross-references to add:**

- `documents/architecture/multiplexer_adapter.md` — links the supervisor contract for the use of `capture-pane` and its UTF-8 decoding.
