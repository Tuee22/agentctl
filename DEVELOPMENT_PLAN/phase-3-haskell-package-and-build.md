# Phase 3 — Haskell package, quality legs and digest-keyed build

**Status**: Done
**Depends on**: [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md)
**Host lane**: any-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R5, R14

> **Purpose**: Ship the Cabal project as package data, gate it with `-Werror`, fourmolu and hlint so check runs all
> eight legs, and build the core binary into a digest-keyed cache whose identity step names the bytes the tests ran.

## Phase Objective

The Cabal project is ordinary package data at `src/agentctl/haskell/` (D-23), so an editable install builds the
checkout's own sources and a wheel carries them with no extra rule. One build function in
`src/agentctl/bootstrap/build.py` serves the passthrough commands and `agentctl check` alike, with the GHC and cabal of
[Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) and a private `CABAL_DIR`, so a user's binary is built
exactly as the gate builds it. [The binary build](../documents/engineering/binary_build.md),
[the quality gate](../documents/engineering/quality_gate.md) and [the code standards](../documents/engineering/code_standards.md)
are the contracts.

- **Components.** The `AgentCtl.*` library, the core binary `agentctl-core` with its handshake and its refusal to run
  without the handoff, `agentctl-core-eval`, through which every later Haskell kernel reaches its oracle as `value`
  evidence, and the tasty suite `agentctl-core-test`. `agentctl-fake-agent` arrives with
  [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md).
- **The gate.** check gains the `cabal-build` and `cabal-test` legs and suite routing (Sprint 3.1), the `fourmolu` and
  `hlint` legs that make eight (Sprint 3.2, closing R14), and the `binary-identity` step (Sprint 3.3, closing R5), after
  which check's steps equal every row of `tests/oracles/check_steps.toml`.
- **Mutants.** The runner of Sprint 1.2 gains Haskell support; Haskell mutants cover pure kernels and bounded effects on private native backends and controlled observers, never live-agent tests.
- **No claim of reproducibility.** Identity is the SHA-256 of the file `cabal list-bin` names in this run, never a
  digest the binary reports about itself.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R14 — the actual pipeline contains all eight legs in the required order | `tests/oracles/check_legs.toml` | value: the full executable leg table and the pipeline both equal the independent rows | `M-style-drop-hlint` | `tests/unit/test_check_legs.py::test_full_leg_set_matches_oracle` |
| R14 — native pinned style checks reject defects without rewriting sources | `tests/oracles/check_legs.toml`, `tests/oracles/pins.toml` | real: Fourmolu rejects a formatting defect, HLint rejects a hint, and both pinned binaries work with an empty PATH | `M-style-fourmolu-inplace`, `M-style-hlint-exit-ignored`, `M-style-tools-from-path` | `tests/integration/test_haskell_style_legs.py::test_fourmolu_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_haskell_style_legs.py::test_style_tools_report_pins` |
| R14 — answering cached style pins trigger no package installation | `tests/oracles/style_tools.toml` | observer: a warm ensure records only both native version queries, beside a live positive spawn control and a vetoed harmless installer candidate | `M-style-reinstall-always` | `tests/integration/test_haskell_style_legs.py::test_tools_idempotent` |
| R14 — complete style configuration retains all default HLint hints | `tests/oracles/style_tools.toml` | value: complete root configuration passes and ignored hints, missing keys, duplicate keys and nested overrides fail | `M-style-hlint-ignore-allowed` | `tests/governance/test_style_config.py::test_style_configs_have_no_ignores` |
| R14 — every Cabal invocation enables tests with the required flags | `tests/oracles/check_legs.toml` | value: the declared legs and shared application arguments match the independent Cabal rows | `M-build-tests-disabled` | `tests/unit/test_check_legs.py::test_leg_table_matches_oracle` |
| R14 — warnings fail the build independently of user Cabal configuration | `tests/oracles/check_legs.toml` | real: an unused binding fails under the common warnings stanza while the compiling twin builds, including a test-owned user configuration that relaxes warnings | `M-build-drop-werror`, `M-build-user-cabal-dir` | `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_legs.py::test_user_cabal_config_ignored` |
| R14 — every Haskell suite is routed and nonempty | none — component declarations, listing and XML outcomes are observed directly | real: a routed suite passes and extra, conditional or empty suites fail | `M-build-routing-blind` | `tests/integration/test_haskell_legs.py::test_every_suite_routed` |
| R5 — the binary digest covers the source, raw pins and native platform, excluding style files | `tests/oracles/pins.toml` | value: expected digests computed independently with hashlib from every source/pin/platform edit row | `M-cache-digest-omits-cabal-file`, `M-cache-digest-includes-style-config` | `tests/unit/test_digest.py::test_oracle_rows` |
| R5 — digest hits avoid provisioning and compilation | none — native spawn events and published bytes are observed directly | observer: a warm hit records only its handoff control, and a real lock waiter reuses its predecessor's publication | `M-cache-hit-ignored` | `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_build_cache.py::test_waiter_uses_published_winner` |
| R5 — failed builds and wrong handshakes publish nothing | none — native compiler failures, wire answers and directory contents are observed directly | real: a type-error build and a compiling wrong-protocol twin leave all previous published bytes unchanged | `M-cache-nonatomic-publish`, `M-cache-skip-handshake` | `tests/integration/test_build_cache.py::test_failed_build_keeps_previous`, `tests/integration/test_build_cache.py::test_handshake_mismatch_rejected` |
| R5 — the executable gate retains binary identity after build | `tests/oracles/check_steps.toml` | value: the actual full step table equals the independent ordered row | `M-cache-identity-step-dropped` | `tests/unit/test_check_steps.py::test_step_table_equals_oracle` |
| R5 — source distributions carry the checkout's Haskell project | none — archive members are compared to an independent filesystem inventory | real: the wheel and sdist include uncommitted source data and exclude generated build directories | `M-build-wheel-excludes-haskell` | `tests/integration/test_haskell_legs.py::test_wheel_ships_haskell_sources` |
| R6 — the core binary refuses invocation without the protocol handoff (contributing) | none — the native refusal and successful twin are observed directly | real: absent and different handoff versions refuse commands while the correct version answers the handshake | `M-build-handoff-unchecked` | `tests/integration/test_haskell_legs.py::test_direct_invocation_refused` |
| R6 — the handshake and JSONL evaluator preserve the protocol (contributing) | `tests/oracles/protocol.toml` | value: the pure native handshake reports all commands and each JSONL case has its ordered answer | `M-build-handshake-drops-commands`, `M-build-eval-drops-case` | `haskell:agentctl-core-test/Handshake/protocol-fields`, `tests/integration/test_eval_executable.py::test_every_case_answered` |
| R6 — the published core binary is never on PATH (contributing) | none — the PATH lookup and binary bytes are observed directly | real: the identity step compares the built and published bytes and refuses a PATH entry | `M-cache-identity-unchecked` | `tests/integration/test_build_cache.py::test_identity_step_rejects_foreign_binary`, `tests/integration/test_binary_boundaries.py::test_identity_refuses_missing_output_incomplete_publish_and_path` |

## Not Proven By This Gate

- Building the project and the pinned fourmolu and hlint on macOS. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- Building them on Windows, under deep cabal store paths and with no MSYS2. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- A first build from an empty private store, run from a non-editable wheel install on a pristine host. — owed to [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md).
- Bit-for-bit reproducibility: GHC does not promise identical output, so identity covers only the bytes this run built. — not proven by any phase.
- An install from a published release, a tag or an archive URL, which needs a release the user makes. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 3.1: Cabal project, build and test legs, handshake [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/cabal.project`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/haskell/test/`, `src/agentctl/bootstrap/build.py`, `src/agentctl/check/legs.py`, `tests/governance/test_mutants.py`, `tests/mutants/haskell_build.toml`, `src/agentctl/check/haskell.py`, `src/agentctl/check/haskell_mutants.py`, `src/agentctl/process.py`, `tests/oracles/protocol.toml`, `tests/harness/haskell.py`, `tests/support.txt`, `pyproject.toml`, `.gitignore`, `src/agentctl/check/steps.py`, `src/agentctl/check/preconditions.py`, `src/agentctl/check/validator/source.py`, `tests/conftest.py`
**Validation tests**: `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_legs.py::test_every_suite_routed`, `tests/integration/test_haskell_legs.py::test_user_cabal_config_ignored`, `tests/integration/test_haskell_legs.py::test_direct_invocation_refused`, `tests/integration/test_haskell_legs.py::test_wheel_ships_haskell_sources`, `tests/integration/test_eval_executable.py::test_every_case_answered`, `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`, `haskell:agentctl-core-test/Handshake/protocol-fields`, `tests/unit/test_haskell_gate.py::test_closed_components_and_listings`, `tests/unit/test_haskell_gate.py::test_xml_requires_actual_nonempty_cases`, `tests/unit/test_haskell_gate.py::test_native_evidence_must_be_fresh_and_complete`, `tests/unit/test_haskell_gate.py::test_index_pin_and_owned_environment`, `tests/integration/test_haskell_legs.py::test_native_leg_execution_and_failures`, `tests/integration/test_haskell_legs.py::test_process_utf8_input`, `tests/integration/test_build_boundaries.py::test_native_command_and_artifact_failures`, `tests/integration/test_build_boundaries.py::test_private_index_receipt_and_failure_boundaries`, `tests/integration/test_build_boundaries.py::test_report_recording_rejects_bad_and_unreadable_input`, `tests/integration/test_haskell_mutations.py::test_native_edge_vetoes`, `tests/integration/test_haskell_mutations.py::test_native_mutation_failures_never_count_as_kills`, `tests/integration/test_haskell_mutations.py::test_native_mutation_report_boundaries`, `tests/unit/test_check_legs.py::test_planned_owner_diagnostic`
**Mutants**: `M-build-drop-werror`, `M-build-routing-blind`, `M-build-user-cabal-dir`, `M-build-tests-disabled`, `M-build-handoff-unchecked`, `M-build-handshake-drops-commands`, `M-build-eval-drops-case`, `M-build-wheel-excludes-haskell`
**Closes**: none
**Docs to update**: `documents/engineering/binary_build.md`, `documents/engineering/quality_gate.md`, `documents/engineering/code_standards.md`, `documents/engineering/testing.md`, `documents/architecture/python_haskell_boundary.md`

#### Objective

Make the bundled Cabal project build and test under `-Werror` with the pinned toolchain, route every suite, and give
the binary its handshake and the eval executable its first cases.

#### Deliverables

- `agentctl-core.cabal` declares the library, `agentctl-core`, `agentctl-core-eval` and the tasty suite
  `agentctl-core-test`, each importing the common warnings stanza of the code standards, with no `flag`, `if` or
  `buildable` field; `cabal.project` pins the Hackage `index-state`.
- `build.py` holds the one build invocation: the recorded absolute cabal and ghc, `CABAL_DIR` set to `cache/cabal` so
  the user's cabal configuration changes no flag, repository or store, a build directory outside the tree, and tests
  enabled. `cabal update` runs only when the private index does not reach the pinned `index-state`, which is recorded.
- The `cabal-build` leg builds `all` and fails unless every component the cabal file declares was built; the
  `cabal-test` leg runs `test all`, and each suite writes a tasty report into the run dir with at least one case and no
  failure, which is also the listing of `haskell:agentctl-core-test/<Group>/<case>` ids that `plan.cited-ids` reads.
- Suite routing: the `test-suite` stanzas are exactly `agentctl-core-test`, none conditional, and a stanza the leg does
  not run fails it.
- `AgentCtl.Protocol` answers a handshake with the protocol version and the command list; when the protocol version
  from Python's handoff is absent or different it refuses every command and tells the user to run `agentctl`, without
  naming the binary. No CPP and no embedded digest.
- `agentctl-core-eval`, located through `cabal list-bin`, reads JSON cases on stdin and prints one JSON result per case,
  which `tests/harness/oracle.py::assert_oracle` compares; each later phase adds its kernels as subjects.
- The mutant runner builds a Haskell mutant's scratch copy in one fixed `-O0` build directory under the run dir and runs
  its pure-kernel or bounded private-effect killers against that build, never a live-agent test.
- The wheel and sdist carry every checkout file under `src/agentctl/haskell/` and no `dist-newstyle/`, with no
  hatchling force-include.

#### Validation

1. An unused binding in a temp copy fails `cabal-build` naming the warning, while the unmodified copy builds —
   `tests/integration/test_haskell_legs.py::test_werror_fires`; fails when the stanza drops `-Werror`; mutant
   `M-build-drop-werror`.
2. A temp copy with an extra `test-suite` stanza, or a suite reporting no case, fails `cabal-test`, while the routed
   suite passes — `tests/integration/test_haskell_legs.py::test_every_suite_routed`; fails when the leg runs only the
   suites it knows; mutant `M-build-routing-blind`.
3. A user cabal configuration under a test-owned `HOME` that relaxes warnings leaves item 1's fixture failing —
   `tests/integration/test_haskell_legs.py::test_user_cabal_config_ignored`; fails when the legs read the user's cabal
   directory; mutant `M-build-user-cabal-dir`.
4. Check's legs remain an ordered subsequence of `check_legs.toml`, each with its row's flags —
   `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`; fails when `cabal-build` loses `--enable-tests`;
   mutant `M-build-tests-disabled`.
5. The built binary run without the handoff exits non-zero and names `agentctl`, while with Python's protocol version it
   answers the handshake — `tests/integration/test_haskell_legs.py::test_direct_invocation_refused`; fails when the
   version check is skipped; mutant `M-build-handoff-unchecked`.
6. The handshake carries the protocol version and the full command list —
   `haskell:agentctl-core-test/Handshake/protocol-fields`; fails when a command is dropped; mutant
   `M-build-handshake-drops-commands`.
7. Every case `agentctl-core-eval` reads is answered once, in order, and a malformed case yields an error result rather
   than a crash — `tests/integration/test_eval_executable.py::test_every_case_answered`; fails when a case is skipped;
   mutant `M-build-eval-drops-case`.
8. A wheel and an sdist built from a copy of the checkout contain every checkout file under `src/agentctl/haskell/` and
   no `dist-newstyle/` path — `tests/integration/test_haskell_legs.py::test_wheel_ships_haskell_sources`; fails when
   the project directory is excluded from the wheel; mutant `M-build-wheel-excludes-haskell`.

#### Remaining Work

None.

### Sprint 3.2: fourmolu and hlint legs [Done]

**Status**: Done
**Implementation**: `src/agentctl/bootstrap/build.py`, `src/agentctl/bootstrap/pins.toml`, `src/agentctl/check/legs.py`, `src/agentctl/haskell/fourmolu.yaml`, `src/agentctl/haskell/.hlint.yaml`, `tests/oracles/pins.toml`, `tests/mutants/style_legs.toml`, `src/agentctl/bootstrap/style.py`, `src/agentctl/check/style.py`, `src/agentctl/check/steps.py`, `src/agentctl/bootstrap/pins.py`, `tests/oracles/style_tools.toml`, `tests/integration/test_style_cache.py`
**Validation tests**: `tests/unit/test_check_legs.py::test_full_leg_set_matches_oracle`, `tests/integration/test_haskell_style_legs.py::test_fourmolu_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_haskell_style_legs.py::test_style_tools_report_pins`, `tests/integration/test_haskell_style_legs.py::test_tools_idempotent`, `tests/governance/test_style_config.py::test_style_configs_have_no_ignores`, `tests/unit/test_style_tools.py::test_style_identity_and_install_arguments`, `tests/integration/test_haskell_style_legs.py::test_style_installer_and_leg_vetoes`, `tests/integration/test_style_cache.py::test_tools_publish_together_and_keep_existing`, `tests/integration/test_style_cache.py::test_incomplete_or_wrong_version_tools_refused`, `tests/integration/test_style_cache.py::test_style_preparation_and_staging_failures`
**Mutants**: `M-style-drop-hlint`, `M-style-fourmolu-inplace`, `M-style-hlint-exit-ignored`, `M-style-tools-from-path`, `M-style-reinstall-always`, `M-style-hlint-ignore-allowed`
**Closes**: R14
**Docs to update**: `documents/engineering/quality_gate.md`, `documents/engineering/code_standards.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`, `documents/engineering/testing.md`

#### Objective

Add the pinned Haskell formatter and linter as legs, so check runs all eight legs of R14 in order.

#### Deliverables

- `pins.toml` and `tests/oracles/pins.toml` gain the fourmolu and hlint pins, versions that build with GHC 9.12.4, with
  any build constraint they need.
- `build.py` builds both once with the pinned GHC through `cabal install` and the private `CABAL_DIR` into
  `cache/tools/<pin-digest>`, the digest over the style-tool and GHC pins; the `fourmolu` step builds them only when
  that directory is absent.
- `fourmolu.yaml` writes out every setting, and `.hlint.yaml` keeps hlint's default hints with no `ignore` entry; the
  project holds one of each.
- The `fourmolu` leg runs in check mode over every `.hs` under `app/`, `src/` and `test/`, and the `hlint` leg over
  those three directories, both by absolute path from `cache/tools/<pin-digest>`, never from PATH, each over a
  non-empty file walk.
- check's leg table equals the eight rows of `tests/oracles/check_legs.toml`: `ruff-check`, `ruff-format`, `ty`,
  `fourmolu`, `hlint`, `cabal-build`, `cabal-test` and `pytest`.

#### Validation

1. The leg table equals the eight rows in order with their flags —
   `tests/unit/test_check_legs.py::test_full_leg_set_matches_oracle`; fails when a leg is missing, extra, reordered or
   re-argued; mutant `M-style-drop-hlint`.
2. A misformatted module in a temp copy fails the `fourmolu` leg naming the file and keeps its bytes, while the
   repository sources pass — `tests/integration/test_haskell_style_legs.py::test_fourmolu_fires`; fails when the leg
   rewrites the file and passes; mutant `M-style-fourmolu-inplace`.
3. A redundant bracket in a temp copy makes hlint report a hint and the leg fail, while the repository sources pass —
   `tests/integration/test_haskell_style_legs.py::test_hlint_fires`; fails when hlint's exit is ignored; mutant
   `M-style-hlint-exit-ignored`.
4. Under a constructed PATH holding no fourmolu or hlint the legs still run, and each tool answers `--version` with its
   pin — `tests/integration/test_haskell_style_legs.py::test_style_tools_report_pins`; fails when a leg looks the tool
   up on PATH; mutant `M-style-tools-from-path`.
5. A second ensure records no `cabal install` spawn beside the recorded version queries —
   `tests/integration/test_haskell_style_legs.py::test_tools_idempotent`; fails when the tools are rebuilt every run;
   mutant `M-style-reinstall-always`.
6. `.hlint.yaml` has no `ignore` entry and the project one configuration of each kind, while a fixture with an `ignore`
   entry is rejected — `tests/governance/test_style_config.py::test_style_configs_have_no_ignores`; fails when an
   ignore is accepted; mutant `M-style-hlint-ignore-allowed`.

#### Remaining Work

None.

### Sprint 3.3: Digest-keyed build cache and binary identity [Done]

**Status**: Done
**Implementation**: `src/agentctl/bootstrap/build.py`, `src/agentctl/bootstrap/cache.py`, `src/agentctl/bootstrap/binary.py`, `src/agentctl/check/identity.py`, `src/agentctl/check/preconditions.py`, `src/agentctl/check/haskell.py`, `src/agentctl/check/steps.py`, `src/agentctl/hostfacts.py`, `pyproject.toml`, `tests/mutants/build_cache.toml`, `tests/oracles/pins.toml`, `tests/harness/binary.py`, `tests/support.txt`, `tests/integration/test_build_cache.py`, `tests/integration/test_binary_boundaries.py`, `tests/fixtures/haskell/cache_actor.py.txt`, `tests/fixtures/haskell/cache_boundary_actor.py.txt`
**Validation tests**: `tests/unit/test_digest.py::test_oracle_rows`, `tests/unit/test_digest.py::test_inventory_and_protocol_boundaries`, `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_build_cache.py::test_failed_build_keeps_previous`, `tests/integration/test_build_cache.py::test_handshake_mismatch_rejected`, `tests/integration/test_build_cache.py::test_identity_step_rejects_foreign_binary`, `tests/integration/test_build_cache.py::test_waiter_uses_published_winner`, `tests/unit/test_check_steps.py::test_step_table_equals_oracle`, `tests/integration/test_binary_boundaries.py::test_source_pin_and_toolchain_failures`, `tests/integration/test_binary_boundaries.py::test_publication_failures_never_replace_existing`, `tests/integration/test_binary_boundaries.py::test_native_lock_contention_timeout_and_exception_release`, `tests/integration/test_binary_boundaries.py::test_request_and_identity_lock_failures`, `tests/integration/test_binary_boundaries.py::test_handshake_checks_native_output_and_status`, `tests/integration/test_binary_boundaries.py::test_identity_refuses_missing_output_incomplete_publish_and_path`, `tests/integration/test_binary_boundaries.py::test_native_lock_spawn_hash_and_publication_race_controls`
**Mutants**: `M-cache-digest-omits-cabal-file`, `M-cache-digest-includes-style-config`, `M-cache-hit-ignored`, `M-cache-nonatomic-publish`, `M-cache-skip-handshake`, `M-cache-identity-unchecked`, `M-cache-identity-step-dropped`
**Closes**: R5
**Docs to update**: `documents/engineering/binary_build.md`, `documents/engineering/quality_gate.md`, `documents/reference/files_and_state.md`, `documents/operations/troubleshooting.md`

#### Objective

Build the core binary once per digest of its sources and pins, publish it without ever overwriting one, and prove the
binary the suite runs is the one cabal built from this tree in this run.

#### Deliverables

- The digest is a SHA-256 over length-prefixed inputs: the relative POSIX path and bytes of `agentctl-core.cabal`,
  `cabal.project` and every file under `app/`, `src/` and `test/` in sorted order; the bytes of `pins.toml`; and the
  host's platform triple. `fourmolu.yaml`, `.hlint.yaml` and everything else are left out.
- A digest hit, `data/bin/<digest>/agentctl-core` present, builds and spawns nothing; otherwise the build locks
  `cache/build/<digest>`, looks again, runs the provisioning plan and builds there.
- Publish copies the file `cabal list-bin exe:agentctl-core` names into a temporary directory under `data/bin/`, asks
  it for the handshake, and renames the directory to `data/bin/<digest>` only on the expected protocol version; a
  rename that finds the digest published discards the copy, and a failed build or wrong handshake publishes nothing.
- Published `data/bin/<digest>` entries are never overwritten or deleted by agentctl; owned temporary staging
  directories are removed after success, refusal or failure. A publication lock in `data/locks/` serialises writers.
- The `binary-identity` step runs after `cabal-build`: it publishes this run's build when its digest has no directory,
  then requires the SHA-256 of the built file to equal that of `data/bin/<digest>/agentctl-core`, and `agentctl-core`
  to resolve nowhere on PATH. The suite's end-to-end tests run the published binary.
- `[project.scripts]` in `pyproject.toml` names only `agentctl`.
- check's step table equals every row of `tests/oracles/check_steps.toml`, in order.

#### Validation

1. Each expected digest is computed in the test with hashlib from the rule: editing a `.hs` file, the `.cabal` file,
   `cabal.project` or a pin changes it, and editing `fourmolu.yaml` or a file outside the project does not —
   `tests/unit/test_digest.py::test_oracle_rows`; fails when an input is dropped or a style file enters; mutants
   `M-cache-digest-omits-cabal-file`, `M-cache-digest-includes-style-config`.
2. A second run on an unchanged tree records the handoff's spawn (the positive control) and no ghcup or cabal spawn,
   and the published bytes are unchanged — `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`;
   fails when a hit rebuilds; mutant `M-cache-hit-ignored`.
3. A type error in a temp copy leaves the previous digest's directory byte-identical and adds no `data/bin/` entry,
   while the clean copy publishes — `tests/integration/test_build_cache.py::test_failed_build_keeps_previous`; fails
   when a partial directory appears; mutant `M-cache-nonatomic-publish`.
4. A build answering another protocol version publishes nothing —
   `tests/integration/test_build_cache.py::test_handshake_mismatch_rejected`; fails when the handshake is not asked;
   mutant `M-cache-skip-handshake`.
5. A stub placed at the digest path of a temp data dir fails the identity step, while the genuine publish passes and
   `agentctl-core` resolves nowhere on PATH — `tests/integration/test_build_cache.py::test_identity_step_rejects_foreign_binary`;
   fails when the hashes are not compared; mutant `M-cache-identity-unchecked`.
6. The step table equals the oracle — `tests/unit/test_check_steps.py::test_step_table_equals_oracle`; fails when a
   step is missing, extra or out of order; mutant `M-cache-identity-step-dropped`.
7. A waiter reaches the native build lock before another invocation publishes, then reuses the winner without a
   toolchain or Cabal spawn — `tests/integration/test_build_cache.py::test_waiter_uses_published_winner`; fails when
   the post-lock cache check is omitted; no mutant: the native contention and spawn observer provide the control.
8. Missing sources, pins and tool records, malformed native handshakes, blocked or contended locks, incomplete
   published directories and PATH entries refuse without replacing an existing publish —
   `tests/integration/test_binary_boundaries.py::test_source_pin_and_toolchain_failures`,
   `tests/integration/test_binary_boundaries.py::test_publication_failures_never_replace_existing`,
   `tests/integration/test_binary_boundaries.py::test_native_lock_contention_timeout_and_exception_release`,
   `tests/integration/test_binary_boundaries.py::test_request_and_identity_lock_failures`,
   `tests/integration/test_binary_boundaries.py::test_handshake_checks_native_output_and_status`,
   `tests/integration/test_binary_boundaries.py::test_identity_refuses_missing_output_incomplete_publish_and_path`;
   fails when an error becomes success or a held lock outlives an exceptional exit; no mutant: native negative twins.
9. Native lock, spawn and hash vetoes and a racing publisher produce fresh nonce-bound records beside a successful
   process control — `tests/integration/test_binary_boundaries.py::test_native_lock_spawn_hash_and_publication_race_controls`;
   fails when a boundary failure is swallowed or a winner is overwritten; no mutant: two-sided boundary controls.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/python_haskell_boundary.md` — the handshake, protocol version and command list, the refusal
  without the handoff, and the binary never on PATH.

**Engineering docs to create/update:**

- `documents/engineering/binary_build.md` — the package-data layout, the digest rule, build and publish, the private
  cabal directory, binary identity and packaging.
- `documents/engineering/quality_gate.md` — the eight legs in order with their invocations, suite routing and the
  `binary-identity` step.
- `documents/engineering/code_standards.md` — the common warnings stanza, the repository style configuration with no
  ignores, pure kernels and bounded private effects as Haskell mutant targets, and no live-agent killers.
- `documents/engineering/testing.md` — `agentctl-core-eval` as the bridge to the oracles, the Haskell case listing, and
  Haskell mutant builds.

**Operations and reference docs to create/update:**

- `documents/reference/files_and_state.md` — `cache/build/<digest>`, `cache/cabal`, `cache/tools/<pin-digest>` and
  `data/bin/<digest>`.
- `documents/reference/external_tool_facts.md` — the fourmolu and hlint pins with their provenance.
- `documents/operations/troubleshooting.md` — a failed build, and an identity mismatch whose remedy is deleting that one
  `data/bin/<digest>` directory.

**Cross-references to add:**

- `documents/engineering/binary_build.md` — links `documents/engineering/quality_gate.md` for the legs that share the
  build function.
