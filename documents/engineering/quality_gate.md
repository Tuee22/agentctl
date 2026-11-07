# Quality Gate

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)

> **Purpose**: State what `agentctl check` runs, in which order and with which exact invocations, what must hold before it starts, how its tools are configured, and what its lane summary and EVIDENCE line report.

`agentctl check` is the only gate ([§ N](../../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes)). It takes no
arguments, runs from a scrubbed environment, and fails when any step or leg fails or does not run
(`tests/unit/test_check_legs.py::test_failing_leg_fails_check`). The Python tool dispatcher allows two hours per complete leg; native queries and process controls retain their
individual deadlines. A host's first run also installs GHC and builds fourmolu and
hlint. Focused tests and application-owned build calls help development and never close work. This page is the prose home of R2, R14 and
R14.1 in the [requirements table](../../DEVELOPMENT_PLAN/00-overview.md#requirements): their data homes are `tests/oracles/command_surface.toml`, which the
click group's command table must equal, and `tests/oracles/check_legs.toml`, which holds the eight legs; `tests/oracles/check_steps.toml` holds the eighteen
steps. What a pass of each step is evidence of is in [testing](testing.md#gate-legs-and-what-each-proves).

## Check Steps

**The run.** The packaged `00_agentctl_no_bytecode.pth` disables import bytecode in agentctl's private application
environment before the console entry imports its editable source. A real child without Python environment
controls observes the policy, beside a `-S` control that writes bytecode
(`tests/integration/test_python_startup.py::test_startup_precedes_editable_imports`). Check creates a fresh run directory, `agentctl-check-` plus a random suffix, under the system temporary directory, removes it when the run ends,
and re-executes itself through `src/agentctl/process.py` with `PYTHONPYCACHEPREFIX` pointing into it, so neither check nor any child reads or writes bytecode in
the tree, and the write-guard needs to exclude only `.git`. The run directory holds the children's `TMPDIR`, the ty configuration home, the coverage data, the
gate plugin's manifest, the tasty reports and every private tmux server, and check draws one nonce for the run.

Each Python tool-leg command has a two-hour deadline, including the whole pytest suite and its mutant cases. The
enclosing gate reserves eight complete leg budgets, covering bootstrap and the complete pipeline without cutting
off a leg that is still inside its own deadline. Individual native queries and process controls retain their
shorter deadlines. These are execution resource bounds; test collection, assertions, coverage requirements and
mutation-kill criteria are mandatory throughout the run.

**The environment.** Inherited host inputs use a closed allowlist kept in `src/agentctl/check/steps.py`: `PATH`, `HOME`, `USER`, a `C.UTF-8` locale, agentctl's
XDG directory variables, `GHCUP_INSTALL_BASE_PREFIX` and `GHCUP_USE_XDG_DIRS`, the agents' configuration and credential variables that the live lane observes, including the published `CODEX_SQLITE_HOME` runtime location,
and on Windows `SYSTEMROOT`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `PATHEXT` and `COMSPEC`. Everything else, including `PYTHONPATH`, `PYTEST_ADDOPTS`,
`PYTEST_PLUGINS`, `TY_CONFIG_FILE`, `VIRTUAL_ENV`, `TMUX` and `TMUX_PANE`, is absent. The runner then supplies controlled run-specific values: `TMPDIR`, `TEMP`,
`TMP` and `PYTHONPYCACHEPREFIX` under the run directory, explicit `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, and the explicit variables each leg owns, including `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, the isolated ty
configuration home and private `CABAL_DIR`. The leg-plan oracle records these additions, so scrubbing cannot discard them or preserve hostile inherited values
(`tests/unit/test_check_legs.py::test_leg_table_matches_oracle`).

| # | Step | What it checks |
|---|---|---|
| 1 | `preconditions` | P1 to P10 below, reporting every unmet one with its remedy |
| 2 | `write-guard-snapshot` | records path, size and SHA-256 of every file in the checkout, ignored files included and only `.git` excluded, plus `HEAD`, the refs and `packed-refs` |
| 3 | `validators` | every static `docs.*`, `plan.*`, `oracles.*`, `tree.*`, `src.*`, `config.*` and `validator.*` check over the live tree, each with its own negative-fixture test, such as `tests/governance/test_doc_validator.py::test_docs_links` |
| 4 | `ruff-check` | leg; see [the eight legs](#the-eight-legs) |
| 5 | `ruff-format` | leg |
| 6 | `ty` | leg |
| 7 | `toolchain-ensure` | runs the provisioning plan of the [toolchain bootstrap](toolchain_bootstrap.md), the same code path as first use, non-interactively, and requires every pin to answer `--numeric-version` and ghcup's unversioned `ghc` and `cabal` links to be unchanged across the step (`tests/integration/test_toolchain.py::test_default_links_unchanged_by_step`) |
| 8 | `fourmolu` | leg; first ensures the pinned fourmolu and hlint in `cache/tools/<pin-digest>`, building them only when that directory is absent |
| 9 | `hlint` | leg |
| 10 | `cabal-build` | leg |
| 11 | `binary-identity` | publishes the built binary when its digest has no directory, then requires the SHA-256 of the file `cabal list-bin exe:agentctl-core` names to equal that of `data/bin/<digest>/agentctl-core`, and no `agentctl-core` to resolve on PATH ([binary build](binary_build.md)) |
| 12 | `cabal-test` | leg, with suite routing |
| 13 | `pytest` | leg: the entire suite, mutant cases included, under branch coverage with `fail_under = 100` |
| 14 | `post-run-verifier` | requires the plugin's manifest to carry the run's nonce and list the same ids as collected, executed and passed, every Validation test a Done sprint cites to have run and passed in this run (`plan.cited-ids`, Haskell ids included), and every mutant record to have a passing case |
| 15 | `ratchet` | runs `ratchet.append-only` against HEAD with read-only git and reports the commit it compared against, or `no baseline` in an unborn repository; neither case requires a new commit |
| 16 | `containment` | requires that no private tmux server under the run directory and no observer pid recorded in this run is alive, and that no session carrying the run's nonce exists on the user's server, which it reads with `list-sessions` only |
| 17 | `write-guard-compare` | re-walks the checkout and requires no added, removed or changed file and no moved ref |
| 18 | `lane-summary` | evaluates the lanes, requires the lane of every Done self-verifying phase to be met (`plan.lanes`, `tests/unit/test_lane.py::test_refusal_when_done_lane_unmet`), and prints the [EVIDENCE line](#lane-summary-and-evidence-line) |

`tests.orphan-modules` runs inside the pytest leg, through the gate plugin, because it needs the collection; `plan.cited-ids` and `plan.lanes` run in steps 14
and 18 because they need this run's results. The first failing step ends the run: every later step and leg is reported `not run`, which is itself a failure,
except that `containment` and `write-guard-compare` always run once `write-guard-snapshot` has. check exits 0 only when all eighteen ran and passed
(`tests/unit/test_check_legs.py::test_failing_leg_fails_check`).

Steps 1, 3 to 6 and 13 come from [Governance, documentation standards and the check skeleton](../../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md);
steps 2 and 14 to 18, coverage, and the later validator checks from [Gate-integrity apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md); step
7 and preconditions P7 to P10 from [Toolchain bootstrap](../../DEVELOPMENT_PLAN/phase-2-toolchain-bootstrap.md); steps 8 to 12 from [Haskell package, quality
legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md); and precondition P6 from [Multiplexer
adapter](../../DEVELOPMENT_PLAN/phase-4-multiplexer-adapter.md).

The table describes the complete gate. During construction a step or precondition activates in the sprint that introduces it, and each later run retains it.
Planned steps are specification rows, never registered no-op legs; check runs every introduced step and the entire suite that exists in that checkout
(`tests/unit/test_check_legs.py::test_leg_table_matches_oracle`). The mutant runner activates retrospective governance mutants when [Gate-integrity
apparatus](../../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) introduces it; the earlier gate uses direct negative-control tests
(`tests/governance/test_mutants.py::test_corpus`).

`cabal-build` and `binary-identity` use the same digest-keyed build directory and its native `build.lock`. Identity
asks Cabal for the executable path, publishes through the application path when absent, and hashes both actual files.
It refuses a foreign published file, an incomplete entry or a core executable on PATH; a build, spawn, lock or hash
failure is a failed step (`tests/integration/test_build_cache.py::test_identity_step_rejects_foreign_binary`,
`tests/integration/test_binary_boundaries.py::test_identity_refuses_missing_output_incomplete_publish_and_path`,
`tests/integration/test_binary_boundaries.py::test_native_lock_spawn_hash_and_publication_race_controls`).

## The Eight Legs

`tests/oracles/check_legs.toml` lists the eight legs of R14 in this order with their required flags, and
`tests/unit/test_check_legs.py::test_full_leg_set_matches_oracle` fails on a missing, extra, reordered or re-argued leg. In the invocations, `<py>` is
`sys.executable` of the editable install that P1 verified, so each Python tool is the pinned one installed beside agentctl and never one found on PATH; `<root>`
is the checkout root; `<run>` is the run directory; `<hs>` is `<root>/src/agentctl/haskell`; `<cabal>` and `<ghc>` are the absolute paths the toolchain
bootstrap resolved; `<tools>` is `cache/tools/<pin-digest>`; and `<build>` is `cache/build/<digest>`. The Python legs run in `<root>`; the Haskell legs run in
`<hs>`, and both cabal legs set `CABAL_DIR` to `cache/cabal`.

```text
ruff-check   <py> -m ruff check --config <root>/pyproject.toml --no-cache --no-fix <py-files>
ruff-format  <py> -m ruff format --check --config <root>/pyproject.toml --no-cache <py-files>
ty           <py> -m ty check --python <py> --error-on-warning <py-files>
               with XDG_CONFIG_HOME, and APPDATA on Windows, set to the empty <run>/ty-config
fourmolu     <tools>/fourmolu --mode check <hs-files>
hlint        <tools>/hlint app src test
cabal-build  <cabal> build all --enable-tests -w <ghc> --builddir=<build>
cabal-test   <cabal> test all --enable-tests -w <ghc> --builddir=<build> --test-show-details=direct
pytest       <py> -m coverage run --rcfile=<root>/pyproject.toml --data-file=<run>/coverage --branch
               --source=agentctl -m pytest -c <root>/pyproject.toml --rootdir=<root> -p no:cacheprovider
               -p pytester -p agentctl.check.gate_plugin tests, with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
             <py> -m coverage report --rcfile=<root>/pyproject.toml --data-file=<run>/coverage
               --fail-under=100 --show-missing
```

`<py-files>` is every `.py` file under `src/` and `tests/` and `<hs-files>` every `.hs` file under `app/`, `src/` and `test/`, each from a filesystem walk, so
neither a `.gitignore` entry nor a tool's own exclusion hides a file. Every leg asserts a non-empty target set, as [§
M](../../DEVELOPMENT_PLAN/development_plan_standards.md#m-gate-integrity) requires: an empty walk, a build of less than the complete declared component set, a
suite reporting no case, or a pytest run collecting nothing is a failure of that leg (for the suites,
`tests/integration/test_haskell_legs.py::test_every_suite_routed`).

| Leg | Proves | Cannot prove |
|---|---|---|
| `ruff-check` | every Python file in the package and the tests is clean under `select = ["ALL"]` with only the pinned ignores, so a banned `typing.Any`, `typing.cast` or `unittest.mock` fails the leg (`tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`) | correctness; rules newer than ruff 0.17.3 |
| `ruff-format` | the files are in ruff's canonical format | anything about behaviour |
| `ty` | the package and the tests type-check with every rule an error, ignore comments disrespected, and no user-level ty configuration merged | soundness gaps of a beta checker (ty 0.0.95); facts typing cannot express |
| `fourmolu` | every Haskell source matches the repository `fourmolu.yaml` | behaviour |
| `hlint` | no hint fires under the repository `.hlint.yaml`, which ignores nothing | behaviour; hints the pinned hlint lacks |
| `cabal-build` | the library, the three executables and the test suite compile warning-free under `-Werror` with the pinned GHC | behaviour; other GHC versions |
| `cabal-test` | every routed suite ran in this run, reported at least one case, and passed | properties its cases do not state; any effect on a real tool |
| `pytest` | every collected test ran and passed, with no skip, selection, deselection or warning, and every branch of the package ran | anything owed to an acceptance phase or listed as not proven; that the assertions are adequate, which mutants bound |

- **The static legs are shown firing.** Each rejects a fixture from `tests/fixtures/static_negative/` copied to
  a temp dir: `tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`,
  `tests/integration/test_static_legs.py::test_ruff_format_fires_on_fixture` and
  `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`, which requires an error rather than a
  warning; a user-level ty configuration that downgrades rules must change nothing
  (`tests/integration/test_static_legs.py::test_ty_ignores_user_config`); and the Haskell legs fire on a
  misformatted module, a hinted expression and an unused binding
  (`tests/integration/test_haskell_style_legs.py::test_fourmolu_fires`,
  `tests/integration/test_haskell_style_legs.py::test_hlint_fires`,
  `tests/integration/test_haskell_legs.py::test_werror_fires`).
- **The style tools are the pinned ones.** Each answers `--version` with its pin in `pins.toml`, and a second
  ensure builds nothing (`tests/integration/test_haskell_style_legs.py::test_style_tools_report_pins`,
  `tests/integration/test_haskell_style_legs.py::test_tools_idempotent`).
  The Fourmolu leg prepares both tools together through the private Cabal directory with the project's index pin,
  explicit GHC and parser constraint; the HLint leg consumes the verified cache. Neither leg reads inherited
  formatter or linter controls. A formatting defect and a redundant bracket fail their actual native commands,
  preserving source bytes (`tests/integration/test_haskell_style_legs.py::test_fourmolu_fires`,
  `tests/integration/test_haskell_style_legs.py::test_hlint_fires`).
- **Suite routing.** The `test-suite` stanzas of `agentctl-core.cabal` are exactly `agentctl-core-test`, none
  conditional, and each writes a tasty XML report into the run directory with at least one case and no failure;
  `agentctl-core-eval` and `agentctl-fake-agent` are executables, outside routing
  (`tests/integration/test_haskell_legs.py::test_every_suite_routed`).
- **The suite is whole.** Under check the gate plugin fails the session on any skip, skipif, xfail,
  importorskip, deselection, `-k` or `-m` selection, or node-id narrowing, and records collected and executed
  ids with the run's nonce (`tests/governance/test_gate_plugin.py::test_skip_fails_session`,
  `tests/governance/test_gate_plugin.py::test_selector_under_check_fails`).

## Preconditions

The Cabal legs use the shared application build path and the ensured absolute toolchain. Component declarations
are unconditional and the sole suite route is `agentctl-core-test`. Before `test all`, check lists its cases;
it then removes the previous owned XML report, supplies `TASTY_XML` itself and requires each listed case to appear
and pass. The separate native manifest carries this run's nonce and joins the Python manifest before closure
(`tests/integration/test_haskell_legs.py::test_every_suite_routed`,
`tests/integration/test_haskell_legs.py::test_native_leg_execution_and_failures`,
`tests/unit/test_haskell_gate.py::test_xml_requires_actual_nonempty_cases`,
`tests/unit/test_haskell_gate.py::test_native_evidence_must_be_fresh_and_complete`).

The initial dependency and checkout diagnostics in `check/preconditions.py` use only the standard library, so an
interpreter without site packages reports missing dependencies instead of failing to import
(`tests/integration/test_runtime_boundaries.py::test_preconditions_real_interpreters`). P9 observation lives in
`check/prerequisites.py` and runs after those diagnostics pass.

| # | Holds when | Remedy |
|---|---|---|
| P1 | editable identity: see below | from the checkout root, `pipx install --force --editable '.[dev]'`, or `uv tool install --editable '.[dev]'` |
| P2 | `importlib.metadata` reports exactly click 8.5.0, ruff 0.17.3, ty 0.0.95, pytest 9.2.0, coverage 7.17.0 and hatchling 1.33.0 | the P1 reinstall |
| P3 | the running interpreter is at least 3.12, the floor `requires-python` declares | `pipx install --python python3.12 --force --editable '.[dev]'` |
| P4 | the checkout is a git work tree and `git` is on PATH | install git, or work from a clone |
| P5 | no other check holds the single-run lock, `locks/check.lock` in agentctl's `state` directory | wait for the run that holds it, which the message names |
| P6 | the longest private tmux socket path under the run directory is at most 100 bytes | point `TMPDIR` at a shorter directory, such as `/tmp` |
| P7 | ghcup's directory and agentctl's `cache` have room for every pin not yet installed | free space |
| P8 | every pin is installed, or `downloads.haskell.org` and `hackage.haskell.org` are reachable | connect to a network; only a first run or a pin change needs it |
| P9 | GHC's OS prerequisites are present, or on Linux a verified set is installable without a prompt: consent from `--assume-yes`, privilege as root or through `sudo -n true`; macOS needs existing Command Line Tools | the printed package-manager command, or `agentctl --assume-yes check` with passwordless sudo; macOS GUI setup stays outside check |
| P10 | the platform is Linux x86_64 or aarch64, macOS x86_64 or arm64, or Windows x86_64 | none: no GHC bindist exists for any other |

P5 reserves the Windows lock byte at offset 4096, outside the PID text. A competing handle can read the owner
while its lock attempt is refused; scope exit releases the lock
(`tests/integration/test_runtime_boundaries.py::test_single_run_lock_releases`).

P6 predicts `<run>/mux/<eight hex characters>/tmux-<uid>/default` from the canonical run directory and its native owner.
It counts UTF-8 bytes, including multibyte names, before any private server can start. Linux and macOS use this
common 100-byte bound; Windows has no Unix socket endpoint. An unreadable run directory fails with its filesystem
diagnostic (`tests/unit/test_preconditions.py::test_socket_path_length`,
`tests/integration/test_mux_resolution.py::test_socket_directory_inspection`).

The pure toolchain readiness policy compares observed free capacity with the budget for missing pins, accepts
offline operation when both pins are ready, and selects only the package's declared bindist platforms. Its
boundary cases and exact remedies live in `tests/oracles/toolchain_preconditions.toml`
(`tests/unit/test_preconditions.py::test_toolchain_preconditions`).

P7's conservative policy budgets are 10 GiB for a missing GHC, 1 GiB for a missing cabal and 4 GiB of cold cache.
On a shared filesystem their simultaneous needs are added; answering pins reserve nothing. The native observer
queries each directory's existing ancestor and opens bounded TCP connections to port 443 of both P8 endpoints only
for a cold toolchain. Warm readiness sends no network input
(`tests/unit/test_toolchain_gate.py::test_storage_budget_values`,
`tests/unit/test_toolchain_gate.py::test_native_readiness_and_warm_network_absence`,
`tests/unit/test_toolchain_gate.py::test_reachability_opens_and_closes_owned_endpoints`).

P9 uses a private compiler workspace under the run directory and prints concrete remediation commands for failed
probes. It observes non-interactive privilege only for a verified Linux package proposal after `--assume-yes`;
it never invokes an installer or an Xcode dialog itself
(`tests/unit/test_preconditions.py::test_prerequisite_inspection_consent_and_privilege`,
`tests/unit/test_preconditions.py::test_prerequisite_inspection_platforms_and_errors`).

**Editable identity (P1).** The running distribution's PEP 610 `direct_url.json` says `editable`, its `url` is the `file://` URL of the checkout root, and
`agentctl.__file__` resolves under `<root>/src/agentctl`. Any PEP 610 editable installer qualifies, and the dev tools are the `dev` extra because pipx has no
dependency-group support. Without the rule an older or non-editable install runs its own code against this tree's tests and can pass, which is the stale-install
trap of hostbootstrap (`tests/unit/test_identity.py::test_non_editable_refused`, `tests/unit/test_identity.py::test_other_checkout_refused`).

## Tool Configuration

The Python dev extra pins coverage and the hatchling backend used by packaging controls alongside the versions in P2. The static negative controls use the same installed tools and a byte-for-byte copy of the project configuration beside fixture targets outside the checkout. The hostile ty override uses a project-local glob, and its unisolated control must downgrade the same file. Only the ty leg receives the empty configuration home and APPDATA override; the other legs retain the allowed user configuration locations (`tests/integration/test_static_legs.py::test_ty_ignores_user_config`, `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`).

The configuration lives in `pyproject.toml`, co-designed by running the pinned tools on the package skeleton and then frozen: `config.pinned` holds the live
ruff, ty, pytest and coverage tables equal to `tests/oracles/lint_config.toml`, and `ratchet.append-only` lets configuration only tighten against HEAD.

```toml
[tool.ruff.lint]
select = ["ALL"]
ignore = ["D203", "D213", "COM812"]

[tool.ruff.lint.per-file-ignores]
"src/agentctl/process.py" = ["S603", "S606"]
"tests/**/*.py" = ["S101"]
"src/agentctl/check/writeguard.py" = ["PTH115"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"typing.Any".msg = "Any switches type checking off; name the precise type."
"typing.cast".msg = "cast asserts a type without proof; parse into the type instead."
"typing.no_type_check".msg = "it turns the type checker off for a function."
"unittest.mock".msg = "a mocked subject is never evidence; observe with the spawn audit or the fake agent."

[tool.ty.rules]
all = "error"

[tool.ty.analysis]
respect-type-ignore-comments = false

[tool.ty.terminal]
error-on-warning = true

[tool.pytest]
minversion = "9.0"
strict = true
filterwarnings = ["error"]
testpaths = ["tests"]
markers = ["evidence(cls): the evidence class of the test: value, real or observer"]

[tool.coverage.run]
branch = true
source = ["agentctl"]
patch = ["subprocess"]

[tool.coverage.report]
fail_under = 100
```

- **ruff.** D203, D213 and COM812 are ignored because ruff's formatter conflicts with them when every rule is
  selected. S603 and S606 flag every process call, so they are allowed only in the one module that may spawn;
  S101 is allowed in the tests because pytest asserts with plain `assert`. The co-design adds an entry only where
  a pinned tool proves the need. No `exclude`, `extend-exclude` or `fix` key exists, and `noqa` comments are
  banned by `src.suppression-ban`.
  PTH115 is allowed only in the write-guard adapter: `os.readlink` preserves the raw link text that `Path.readlink`
  normalises, and the guard hashes the literal link rather than a normalised path. A copied canary verifies the
  exception's exact module scope (`tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`,
  `tests/integration/test_guard.py::test_write_detected`).
- **ty.** ty has no strict switch, so every rule is set to `error`, including those that default to ignore.
  Ignore comments are disrespected, which leaves `ty: ignore` working, so `src.suppression-ban` bans it.
  ty merges a user-level configuration file and does not discover a pipx venv, so the leg passes `--python`
  and an empty configuration home, and the allowlist drops `TY_CONFIG_FILE`. No overrides table exists.
- **pytest.** `strict = true` turns on strict configuration, markers, parametrization ids and xfail;
  `filterwarnings = ["error"]` makes every warning a failure, including click 8.5's deprecation of
  `CliRunner.isolated_filesystem`. Native `[tool.pytest]` cannot coexist with `[tool.pytest.ini_options]`, and
  `config.pinned` rejects an `addopts` key (`tests/governance/test_source_guards.py::test_lint_config_matches_oracle`).
  The `evidence` marker is described in [testing](testing.md#evidence-classes).
- **coverage.** No `omit`, `exclude_lines` or `exclude_also` key exists; a `pragma: no cover` stands only at a
  line the `src.suppression-ban` allowlist names.
  The subprocess patch collects actual-subject child interpreters into parallel files under the run directory.
  Check combines those files before the report. Mutant killers clear coverage startup settings so baseline and
  defective scratch copies cannot contribute to the package result.
- **Haskell.** `fourmolu.yaml` and `.hlint.yaml` live in the Cabal project, the latter with no ignore
  entry, and the warnings stanza is in [code standards](code_standards.md).

The write-guard includes ignored entries and records raw symlink text. Its installed-environment boundary hashes
metadata and raw RECORD contents, then reads every literal CSV path. It avoids `importlib.metadata.files`, which
can omit missing entries. Missing recorded files and unsupported or unreadable layouts produce a diagnostic
(`tests/integration/test_guard.py::test_snapshot_error_boundaries`, `tests/integration/test_guard.py::test_record_schema`).
Containment queries only registered observer pids and owned server paths, and both integrity finalizers run after
a post-snapshot leg failure (`tests/integration/test_guard.py::test_ignored_write_detected`,
`tests/integration/test_guard.py::test_venv_change_detected`, `tests/integration/test_guard.py::test_finalizers_run_after_failed_leg`).

## Lane Summary and Evidence Line

The pytest leg includes each applicable mutation record as an ordinary collected case. A passing killer baseline, an exact-once patch and the recorded failure reason are all required; the independent scratch execution supplies no gate evidence or outer-session ids (`tests/governance/test_mutants.py::test_corpus`, `tests/governance/test_gate_plugin.py::test_manifest_matches_execution`).

The `lane-summary` step reads the host observations `tests/harness/host.py` recorded with the run's nonce during the pytest leg and evaluates the lane table of
[§ N](../../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes). It prints each lane as met or unmet with the
observation behind it, and the ratchet baseline. check fails when the lane of any Done self-verifying phase is unmet on this host
(`tests/unit/test_lane.py::test_refusal_when_done_lane_unmet`); acceptance lanes are reported and never required. Only when every step passed does it print, for
each lane the host meets:

```text
EVIDENCE <YYYY-MM-DD> ; <lane> ; agentctl check ; pass ; tree <sha256> ; <detail>
```

- `<YYYY-MM-DD>` is the run's UTC date, and the third field is always the literal gate, also under
  `--assume-yes`.
- `tree <sha256>` hashes sorted relative paths, entry kinds and length-prefixed bytes of `pyproject.toml` and
  every file under `src/` and `tests/`, ignored and untracked inputs included. Symlinks contribute their link text
  and resolved bytes; unreadable or escaping inputs fail. Build products and tool caches live outside those paths.
  Every covered change therefore stales a row; `DEVELOPMENT_PLAN/` lies outside, so recording a row never stales it
  (`tests/governance/test_plan_validator.py::test_plan_evidence_rows`).
  The encoding includes the `src` and `tests` directory entries. Each entry supplies its POSIX relative path as
  UTF-8, its kind as ASCII (`directory`, `file` or `symlink`), then its payloads. A directory supplies empty bytes,
  a file its literal bytes, and a file symlink its raw link text followed by the resolved bytes. Every field has
  an eight-byte unsigned big-endian length prefix. Entry order is lexical by relative path. Special entries and
  unreadable or escaping links fail the digest (`tests/governance/test_run_evidence.py::test_digest_byte_vector_and_currency`,
  `tests/governance/test_run_evidence.py::test_digest_link_bytes_and_errors`).
- `<detail>` is a comma-separated list of `key=value` observations for the reader: OS and architecture, the
  observed tmux, psmux, claude and codex versions, and the ratchet baseline.

The closing agent copies the line into its phase's `**Gate evidence**`; `plan.evidence-rows` recomputes the digest over `**Evidence covers**` and compares only
the lane, against `**Host lane**`, and the digest. A digest proves the tree is current, not that a run happened: anyone can recompute it without running
anything, so a row raises the cost of a false claim to recording a result that was not obtained, and holds only as far as [§
P](../../DEVELOPMENT_PLAN/development_plan_standards.md#p-the-ratchet-and-automatic-closure) allows.

## Related

- [testing.md](testing.md#gate-legs-and-what-each-proves) — what a pass of each step and leg is evidence of.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — the code path the `toolchain-ensure` step runs.
- [binary_build.md](binary_build.md) — the build, the publish and the identity the Haskell legs rely on.
- [code_standards.md](code_standards.md) — the rules the static legs hold mechanically.
- [development_plan_standards.md](../../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes) — the single gate, gate kinds and the canonical lane table.
- [documentation_standards.md](../documentation_standards.md) — every `docs.*` check the `validators` step runs.
- [system-components.md](../../DEVELOPMENT_PLAN/system-components.md#python-package) — the modules that implement each step.
- [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) — the phase that completes the eight legs.
