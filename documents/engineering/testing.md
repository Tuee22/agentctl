# Testing

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md)

> **Purpose**: State how a test earns its evidence class, how tests isolate real tools from the user's state, how observers, oracles and mutants work, what each gate leg proves, and which paths are unsupported.

This page is the prose home of R20 in the [requirements table](../../DEVELOPMENT_PLAN/00-overview.md#requirements): every phase has strict validation that
cannot be spoofed and that an agent runs with no human input. Its data home is `tests/oracles/check_steps.toml`.

- **No human input.** `agentctl check` takes no arguments, never prompts and runs the whole suite. The human
  acts the plan depends on (logging in, finishing the Xcode dialog, providing a macOS or Windows host, committing)
  are never gate inputs: a logged-out agent is a branch the tests assert, the hosts are acceptance lanes, and
  commits only set the ratchet's baseline.
- **Not spoofable.** Every claim rests on one of the evidence classes below, each Gate Integrity row has mutants
  that die for a named reason, every observer record carries a fresh nonce, and gate data only grows against
  HEAD. That holds against a HEAD the user has committed and no further
  ([§ P](../../DEVELOPMENT_PLAN/development_plan_standards.md#p-the-ratchet-and-the-users-commit-points)).

[§ L](../../DEVELOPMENT_PLAN/development_plan_standards.md#l-evidence-classes-and-what-cannot-count) defines the classes; this page gives their mechanics, and
[the quality gate](quality_gate.md) gives the steps that run them.

## Evidence Classes

Each test function carries exactly one `pytest.mark.evidence` marker whose argument is `value`, `real` or `observer`. The marker is registered in the pinned
pytest configuration, so a misspelt class fails collection under `strict = true`, and the gate plugin fails the session when a collected test carries none or
more than one (`tests/governance/test_gate_plugin.py::test_evidence_marker_required`). `owed` never marks a test: it appears only in Gate Integrity cells,
naming the acceptance phase whose run confirms the row. In `agentctl-core-test` a top-level group whose name ends in `Real` holds `real` cases, each owning its
scope as [isolation](#isolation) requires, and every other group holds `value` cases, properties of pure kernels; a requirement's oracle rows reach Haskell only
through `agentctl-core-eval`.

| Class | A test produces it by | It claims no more than |
|---|---|---|
| `value` | passing a pure subject, or `agentctl-core-eval` for a Haskell kernel, to `tests/harness/oracle.py::assert_oracle` with an oracle file ([oracles](#oracles)) | that the subject computes the specified function on those rows |
| `real` | running the real tool in a scope it owns ([isolation](#isolation)): a private tmux server, psmux under `PSMUX_DATA_DIR`, logged-out claude and codex, `--help` canaries, the pinned ghcup, GHC and cabal, or pytester | that tool's behaviour at the version this run observed, which the lane summary's detail records |
| `observer` | reading the record of `agentctl-fake-agent` or of the spawn audit ([observers](#observers-and-nonces)) | what the subject sent, and what it did not send while the observer was demonstrably live |

A `--help` canary is paired with a negative control that shows the same probe can say no: codex exits 2 on a made-up flag before printing help, while claude's
`--help` hides argument errors, so its canary searches the help text, and the same search for a made-up flag must find nothing
(`tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags`).

| Never evidence | Why | What keeps it out |
|---|---|---|
| skipped, xfailed, xpassed, deselected or zero-assert tests | the claim never ran | the gate plugin, the `post-run-verifier` step, and mutants: a zero-assert test kills none, so it is never a killer |
| expected values produced by the subject | the subject would grade itself | provenance on every oracle row, and `oracles.independence` |
| fixtures without provenance | nobody can say what they show | screen fixtures carry a `captured` or `documented` sidecar; negative fixtures name the rule they break |
| subject self-reports | the subject could say anything | observers record from outside; binary identity is a hash of the built file |
| production branches that exist for tests | the tested path is not the shipped one | `src.no-test-branches`; tests isolate through variables the real tools read |
| mocks or monkeypatches of the subject | they prove only the mock | `unittest.mock` is on ruff's banned-api list; `monkeypatch` serves only `setenv`, `delenv` and `chdir` |
| hand-typed counts | nothing re-checks them | `plan.no-narrative` |
| cached verdicts | they describe another tree | `-p no:cacheprovider`, and every mutant runs on every run; only compilation is cached |

## Isolation

Real tools run only in scopes the test owns, each set up by one harness module, so production code needs no switch.

- **tmux.** `tests/harness/tmux.py` makes `TMUX_TMPDIR` a short 0700 directory under the run directory, unsets
  `TMUX` and `TMUX_PANE`, and starts the private server itself with `-f /dev/null`, so no user configuration is
  read. The subject then reaches that server as its normal default server. The harness runs `kill-server` only
  after asserting that the socket path lies under the run directory, and precondition P6 keeps that path within
  100 bytes.
- **psmux.** Every psmux process gets an absolute, test-owned `PSMUX_DATA_DIR` and `PSMUX_NO_WARM=1`; teardown
  never ends psmux processes by image name.
- **Agents logged out by construction.** `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are empty temp dirs, and
  `CODEX_HOME/config.toml` sets `cli_auth_credentials_store = "file"`, so a keyring credential cannot answer.
  The credential variables both CLIs read are removed: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN`, the `CLAUDE_CODE_USE_*` provider switches, `OPENAI_API_KEY`, `CODEX_API_KEY` and
  `CODEX_ACCESS_TOKEN`. `DISABLE_AUTOUPDATER=1` keeps claude from updating itself, and `HOME`, `XDG_CONFIG_HOME`
  and, on Windows, `USERPROFILE` and `APPDATA` point into the test's temp dir, because claude keeps keyless
  Console sign-ins outside its config dir and nothing a CLI writes may reach the user's home. The construction is
  checked, not assumed: `claude auth status` and `codex login status` must exit 1 inside it, and a 0 is a leaked
  credential that fails the test (`tests/integration/test_agent_real.py::test_logged_out_by_construction`).
- **agentctl's own directories.** `paths.py` honours XDG overrides on every OS, so a test points
  `XDG_STATE_HOME`, and `XDG_CACHE_HOME` and `XDG_DATA_HOME` when it exercises a build or a publish, into its
  temp dir. Tests that only run the binary use the one check published, which is never overwritten.
- **ghcup.** A test that runs ghcup sets `GHCUP_INSTALL_BASE_PREFIX`, a variable ghcup itself reads, to a
  test-owned directory, because a ghcup command other than `--help` or `--version` can rewrite the user's ghcup
  log.
- **Toolchain provenance.** `tests/harness/host.py` calls the toolchain agentctl-installed when the clean-lane
  recipe's pre-bootstrap record, which the recipe writes and agentctl never does, is present, and the user's
  otherwise. A test that branches on it asserts the fresh-bootstrap facts or the reuse contract of the
  [toolchain bootstrap](toolchain_bootstrap.md), never less on either branch.
- **Tool absence is constructed.** A missing-tool case runs the subject with `PATH` set to a temp directory
  holding links to exactly the executables the case allows. No test inspects the host to decide what to assert,
  so on a host without tmux a test that needs tmux is a failure, never a degraded pass.
- **The fixed live folder.** Live tests, which branch on the user's real login state, start the real agent only
  in one fixed folder, `live-acceptance/` under the real `state` directory
  ([files and state](../reference/files_and_state.md)), on a private tmux server, with `DISABLE_AUTOUPDATER=1`.
  They reuse the user's credentials in place and never copy them, send no input, and accept `TrustDialog`,
  `BypassWarning` or `IdlePrompt` as a live agent; on Linux they read `/proc/<pane_pid>/cmdline`, which must end
  with the mandatory flags (an npm-installed codex runs as `node` with `codex.js`). A logged-out agent makes them
  assert the refusal and its remedy instead.

## Observers and Nonces

An observer stands at a boundary the subject crosses and records what crossed it. It proves only what the subject sent, never what a real tool would do with it.

- **The fake agent.** `agentctl-fake-agent`, a cabal executable outside suite routing, is copied into a temp bin
  as `claude` or `codex` (`claude.exe` or `codex.exe` on Windows), and the subject's constructed `PATH` resolves
  it through the same lookup a real agent gets. It writes one record of its argv, working directory, environment
  keys (never values), the multiplexer session it runs in and the nonce, then exits at once or stays running as
  the case requires. Its pid goes into the record, so `containment` can require it dead.
- **The spawn audit.** `src/agentctl/check/audit.py` installs a `sys.addaudithook` hook for the suite. It records
  every Python spawn a subject makes, with the nonce, and vetoes the forbidden ones by raising (every package
  manager, sudo, `xcode-select --install` and ghcup's install commands), so a test sees the exact argv a subject
  would run without running it, and without monkeypatching the subject. Harmless spawns, such as the prerequisite
  probe's compiler, are recorded and allowed, which is what makes them positive controls.
- **Nonces.** `tests/harness/nonce.py` issues a fresh nonce for each observer run, prefixed with the run's
  nonce, so `containment` finds anything the run created. The test hands it to the subject as one of the
  passthrough ARGS, so a record that carries it was written by a process the subject started in this run, and a
  replayed or pre-written record carries none.
- **Paired positive controls.** Every absence assertion sits beside a positive control in the same test that
  shows the observer was live: "no session is left behind" beside the fake agent's record that the session
  existed; "no login command ran" beside the recorded auth-status probe; "no package manager ran after `n`"
  beside the recorded probe spawn
  (`tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`).

## Oracles

An oracle is a TOML file under `tests/oracles/`, committed before the subject it judges. Each row carries an `id`, a `provenance`, an `input` and an `expected`
value, and a correcting row also carries `amends`, naming the row it supersedes:

```toml
[[row]]
id = "ghcup-x86_64-linux"
provenance = "tool:ghcup 0.2.6.2 https://downloads.haskell.org/~ghcup/0.2.6.2/SHA256SUMS"
input = { triple = "x86_64-linux" }
expected = { file = "x86_64-linux-ghcup-0.2.6.2", sha256 = "9ed5da5449b48043a0d17e767c05d2ef585e25a639bb934329496c6d2fad9cf8" }
```

- **Provenance.** `request:R<n>` for a requirement whose quote is in the request block of
  [rationale.md](../../DEVELOPMENT_PLAN/rationale.md#originating-request); `tool:<name> <version> <source>` for a
  fact recorded in [external tool facts](../reference/external_tool_facts.md); `decision:D-<nn>` for a row of the
  [decisions table](../../DEVELOPMENT_PLAN/rationale.md#decisions). No expected value is ever subject output.
- **One comparison.** `tests/harness/oracle.py::assert_oracle` loads a file, applies the subject to every row and
  reports each mismatch by row id, and a file with no rows counts as a mismatch. It imports nothing from `agentctl`: the test passes
  the subject in (`oracles.independence`). An expectation derived by a rule, such as a digest, is computed in the
  test from the rule and never with the subject's own helper.
- **Haskell subjects.** `agentctl-core-eval`, located with `cabal list-bin` in the current build directory, reads
  JSON cases on stdin and prints one JSON result per case; Python compares them, so the comparison is the same
  code for both languages.
- **Append-only.** Rows only grow against HEAD (`ratchet.append-only`), so a correction is a new row with
  `amends`. The request-derived oracles, for argv, session names, preflight and auth, the check legs and steps,
  and the recovery transitions and backoff, are frozen by
  [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) before any product
  code exists, and the user's commit after it is what makes them binding.

## Mutants

Mutation checks activate when [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) introduces the runner. Before that boundary
the governance skeleton uses its direct pytester and negative-fixture tests; afterward every run also proves its declared retrospective mutants. Later Planned
capabilities contribute declarations until their implementation sprint, never runnable patches against absent code
(`tests/governance/test_mutants.py::test_corpus`).

A mutant is a deliberate defect the suite must catch, for the reason it names. Records live in `tests/mutants/<capability>.toml`:

```toml
[[mutant]]
id = "M-<prefix>-<change>"
operator = "delete"
target = "src/agentctl/bootstrap/ghcup.py"
search = "<the exact source text, matching exactly once>"
replace = "<the text that takes its place>"
killers = ["tests/integration/test_ghcup.py::test_sha_mismatch_refused_no_file"]
reason = "<a substring of the killer's failure output>"
```

- **A closed operator set.** `delete` removes a statement, call or argument; `negate` inverts a condition or
  comparison; `replace-literal` changes a constant such as a flag, version, path or number; `reorder` swaps two
  adjacent items; `widen` loosens a predicate to accept more than the rule allows; `short-circuit` returns a
  fixed value before the logic runs. A record with any other operator fails its case of
  `tests/governance/test_mutants.py::test_corpus`.
- **Exact-once patches on a scratch copy.** The runner copies the checkout once per run, applies one patch at a
  time, runs its killers against the copy, and restores it, so the checkout itself never changes. A patch that
  does not apply, or matches more than once, fails its case of `tests/governance/test_mutants.py::test_corpus`.
  Haskell mutants target pure kernels only, build the copy in one fixed `-O0` build directory, and are killed by
  `agentctl-core-eval` cases or tasty cases.
- **Killed for the named reason.** Every killer must fail, and the reason substring must appear in its output
  under the mutant and be absent from its baseline output. A survivor fails the gate, and so does a kill for
  another reason (`tests/governance/test_mutants.py::test_wrong_reason_rejected`).
- **Every run, never cached.** Each record is a parametrized case of `tests/governance/test_mutants.py::test_corpus`
  inside the pytest leg, and `post-run-verifier` requires a passing case for every record.
- **About two per Gate Integrity row.** Each row's mutants name that row's tests as killers (`plan.gate-integrity`),
  ids use only their phase's prefixes
  ([§ M](../../DEVELOPMENT_PLAN/development_plan_standards.md#m-gate-integrity)), and records only grow against
  HEAD (`ratchet.append-only`).

## Gate Legs and What Each Proves

[The quality gate](quality_gate.md#check-steps) gives each step's invocation and failure condition; this table says what a pass of each is evidence of.

| Gate leg | Proves | Cannot prove |
|---|---|---|
| `preconditions` | the tree under test is this checkout, with the pinned tools, on a supported host | which lanes the host meets |
| `validators` | plan and documentation structure, pinned configuration, the suppression ban and the boundary guards hold over the live tree | behaviour |
| `ruff-check` | every Python file in the package and the tests is clean under `select = ["ALL"]` with only the pinned ignores | correctness; rules newer than ruff 0.17.3 |
| `ruff-format` | the files are in ruff's canonical format | anything about behaviour |
| `ty` | the package and the tests type-check with every rule an error, ignore comments disrespected, and no user-level configuration merged | soundness gaps of a beta checker (ty 0.0.95) |
| `toolchain-ensure` | the pinned GHC and cabal answer at absolute paths, and the user's default links did not change | a first install on a pristine host, owed to [Clean-host bootstrap acceptance](../../DEVELOPMENT_PLAN/phase-12-clean-container-acceptance.md) |
| `fourmolu` | every Haskell source matches the committed `fourmolu.yaml` | behaviour |
| `hlint` | no hint fires under the committed `.hlint.yaml`, which ignores nothing | behaviour; hints the pinned hlint lacks |
| `cabal-build` | every component compiles warning-free under `-Werror` with the pinned GHC | behaviour; other GHC versions |
| `binary-identity` | the binary the suite runs is the one cabal built from this tree in this run, and it is not on PATH | bit-reproducibility between builds |
| `cabal-test` | every routed suite ran in this run, reported at least one case, and passed | properties its cases do not state |
| `pytest` | every collected test ran and passed with no skip, selection, deselection or warning, and every branch of the package ran | anything owed or listed as not proven; that the assertions are adequate, which mutants bound |
| `post-run-verifier` | collected equals executed under the run's nonce, every test a Done sprint cites passed, and every mutant died for its reason | that the citations are the right ones |
| `ratchet` | oracle, mutant and requirement rows did not shrink or change, and configuration did not loosen, against HEAD | anything before the user's first commit, or a weakening the user commits |
| `containment` | no private server, observer process or nonce-tagged session outlived the run | a process that never registered with an observer |
| `write-guard-compare` | the run changed no file in the checkout, ignored files included, and moved no ref | writes outside the checkout |
| `lane-summary` | which lanes this host meets, from test-owned observations | that a pasted EVIDENCE line came from a real run |

## Unsupported Paths

None of these counts as evidence, because each would let a pass mean less than it says.

- **Skipping a test.** No skip, skipif, xfail, importorskip, early return, or host check that changes what is
  asserted. A test adapts only to login state, multiplexer kind, OS family and toolchain provenance, and asserts
  what agentctl declares for the state it observed
  ([§ O](../../DEVELOPMENT_PLAN/development_plan_standards.md#o-the-no-skip-suite-and-host-state-adaptivity)).
- **Selectors.** `-k`, `-m`, node ids, `--deselect`, `--lf`, `PYTEST_ADDOPTS`, or a conftest that drops items:
  under check the gate plugin fails the session
  (`tests/governance/test_gate_plugin.py::test_selector_under_check_fails`), and outside check a selected run is
  an inner-loop run, never a gate verdict. The mutant runner's child processes select exactly their named killers
  outside that gate session; only the outer, fully collected corpus case can credit their baseline and named failure.
  Corpus-driver tests cannot be killers, so child selection cannot recurse or narrow the outer suite
  (`tests/governance/test_mutants.py::test_corpus_killer_rejected`, `tests/governance/test_mutants.py::test_corpus`).
- **Bare pytest as the gate.** A bare `pytest`, `cabal test` or single leg has no gate plugin, run nonce,
  coverage floor, mutant corpus or write-guard, so it closes no sprint and its count is never quoted.
- **Crediting a fake CLI with real CLI behaviour.** The fake agent proves only what agentctl sent. Real behaviour
  comes from logged-out real CLIs, `--help` canaries with their negative controls, and the owed live
  confirmations of [Live agent acceptance](../../DEVELOPMENT_PLAN/phase-11-live-agent-acceptance.md).
- **Logging in through a REPL.** No test, fixture or agentctl path runs a login command or types a login into an
  agent (`src.no-login-construction`); the user types `claude auth login` or `codex login`.
- **Answering dialogs.** The workspace-trust and bypass-warning dialogs are the user's consent, so nothing
  answers them; a live test accepts either screen as a live agent and sends nothing.
- **Touching the user's tmux server or credentials.** No test creates, attaches to, sends to or kills a session
  on the user's server, and none reads, copies or writes credentials, `~/.claude.json` or agent configuration
  ([§ Q](../../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection)).
  `containment` and `write-guard-compare` check what can be checked afterwards.
- **Editing gate data to pass.** Changing an oracle's expected value or deleting a mutant to turn a run green is
  a weakening the ratchet rejects against HEAD (`tests/governance/test_ratchet.py::test_edited_row_rejected`); a
  correction is an appended row with `amends`.

## Related

- [quality_gate.md](quality_gate.md) — the steps, legs, preconditions and configuration that run these tests.
- [development_plan_standards.md](../../DEVELOPMENT_PLAN/development_plan_standards.md#m-gate-integrity) — § L, § M and § O, the governance this page implements.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — the consent tests and the clean-lane facts that use these observers.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — the tmux and psmux behaviour the isolated servers exercise.
- [launch_contract.md](../architecture/launch_contract.md#preflight) — the logged-out branch, and the fixture that keeps `Ready` opaque.
- [external_tool_facts.md](../reference/external_tool_facts.md) — the facts that `tool:` provenance points at.
- [system-components.md](../../DEVELOPMENT_PLAN/system-components.md#test-apparatus) — the inventory of the harness, oracles, mutants and fixtures.
- [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) — the phase that builds this apparatus.
