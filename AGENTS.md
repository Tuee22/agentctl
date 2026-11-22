# Agent Working Rules

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define the working policy for agents changing this repository and validating its native capabilities.

Follow [the development plan](DEVELOPMENT_PLAN/README.md) and its
[standards](DEVELOPMENT_PLAN/development_plan_standards.md). Work the lowest Active phase, then the lowest
eligible Planned phase. Update its sprints, Remaining Work, deletion rows and status table as work proceeds.
A later phase extends earlier contracts; it cannot make earlier closure depend on an incomplete later feature.

`agentctl check` is the sole no-argument closure gate. It runs the complete present test/source census and
reports independent phase/lane verdicts plus overall checkout health. Close only from the complete current
passing phase verdict and its prerequisites; a later owned failure does not erase earlier trustworthy
evidence. Shared collection/nonce/write-guard/ownership/containment failures invalidate affected consumers.
Focused tools help development but close no work. Never add skips, expected failures, suppressions or alternate
workflow runners, hide legacy source, weaken an oracle/mutant or rewrite ownership to launder a failure.

Use targeted tests and checks during development, choosing the smallest meaningful coverage for each change.
Avoid lengthy full-suite or full-gate reruns for small incremental edits. Run broader validation when changes
affect shared behavior or when targeted results leave relevant uncertainty, and reserve the complete
`agentctl check` for significant validation milestones, including phase closure. Once appropriate checks pass,
repeat or broaden them only when subsequent changes, failures or unresolved concerns justify it. Targeted
checks do not replace the complete passing gate and prerequisites required to close a phase.

Follow [code standards](documents/engineering/code_standards.md). Python is minimal bootstrap/transport and
developer-gate infrastructure, with strict functional doctrine: typed immutable values, single assignment,
total pure calculations, structural parsing and explicit effects. Migration includes checker/tests/stubs.
Haskell owns runtime host policy, Debian tmux and Windows private Rust/psmux source-build workflows.
Agent CLIs remain user-installed; fail clearly when missing and never install or log them in.

Never run `git add`, `git commit` or `git push`, or move HEAD. Commits, review and a clean tree are never
acceptance prerequisites. Never call the core executable or cabal directly; the application and its gate own
those invocations. Source/backend preparation is application-owned work outside ordinary checks and tests.
Check never prompts; tests never run real package managers, sudo, installers, login or answered dialogs.

On a Windows machine, Linux validation runs in a dedicated agentctl Debian VirtualBox VM under all of these conditions:

- Create or use a dedicated agentctl VM, not another project's VM. Observe its identity, Linux kernel,
  host capacity and VM CPU, memory, swap and virtual disk/free-storage capacity. Size the VM with host
  headroom and use dedicated storage, aiming to avoid resource contention with other projects. Record
  allocations and observed usage when practical; proof of cross-project CPU, memory or storage isolation
  is not a prerequisite for Linux validation.
- Install all required Linux dependencies in that dedicated instance, including pipx, the editable dev extra,
  native build tools, tmux and any agents required by the selected lane. Host preparation is separate from
  tests; the application still never installs agent CLIs.
- Expose the live local Windows agentctl repository to the VM and bind mount it into the Linux workspace.
  A separate clone, copy,
  archive, rsync mirror or commit-based transfer cannot substitute. Prove the mount/source identity and
  bidirectional fresh nonce visibility, including unstaged/untracked state, then remove owned sentinels
  before the write-guard snapshot.
- Keep Linux build/cache/toolchain/temp/state and test roots on dedicated Linux storage. Observe and record
  the source mount's permission-change, lock, case and symlink behavior; these are mount facts, not Linux
  qualification prerequisites, and tests needing POSIX filesystem semantics use Linux roots. Use the same
  actual source tree, and never run Windows and VM checks concurrently while that tree can change.
- Follow applicable non-WSL-specific requirements in the [validation runbook](documents/operations/validation_runbook.md).
  Do not change other VMs, their allocations or existing sessions. If source identity, byte census agreement,
  two-way nonce visibility or sentinel cleanup cannot be verified, report the Linux route unmet.

VirtualBox guest evidence is Linux evidence only. It never establishes native Windows or macOS behavior. Each phase
requires Linux and at most one of those native families. Never substitute another kernel or manual attestation.

Agents may prepare/install/configure dependencies and agents in their dedicated validation instance. They may
copy host credentials into restricted private instance storage while preserving the originals. These permissions
do not extend to changing host credentials, agent configuration, shell profiles, selected toolchains or existing
running sessions. Never run login commands or send login keystrokes.

Tests use private multiplexer servers, XDG/state directories and nonce-registered processes/endpoints/short
build roots. Kill a private server only after checking its endpoint lies inside its recorded run boundary.
Never kill by executable image name. Before recursive deletion or movement verify the resolved absolute target
is within the owned resource boundary; wait for child/file-handle closure. Preserve primary failures alongside
cleanup failures and retain full reports outside disposable trees.

Live acceptance launches real agents only in `<state>/live-acceptance/`, with automatic updating disabled.
Ordinary checks send no live input and answer no trust, bypass-warning or approval dialog. Every criterion is
executable without human intervention; missing capability/authentication remains unmet.

Screen-fixture capture is optional and outside gate closure. Use a private server and explicitly requested
capture in the fixed live folder, recording agent version, exact command, evidence span and captured provenance.
A capture requiring agent input needs explicit authorization because it can consume quota. Otherwise use
documented fixtures with their source or capture an already visible screen without sending input.
