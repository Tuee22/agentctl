# Documentation Standards

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Define how agentctl's governed documents are structured, named, linked, worded and kept current, and list every documentation check with the test that proves it and its negative fixture.

These rules govern every page under `documents/` and the three root documents; plan files follow
[development_plan_standards.md](../DEVELOPMENT_PLAN/development_plan_standards.md), whose
[§ J](../DEVELOPMENT_PLAN/development_plan_standards.md#j-readme-and-documents-harmony) is the plan's side of the same
harmony. A rule that a `docs.*` check covers ends by naming the check and its test. Agents apply authoring rules
that name no check; optional human review adds no gate-closure requirement.

## TL;DR

- `documents/` is the only documentation root, with four categories: `architecture/`, `engineering/`, `operations/` and
  `reference/`.
- Each page owns one topic and names the one phase that builds its contract. It opens with the metadata block and ends
  with `## Target Contracts and Migration Evidence

Governed pages describe required target contracts; the plan alone records whether their implementation and
evidence qualify. An existing command or a newly written rule supplies no conformance evidence by itself.
Every standing incompatible shape has a concrete deletion owner in the plan ledger; all present source and
tests remain in the gate census.

A named enforcement claim identifies the actual test/control that establishes it. A required new mechanism
is explicitly a deliverable of its owning contract, not a claim that the current validator already implements
it. Accepting/refusing controls and applicable mutants accompany new enforcement. No skip, suppression,
alternate runner or hidden legacy source bridges the migration.

The single gate emits independently attributable phase/lane verdicts and a complete overall result. Prose
must distinguish a phase-specific passing receipt from final whole-product acceptance. An unmet later native
lane does not invalidate an earlier Linux contract, while shared integrity failures invalidate all consumers.
Each phase needs Linux and at most one additional native family. WSL2 facts are Linux facts and use the
dedicated-instance, resource/dependency and same-checkout bind-mount contract in the validation runbook.

## Related`; an architecture page opens with `## TL;DR`.
- The plan owns status. A page states the contract its owning phase builds, in the present tense, and never says
  whether that phase is built.
- Each fact has one home, a prose home that states it or a data home the tests read, and other pages link that home.
- Outside `DEVELOPMENT_PLAN/` a phase is cited by its title, as a link, never by number, and no sprint is cited.
- The pages a user reads never name the core binary.

## Metadata Block

Every page under `documents/` opens with this block, with nothing before the title. A page inside a category reaches the
plan through `../../DEVELOPMENT_PLAN/`; the two pages at the root of `documents/` use `../DEVELOPMENT_PLAN/`.

```text
# <Title>

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [<phase title>](../../DEVELOPMENT_PLAN/phase-N-<slug>.md)

> **Purpose**: <one sentence>.
```

| Field | Rule |
|---|---|
| `# <Title>` | The first line, and the page's only `#` heading. |
| `**Status**` | `Authoritative source`: the page is the one home of its topic. `Reference only`: the page points at, or records with sources, facts whose authority lies elsewhere, in another document or in an external tool's own behaviour. `Deprecated`: the page is to be deleted, and a row of the [legacy ledger](../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md) names the phase that deletes it. No other value exists. |
| `**Supersedes**` | `N/A`, or the backticked path of a deleted file whose topic this page absorbed; git holds that file's content. |
| `**Owning phase**` | A link to the phase file that builds the page's contract, with that phase's exact title as the link text. |
| `> **Purpose**` | One sentence saying what the page is for. |

The block has no other field and no YAML front matter. It has no `Referenced by` line, because back-links drift while
forward links resolve or fail and `grep` finds every page that links a given one, and no `Generated sections` line,
because no page holds generated content.

Checked by `docs.metadata` (`tests/governance/test_doc_validator.py::test_docs_metadata`) and `docs.owning-phase`
(`tests/governance/test_doc_validator.py::test_docs_owning_phase`).

## Root Documents

The repository root holds three entry documents, all written by
[Governance and phase evidence](../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md):

- **`README.md`** orients a new reader: what agentctl is, how to install it, and the commands whose owning phase the plan
  records as built. It links both indexes, `DEVELOPMENT_PLAN/README.md` and `documents/README.md`, states no status and
  never names the core binary.
- **`AGENTS.md`** is the authoritative policy for agents working in the repository: they never run `git add`,
  `git commit` or `git push`; they take up work in the order the plan's README gives; `agentctl check` is the only gate;
  commits, human review and interactive actions never gate closure or phase advancement;
  they never run a login command, call the core binary or `cabal` directly, weaken an oracle or a mutant, or add a skip
  or a suppression. It also states the isolation and live-folder rules and the optional capture of screen fixtures
  outside gate closure.
- **`CLAUDE.md`** is a pointer: its metadata block, one sentence sending the reader to `AGENTS.md`, and the import line
  `@AGENTS.md`. It states no rule of its own, so the two files cannot disagree.

Each opens with `# <Title>`, `**Status**`, `**Supersedes**` and `> **Purpose**`, with no `**Owning phase**` line, since
the governance phase owns all three. `AGENTS.md` is `Authoritative source`, and `README.md` and `CLAUDE.md` are
`Reference only`. The structure rules below do not apply to them.

Checked by `docs.root-entry` (`tests/governance/test_doc_validator.py::test_docs_root_entry`).

## Taxonomy

```text
documents/
├── README.md                    the index and the glossary
├── documentation_standards.md   this file
├── architecture/                product contracts, one per page
├── engineering/                 provisioning, build, tests, the gate and the code rules
├── operations/                  installing, upgrading, removing, and each warning's remedy
└── reference/                   commands, files and state, and external tool facts
```

- `documents/` is the only documentation root, and no `docs/` directory exists anywhere in the repository.
- Every page sits in exactly one category, except `README.md` and this file at the root.
  [§ S](../DEVELOPMENT_PLAN/development_plan_standards.md#s-contract-homes) lists the page that is each product
  contract's home.
- There is no other category. Adding one changes this file, `documents/README.md` and the validator's closed set of
  categories in the same change.
- No path outside `DEVELOPMENT_PLAN/` carries a phase ordinal
  ([§ E](../DEVELOPMENT_PLAN/development_plan_standards.md#e-one-canonical-folder-model)).

Checked by `docs.taxonomy` (`tests/governance/test_doc_validator.py::test_docs_taxonomy`).

## Source of Truth

Each fact has one home, and every other page links it.

| Fact | Its one home |
|---|---|
| Phase order, status, closure criteria and evidence rows | `DEVELOPMENT_PLAN/`; status in its [status table](../DEVELOPMENT_PLAN/README.md#current-phase-status) alone |
| Requirements, with each one's prose home and data home | the [requirements table](../DEVELOPMENT_PLAN/00-overview.md#requirements) |
| Decisions the request leaves open | the [decision rows](../DEVELOPMENT_PLAN/rationale.md#decisions) |
| Lanes | [§ N](../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes) |
| What counts as evidence | [§ L](../DEVELOPMENT_PLAN/development_plan_standards.md#l-evidence-classes-and-what-cannot-count), with the mechanics in [testing.md](engineering/testing.md#evidence-classes) |
| A product or engineering contract | its page under `architecture/` or `engineering/` |
| Commands, files agentctl writes, warnings | [cli_reference.md](reference/cli_reference.md), [files_and_state.md](reference/files_and_state.md), [troubleshooting.md](operations/troubleshooting.md) |
| Facts about external tools | [external_tool_facts.md](reference/external_tool_facts.md) |
| Expected values the tests compare against | the oracles under `tests/oracles/` and the screen fixtures under `tests/fixtures/screens/` |

- **Prose homes and data homes.** A prose home states a rule; a data home is the independently authored file the tests read for it.
  Neither restates the other: the page states the rule and names the file, and the file holds the cases. A page quotes
  a value from a data home only as an example, and a user-facing page quotes a command where the reader needs it, such
  as an install command or a remedy, and links where it comes from.
- **The plan owns status.** No page states a phase's or sprint's status, so a page reads the same before and after its
  phase is built; `documents/README.md` says this once for every page.
- **Disagreements.** A page that disagrees with the plan about what a phase builds is reconciled to the plan in the same
  change. A page that disagrees with its data home means the change that introduced the disagreement is wrong: the fix
  corrects the page or appends an oracle row naming the row it amends, and never edits a committed row
  ([§ P](../DEVELOPMENT_PLAN/development_plan_standards.md#p-the-ratchet-and-automatic-closure)).

Checked by `docs.no-status` (`tests/governance/test_doc_validator.py::test_docs_no_status`).

## Naming and Linking

- **File names** under `documents/` are lower-case `snake_case` with `.md`; `README.md`, `AGENTS.md` and `CLAUDE.md`
  are the only upper-case names. A name describes its topic and carries no date, version or phase ordinal.
- **Links are relative and resolve.** An anchor is the slug of a heading the target has: lower-case, every character
  other than letters, digits, spaces, `-` and `_` removed, and spaces written as `-`. A heading other pages link to
  keeps its text; renaming it updates every link to it in the same change.
- **External sources** are backticked URLs, never links, so validating links never needs the network;
  [external_tool_facts.md](reference/external_tool_facts.md) holds them.
- **Phases are cited by title**, as the title linked to the phase file. No sprint is cited: a page names the phase.
- **Code names** (modules, commands, flags, paths, files, environment variables and types) are in backticks.

```text
WRONG: The supervisor arrives in Phase 10, Sprint 10.2.
WHY:   inserting a phase renumbers every later one and sprints move between phases;
       a title stays right, and a link fails loudly when its file goes away.
RIGHT: [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) builds `supervisor run`.
```

Checked by `docs.links` (`tests/governance/test_doc_validator.py::test_docs_links`) and `docs.phase-citation`
(`tests/governance/test_doc_validator.py::test_docs_phase_citation`).

## Content Rules

- **Declarative present tense.** A page states the contract as what the system does. It never uses the future tense and
  never narrates history; git holds the history.
- **No API sketches.** No fenced Haskell or Python restates a declaration or a type signature. A page names the module,
  describes its contract in prose with backticked names, and may tabulate the cases a closed type admits.
- **Fences.** Every fenced block carries one of the tags `text`, `toml`, `console`, `haskell`, `python` or `json`, and
  holds TOML or JSON rows, `console` lines of `agentctl ...` invocations, or `text` trees, diagrams and examples. No
  diagram is mandatory, since no check can read one.
- **WRONG/RIGHT pairs** are encouraged for a rule that is not obvious, and every WRONG states why it is wrong.
- **No dates and no counts.** Dates appear only as fact provenance in external tool facts. No page types a count of
  tests, passes, mutants or rows; counts exist only in the output of the run that produced them.
- **Enforcement claims cite their test.** A sentence that says a check, test, validator or `agentctl check` enforces,
  rejects, refuses or fails on something sits in a paragraph, list item or table row that also holds the node id of the
  test proving it: `tests/<tier>/test_<x>.py::test_<y>` or `haskell:agentctl-core-test/<Group>/<case>`. A product
  contract stated as what the owning phase builds needs no inline id, because that phase's Gate Integrity table names
  its tests.
- **Automatic validation.** Every validation criterion names an executable test and its observable outcome. Human
  review, a git commit, a clean worktree, a manual attestation, answered dialog or authorized capture is never a
  closure criterion. Optional human activities and claims no automated gate proves stay outside validation.

```text
WRONG: The core binary will resolve the agent to an absolute path.
WHY:   it reads as a promise about a later revision; the plan's status table says what is built.
WRONG: The registry used to hold managed sessions until session options replaced it.
WHY:   a reader must replay a history to learn the current rule; git holds the history.
RIGHT: The core binary resolves the agent to an absolute path.

WRONG: a haskell fence copying the exported signatures of AgentCtl.Agent.Argv.
WHY:   no compiler checks the copy, so it drifts from the module, and a design against it is
       a design against nothing.
RIGHT: `AgentCtl.Agent.Argv` builds the launch argv: it removes user copies of the mandatory
       flags and appends the flags at the end, or before the first bare `--`.

WRONG: agentctl check fails on a skipped test.
WHY:   a reader cannot tell whether anything checks it.
RIGHT: agentctl check fails on a skipped test (tests/<tier>/test_<x>.py::test_<y>).
```

Checked by `docs.enforcement-cited` (`tests/governance/test_doc_validator.py::test_docs_enforcement_cited`).

## User-Facing Vocabulary

The root `README.md`, `operations/` and `reference/` are the pages a user reads.

- They never name the core binary: the string `agentctl-core` occurs nowhere in them, fenced blocks included. They say
  "the core binary".
- Every action they describe is an `agentctl <command>` the user types, or a command of another tool the user types:
  `pipx`, `claude auth login`, `codex login`, a package manager.
- They describe behaviour, messages and files; module names and source paths belong in `architecture/` and
  `engineering/`.

```text
WRONG: $ <data>/bin/<digest>/agentctl-core list
WHY:   the user never runs the core binary: it refuses to run without agentctl's handoff, its
       path changes with every digest, and a copyable example invites the direct call.
RIGHT: $ agentctl list
```

Checked by `docs.binary-unnamed` (`tests/governance/test_doc_validator.py::test_docs_binary_unnamed`).

## Structure

- An architecture page's first `##` section is `## TL;DR`: a few bullets stating its contract.
- Every page's last `##` section is `## Related`: bullets, each a link and a one-line reason to follow it.
- Between them, sections follow the topic, and a page whose headings other pages link to keeps those headings.

Checked by `docs.structure` (`tests/governance/test_doc_validator.py::test_docs_structure`).

## Brevity

A page past about 250 lines asks whether it holds two topics, since two focused pages read better than one long one.
The rule is advisory and deliberately unchecked: some contracts do not decompose, and a check that reports what nobody
can fix trains its readers to ignore it.

## Update Rules

Every update happens in the same change as the thing it describes:

- A change to a contract updates its page, its owning phase file and its data home, and `system-components.md` when a
  component changes; a sprint's `**Docs to update**` names those pages
  ([§ H](../DEVELOPMENT_PLAN/development_plan_standards.md#h-documentation-requirements-section)).
- A new or changed command updates [cli_reference.md](reference/cli_reference.md); a new file in a per-user directory
  updates [files_and_state.md](reference/files_and_state.md); a new warning updates
  [troubleshooting.md](operations/troubleshooting.md) and the oracle rows that hold its wording.
- A fact about an external tool enters [external_tool_facts.md](reference/external_tool_facts.md), with its version,
  date and source, before any oracle row cites it.
- A new page updates the index in [README.md](README.md), a new shared term its glossary, and a renamed heading every
  link to it.
- A change to the repository's working rules reviews the root `README.md`, `AGENTS.md` and `CLAUDE.md`.

## Validation

The documentation validator, `src/agentctl/check/validator/docs.py`, runs in the `validators` step of `agentctl check`.
It reads every page under `documents/` and the root documents, and `docs.links` also reads `DEVELOPMENT_PLAN/`. Fenced
blocks are examples, so only `docs.binary-unnamed` reads inside them.

Each check has one test in `tests/governance/test_doc_validator.py`, named `test_` and the check name with `.` and `-`
written as `_`, and one negative fixture directory under `tests/fixtures/docs_negative/`, named the same way without
`test_`. The test runs its check over the fixture, a minimal tree that must yield exactly the named violation and no
other, and over the live tree, which must yield none; the fixture is the positive control that keeps the live tree's
clean result from passing vacuously.

Root-page presence is required when the root-entry sprint begins; before that point its absence is the declared
construction boundary, not a missing-link exemption. Existing root pages always receive metadata and content checks,
and negative fixture trees always provide their own root pages. The document set under `documents/` and all plan links
remain required throughout (`tests/governance/test_doc_validator.py::test_docs_root_entry`).

| Check | Enforces | Test | Negative fixture |
|---|---|---|---|
| `docs.metadata` | Every page opens with `# <Title>`, `**Status**` from the closed set, `**Supersedes**`, `**Owning phase**` and `> **Purpose**`, in that order and with no other field; a root document has the same block without `**Owning phase**` | `tests/governance/test_doc_validator.py::test_docs_metadata` | `tests/fixtures/docs_negative/docs_metadata/`: a page whose `**Status**` is `Draft` |
| `docs.structure` | An architecture page's first `##` is `## TL;DR`, and every page's last `##` is `## Related` | `tests/governance/test_doc_validator.py::test_docs_structure` | `tests/fixtures/docs_negative/docs_structure/`: an architecture page whose first section is `## Overview` |
| `docs.taxonomy` | Every page sits at the root of `documents/` or in one of the four categories, with a lower-case `snake_case` `.md` name, and no `docs/` directory exists | `tests/governance/test_doc_validator.py::test_docs_taxonomy` | `tests/fixtures/docs_negative/docs_taxonomy/`: a page at `documents/guides/setup.md` |
| `docs.links` | Every relative link outside a fenced block in `documents/`, the root documents and `DEVELOPMENT_PLAN/` resolves to an existing file, and its anchor, if any, to a heading of that file | `tests/governance/test_doc_validator.py::test_docs_links` | `tests/fixtures/docs_negative/docs_links/`: a link to `#install` in a page with no such heading |
| `docs.owning-phase` | A page's `**Owning phase**` links an existing phase file, with that phase's title as the link text | `tests/governance/test_doc_validator.py::test_docs_owning_phase` | `tests/fixtures/docs_negative/docs_owning_phase/`: an `**Owning phase**` link to a phase file that does not exist |
| `docs.no-status` | No page and no root document puts `Planned`, `Active` or `Done` on a line with a phase title or a link to a phase file | `tests/governance/test_doc_validator.py::test_docs_no_status` | `tests/fixtures/docs_negative/docs_no_status/`: a line calling a linked phase `Done` |
| `docs.phase-citation` | Outside `DEVELOPMENT_PLAN/`, no line outside a fenced block, link text and code spans included, holds `Phase` or `Sprint`, in any case, followed by a space and a digit | `tests/governance/test_doc_validator.py::test_docs_phase_citation` | `tests/fixtures/docs_negative/docs_phase_citation/`: prose citing a phase by its number |
| `docs.binary-unnamed` | `agentctl-core` occurs nowhere in `documents/operations/`, `documents/reference/` or the root `README.md`, fenced blocks included | `tests/governance/test_doc_validator.py::test_docs_binary_unnamed` | `tests/fixtures/docs_negative/docs_binary_unnamed/`: an operations page whose `console` example runs the core binary by name |
| `docs.enforcement-cited` | A paragraph, list item or table row that says a check, test, validator or `agentctl check` enforces, rejects, refuses or fails on something also holds a test node id | `tests/governance/test_doc_validator.py::test_docs_enforcement_cited` | `tests/fixtures/docs_negative/docs_enforcement_cited/`: a paragraph saying `agentctl check` fails on a skipped test, with no node id |
| `docs.root-entry` | The root `README.md` links `DEVELOPMENT_PLAN/README.md` and `documents/README.md`, and `CLAUDE.md` holds only its metadata block, one sentence pointing to `AGENTS.md` and the line `@AGENTS.md` | `tests/governance/test_doc_validator.py::test_docs_root_entry` | `tests/fixtures/docs_negative/docs_root_entry/`: a `CLAUDE.md` with a rule of its own beside `@AGENTS.md` |

Mutants with the `M-docval-` prefix, recorded under `tests/mutants/`, each weaken one of these checks and name its test
as their killer ([testing.md](engineering/testing.md#mutants)). The `plan.*` checks that validate `DEVELOPMENT_PLAN/` are
listed, with the sprints that land them, in [development_plan_standards.md](../DEVELOPMENT_PLAN/development_plan_standards.md).

Completion citations join the current gate's observations. A Done sprint's implementation paths must exist,
and each cited test must have passed in this run; parametrized citations expand to the collected cases
(`tests/governance/test_plan_validator.py::test_plan_cited_paths`,
`tests/governance/test_plan_validator.py::test_plan_cited_ids`). Acceptance rows retain their lane and the current
covered-tree digest, with the encoding and limits defined by the
[quality gate](engineering/quality_gate.md#lane-summary-and-evidence-line)
(`tests/governance/test_plan_validator.py::test_plan_evidence_rows`).

## Related

- [README.md](README.md) — the index of pages and the glossary of shared terms.
- [development_plan_standards.md § J](../DEVELOPMENT_PLAN/development_plan_standards.md#j-readme-and-documents-harmony) — the plan's side of status, citation and naming harmony.
- [development_plan_standards.md § S](../DEVELOPMENT_PLAN/development_plan_standards.md#s-contract-homes) — the page that is the home of each product contract.
- [00-overview.md](../DEVELOPMENT_PLAN/00-overview.md#requirements) — each requirement's prose home and data home.
- [testing.md](engineering/testing.md#oracles) — the data homes the tests read, and their provenance.
- [quality_gate.md](engineering/quality_gate.md#check-steps) — the `validators` step that runs these checks.
- [external_tool_facts.md](reference/external_tool_facts.md) — the one home of external facts and their sources.
