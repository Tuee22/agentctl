# Validation Runbook

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Define automatic, resource-budgeted native, VirtualBox Linux and native Darwin validation against the same editable checkout without Git commits or changes to the user's running environments.

This runbook specifies preparation, one-time host setup and the run sequence. Preparation runs outside
`agentctl check` and is never evidence: the gate re-observes the prepared state under the run nonce, so missing
preparation can leave a phase's half unrun
([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), and preparation itself never makes a phase
pass
([§ A](../../DEVELOPMENT_PLAN/development_plan_standards.md#a-well-ordered-constructive-narrative),
[§ Q](../../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection)).
[External tool facts](../reference/external_tool_facts.md) holds the official interfaces and verification sources
used here, and the [quality gate](../engineering/quality_gate.md) holds the gate mechanics.

## Select the Halves

A run natively evaluates only the halves its sealed host qualifies; every other half of a phase comes from the
latest stored receipt of a verified run with equal identities
([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict) V8).

| Half | Host that supplies it |
|---|---|
| `linux` | Native Debian, or the dedicated Debian VirtualBox guest on Windows |
| `windows` | Native Windows on this host |
| `macos` | Native Darwin hardware |
| `linux-clean` | A clean Debian container of the container runtime in the dedicated guest |
| `linux-live` | The dedicated guest or a native Debian host, with logged-in agents |

The plan README's [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) table records which halves
and setup capabilities are available; it changes selection, never a verdict. A half that no host supplies prints
`absent`, so the phases that require it are at best `awaiting:<half>`
([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)), never passed by a manual attestation.
Guest evidence is Linux evidence only: it supplies no native Win32 process, ACL or console behavior, psmux or
Darwin behavior.

All validation uses the same no-argument `agentctl check` entry point from an editable dev installation.
Preparation can invoke the public application before the test process begins; test bodies run no package
manager, sudo, login command or installer. Ordinary checks neither prompt nor answer a dialog.

## Dedicated VirtualBox VM

On Windows, use a Debian VM dedicated to agentctl. Observe its identity, host and guest capacity, configured
CPU and memory allocation, storage and swap, with host headroom and observed usage when practical.
Keep VM state and build outputs on dedicated storage. Install and verify the dependencies needed for the selected
work, and give the guest agent credentials as [Agent Credentials in the VM](#agent-credentials-in-the-vm)
describes. Do not alter other VMs, projects or existing sessions. Expose the live checkout to the guest and bind
mount it; prove source identity, complete byte census agreement, two-way fresh nonce visibility including unstaged
and untracked state, ordinary read/write and owned-sentinel cleanup. Observe and record the mount's
permission-change, lock, case and symlink behavior as mount facts; they are not qualification prerequisites, and
tests needing POSIX filesystem semantics use dedicated Linux roots. When any of these proofs is missing, the binding
is not established: do not run the guest gate, so the halves it would evaluate stay unrun
([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms),
[§ A](../../DEVELOPMENT_PLAN/development_plan_standards.md#a-well-ordered-constructive-narrative) A2), and report
the missing proof; a run on the bound checkout without a current binding receipt fails
`tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`.

The transport is a transient VirtualBox shared folder named `agentctl-src` whose host path is the live checkout,
with the per-share symlink-creation setting enabled; a transient share does not persist after the VM stops, so it
is added again after each VM start. The guest mounts it with the in-kernel `vboxsf` driver at `/mnt/agentctl-src`
using `uid=1000,gid=1000,fmode=0644,dmode=0755` and bind mounts that path at `/srv/agentctl`; the repository has
`core.filemode=false` and every tracked file is mode 100644. Recorded mount facts on this transport: `chmod`
succeeds but the observed mode stays the mount's fixed mode; case-distinct names collide; a guest-created relative
symlink is created as a Windows symbolic link and reads back; and guest byte-range locks are not coordinated with
Windows handles. The editable dev extra installs with `pipx` into the guest user's Linux home, and gate state,
reports and toolchains live on the guest's ext4 root filesystem.

The binder is preparation outside `agentctl check` and a host-declared Windows source of
[Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md), which
receives it with its claims from
[Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) and cites its
evidence (D-137, R25.1); the [canonical run sequence](#canonical-run-sequence) gives its command. It reads the VM
UUID, creates a fresh nonce challenge in the live checkout, has the guest answer it with the application's own
`binding_challenge.answer` over strict-host-key batch SSH, scans guest process command lines for the nonce and
treats an unreadable process entry as unknown rather than stopped. It removes the owned sentinels, then compares
the host and guest source census digests, and it takes no guest facts from an unsuccessful command even when its
output is valid JSON. On agreement it writes `virtualbox-binding.json` into the guest user's private agentctl
state directory. Inside the gate,
`tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity` recomputes the live census and the
`vboxsf` bind-mount entry and requires both to equal the receipt;
`tests/integration/test_virtualbox_binding.py::test_capacity_and_dependency_receipt` requires the same CPU affinity,
memory, swap and dependency versions. Any source edit after binding fails identity until binding is rerun. These
nodes key on the checkout being the `vboxsf` bind mount, as the gate preflight does: on native Debian outside
VirtualBox, and inside the guest on a non-shared tree such as the clean container, they assert that no
shared-folder binding is claimed, and on Windows and macOS they assert refusal (D-164); the
[deletion ledger](../../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md) records where present nodes key on the
guest's product name instead. The receipt proves only that the binding is current
([T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C1), and containment beyond recorded
identities is outside the verdict (T.C C4). Guest runs set `TMPDIR` to a short directory on the ext4 root, such
as `/t`, so private socket paths stay short and temporary trees stay off memory-backed storage.

The binding nonce challenge refuses a source root that is a symbolic link or Windows junction
(`tests/integration/test_binding_challenge.py::test_challenge_refuses_linked_source_root`). Limits:
[T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C4.

D-133 and D-134 retire the superseded route, which the
[deletion ledger](../../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md) tracks until it is deleted; it supplies
no half.

## Agent Credentials in the VM

Agent credentials reach the guest only this way, and no credential content enters a report or log
([§ Q](../../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection)):

1. Add transient read-only shared folders of the host user's `.claude` and `.codex` folders to the running VM with
   `VBoxManage sharedfolder add <vm> --name=<share> --hostpath=<absolute folder> --readonly --transient`
   ([external tool facts](../reference/external_tool_facts.md)). No binary or installation directory is shared.
2. Mount them read-only with the in-kernel `vboxsf` driver at `/mnt/host-agents/claude` and
   `/mnt/host-agents/codex`, owned by the guest user with owner-only modes.
3. Symlink only `~/.claude/.credentials.json` to `/mnt/host-agents/claude/.credentials.json` and
   `~/.codex/auth.json` to `/mnt/host-agents/codex/auth.json`. The guest keeps its own writable `~/.claude.json`
   and settings, and the host stays the single writer of refreshed tokens.
4. Run each agent's status probe, `claude auth status` and `codex login status`; an agent whose probe succeeds is
   logged-in ([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)).
5. If a probe fails or the tokens desynchronize, replace those two symlinks with copies of the host files, mode
   0600, keep the host originals intact and record the choice in the host-facts diagnostics.

Never run a login command or send login keystrokes. While an agent is not logged-in, its logged-out branch still
runs, the `linux-live` half prints `absent`, and each phase that requires that half is at best
`awaiting:setup:agents-logged-in` ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)).

## One-Time Host Setup

Validation agents perform this setup as preparation, outside any gate run, for the capabilities whose provider in
the [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) table is the agent. Each capability has a
probe declared by the phase that awaits it; while the probe reports absence, only the phases awaiting it wait, each
at best `awaiting:setup:<capability>` ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)).

| Capability | Agent action |
|---|---|
| `setup:agents-logged-in` | Install the claude and codex CLIs in the dedicated guest, on the `PATH` the guest gate run inherits, and share their credentials as [Agent Credentials in the VM](#agent-credentials-in-the-vm) describes; the application itself never installs an agent CLI or logs it in |
| `setup:msvc-build-tools` | Install Visual Studio Build Tools and the Windows SDK on the Windows host with an explicit component plan, quietly and without a restart |
| `setup:container-runtime` | Install a container runtime from the guest's Debian archives, such as `podman`, which builds the clean recipe without a daemon and runs rootless for the guest user, for the `linux-clean` half |
| `setup:agent-permissions` | Maintain the Claude Code allowlist in the user-level `~/.claude/settings.json`, outside the checkout, limited to ssh to the dedicated VM, `VBoxManage` for that VM, the binder, `agentctl` and deletion of verified cache paths, with no wildcard grant |

[External tool facts](../reference/external_tool_facts.md) records the interfaces these actions use. Setup never
runs a login command or sends login keystrokes, never changes another VM or session, grants no wildcard permission
and changes no host agent configuration beyond that allowlist. A capability whose setup needs elevation or a
restart the host cannot grant without disturbing existing environments stays absent.

No setup ever restarts the host. Native runs on the Windows host or the Mac wait until the non-disruptive gate
environment and, on Windows, its job containment arm are in place, and until then all testing runs in the dedicated
guest (D-181). Build parallelism stays within the resource plan so running VMs keep headroom. The `linux-live` half
runs only on the triggers of the [testing-cost method](../../AGENTS.md#testing-cost-method). The Windows harness
provisioning leg is the only gate step outside the live half that uses the network, and only for pinned,
digest-checked downloads (D-180).

## Quantitative Resource Plan

Before preparation, record actual Windows logical processors, available physical memory, system commit/limit,
free bytes on the VDI and source volumes, other running VMs and the dedicated VDI's configured capacity. Inside
Debian, record available processors and affinity, memory/swap availability, cgroup controllers/effective limits
and filesystem free bytes/inodes. A disk's sparse maximum is not its currently allocated size or host free space.
A copied value from another machine is not a resource observation.

The resource receipt names numerical values for the following plan before a run starts:

| Budget | Basis and required observation |
|---|---|
| CPU | Chosen worker count and affinity/quota bounded by measured available host/VM capacity after an explicit reserve for other workloads |
| Memory | Effective workload limit, measured per-worker/build peak and aggregate parallelism, plus explicit headroom for tools and native agents |
| Swap/commit | Chosen owned-workload swap policy and host commitment reserve; neither unlimited swapping nor RSS alone establishes safety |
| Storage | Debian root filesystem, toolchains, dependency stores, simultaneous build/mutant trees, temporary data and retained logs, plus explicit safety/free-space reserve |
| Duration | Step and whole-run deadlines, including the leg deadline decision D-139 records, plus independent sampling interval and stop threshold for resource pressure |

Choose build parallelism so its measured peak plus fixed process overhead fits the effective memory budget.
Choose native mutation concurrency from the same aggregate calculation. Until a workload has a measured peak,
start with a bounded single-worker calibration and retain its measurements; do not assume an arbitrary RAM
number is sufficient for every machine. Calibration failure is evidence for resizing the owned environment,
not permission to relax assertions, mutate tool pins or repeatedly exhaust host commitment. Rerunning a full
gate is never a calibration step; follow the testing-cost method in [AGENTS.md](../../AGENTS.md) instead.

The budget calculation checks supplied peak, capacity, reserve and deadline values, including combined demand
when the source and the VM disk share a host volume
(`tests/governance/test_wsl_budget.py::test_budget_combines_shared_volume_demands`). The cgroup observation reads
one process's identity, affinity and hierarchical CPU, memory and swap limits twice, refusing a changed sample
(`tests/integration/test_wsl_cgroup_observation.py::test_process_limits_refuse_changed_sample`), and the guest
sample reads Linux memory, affinity and filesystem facts
(`tests/integration/test_wsl_guest_sample.py::test_guest_sample_reads_native_filesystem`). Their results are
recorded host facts; containment beyond recorded identities, including escaped descendants and continuous
sampling, is outside the verdict ([T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C4).

On Windows and Linux, newly registered test observers include native process creation identity so
containment can distinguish an owned process from a later process that reused its PID. Older PID-only
records remain conservative. Darwin creation identity is built by
[macOS acceptance](../../DEVELOPMENT_PLAN/phase-13-macos-acceptance.md).

Apply workload-local cgroup v2 memory/swap/CPU limits and affinity where supported, and record their effective
values for the gate and its descendants. A dedicated systemd scope/slice is one supported mechanism after its
controllers are observed; merely supplying a command-line setting is not proof of enforcement. Budget the VM disk
and build storage, and record Linux space and the host-volume reserve; observed limits are recorded host facts,
never a readiness gate (T.C C4). No validation action terminates other VMs or host sessions.

## Bind the Same Checkout

The Linux working path must be a real bind mount of the live Windows agentctl checkout, not a clone, copy,
archive extraction, rsync mirror or export of the last commit. This is essential because agents never commit:
uncommitted edits and new files must immediately exist on both sides.

The guest exposes the checkout through the `vboxsf` shared folder at `/mnt/agentctl-src`, bound at
`/srv/agentctl`, and the binder of [Dedicated VirtualBox VM](#dedicated-virtualbox-vm) proves source identity,
complete byte census agreement, two-way fresh nonce visibility including unstaged and untracked state, ordinary
read/write and owned-sentinel cleanup before the write-guard snapshot. The gate does not mount
filesystems itself. The binding challenge creates an exclusive nonce directory, verifies both sentinel contents
and leaves unexpected or changed files in place
(`tests/integration/test_binding_challenge.py::test_challenge_refuses_changed_bytes`,
`tests/integration/test_binding_challenge.py::test_challenge_preserves_unexpected_entries`).

Do not alter shared source files during either host's check, and never run the Windows and guest gates
concurrently against a mutable checkout. All Linux build outputs, virtual environments, package stores, temporary
files, private sockets, state and observer records remain on the guest's ext4 filesystem, outside the
bind-mounted checkout. The `vboxsf` mount keeps its own permission, case and link behavior, recorded as mount
facts; checks needing POSIX source semantics run on guest ext4 roots, and no Linux-native source copy replaces
the bound checkout.

## Prepare Linux Dependencies

Inside the dedicated Debian instance, install all declared Linux prerequisites before running checks: supported
Python and pipx, the editable agentctl dev extra, the gate's actual development tools, Git for the read-only
baseline, then GHC build prerequisites, pinned ghcup/GHC/cabal and style tools, tmux and external agent CLIs only
when introduced subjects require them. Validation of
[Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) and
[Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md)
needs no later compiler, backend or agent dependency. Invoke the Linux executables and inspect their actual
native paths.

Use Haskell's public runtime preparation for Debian tmux and Python's necessary application bootstrap. The
preparation receipt records all actions and subsequent readiness probes. Install and configure agents only in
this dedicated environment. Credentials reach the guest only as
[Agent Credentials in the VM](#agent-credentials-in-the-vm) describes. Never run login or send dialog or prompt
input to manufacture a `pass`.

## Canonical Run Sequence

Run `agentctl check` only on the triggers of the testing-cost method in [AGENTS.md](../../AGENTS.md). A run that
produces phase evidence follows these steps in order. No source edit happens between the binder and the last gate;
an edit restarts the sequence at its first step.

1. Finish the last source edit. Run the changed and new targeted nodes. Run the search-only check below, which
   confirms that every corpus search matches its target exactly once without running any killer, and rerun
   `tests/governance/test_mutants.py::test_corpus[<mutant>]` only for a mutant whose target, search or killer
   changed. Run the ratchet and register every new file in `src/agentctl/check/source_ownership.toml`; an unowned
   present artifact is a shared failure of every phase
   ([T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures)). From the checkout root, the search-only check
   prints the ids whose search does not match exactly once, so `[]` passes:

   ```text
   python -B -c "from pathlib import Path; from agentctl.check.mutants import corpus, patch; from agentctl.foundation import Err; print([m.identifier for m in corpus(Path('.')).value if isinstance(patch(Path(m.target).read_bytes(), m.search.encode(), m.replacement.encode()), Err)])"
   ```

2. Clear tool caches from the checkout: delete exactly the verified `.pytest_cache`, `.ruff_cache` and
   `__pycache__` directories inside it.
3. From the checkout root on Windows, run the binder with the editable dev installation's interpreter:
   `python -I -B -m agentctl.check.virtualbox_bind ROOT VM SHARE GUEST_ROOT KEY KNOWN_HOSTS PORT USER`. Isolated
   mode ignores every `PYTHON*` variable, so `-B` is what keeps bytecode out of the checkout
   ([external tool facts](../reference/external_tool_facts.md)).
4. In the guest, run `agentctl check` from `/srv/agentctl` with `TMPDIR` set to a short ext4 directory such as
   `/t`, detached from the SSH session, with its output written outside the checkout.
5. For a `linux-clean` half, build the clean container in the guest with its container runtime from the
   clean-host recipe, using a byte-identical copy of the bound checkout, run `agentctl check` inside it with its
   output and state on the guest's ext4 storage, and import its receipts into the guest store; the container never
   substitutes for the bind mount (D-142). The guest run evaluates the `setup:container-runtime` probe, and the
   container run natively evaluates only the `linux-clean` half, which it qualifies from the clean state it
   observes under its own nonce, never from that probe (D-164), and the kills and coverage that only the bound
   checkout reaches come from the guest run of step 4
   ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict), D-168).
6. For a `windows` half, export the stored guest receipts and import them into the host store over the binder's
   SSH channel, run the native Windows `agentctl check` on the same checkout, then carry its receipts back to the
   guest store the same way. The receipt store's import and export belong to
   [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md), and
   [Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) builds the SSH channel.

Never run the Windows and guest gates concurrently while the checkout can change.

## Focused Development Sweep

The sweep of the testing-cost method is a focused development tool, never closure evidence
([§ R](../../DEVELOPMENT_PLAN/development_plan_standards.md#r-imported-practices-and-explicit-non-adoption)), and
`--stepwise` is never passed to `agentctl check`. In the guest it runs from `/srv/agentctl` with every cache
outside the checkout:

```text
cd /srv/agentctl
export TMPDIR=/t RUFF_CACHE_DIR=/t/sweep/ruff PYTHONPYCACHEPREFIX=/t/sweep/pyc COVERAGE_FILE=/t/sweep/coverage
unset PYTEST_ADDOPTS
~/.local/share/pipx/venvs/agentctl/bin/python -m pytest --stepwise -o cache_dir=/t/sweep/pytest <targets>
```

Stepwise keeps its state in the pytest cache, so the sweep moves the cache with a private `cache_dir` instead of
disabling the cache provider, which would also remove `--stepwise`
([external tool facts](../reference/external_tool_facts.md)). The sweep runs with `PYTEST_ADDOPTS` unset, because
a cache provider disabled there leaves `--stepwise` accepted but inactive. Each sweep resumes from the last
failing test it recorded, so a corrected failure continues the sweep instead of restarting it. Other focused
pytest runs pass `-p no:cacheprovider`, and the static tools run with the same environment.

## Run and Retain Evidence

Follow the [canonical run sequence](#canonical-run-sequence) with the dev extra installed. The parent retains its
report outside the checkout before removing temporary roots: original UTF-8 output, nonce-bound
collection/execution manifests, scoped coverage and mutants, source, tool and backend hashes, resource and binding
observations and finalizer results. It publishes verdicts as the
[quality gate](../engineering/quality_gate.md#phase-verdicts-and-evidence-line) describes
([T.O](../../DEVELOPMENT_PLAN/development_plan_standards.md#to-output)) and writes a receipt for each half the run
evaluates natively into the [receipt store](../engineering/quality_gate.md#receipt-store). A later owned failure
leaves an earlier verdict unchanged; the shared failures of
[T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures) fail every phase.

A native Windows run independently observes its private psmux build and actual server identities. A native
Darwin run independently observes Darwin toolchain and backend behavior. A foreign half joins only through a
stored receipt with equal logical and prerequisite identities
([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict) V8,
[T.I](../../DEVELOPMENT_PLAN/development_plan_standards.md#ti-identity)); Linux evidence is never relabelled as
another OS.

## Native Darwin Run

[macOS acceptance](../../DEVELOPMENT_PLAN/phase-13-macos-acceptance.md) builds the native Darwin gate entry. This
run applies once the [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) table lists `macos` as
available:

1. Prepare the Mac's prerequisites as their capability probes require. The Command Line Tools that
   `setup:xcode-clt` probes need a dialog that a person completes (the GHC system requirements row of
   [external tool facts](../reference/external_tool_facts.md)), so they are host provision that the user supplies
   with the Mac, as [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) records. No run, check or
   agent answers that dialog; while the probe reports absence, the phases that need the `macos` half are at best
   `awaiting:setup:xcode-clt` ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)).
2. Place on the Mac a byte-identical tree of the checkout whose logical identity equals that of the stored `linux`
   receipts ([T.I](../../DEVELOPMENT_PLAN/development_plan_standards.md#ti-identity), D-151); that tree never
   substitutes for the bind mount of the live checkout. Install it with `pipx install --editable '.[dev]'`.
3. Export the stored `linux` receipts and import them into the Mac's receipt store over a channel the agent
   prepares, clear tool caches and run the native `agentctl check` with a short `TMPDIR`, with no edit since the
   Linux gate.
4. Import the `macos` receipts into the Linux receipt store the same way. On the Mac, that phase's verdict line
   shows its `linux` half as `stored` and its `macos` half as `own`
   ([T.O](../../DEVELOPMENT_PLAN/development_plan_standards.md#to-output)); no other family substitutes for `macos`.

## Cleanup and Reuse

Inspect owned process/endpoint liveness, reap children and close file handles before removing registered
run roots. Check every resolved absolute deletion target against the registered allowed roots. End a private
server only after verifying its endpoint lies there; never kill by executable image name. Preserve failed
reports and exact cleanup diagnostics. Do not unregister the VM, delete its disk or modify unrelated VMs or
sessions as routine gate cleanup. Reuse qualified dependency caches, but never a test verdict, baseline or kill
from another run ([T.K](../../DEVELOPMENT_PLAN/development_plan_standards.md#tk-kill)); a foreign half enters
only through the receipt store.

## Related

- [quality_gate.md](../engineering/quality_gate.md) — gate mechanics, verdicts and receipts.
- [testing.md](../engineering/testing.md) — evidence, isolation and resource controls.
- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — preparation owners and consent.
- [installation.md](installation.md) — pipx and first-use behavior.
- [troubleshooting.md](troubleshooting.md) — unmet native, resource and binding capabilities.
- [files_and_state.md](../reference/files_and_state.md) — registered roots and retained reports.
- [external_tool_facts.md](../reference/external_tool_facts.md) — official VirtualBox and native interfaces.
- [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) — the available halves and setup capabilities.
- [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) — runbook and phase-evidence owner.
