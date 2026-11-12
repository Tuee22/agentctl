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

Follow [code standards](documents/engineering/code_standards.md). Python is minimal bootstrap/transport and
developer-gate infrastructure, with strict functional doctrine: typed immutable values, single assignment,
total pure calculations, structural parsing and explicit effects. Migration includes checker/tests/stubs.
Haskell owns runtime host policy, Debian tmux and Windows private Rust/psmux source-build workflows.
Agent CLIs remain user-installed; fail clearly when missing and never install or log them in.

Never run `git add`, `git commit` or `git push`, or move HEAD. Commits, review and a clean tree are never
acceptance prerequisites. Never call the core executable or cabal directly; the application and its gate own
those invocations. Source/backend preparation is application-owned work outside ordinary checks and tests.
Check never prompts; tests never run real package managers, sudo, installers, login or answered dialogs.

On a Windows machine, Linux validation may run in WSL2 only under all of these conditions:

- Use a dedicated agentctl Debian WSL2 instance, not a user's existing development distro. Observe its identity,
  WSL version, actual CPU/memory/commit and VHD/free-storage capacity. Choose and verify numerical workload
  CPU/memory/swap and storage budgets from measured build/test peaks with explicit host headroom.
- Install all required Linux dependencies in that dedicated instance, including pipx, the editable dev extra,
  native build tools, tmux and any agents required by the selected lane. Host preparation is separate from
  tests; the application still never installs agent CLIs.
- Bind mount the live local Windows agentctl repository into the Linux workspace. A separate clone, copy,
  archive, rsync mirror or commit-based transfer cannot substitute. Prove the mount/source identity and
  bidirectional fresh nonce visibility, including unstaged/untracked state, then remove owned sentinels
  before the write-guard snapshot.
- Keep Linux build/cache/toolchain/temp/state on dedicated Linux storage and verify the source mount's
  permissions, locks, case and symlink behavior. Use the same actual source tree, and never run Windows and
  WSL checks concurrently while that tree can change.
- Follow [the validation runbook](documents/operations/validation_runbook.md). Global `.wslconfig` limits are
  shared VM controls, not per-distro CPU/RAM isolation; use verified workload-local controls without changing
  other distributions, default distro settings or global shutdown. If capacity, limits or mount semantics
  cannot be proven, report the Linux route unmet.

WSL2 evidence is Linux evidence only. It never establishes native Windows or macOS behavior. Each phase
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
