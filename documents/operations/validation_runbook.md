# Validation Runbook

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Define automatic, resource-budgeted native and VirtualBox Linux validation against the same editable checkout without Git commits or changes to the user's running environments.

This runbook specifies preparation and evidence requirements. It does not attest that a distribution,
resource limit, bind mount or backend is present. The gate independently observes the prepared state and
records the actual source/tool/backend identities. [External tool facts](../reference/external_tool_facts.md)
holds the official interfaces and verification sources used here.

## Select the Native Lane

The development plan declares Linux plus at most one additional hardware family for any phase. A dedicated
Debian VirtualBox guest can supply Linux execution from a Windows workstation. It cannot supply native Win32 process/ACL/console,
psmux or Darwin behavior. Required Windows runs use native Windows executables; required macOS runs use actual
Darwin hardware. Missing hardware remains unmet evidence and never becomes a manual attestation.

All validation uses the same no-argument `agentctl check` entry point from an editable dev installation.
Preparation can invoke the public application before the test process begins; test bodies run no package
manager, sudo, login command or installer. Ordinary checks neither prompt nor answer a dialog.

## Dedicated VirtualBox VM

On Windows, use a Debian VM dedicated to agentctl. Observe its identity, host and guest capacity, configured
CPU and memory allocation, storage and swap, with host headroom and observed usage when practical.
Keep VM state and build outputs on dedicated storage. Install and verify the dependencies needed for the selected
work; use restricted private copies of host credentials only as authorized in AGENTS.md. Do not alter other
projects or existing sessions. Expose the live checkout to the guest and bind mount it; prove source identity,
complete byte census agreement, two-way fresh nonce visibility and owned-sentinel cleanup. Observe and record the
mount's permission-change, lock, case and symlink behavior as mount facts; they are not qualification
prerequisites, and tests needing POSIX filesystem semantics use dedicated Linux roots. Missing identity, census,
visibility or cleanup proof is an unmet Linux route, not a passing result.

The current transport is a transient VirtualBox shared folder named `agentctl-src` whose host path is the live
checkout, with the per-share symlink-creation setting enabled. The guest mounts it with the in-kernel `vboxsf`
driver at `/mnt/agentctl-src` using `uid=1000,gid=1000,fmode=0644,dmode=0755` and bind mounts that path at
`/srv/agentctl`; the repository has `core.filemode=false` and every tracked file is mode 100644. Recorded mount
facts on this transport: `chmod` succeeds but the observed mode stays the mount's fixed mode; case-distinct names
collide; a guest-created relative symlink is created as a Windows symbolic link and reads back; and guest
byte-range locks are not coordinated with Windows handles. The editable dev extra installs with `pipx` into the
guest user's Linux home, and gate state, reports and toolchains live on the guest's ext4 root filesystem.

After the last source edit and before each guest `agentctl check`, run the pre-gate binding from Windows:
`python -I -m agentctl.check.virtualbox_bind ROOT VM SHARE GUEST_ROOT KEY KNOWN_HOSTS PORT USER`. It reads the VM UUID,
creates a fresh nonce challenge in the live checkout, has the guest answer it with the application's own
`binding_challenge.answer` over strict-host-key batch SSH, confirms no guest process still carries the nonce, removes
the owned sentinels, then compares the host and guest source census digests. On agreement it writes
`virtualbox-binding.json` into the guest user's private agentctl state directory. Inside the gate,
`tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity` recomputes the live census and the
`vboxsf` bind-mount entry and requires both to equal the receipt;
`tests/integration/test_virtualbox_binding.py::test_capacity_and_dependency_receipt` requires the same CPU affinity,
memory, swap and dependency versions. Any source edit after binding fails identity until binding is rerun. On native
Debian outside VirtualBox these tests assert that no shared-folder binding is claimed; on Windows and macOS they assert
refusal. The receipt is a local currency check, not an authenticated record of a historical run. Guest runs set
`TMPDIR` to a short directory on the ext4 root, such as `/t`. VirtualBox observations, bridge containment and
resource evidence are not yet integrated into the gate and must be implemented and validated in
[governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md).

The binding nonce challenge refuses a source root that is a symbolic link or Windows junction
(`tests/integration/test_binding_challenge.py::test_challenge_refuses_linked_source_root`). This check does not
establish race-free path containment or qualify a sharing transport.

The diagnostic VirtualBox guest observer reads Debian, kernel, DMI, machine-ID and effective-UID facts and
exchanges them with a nonce. Its value and bounded-input controls are
`tests/governance/test_virtualbox_guest.py::test_guest_identity_rejects_foreign_and_ambiguous_values`,
`tests/governance/test_virtualbox_guest.py::test_guest_protocol_rejects_stale_foreign_and_ambiguous_values`
and `tests/integration/test_virtualbox_observe.py::test_guest_protocol_input_is_bounded`. Matching guest-supplied
values do not authenticate the VM, transport, source mount or any gate receipt.
The guest-capacity protocol binds a nonce and canonical guest storage path to guest identity, affinity, memory,
swap and filesystem values, with identity observations around the local resource read
(`tests/governance/test_virtualbox_guest_capacity.py::test_capacity_protocol_refuses_stale_ambiguous_and_invalid_values`,
`tests/governance/test_virtualbox_guest_capacity.py::test_capacity_join_rejects_changed_identity`,
`tests/integration/test_virtualbox_observe.py::test_guest_capacity_protocol_refuses_ambiguous_input`). It does
not authenticate the peer or storage path provenance. A separate value join checks the exact request and
compares guest CPU, memory and filesystem sizes against host samples and the VM's reported resources
(`tests/governance/test_virtualbox_capacity.py::test_guest_capacity_join_refuses_mismatched_or_impossible_values`).
Numerical consistency does not establish that the guest filesystem resides on the observed disks.
The host diagnostic brackets a `VBoxManage` query with executable-file identity observations, matches its owned
child PID and process-image path, and checks the requested UUID and required configuration fields. Its controls
include `tests/governance/test_virtualbox_host.py::test_machine_observation_rejects_ambiguity_and_wrong_identity`,
`tests/governance/test_virtualbox_host.py::test_process_image_join_rejects_other_files_and_pids` and
`tests/integration/test_virtualbox_observe.py::test_host_observer_refuses_missing_executable`. The shared Windows
process-image observer reads a path, creation time and wait state through one process handle; its controls include
`tests/governance/test_process_image.py::test_checked_image_refuses_dead_or_ambiguous_values` and
`tests/integration/test_virtualbox_observe.py::test_exited_process_image_is_refused`. A path observation does not
prove mapped executable bytes, VM provisioning, storage ancestry, peer identity or complete process containment.
The NAT diagnostic accepts only one connected NAT adapter, seven explicitly disabled adapters and one requested
IPv4 loopback TCP forward, and compares two VM configurations
(`tests/governance/test_virtualbox_host.py::test_nat_route_requires_one_loopback_forward`,
`tests/governance/test_virtualbox_host.py::test_nat_join_refuses_changed_route_or_vm`). A matching host rule does
not authenticate the SSH listener or guest process; network and guest containment remain required.
The listener diagnostic additionally checks that a locked VirtualBox session PID matches the unique loopback
TCP listener owner, then repeats the host and process observations
(`tests/governance/test_virtualbox_host.py::test_listener_binds_locked_vm_to_loopback_owner`,
`tests/governance/test_virtualbox_host.py::test_listener_join_requires_original_process`). It does not
authenticate the SSH guest key, COM server, mapped process bytes or continuous containment.
The SSH host-key value comparison checks a canonical Ed25519 key and a single literal loopback known-host
entry (`tests/governance/test_virtualbox_guest.py::test_guest_host_key_comparison_refuses_foreign_or_malformed_keys`).
An application diagnostic brackets a fixed guest-control public-key read with listener and local-file observations
(`tests/integration/test_virtualbox_observe.py::test_guest_control_key_files_are_bounded_and_contained`,
`tests/governance/test_virtualbox_host.py::test_guest_control_key_join_retains_independent_failures`). It checks
the host child image and retains errors without reading credential contents into its result. It does not establish
guest process termination after a failure, file-operation race resistance, credential ACLs or an authenticated SSH
session. The guest command requests both output waits and uses a fresh nonce in its argument zero, but no independent
guest process observation currently binds that nonce. An owned timeout experiment left a VirtualBox guest session
after its guest PID exited; a host child exit alone cannot establish guest-session cleanup. The key diagnostic now
refuses a still-visible session matching its host PID and VM while preserving unrelated sessions
(`tests/governance/test_virtualbox_host.py::test_guest_control_session_listing_preserves_other_sessions`). An absent
listed session is not proof that guest processes and descendants have terminated, and this observer never closes one.
The VDI diagnostic reads a bounded version-1.1 base dynamic image header and checks the file identity inside a
supplied root (`tests/governance/test_virtualbox_storage.py::test_vdi_header_refuses_invalid_identity_and_capacity`,
`tests/governance/test_virtualbox_storage.py::test_vdi_file_observation_checks_owned_root`). It does not prove
VM attachment, race-free containment, physical allocation or differencing-image ancestry. A separate diagnostic
joins one explicitly selected controller slot to repeated VM and VDI observations
(`tests/governance/test_virtualbox_snapshot.py::test_attachment_refuses_ambiguous_and_invalid_slots`,
`tests/governance/test_virtualbox_snapshot.py::test_snapshot_join_refuses_changed_vm_and_foreign_disk`); it does
not authenticate the VM. A further diagnostic enumerates reported ports on supported AHCI controllers and
joins every supported VDI across repeated observations
(`tests/governance/test_virtualbox_inventory.py::test_inventory_includes_all_disks_and_refuses_ambiguous_slots`,
`tests/governance/test_virtualbox_inventory.py::test_inventory_join_rejects_changed_or_missing_disks`). It
refuses other controller layouts and unsupported disk formats; the full storage vocabulary and authenticated
census remain open. A running-VM diagnostic
found that `VBoxManage`'s reported on-disk size differed substantially from the host file's logical length; neither
value alone establishes a storage budget. The versioned header source is in [external tool facts](../reference/external_tool_facts.md#virtualbox-vdi-metadata).
The capacity diagnostic brackets a host memory/commit and volume sample with VirtualBox inventories
(`tests/governance/test_virtualbox_capacity.py::test_capacity_requires_stable_inventory_and_complete_host_facts`).
Its counter executable uses the native system-directory lookup and file-identity checks
(`tests/integration/test_wsl_host_sample.py::test_host_counter_executable_ignores_environment_redirect`).
The result is a point-in-time observation, not an authenticated receipt, measured workload peak or isolation proof.

The following WSL-specific mechanisms document existing implementation and historical observations for
migration. They do not authorize WSL validation on Windows or constitute VirtualBox evidence. Existing Hyper-V
observers also remain migration inputs; neither route proves VirtualBox readiness. Preserve their controls until
equivalent VirtualBox observations and negative cases are implemented and validated.

The legacy Hyper-V diagnostic reads exactly one well-formed effective UID field from process status;
malformed duplicate UID fields are refused (`tests/governance/test_hyperv_guest.py::test_guest_identity_refuses_foreign_and_ambiguous_hosts`).
That local control does not authenticate a VM peer or establish VirtualBox evidence.

## Legacy WSL2 Distribution Mechanisms

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

The Windows registration observer reads the current user's WSL registry and native verbose listing, and can
compare the observed version, registration identifier and storage path with a recorded provisioning identity.
That comparison does not authenticate the provisioning record. The read-only `wsl_vhd.observe` adapter uses the Windows information-only virtual-disk API to observe the contained VHD virtual and physical sizes while checking file identity before and after; it does not establish provisioning ownership or a resource receipt. The `wsl_capacity.observe` join also brackets host counters and volume space with the VHD identity and retains the lowest free-space observations; guest identity, live limits and provenance remain separate. The listing decoder supports a UTF-16 fallback
when the child-only UTF-8 request is not honored; the fallback still needs native validation in that condition.
The storage observer resolves the VHD under an explicitly owned root and records its file identity, current file
length and host-volume free space. It does not establish the VHD's configured maximum, resource limits or workload
readiness.

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

The current `wsl_budget.problems` calculation checks supplied peak, capacity, reserve and deadline values,
including combined demand when source and VHD share a host volume. `wsl_cgroup.observe` reads one process's
identity, affinity and hierarchical CPU, memory and swap limits twice, refusing a changed sample. `wsl_tree`
compares process descendants with all members of a private cgroup and repeats the observations. `wsl_mount`
checks native mount and device identities twice, refuses partial hierarchies and hidden process namespaces,
and brackets the native tree observation. These operations do not establish workload ownership, detect processes
that escaped before or between samples, or apply limits. The mount observer has not yet been validated in WSL.
`wsl_host_sample` reads Windows memory counters and both volume identities; inaccessible or localized counter
names remain unmet. `wsl_guest_sample` reads Linux memory, affinity and filesystem facts, but its results still
need an independently observed VHD maximum and authenticated storage identity. `wsl_monitor` checks supplied
resource and process samples, including previously seen processes that remain alive outside the scope.
Coordinated live sampling, continuous escape detection and stopping owned work on pressure remain required.

On Windows and Linux, newly registered test observers include native process creation identity so
containment can distinguish an owned process from a later process that reused its PID. Older PID-only
records remain conservative. The Linux adapter still needs native validation; macOS creation identity
remains required before relying on that distinction there.

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

The current `binding_challenge.exchange` operation creates an exclusive nonce directory, verifies both
sentinel contents and refuses to remove unexpected or changed files. Its separate-process controls exercise
those operations. `binding_inventory` transports and compares complete relative paths, entry kinds and bytes
with a nonce, including ignored and untracked files. These operations alone are not a WSL binding receipt:
`binding_peer` also reads Linux host, mount and inode facts before answering the challenge. The initiating
transaction joins the peer message to local source bytes and compares source and Git observations around
cleanup. The peer can recheck host and mount identity around its observation that the nonce entry is absent. The observation response also carries guest memory, affinity and root filesystem capacity captured during the exchange; this does not establish which VHD backs that filesystem or authenticate a resource budget.
The transaction and standalone challenge exchange retain the challenge if their termination observer fails or
reports that the peer is active,
including when the peer already returned a response. A production observer must prove the actual guest peer
and its owned descendants stopped; a caller-supplied result alone does not establish that proof.
The host can hold the peer's request until a live systemd observation matches its nonce-derived unit, user,
control group and configured limits. A preliminary absence probe succeeded after that observation. The unit
status is not a process-origin receipt. A native observer can match the guest PID, executable, command, UID,
creation identity and cgroup against that unit while checking the native mount hierarchy. The integrated
observer brackets that process check with matching systemd unit observations; a preliminary WSL probe succeeded.
The launcher now retains a registered host handle across a timed-out wait, rechecks the original registration
before release and after termination, and checks guest termination before exposing a response. A termination
observer brackets checks of the original PID and recursive cgroup
population with terminal unit observations. Dedicated-WSL probes refused a live peer and accepted termination
after the same host child was reaped, including after a deliberately timed-out wait. A staged transaction has
joined the launcher to a fresh challenge, rechecked it before removal and completed an independently launched
remote-absence probe against the live checkout. A step-driven workflow has also completed that path while
retaining the same child across waits; the retained summary is diagnostic, not a binding receipt.
The launcher still must prove there is no delayed launch or escaped descendant, complete failure recovery and
provide an automated entry point. A retained timeout is still a failure even if the child later exits.
The peer's bounded stdin protocol handles observation and cleanup requests. It checks a configured non-root UID
for both responses, and brackets the cleanup observation with matching host identity. These are consistency
checks, not proof of process origin. The Windows-side command and response checks are implemented as value
calculations. A prepared transient systemd service now specifies a nonce-derived unit, non-root user, resource
limits and control-group cleanup. A preliminary dedicated-WSL absence request succeeded under that service,
and its unit was subsequently observed inactive and unloaded. The service receives its WSL distribution name
from the requested configuration, so that value alone does not authenticate its origin. A contained launcher
that authenticates the actual unit and proves peer and descendant termination on timeout remains required. The launcher,
authenticated cross-OS observations and receipt authentication remain required before this route can supply
Linux gate evidence.

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
