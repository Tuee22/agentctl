# Validation Runbook

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Define automatic, resource-budgeted native and WSL2 validation against the same editable checkout without Git commits or changes to the user's running environments.

This runbook specifies preparation and evidence requirements. It does not attest that a distribution,
resource limit, bind mount or backend is present. The gate independently observes the prepared state and
records the actual source/tool/backend identities. [External tool facts](../reference/external_tool_facts.md)
holds the official interfaces and verification sources used here.

## Select the Native Lane

The development plan declares Linux plus at most one additional hardware family for any phase. Debian on
WSL2 can supply Linux execution from a Windows workstation. It cannot supply native Win32 process/ACL/console,
psmux or Darwin behavior. Required Windows runs use native Windows executables; required macOS runs use actual
Darwin hardware. Missing hardware remains unmet evidence and never becomes a manual attestation.

All validation uses the same no-argument `agentctl check` entry point from an editable dev installation.
Preparation can invoke the public application before the test process begins; test bodies run no package
manager, sudo, login command or installer. Ordinary checks neither prompt nor answer a dialog.

## Dedicated WSL2 Distribution

Use a Debian distribution dedicated to agentctl, with a distinct registered name, installation location,
Linux user, home and dependency stores. Observe its actual WSL version and require version 2, then read its
native `os-release` and require exact `ID=debian`. An existing personal/work distribution is not repurposed.
Inspect existing registered distributions read-only before provisioning the dedicated one.

Creation/import uses the installed WSL interface and verified Debian rootfs provenance. Record distribution
name, rootfs identity, WSL/kernel version, canonical installation/VHD location and native Linux architecture.
No validation action changes another distribution, changes the default distribution, edits the user's global
`.wslconfig`, or runs global WSL shutdown. An owned distro can be stopped only after checking its identity and
confirming no owned validation is active. Host feature/elevation/restart requirements that cannot be met
without affecting existing environments remain explicit unmet setup capabilities.

A WSL2 distribution is a separate Linux environment but can share the WSL utility VM's kernel and resources.
Its name alone does not prove independent CPU/RAM limits. Global `.wslconfig` limits apply across WSL2; use
verified workload-local Linux controls in the dedicated distro rather than changing that global configuration.

## Quantitative Resource Plan

Before preparation, record actual Windows logical processors, available physical memory, system commit/limit,
free bytes on the VHD/source volumes, other active WSL workloads and the dedicated VHD's configured capacity.
Inside Debian, record available processors and affinity, memory/swap availability, cgroup controllers/effective
limits and filesystem free bytes/inodes. A disk's sparse maximum is not its currently allocated size or host
free space. A copied value from another machine is not a resource observation.

The resource receipt names numerical values for the following plan before a run starts:

| Budget | Basis and required observation |
|---|---|
| CPU | Chosen worker count and affinity/quota bounded by measured available host/WSL capacity after an explicit reserve for other workloads |
| Memory | Effective workload limit, measured per-worker/build peak and aggregate parallelism, plus explicit headroom for tools and native agents |
| Swap/commit | Chosen owned-workload swap policy and host commitment reserve; neither unlimited swapping nor RSS alone establishes safety |
| Storage | Debian/rootfs, toolchains, dependency stores, simultaneous build/mutant trees, temporary data and retained logs, plus explicit safety/free-space reserve |
| Duration | Step and whole-run deadlines, plus independent sampling interval and stop threshold for resource pressure |

Choose build parallelism so its measured peak plus fixed process overhead fits the effective memory budget.
Choose native mutation concurrency from the same aggregate calculation. Until a workload has a measured peak,
start with a bounded single-worker calibration and retain its measurements; do not assume an arbitrary RAM
number is sufficient for every machine. Calibration failure is evidence for resizing the owned environment,
not permission to relax assertions, mutate tool pins or repeatedly exhaust host commitment.

Apply workload-local cgroup v2 memory/swap/CPU limits and affinity where supported, and verify their effective
values for the gate and every descendant. A dedicated systemd scope/slice is one supported mechanism after its
controllers are observed; merely supplying a command-line setting is not proof of enforcement. Budget the
VHD and build storage through the supported installed WSL/filesystem controls, and verify both Linux space
and host-volume reserve. If limits or storage guarantees cannot be established, the environment is not ready.
A watcher records pressure throughout preparation/build/test execution and stops only owned work before the
recorded host reserve is breached. It never terminates other WSL distributions or host sessions.

## Bind the Same Checkout

The Linux working path must be a real bind mount of the live Windows agentctl checkout, not a clone, copy,
archive extraction, rsync mirror or export of the last commit. This is essential because agents never commit:
uncommitted edits and new files must immediately exist on both sides.

For a checkout at `C:/Users/matth/agentctl`, the observed Windows-mounted source is normally exposed through
`/mnt/c/Users/matth/agentctl`. Verify that actual mapping before using it. Create an owned Linux mountpoint
such as `/work/agentctl` and bind the observed source there through the Linux mount interface. Provisioning
privilege applies only to this dedicated environment. The gate does not mount filesystems itself.

Before the write-guard starts, an independent binding check performs all of these operations:

1. Resolve the canonical Windows source path and Linux source/mountpoint paths. Record the applicable mount
   entry from `/proc/self/mountinfo` and the source/root mapping observed by native mount inspection.
2. Create a fresh unpredictable sentinel within a reserved source-binding directory from Windows, containing
   the binding nonce; read exactly those bytes through the Linux bind mount.
3. Write a distinct nonce-bound acknowledgment through the Linux mount, then verify it from the Windows
   checkout. Verify new uncommitted files are visible in both directions and changes affect the same source.
4. Compare the complete declared source inventory by relative path and bytes, including uncommitted files,
   while preserving the read-only Git HEAD/index/ref observations. No commit or staging action participates.
5. Remove only those exact owned sentinels and confirm their absence on both sides before taking the gate's
   checkout snapshot. Retain their hashes, nonce and mount observations in the external binding receipt.

Do not alter shared source files during either host's check. Do not run Windows and WSL gates concurrently
against a mutable checkout. All Linux build outputs, virtual environments, package stores, temporary files,
private sockets, state and observer records remain in the dedicated distro's Linux filesystem, outside the
bind-mounted checkout. Bind mounting DrvFs source does not turn its permission/case/link behavior into ext4.
Probe the source semantics actually needed by packaging/digest validation; if they are unsupported, report
the limitation instead of inventing a Linux-native source-copy pass. Native filesystem tests use owned Linux
roots and separately identify their source filesystem assumptions.

## Prepare Linux Dependencies

Inside the dedicated Debian instance, install all declared Linux prerequisites before running checks: supported
Python and pipx, the editable agentctl dev extra, the gate's actual development tools, Git for the read-only
baseline, then GHC build prerequisites, pinned ghcup/GHC/cabal and style tools, tmux and external agent CLIs only when introduced subjects require them. Governance and Python-discipline validation do not require future compiler/backend/agent dependencies. Invoke the Linux executables and inspect their actual native paths;
WSL interoperability must not silently select Windows `python.exe`, `claude.exe` or another host tool.

Use Haskell's public runtime preparation for Debian tmux and Python's necessary application bootstrap. The
preparation receipt records all actions and subsequent readiness probes. Install/configure agents only in
this dedicated environment. Authorized copies of host credentials remain private to its Linux user, with
restricted files/directories and host originals intact; no credential content is printed or stored in reports.
If authentication is unavailable, the automatically observed logged-out branch still runs, and live-agent
acceptance remains unmet. Never run login or send dialog/prompt input to manufacture a passing lane.

## Run and Retain Evidence

Run `agentctl check` from the bind-mounted editable checkout with the dev extra installed. Preserve original
UTF-8 output, nonce-bound collection/execution manifests, scoped coverage/mutants, source/tool/backend hashes,
resource/binding observations, shared integrity finalizers and independent phase/lane verdicts. Publish reports
outside the checkout before removing temporary roots. Later failures remain in the overall result without
erasing an earlier complete verdict; a shared integrity failure invalidates every dependent receipt.

A native Windows run independently observes its private psmux build and actual server identities. A native
macOS run independently observes Darwin toolchain and backend behavior. Lane receipts join only matching
source/prerequisite contract identities; Linux evidence is never relabelled as another OS.

## Cleanup and Reuse

Inspect owned process/endpoint liveness, reap children and close file handles before removing registered
run roots. Check every resolved absolute deletion target against the registered allowed roots. End a private
server only after verifying its endpoint lies there; never kill by executable image name. Preserve failed
reports and exact cleanup diagnostics. Do not unregister a distro, delete its VHD or modify unrelated sessions
as routine gate cleanup. Reuse qualified dependency caches, never old test verdicts or mutant kills.

## Related

- [quality_gate.md](../engineering/quality_gate.md) — independent phase/lane verdicts and receipts.
- [testing.md](../engineering/testing.md) — evidence, isolation and resource controls.
- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — preparation owners and consent.
- [installation.md](installation.md) — pipx and first-use behavior.
- [troubleshooting.md](troubleshooting.md) — unmet native, resource and binding capabilities.
- [files_and_state.md](../reference/files_and_state.md) — registered roots and retained reports.
- [external_tool_facts.md](../reference/external_tool_facts.md) — official WSL/native interfaces.
- [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) — runbook and phase-evidence owner.
