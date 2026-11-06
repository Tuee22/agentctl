# Testing

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md)

> **Purpose**: State how a test earns its evidence class, how tests isolate real tools from the user's state, how observers, oracles and mutants work, what each gate leg proves, and which paths are unsupported.

This page is the prose home of R20 in the [requirements table](../../DEVELOPMENT_PLAN/00-overview.md#requirements): every phase has strict validation that
cannot be spoofed and that an agent runs with no human input. Its data home is `tests/oracles/check_steps.toml`.

- **No human input.** `agentctl check` takes no arguments, never prompts and runs the whole suite. Every validation
  criterion is executable by an agent. Commits, clean worktrees, human review, approval and interactive actions are
  never prerequisites for closure or phase advancement. Authentication and native-host capabilities are observed
  automatically: a logged-out agent is a branch the tests assert, and acceptance lanes require their actual host
  evidence. Login, GUI setup and optional fixture capture are outside validation.
- **Not spoofable.** Every claim rests on one of the evidence classes below, each Gate Integrity row has mutants
  that die for a named reason, every observer record carries a fresh nonce, and gate data only grows against
  the available HEAD baseline. Historical protection covers only data present in that baseline; it cannot protect
  coordinated changes to uncommitted expectations and their subject before the run
  ([§ P](../../DEVELOPMENT_PLAN/development_plan_standards.md#p-the-ratchet-and-automatic-closure)).

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

The collection plugin reads `tests/support.txt` for explicit support modules and joins collected modules to sprint citations. A support entry cannot hide a file matching pytest's test-module naming convention (`tests/governance/test_gate_plugin.py::test_orphan_module_fails`). Negative validator trees use the fixture edit instructions under `tests/fixtures/docs_negative/`; `tests/harness/trees.py` applies each instruction to a fresh copy of the governed tree, leaving the checkout unchanged.

Real tools run only in scopes the test owns, each set up by one harness module, so production code needs no switch.

The host harness independently probes the native multiplexer with `-V` and records its path, raw version and current
nonce under `mux-host/` in the run directory. It applies the recorded floors independently of the Haskell kernel.
Its constructed absent/present PATH test uses the same real executable in owned storage
(`tests/integration/test_mux_resolution.py::test_host_probe_and_constructed_absence`). Version probes use an owned
home and XDG directories, and psmux also receives owned registry storage with warm servers disabled.

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
- **Toolchain provenance.** `tests/harness/host.py` and its standard-library-only bootstrap helper call the toolchain
  agentctl-installed when their independent pre-bootstrap absence record matches the host and prefix, and the user's
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
  with the oracle's final argv tail (an npm-installed codex runs as `node` with `codex.js`). A logged-out agent makes them
  assert the refusal and its remedy instead. Empty-tail and bare-separator live cases preserve the ordinary
  flags-at-end check and also prove a nonempty raw tail without supplying any prompt or pane input. The host observer runs the read-only status probes with updating
  disabled and saves only their statuses and the run nonce, never their identity or credential output. The
  live-agents lane requires both successful probes; the launch test probes each agent freshly and fully asserts
  its selected branch (`tests/live/test_live_launch.py::test_live_launch`).

## Observers and Nonces

An observer stands at a boundary the subject crosses and records what crossed it. It proves only what the subject sent, never what a real tool would do with it.

- **The fake agent.** `agentctl-fake-agent`, a cabal executable outside suite routing, is copied into a temp bin
  as `claude` or `codex` (`claude.exe` or `codex.exe` on Windows), and the subject's constructed `PATH` resolves
  it through the same lookup a real agent gets. It writes one record of its argv, working directory, environment
  keys (never values), the multiplexer session it runs in and the nonce, then exits at once or stays running as
  the case requires. Its pid goes into the record, so `containment` can require it dead.
  Scripted mode plays fixture frames advanced by a private trigger file, a received-byte threshold or a bounded
  delay. It disables canonical input, echo and control-key processing only in its test-owned terminal, restoring
  the prior native mode on normal scope exit. It preserves input bytes, including a literal sent before Enter.
  `received.jsonl` records byte arrays and cumulative counts; `frames.jsonl` records each rendered fixture. Both
  carry the fresh nonce, pid, pane, session and native monotonic timestamp, and flush each record before advancing.
  The receiving controls check the partial literal, the separate carriage return, every target identity and all
  three advance kinds (`tests/e2e/test_scripted_fake.py::test_scripted_agent_records_every_byte`).
- **Native supervisor stop.** POSIX tests signal only their owned child. Windows tests use a test-only console
  fixture in a second private multiplexer pane; its native helper checks that the supervisor-lock PID belongs to
  that console before sending Ctrl+C or the child's process-group Ctrl+Break. Tests require exit before cleanup,
  bind prior captures to every nonce-bearing managed and adopted target, preserve their pane identities and run a
  fresh controller to prove lock release (`tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`).
  All requests and observations are automatic; Linux compilation does not confirm Windows console handling.
- **Guarded delivery.** The compiled fake multiplexer relay can hold the selected guard after a real flushed send
  proposal, while the test changes a pane and independently observes its native rendering. It distinguishes a
  deferred proposal following an abort from the next actual send offer. Each hold has a nonce-bound generation and
  a bounded release; the relay supplies no capture text. A separate mode refuses the selected literal command
  before forwarding it. Both modes run beside real receiving controls for each agent
  (`tests/e2e/test_supervisor_scenarios.py::test_screen_change_aborts_send`,
  `tests/e2e/test_supervisor_scenarios.py::test_failed_send_closes_unresolved`).
- **The spawn audit.** `src/agentctl/check/audit.py` installs a `sys.addaudithook` hook in disposable subject interpreters. It records
  every Python spawn a subject makes, with the nonce, and vetoes the forbidden ones by raising (every package
  manager, sudo, `xcode-select --install` and ghcup's install commands), so a test sees the exact argv a subject
  would run without running it, and without monkeypatching the subject. Harmless spawns, such as the prerequisite
  probe's compiler, are recorded and allowed, which is what makes them positive controls.
  The immutable hook opts into Python tracing with `__cantrace__`, so coverage observes the hook body too.
- **Prerequisite consent.** Disposable click actors use an owned PATH containing no installers. A recorded link
  attempt establishes that the observer is live; declines attempt no package commands. Each approved command is
  attempted separately under the veto, and an ordinary batch stops at its first veto
  (`tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`,
  `tests/integration/test_prereqs_consent.py::test_accepted_runs_exact_argv`). Value cases cover successful sequencing
  and the post-install observation; native probe cases run their own independent GMP link or Xcode query
  (`tests/unit/test_prereqs.py::test_apply_sequence_and_first_failure`,
  `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`). The clean-container lane owns
  the actual apt installation sequence.
- **Toolchain actuation.** Disposable interpreters record and veto the exact GHC and cabal install attempts. Their
  candidate executable is a harmless native binary, so a broken veto cannot install anything. A separate Python
  spawn proves the hook is live. Controlled resolution values exercise spelling preservation, and actual native
  version checks prove which absolute paths were invoked; a warm run permits exactly those two invocations
  (`tests/integration/test_toolchain.py::test_argv_never_sets`,
  `tests/integration/test_toolchain.py::test_whereis_paths_used_verbatim`,
  `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`).
- **Style-tool actuation.** The gate prepares the native style cache before pytest. Test-owned actors use genuine
  cached executables for version checks, a harmless installer candidate and a nonce-bound spawn audit that vetoes
  every install attempt. Publication tests supply completed or failed operation values and already-built native
  executables to the atomic publisher; they prove publication behavior without claiming an installer ran
  (`tests/integration/test_haskell_style_legs.py::test_tools_idempotent`,
  `tests/integration/test_haskell_style_legs.py::test_style_installer_and_leg_vetoes`,
  `tests/integration/test_style_cache.py::test_tools_publish_together_and_keep_existing`).
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

The gate manifest records each collected case's singular evidence class alongside its separate collected,
executed and passed sets. The post-run join uses the current nonce and requires every applicable mutant's actual
parametrized corpus case. A Done sprint's generic pytest citation expands only to its current collected cases;
every expansion must have passed (`tests/governance/test_run_evidence.py::test_collected_executed_passed_equal`,
`tests/governance/test_run_evidence.py::test_every_mutant_has_current_case`,
`tests/governance/test_plan_validator.py::test_plan_cited_ids`). Missing future Haskell source is reported as not
applicable while its owner is Planned (`tests/governance/test_plan_validator.py::test_validator_non_vacuous`).

An oracle is a TOML file under `tests/oracles/`, with expectations authored independently of the subject from the
request, recorded decisions or external facts. A commit is optional and never required before validation or closure.
Each row carries an `id`, a `provenance`, an `input` and an `expected`
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
  The protocol cases include malformed input and compare the full ordered output to independent rows in
  `tests/oracles/protocol.toml` (`tests/integration/test_eval_executable.py::test_every_case_answered`).
- **Append-only.** Rows only grow against HEAD (`ratchet.append-only`), so a correction is a new row with
  `amends`. The request-derived oracles, for argv, session names, preflight and auth, the check legs and steps,
  and the recovery transitions and backoff, are authored independently by
  [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) before any product
  code exists. The current run validates their provenance and comparisons without requiring a commit or human
  checkpoint; only rows already in HEAD receive historical ratchet protection.

## Mutants

The oracle validator runs the independent standard-library loader in a child interpreter during `validators`. Each file contains only `[[case]]` rows, with `id`, `requirement`, `quote`, `provenance`, `input` and `expected`, plus optional `amends`. `assert_rows` compares each effective row through `assert_oracle`, preserving the row id in an assertion failure (`tests/governance/test_oracles.py::test_empty_oracle_rejected`). Tool provenance uses `tool:<version>:<exact fact text>` and resolves to a versioned row in external tool facts; request and decision references use their stable ids (`tests/governance/test_oracles.py::test_provenance_resolves`).

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
  Haskell mutants build the copy in one fixed `-O0` build directory. Pure kernels are killed by
  `agentctl-core-eval` comparisons or Tasty cases; bounded effects use the real private backend and controlled
  observers. No mutant uses a live-agent test as its killer, and every effect retains the normal isolation and
  process deadlines.
  Both direct Tasty killers and Python comparisons use that scratch build. A selected native killer must list
  exactly its declared case; only its actual XML failure text becomes a named reason. Missing reports, wrong
  selections and compilation errors cannot count as kills
  (`tests/integration/test_haskell_mutations.py::test_native_mutation_failures_never_count_as_kills`,
  `tests/integration/test_haskell_mutations.py::test_native_mutation_report_boundaries`).
Baseline refusals and defective results include the mutant id, killer node and actual child output; compiler
errors and wrong reasons remain failures.

- **Killed for the named reason.** Every killer must fail, and the reason substring must appear in its output
  under the mutant and be absent from its baseline output. A survivor fails the gate, and so does a kill for
  another reason (`tests/governance/test_mutants.py::test_wrong_reason_rejected`).
  The reason must occur in pytest's failure-detail lines, rather than only in quoted source context; an unrelated
  exception beside an assertion message cannot count as that assertion failing. Child interpreters and their nested
  pytester sessions use a controlled scratch `PYTHONPATH`, with fresh bytecode storage per invocation, so they load
  the defective copy rather than the editable installation (`tests/governance/test_mutants.py::test_wrong_reason_rejected`,
  `tests/governance/test_mutants.py::test_corpus`).
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
| `fourmolu` | every Haskell source matches the repository `fourmolu.yaml` | behaviour |
| `hlint` | no hint fires under the repository `.hlint.yaml`, which ignores nothing | behaviour; hints the pinned hlint lacks |
| `cabal-build` | every component compiles warning-free under `-Werror` with the pinned GHC | behaviour; other GHC versions |
| `binary-identity` | the binary the suite runs is the one cabal built from this tree in this run, and it is not on PATH | bit-reproducibility between builds |
| `cabal-test` | every routed suite ran in this run, reported at least one case, and passed | properties its cases do not state |
| `pytest` | every collected test ran and passed with no skip, selection, deselection or warning, and every branch of the package ran | anything owed or listed as not proven; that the assertions are adequate, which mutants bound |
| `post-run-verifier` | collected equals executed under the run's nonce, every test a Done sprint cites passed, and every mutant died for its reason | that the citations are the right ones |
| `ratchet` | oracle, mutant and requirement rows did not shrink or change, and configuration did not loosen, against the available HEAD baseline | rows absent from that baseline, or a coordinated weakening already present in it |
| `containment` | no private server, observer process or nonce-tagged session outlived the run | a process that never registered with an observer |
| `write-guard-compare` | the run changed no file in the checkout, ignored files included, and moved no ref | writes outside the checkout |
| `lane-summary` | which lanes this host meets, from test-owned observations | that a pasted EVIDENCE line came from a real run |

## Unsupported Paths

The run-integrity adapter hashes ignored and untracked entries, raw link text and recorded distribution files. Its
ref controls use independently encoded git objects in disposable repositories; no staging or commit command runs
(`tests/governance/test_ratchet.py::test_head_adapter_real`). The failure-path observer vetoes a real formatter spawn
and records source reads before and after the veto, proving that the snapshot finalizer runs without trusting its
printed verdict (`tests/integration/test_guard.py::test_finalizers_run_after_failed_leg`).

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

## Native multiplexer ownership

Private tmux servers run in the foreground with `-D -f /dev/null`, under a short, owned TMUX_TMPDIR. The harness
holds their process handles and registers real server and actor pids with the gate. It stops fake actors, waits
for their panes to exit, verifies the endpoint scope before kill-server, reaps the foreground server and verifies
registered pids are gone. It then removes its stale socket and completed registry records; a live observer or
socket still fails containment (`tests/integration/test_mux_real.py::test_containment_sees_leftover_server`).

The Windows harness uses its own PSMUX_DATA_DIR with PSMUX_NO_WARM=1 and registers each native per-session server.
The Darwin harness supplies a uid-bound `__CF_USER_TEXT_ENCODING` in its private caller environment to keep
CoreFoundation's text-encoding setup inside the constructed environment. The complete environment-key assertion
continues to require exactly the spec's keys plus the pane's TERM, TMUX and TMUX_PANE
(`tests/integration/test_mux_real.py::test_private_server_roundtrip`).
The test-only native fixture invokes the production typed interpreter, with independent raw clients observing the
server. The compiled fake agent records literal argv, cwd, environment keys, its actual session and pid, and the
fresh nonce; it reports no environment values. A second disposable server is the foreign-endpoint control, so the
scope-guard mutant cannot touch a user's server
(`tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`,
`tests/integration/test_fake_agent.py::test_record_carries_nonce`).

The compiled mux relay is copied to a new owned file and renamed over the disposable native client. This supports
read-only native executable copies while preserving the real backend separately
(`tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`). Installer-veto fixtures copy executable bytes and
permission bits without carrying protected system flags (`tests/integration/test_toolchain.py::test_argv_never_sets`).
The private run directory is canonicalized before deriving binary and socket paths, so an aliased temporary root
retains the same exact executable-argument assertion (`tests/e2e/test_passthrough_argv.py::test_through_stack_rows`).


## Auth probes and installed-agent controls

The native auth fixture invokes the production status-only probe through the application-owned test executable.
Its fake agent receives a fresh nonce in the caller environment so the status argv remains exactly `auth status`
or `login status`. The record contains argv, cwd and environment keys, never environment values
(`tests/integration/test_agent_auth_probe.py::test_probe_sees_caller_environment`).

Installed-agent controls use test-owned home, app-data, XDG and agent configuration directories, no auth environment
variables, `DISABLE_AUTOUPDATER=1` and file-only Codex credential storage. Status probes must report logged out.
The host harness separately records both actual CLI versions with a fresh nonce to qualify agent-host; an absent
CLI leaves it unmet. Help canaries require the mandatory flags and a fresh unknown-flag control; they start no interactive session
(`tests/integration/test_agent_real.py::test_logged_out_by_construction`,
`tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags`).

The installed-agent argv control starts the real trampoline on the private backend, enables remain-on-exit,
and atomically publishes a private spec. It observes the fixed two-second startup window from publication.
The actual launch selector supplies argv; independent agent-table rows supply the expected mandatory flags.
Logged-out interactive panes remain alive, while the Claude auth-status and Codex exec controls reject their
appended flags inside that same window. Linux reads the process argv tail directly; all hosts observe actual
pane liveness and rejection diagnostics. Every native pane pid is registered before spec publication
(`tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`).

## Terminal closure and exit status

A controlled fake child ignores SIGHUP on POSIX and closes its standard streams while remaining alive until its
owned stop file appears.
The test observes that live pid and the backend state independently. A spawn audit releases it only after a
repeated native state query, and the status observer must then return the actual exit 3. tmux exposes terminal
closure before child reaping; Windows publishes the trampoline status file before its pane exits
(`tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status`).
The instant-exit control keeps the same deadline and required status, and waits for status publication as well
as a dead pane (`tests/integration/test_mux_real.py::test_instant_exit_status`).

## Launch callers and child accounting

`tests/harness/launch.py` invokes the real core through the application-owned build boundary, with private home,
agent configuration, XDG and multiplexer directories. The fake agent records its auth probe separately from its
interactive launch, with one fresh caller nonce. It can return a controlled auth status and then stay alive or exit
with a controlled launch status. Teardown releases those actors before closing the private server, then requires
every registered process to have been reaped.

For the hostile-folder control, the same compiled observer is copied as the caller's mux client. It records
nonce-bound argv and cwd, then forwards to a copied genuine native backend without changing its arguments,
streams or exit status. Both the plain-folder positive control and the hostile-folder create must omit `-c`;
the actual pane cwd and sentinel absence are checked independently. Client observer pids are registered for
teardown (`tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`).

Public terminal controls place a caller in a second private server's native PTY. Fixture setup uses independent
native clients and an application-published trampoline; the subject still traverses the real public CLI and
production typed interpreter. The attached-client control releases a waiting caller only after one client is
attached, then requires the same client pid on the new session. Literal-tail rows retain their full corpus,
startup windows and native deadlines. Agent-parametrized killers cover every row for Claude and every row for
Codex in separate bounded processes; a mutant must fail both agent killers for its named reason.

The inherited-stream child transport waits on a worker thread, retaining the native exit result while the main
thread handles console interrupts. A real owned child waits for release while its parent is interrupted, and
its exit 3 must survive (`tests/integration/test_handoff.py::test_child_wait_survives_parent_console_interrupt`).
A genuine broken output pipe prevents transport before any child can start
(`tests/integration/test_handoff.py::test_flush_failure_prevents_handoff`).

The native runner's reap request reads the server pid from the checked multiplexer, validates it as a positive
bounded integer and sends only SIGCHLD. Missing status never means success: the status observer still requires the
actual exit code within its deadline. The policy cases are independent values; the private-server controls require
the genuine native status. A separate compiled observer installs its own SIGCHLD handler and records notification
with the nonce. Controlled client responses prove that malformed server pids are refused before that valid owned
pid receives a notification; psmux makes no reap query or signal. No test signals a user's server
(`tests/integration/test_mux_reap.py::test_reap_request_validates_pid_before_notification`).

Session listing uses a foreign session first without any identity options, then with agent, folder and pane options
but no owner. Both remain excluded beside real managed sessions, and a managed session ended through the independent
native client disappears on the next query (`tests/e2e/test_sessions.py::test_list_shows_only_managed`). The fake
agent's `wait-exit-3` mode keeps its terminal open until a test-owned stop file is released after startup, separating
a live-pane positive control from a retained dead pane with actual exit 3
(`tests/e2e/test_sessions.py::test_status_reports_dead_pane`).

Adoption controls compare the registry's endpoint, pane and pid against independent native queries. A mismatched
socket or another observed live pid is stale beside the restored valid entry. A guarded private-server restart
also leaves the registration stale while its replacement pane stays alive; tmux reuses the first pane id, while
psmux keeps its native id rules (`tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`). The native state
control constructs broad directory access through chmod or an independent Win32 SDDL fixture, then requires the
strict API to refuse it and state preparation to make it private. Existing child bytes and file permissions remain
unchanged (`haskell:agentctl-core-test/SpecReal/state-directory-preparation`).

Screen normalization exercises generated combinations of text, Unicode, CR, LF, spaces and tabs, alongside
independent indentation and bounded-tail examples (`haskell:agentctl-core-test/Normalize/idempotent`). Fingerprint
controls use literal SHA-256 expectations computed independently with Python's `hashlib`; changed blocks include
non-ASCII content, while redraw controls change surrounding text without changing the normalized error content
(`haskell:agentctl-core-test/Fingerprint/stable-under-redraw`,
`haskell:agentctl-core-test/Fingerprint/different-error-differs`). The corresponding mutations change normalization
on a second pass, return a constant hash, or include surrounding output in the hash.

The fake agent's fixture disposition waits for its test-owned `render` file, prints the supplied UTF-8 file and
waits for its separate `stop` file. A changed render marker redraws that file, clearing only the fake's private
display and scrollback, so status controls change the same pane without launching another process. The capture
round-trip resizes each private window before playback, verifies
its actual pane width and screen through independent native commands, and compares the production capture with
Python-normalized fixture text under the C locale. A separate terminal-control fixture forces Unicode and wrapping
even without agent screen data; it makes no claim about an agent's UI. The same test independently observes pane
death after releasing the fake and requires capture to report it
(`tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`).

The screen fixture boundary requires the whole per-agent class vocabulary and a paired TOML sidecar for each text
file. It refuses unknown classes, missing or malformed provenance, evidence absent from the text, non-official
source URLs and captured records without a version and exact command. The parser's captured positive control is a
temporary test record and makes no real-capture claim (`tests/governance/test_screen_fixtures.py::test_every_fixture_has_provenance`).
Precedence fixtures link their overload baseline; independent comparisons require the old error to remain and only
the dominating element to change. Later-output and missing-prompt fixtures also keep error recognition bounded to
the latest event above an empty prompt (`tests/unit/test_screen_classes.py::test_precedence_pairs`,
`tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`).

Native composer controls print faint and ordinary text with the cursor at the same input start, independently
observe the viewport and compare the production visual capture. The ordinary draft remains partial input even
with its cursor at Home (`tests/integration/test_capture_real.py::test_capture_keeps_prompt_visuals`). Pure controls
also refuse a moved cursor, missing or inconsistent evidence, a color index that happens to equal the faint code,
and a whitespace draft (`haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence`).

A compiled client observer forwards the first pane-facts query to the genuine backend, then releases a test-owned
render marker and waits for an independently queried cursor change before returning. The production capture must
retry and obtain matching snapshots; accepting the first unequal pair fails the recorded mutation reason. This
control changes only its fake agent's private pane and sends no terminal input
(`tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`).

The shared live harness preserves authentication, native argv-tail and refusal checks. Its private terminal excludes
`NO_COLOR` for that invocation so faint suggestion styling is observable; user credentials and agent configuration
remain in place, and automatic updating stays disabled. Both the status column and an independently captured pane
must classify as `TrustDialog`, `BypassWarning` or `IdlePrompt` within the bounded startup observation. The tests send
no input and answer no dialog (`tests/live/test_live_launch.py::test_live_launch`,
`tests/live/test_live_classification.py::test_live_screen_classes`).

The recovery matrix compares every effective frozen row to the real step function's complete control result:
state, actions, incident event, handled identities and attempt. Generated native sequences cover every unsafe
screen class in every reachable mode and require a reachable send. Repeated fingerprint episodes also require a
second send for a different fingerprint, while baseline and already handled errors remain suppressed
(`tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`,
`haskell:agentctl-core-test/Machine/never-send-unsafe`,
`haskell:agentctl-core-test/Machine/one-send-per-fingerprint`). Unchanged verification is checked before and at its
deadline, beside working, idle, redraw and typed-input controls
(`haskell:agentctl-core-test/Machine/verify-needs-change`).

Backoff controls inspect all effective oracle ranges and notification thresholds. Generated policies, attempts
and seeds exercise the jitter band and the final cap; invalid and nonfinite policies are refused, an arbitrary-precision attempt stays bounded, and zero-jitter sequences must reach and retain their cap.
Seed pairs must produce different delay sequences, making seed dependence a positive control. The integrated
deadline subject calls the same step function as the transition subject and additionally exposes its deadline
and deduplicated notices (`tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`,
`tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`,
`haskell:agentctl-core-test/Backoff/within-bounds`, `haskell:agentctl-core-test/Backoff/grows-to-cap`,
`haskell:agentctl-core-test/Backoff/seed-determines-delays`).

Watch value cases are authored from the intent contract before the watch kernel. They compare the full registry,
revisions, exit, repeat/refusal notice and every planned native command. Native controls independently read the
watch file and public tables, retain fake-agent nonce controls, and require unchanged live pane pids after pause
and unwatch. Foreign and missing watch refusals preserve exact state bytes beside a successful managed watch
(`tests/unit/test_watch_values.py::test_watch_transitions_oracle`,
`tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`,
`tests/e2e/test_watch_commands.py::test_unwatch_never_touches_session`,
`tests/e2e/test_watch_commands.py::test_watch_refuses_foreign_target`).

The native log-schema scenario observes `RECOVERY_SENT` before awaiting each receiver's attempt record. Each
native state advance and effect retains its own bounded wait; the complete field, kind and outcome comparisons
still apply to every record (`tests/e2e/test_supervisor_log.py::test_records_match_schema`).

## Related

- [quality_gate.md](quality_gate.md) — the steps, legs, preconditions and configuration that run these tests.
- [development_plan_standards.md](../../DEVELOPMENT_PLAN/development_plan_standards.md#m-gate-integrity) — § L, § M and § O, the governance this page implements.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — the consent tests and the clean-lane facts that use these observers.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — the tmux and psmux behaviour the isolated servers exercise.
- [launch_contract.md](../architecture/launch_contract.md#preflight) — the logged-out branch, and the fixture that keeps `Ready` opaque.
- [external_tool_facts.md](../reference/external_tool_facts.md) — the facts that `tool:` provenance points at.
- [system-components.md](../../DEVELOPMENT_PLAN/system-components.md#test-apparatus) — the inventory of the harness, oracles, mutants and fixtures.
- [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) — the phase that builds this apparatus.
