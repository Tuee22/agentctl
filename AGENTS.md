# Agent Working Rules

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define the working policy for agents changing this repository and validating its native capabilities.

## Working the Plan

Follow [the development plan](DEVELOPMENT_PLAN/README.md) and its
[standards](DEVELOPMENT_PLAN/development_plan_standards.md). Take the action that the `selection:` line of the
latest verified `agentctl check` run names
([T.D](DEVELOPMENT_PLAN/development_plan_standards.md#td-status-and-progression)). Until the gate prints one, work
the lowest Active phase whose awaited halves are available; otherwise activate the lowest Planned phase whose
prerequisites are Done, changing its header, first sprint, its Remaining Work (the
[§ C](DEVELOPMENT_PLAN/development_plan_standards.md#c-honest-completion-tracking) table naming every planned node,
mutant id and rule it owes) and its status-table row together. Apply the remaining rules
of the plan README's [Working the Plan](DEVELOPMENT_PLAN/README.md#working-the-plan), and update the phase's
sprints, Remaining Work, ledger rows and status table as work proceeds.

Mark a sprint or phase Done only from a verified run, as T.D defines. Regressed, awaiting and blocked are
computed, never written; a failing Done phase is regressed and repaired in place, never set back to Active. When
`selection:` reads `stop`, report what each blocked phase awaits, or the repeated failure set, instead of retrying.
Change the plan README's [Validation Hosts](DEVELOPMENT_PLAN/README.md#validation-hosts) table only when hardware
or setup changes; it changes selection, never a verdict.

A later phase extends earlier contracts and never contradicts or undoes them, and incomplete later work never
blocks validating an earlier phase
([§ A](DEVELOPMENT_PLAN/development_plan_standards.md#a-well-ordered-constructive-narrative)). Edit an
earlier-owned file only while every Done phase still passes.

## The Gate

`agentctl check` is the sole no-argument closure gate. It runs the complete present test and source census, and a
phase verdict counts only when the run's verified parent publishes it, as
[§ T](DEVELOPMENT_PLAN/development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) defines, with the
mechanics in the [quality gate](documents/engineering/quality_gate.md#phase-verdicts-and-evidence-line). A later
owned failure never changes an earlier verdict; only the shared failures of
[T.F](DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures) fail every phase. Until
per-locus attribution lands, every plan and document defect is shared, so each edit keeps both validators clean on
the whole tree ([§ A](DEVELOPMENT_PLAN/development_plan_standards.md#a-well-ordered-constructive-narrative) A4). The
[testing-cost method](#testing-cost-method) governs every test run, and focused tools, including its stepwise
sweep, help development but close no work.

Never add skips, expected failures, suppressions, alternate workflow runners, mock frameworks or attribute
substitution of first-party code, hide legacy source, weaken an oracle or mutant, rewrite ownership to launder a
failure or restructure code only to change coverage. The sanctioned mocks are registered environment models
bound to declared effect interpreters
([T.E](DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test) E4 and E7, D-170). Never pass
`--stepwise` to `agentctl check`.

Every test touches only the closed list of
[§ Q](DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection): run-owned temp
roots, processes it starts, private multiplexer servers under run-owned names and read-only prepared state, never
the user's agent CLIs, credentials, settings or sessions, installers, the registry, the OS clipboard or other VMs
(D-172). Until rows P0-34 to P0-38 of
[Governance and phase evidence](DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md#remaining-work) land, run
no pytest session, `test_corpus` case, native Haskell test run or `agentctl check` natively on the Windows host or
the Mac; only the in-process plan and document validators run there, and all testing runs in the dedicated guest.
Native Windows test runs also wait for the containment arm of R28.1 (D-181).

## Testing-Cost Method

Testing is costly; be specific and targeted, and never run the complete gate unnecessarily.

1. **Fix in isolation.** Fix each failure individually and rerun only that node, or its
   `test_corpus[<mutant>]` case, before running anything else.
2. **Resume, don't restart.** When every observed failure passes individually, continue the sweep from the
   last corrected failure, not from the beginning. Use `pytest --stepwise` with `-o cache_dir=<private dir>`,
   plus the static legs. The sweep is a focused development tool, never closure evidence; never pass
   `--stepwise` to `agentctl check`.
3. **Full gate only to confirm.** Run the complete `agentctl check` only:
   - after a sweep has finished cleanly, to confirm the fixes introduced no new failure;
   - before marking a sprint or phase Done;
   - after editing gate code, the ownership manifest, the mutant corpus or an input of a Done phase;
   - when `selection:` asks for a run on another host.

   Before any full gate:
   - run the changed and new targeted nodes;
   - check that every corpus search matches its target exactly once with the runbook's
     [search-only check](documents/operations/validation_runbook.md#canonical-run-sequence), without running
     killers;
   - run the ratchet;
   - register every new file in the ownership manifest;
   - clear tool caches from the checkout;
   - for a run on the Windows-hosted guest, rerun the VirtualBox binder.
4. **Keep caches out of the checkout.** Set `PYTEST_ADDOPTS=-p no:cacheprovider` for every other pytest run and
   unset it for the sweep, which moves the cache with `-o cache_dir` instead. Point `RUFF_CACHE_DIR`,
   `PYTHONPYCACHEPREFIX` and `COVERAGE_FILE` at private directories. If the census names a tool cache in the
   checkout, delete exactly that verified directory.
5. **Never duplicate a protected mutant's search text.** Put new logic in new modules rather than duplicating
   any protected mutant's search text.
6. **Rerun Haskell killers through the gate's path.** Rerun a `haskell:` killer through
   `tests/governance/test_mutants.py::test_corpus[<mutant>]`, never by calling cabal directly.
7. **Run the live half only when needed.** Each `linux-live` run starts logged-in agent sessions and uses quota,
   so run it only before marking a sprint of Linux live and clean acceptance Done or when `selection:` names that
   half.

## Source Doctrine

Follow [code standards](documents/engineering/code_standards.md). Python is minimal bootstrap/transport and
developer-gate infrastructure, with strict functional doctrine: typed immutable values, single assignment,
total pure calculations, structural parsing and explicit effects. Migration includes checker/tests/stubs.
Haskell owns runtime host policy, Debian tmux and Windows private Rust/psmux source-build workflows.
The application never installs or logs in agent CLIs and fails clearly when one is missing; validation agents
install them in the VM as setup. Haskell effects reach the OS only through records of operations at the raw OS
boundary, with one native and one model interpreter per subsystem, so behaviour runs as model twins on every host
(D-173).

## Repository Authority

Never run `git add`, `git commit` or `git push`, or move HEAD. Commits, human review, a clean tree and human
actions inside a run never gate closure or phase advancement, and no run, check or agent answers a dialog; host
provision recorded in [Validation Hosts](DEVELOPMENT_PLAN/README.md#validation-hosts) changes only selection
([T.C](DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C7, D-128). Never call the core executable or
cabal directly; the application and its gate own those invocations. Source/backend preparation is
application-owned work outside ordinary checks and tests. Check never prompts; tests never run real package
managers, sudo, installers, login or answered dialogs.

## VirtualBox Linux Validation

On a Windows machine, Linux validation runs in a dedicated agentctl Debian VirtualBox VM under all of these conditions:

- Create or use a dedicated agentctl VM, not another project's VM. Observe its identity, Linux kernel,
  host capacity and VM CPU, memory, swap and virtual disk/free-storage capacity. Size the VM with host
  headroom and use dedicated storage, aiming to avoid resource contention with other projects. Record
  allocations and observed usage when practical; proof of cross-project CPU, memory or storage isolation
  is not a prerequisite for Linux validation.
- Install all required Linux dependencies in that dedicated instance, including pipx, the editable dev extra,
  native build tools, tmux, and the agent CLIs and container runtime that the selected halves need. Host
  preparation is agent-performed setup, separate from tests.
- Expose the live local Windows agentctl repository to the VM and bind mount it into the Linux workspace.
  A separate clone, copy, archive, rsync mirror or commit-based transfer cannot substitute. Before the
  write-guard snapshot, prove source identity, complete byte census agreement, two-way fresh nonce visibility
  including unstaged and untracked state, ordinary read/write and owned-sentinel cleanup.
- Keep Linux build/cache/toolchain/temp/state and test roots on dedicated Linux storage. Observe and record
  the source mount's permission-change, lock, case and symlink behavior; these are mount facts, not Linux
  qualification prerequisites, and tests needing POSIX filesystem semantics use Linux roots. Use the same
  actual source tree, and never run Windows and VM checks concurrently while that tree can change.
- Follow the [validation runbook](documents/operations/validation_runbook.md): its
  [canonical run sequence](documents/operations/validation_runbook.md#canonical-run-sequence) for a full gate and
  its [focused development sweep](documents/operations/validation_runbook.md#focused-development-sweep) for the
  exact sweep commands. Do not change other VMs, their allocations or existing sessions. If the proof of source
  identity, complete byte census agreement, two-way fresh nonce visibility including unstaged and untracked state,
  ordinary read/write and owned-sentinel cleanup is incomplete, the binding is not established: do not run the
  guest gate, so the halves it would evaluate stay unrun
  ([T.X](DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), and report the missing proof; a run on the
  bound checkout without a current binding receipt fails
  `tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`.

VirtualBox guest evidence is Linux evidence only. It never establishes native Windows or macOS behavior. Each phase
requires Linux and at most one of those native families. A half that no available host supplies prints `absent`,
so the phases that require it are at best `awaiting:<half>`
([T.V](DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)); never substitute another kernel or manual
attestation.

## Credentials and Host Setup

Agents may prepare, install and configure dependencies and agents in their dedicated validation instance. Besides
the dedicated VM and its shared folders, they may perform only this enumerated host setup, as preparation outside
any gate run ([one-time host setup](documents/operations/validation_runbook.md#one-time-host-setup)):

- install Visual Studio Build Tools and the Windows SDK;
- install a container runtime and the agent CLIs inside the dedicated VM;
- maintain a Claude Code permission allowlist in the user-level `~/.claude/settings.json`, outside the checkout,
  limited to ssh to the dedicated VM, `VBoxManage` for that VM, the binder, `agentctl` and deletion of verified
  cache paths, with no wildcard grant; an edit of that file also reaches the user's running Claude Code sessions.

No setup, preparation, run or check restarts a host; a setup whose outcome needs a restart leaves its capability
absent (D-141, D-171).

Host provision is what the user supplies and [Validation Hosts](DEVELOPMENT_PLAN/README.md#validation-hosts)
records: hardware such as the Mac, and the setup that comes with it, such as the Command Line Tools of
`setup:xcode-clt`, whose installation needs a dialog that a person completes. No run, check or agent answers a
dialog or restarts the host, and host provision changes only selection
([T.C](DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C7, D-128, D-158). Until the Mac exists,
selection works [macOS acceptance](DEVELOPMENT_PLAN/phase-13-macos-acceptance.md) while its verdict is `fail`; only
once its `linux` half passes and the `macos` half is its only gap is it blocked as `awaiting:macos`, and the
terminal state is then `selection: stop` listing what each blocked phase awaits.

VM agents use the host login, as
[Agent Credentials in the VM](documents/operations/validation_runbook.md#agent-credentials-in-the-vm) details:

- transient VirtualBox shared folders of the host `.claude` and `.codex` folders are mounted read-only at
  `/mnt/host-agents/{claude,codex}`;
- only `~/.claude/.credentials.json` and `~/.codex/auth.json` are symlinked, and the guest keeps its own writable
  `~/.claude.json` and settings;
- binaries are never mounted, and the host stays the single writer of refreshed tokens;
- if the status probe fails, or the tokens desynchronize, copy those two files with mode 0600 instead, keep the
  host originals intact and record the choice in host facts.

Still forbidden: login commands and login keystrokes; changing other VMs or sessions; wildcard permissions; and
changing host credentials, shell profiles, selected toolchain defaults or host agent configuration beyond the
allowlist. When a capability is missing, its probe reports absence, and only its phases wait, each at best
`awaiting:setup:<name>`.

## Isolation and Live Acceptance

Tests use private multiplexer servers, XDG/state directories and nonce-registered processes/endpoints/short
build roots. Kill a private server only after checking its endpoint lies inside its recorded run boundary.
Never kill by executable image name. Before recursive deletion or movement verify the resolved absolute target
is within the owned resource boundary; wait for child/file-handle closure. Preserve primary failures alongside
cleanup failures and retain full reports outside disposable trees.

Live acceptance launches real agents only on the bound dedicated guest, in `<state>/live-acceptance/`, with
automatic updating disabled; agent CLIs are probed or started nowhere else, and every other test uses the agent
models (D-172, D-179). Live-starting nodes execute on every run and assert the branch their qualification requires
(P0-37).
Ordinary checks send no live input and answer no trust, bypass-warning or approval dialog. Every criterion is
executable without human intervention; a missing capability, including an agent that is not logged-in
([T.X](DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), remains unmet and never becomes a
documented-fixture or manual-attestation pass.

Screen-fixture capture is optional and outside gate closure. Use a private server and explicitly requested
capture in the fixed live folder, recording agent version, exact command, evidence span and captured provenance.
A capture requiring agent input needs explicit authorization because it can consume quota. Otherwise use
documented fixtures with their source or capture an already visible screen without sending input.
