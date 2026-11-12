# psmux crash and installation investigation

Investigation date: **November 12, 2026**. All local times below use
**America/Toronto (EST, UTC-05:00)**. Findings describe the workstation as observed
that afternoon; upstream package availability can change.

## Findings

Three attached psmux clients crashed after extreme memory growth exhausted the
Windows system commit limit. Their dumps follow the same failed 64 KiB allocation
path into a fatal abort. The most likely underlying defect is upstream issue
**#882**: an unbounded client queue retains incoming screen frames while terminal
output is stalled.

The installed executables are **psmux 3.4.0**, released before the upstream fix.
Changing to a release-based package manager currently supplies the same affected
version. The recommended remedy is a separate, versioned source installation from
a pinned upstream revision containing the fix and its followup, validated before
switching the command aliases.

The investigation did not reproduce the local stall, build or validate a patched
binary, install software, change configuration, or restart or terminate sessions.

## Confirmed crashes

| Local time | PID | Command recorded in dump | Windows event |
|---|---:|---|---|
| 13:13:30 | 20360 | `psmux.exe new -s hostbootstrap` | Application Error 1000 |
| 13:13:39 | 24480 | `psmux.exe new -s shipnorth` | Application Error 1000 |
| 13:16:26 | 14380 | `psmux.exe new -s qrty` | Application Error 1000 |

All three processes had run since the previous evening. Their crash records agree:

- Executable version: `3.4.0.0`.
- Executable path: `C:\Users\matth\.local\bin\psmux.exe`.
- Exception: `0xc0000409`, with parameter `7` (fatal application exit).
- Fault offset: `psmux.exe+0x6f5c44`.
- Crash occurs on a secondary thread, through the same allocation-error path.

Inspection of the minidumps and executable instructions shows a failed
65,536-byte buffer allocation reaching the fatal abort. The separate
capacity-overflow branch is absent from those stacks. The exception's broad
Windows classification alone does not establish a stack buffer overflow.
The executable is stripped, and no matching PDB or debugger was available;
named-function attribution is therefore limited.

Two older `tmux.exe` crashes occurred on November 6, at 11:27:26 and 11:27:55.
They use a different binary and fault offset. Their underlying cause was not
established, so they are not attributed to this bug.

## Memory exhaustion

Seven Windows Resource-Exhaustion-Detector events, ID `2004`, appeared between
12:00:53 and 13:13:40. At 13:13:30 they attributed the following committed memory
to the three clients:

| Session | PID | Committed bytes | Approximate GiB |
|---|---:|---:|---:|
| `qrty` | 14380 | 120,649,420,800 | 112.4 |
| `shipnorth` | 24480 | 119,946,301,440 | 111.7 |
| `hostbootstrap` | 20360 | 91,601,977,344 | 85.3 |

The final exhaustion event records system commit of **451,727,622,144 bytes out
of 451,780,276,224 bytes: 99.988%**. Physical memory use was approximately
32 GiB out of 127 GiB. This was exhaustion of the Windows commitment limit,
which backs allocations with RAM and paging capacity; resident RAM was not full.

The surviving `systems` client, PID `26692`, had peak private commit of
**78,691,504,128 bytes (73.3 GiB)**. Its process memory counters exactly match its
historical exhaustion-event entry. By the investigation, current private commit
had fallen to approximately **112 MiB**. Address-space inspection found about
77 GiB of retained private reservations, mostly decommitted. That reservation is
not evidence that the process was still consuming 77 GiB of committed memory.

At 13:22:56, system commit had recovered to approximately 62.1 GiB out of a
203.1 GiB limit, about 30%.

## Match to the upstream defect

[Upstream PR #882](https://github.com/psmux/psmux/pull/882) describes an unbounded
incoming frame queue in the attached client. Its socket reader continues receiving
screen snapshots while the main thread is blocked writing terminal output.
Each queued message retains a buffer with at least 64 KiB of capacity.

The upstream reproduction grows to approximately 203.72 MiB in 8.5 seconds with
output blocked and returns to about 3 MiB when output resumes. The combination of
client-only runaway commitment, recovery after a stall, and the local failed
64 KiB allocation strongly matches this defect.

This remains a diagnosis from correlated evidence. The local investigation did
not capture what blocked output, prove that a particular browser or SSH
connection caused it, or reproduce the crash on the active workstation.

The maintainer's October 21 fix,
[`759bf78`](https://github.com/psmux/psmux/commit/759bf78776e5cda3f86d8a67a8f8aa2ee2ce95ce),
replaces superseded queued frames with the newest screen. It also avoids the
server disconnects that the initial bounded-channel patch could cause.
The later revision `063ca7026eb2b7b91a74d3f858bdec3dfc841dbb` includes that fix
and a correction preserving clipboard and bell events during frame replacement.

## Session status at investigation

- `hostbootstrap` and `shipnorth` retained their original server processes and
  have replacement attached clients. Their server PIDs are `20676` and `27824`.
- `qrty` has a new client and an adopted server from 13:17:32. Its original server,
  PID `8584`, is absent. Survival of the original `qrty` session is not established.
- Current `agentctl` and `systems` servers are also running.
- The final query found no additional psmux or tmux Application Error 1000 events
  that day after 13:16:26.

## Current installation

The executable installation is per-user:

| Item | Observed value |
|---|---|
| Binary directory | `%LOCALAPPDATA%\psmux` |
| Actual executable version | `3.4.0` |
| Commands | `psmux.exe`, `tmux.exe`, `pmux.exe` |
| Preferred command directory | `%USERPROFILE%\.local\bin` |
| Command indirection | Three symbolic links into `%LOCALAPPDATA%\psmux` |
| Windows uninstall registration | `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\psmux` |
| Registered display version | `3.3.8` |
| WinGet installed-package query | No match for `marlocarlo.psmux` |
| Scheduled updates | No psmux or relevant package-update task found in the query |

The binary directory is also on the user PATH, after `.local\bin`. The aliases
therefore resolve to the symlink targets under the current PATH ordering.
The installed `psmux.exe` has a valid publisher signature identifying
`Open Source Developer Godwin Josh`. Its SHA-256 is:

```text
BBE825A30F7CDDC91B043084049143A381ABA5F7E9E36E4D0BB587E296D262CA
```

The uninstaller is unsigned and still registered as 3.3.8. A signed 3.4.0 setup
executable is present in `%LOCALAPPDATA%\Temp\psmux-dl`.
These observations establish drift between the executable version and installer
metadata. Updating the binaries separately from the original installer is a
plausible explanation, but the exact installation history was not recovered.
WinGet's current no-match result does not prove WinGet was never involved.

## Why a package-manager switch does not patch this today

As checked on November 12:

| Distribution | Observed behavior |
|---|---|
| GitHub Releases | Latest release is `3.4.0`, published October 13 |
| WinGet | The inspected `marlocarlo.psmux` manifest downloads the 3.4.0 release ZIP |
| Official Scoop bucket | Manifest version is 3.4.0 and downloads the same release |
| Upstream PowerShell installer | Downloads the latest GitHub release unless a local build exists |
| Plain `cargo install psmux` | crates.io's latest stable package is 3.4.0 |
| Upstream CI | Builds Windows binaries but provides no downloadable build artifacts in the inspected workflow |

The October 13 release predates the October 21 memory fix. Reinstalling 3.4.0
through another release channel does not establish that the defect is patched.

## Recommended installation method

Use a **native Windows source build from a pinned official source archive**, with
a separate install directory for each accepted revision. The proposed initial pin
is:

```text
063ca7026eb2b7b91a74d3f858bdec3dfc841dbb
```

This pin contains the frame-queue fix and its clipboard/bell followup. It limits
the initial migration to a known fixed revision rather than an automatically
moving branch. A newer revision can be selected later after the same checks.

1. Download the [official archive for that revision](https://github.com/psmux/psmux/archive/063ca7026eb2b7b91a74d3f858bdec3dfc841dbb.zip)
   and expand it outside any working repository.
2. Prepare native Windows Rust/Cargo, MSVC C++ build tools and the Windows SDK.
   These tools were not found on PATH or at the standard locations inspected.
3. Before building, set the process-local `PSMUX_GIT_SHA` to the full source
   revision so the archive build can record its provenance.
4. Build and install all three aliases from the expanded source using
   `cargo install --path`, with `--locked`, `--bins`, `--jobs 1`, the
   `x86_64-pc-windows-msvc` target and a separate root such as
   `%LOCALAPPDATA%\psmux-builds\063ca70`. Preserve the source identity,
   toolchain versions, build output and resulting executable hashes.
5. Verify the revision shown by each executable's `-V` output and run the upstream
   isolated blocked-output memory regression against the candidate binary.
   Require passing memory, output-resumption and clean-detach checks before
   activating it. The proposed patched build has not been tested locally.
6. Repoint all three `.local\bin` aliases together after validation. Keep the old
   directory for rollback, verify command resolution, and reconnect attached
   clients using the new executables. Existing client processes do not acquire
   a patch merely because their executable paths change.

The patched source still reports package version **3.4.0**. Version text alone
cannot distinguish it from the vulnerable release; the source revision and
behavioral regression are required to establish patch inclusion and behavior.
A local source build also lacks the publisher signature of the signed release.

For future maintenance, stage each candidate revision separately and repeat the
focused validation before switching aliases. Return to a release-managed package
when a verified upstream release contains the fix. A pinned source installation
does not update itself automatically.

Until the patch is installed, detaching before leaving browser or SSH terminals
unattended may reduce exposure to stalled output. This mitigation was not
validated locally and does not replace the fix.

## Evidence and sources

Raw investigation artifacts are under `C:\tmp`. They are local diagnostic files,
not committed repository evidence or permanent archival storage.

| File | Contents |
|---|---|
| `psmux-events-application.txt` | Crash events and WER grouping |
| `psmux-events-detail.txt` | WER details and process start times |
| `psmux-events-resource-history.txt` | Memory exhaustion and historical tmux events |
| `psmux-events-resource-xml.txt` | Exact system commitment statistics |
| `psmux-events-memory-counters.txt` | Surviving client's current and peak private commitment |
| `psmux-events-vmquery.txt` | Reserved and committed address-space classification |
| `psmux-dump-parse.txt` | Dump process identity, exception and stack observations |
| `psmux-dump-alloc.txt`, `psmux-dump-alloc2.txt` | Executable allocation-error path inspection |
| `psmux-memory-now.txt`, `psmux-final-status.txt` | Current memory and final crash query |
| `psmux-install-inventory.txt`, `psmux-install-history.txt` | Paths, symlinks, registry, signatures and update-task observations |
| `psmux-winget-current.txt` | WinGet installed-package query |
| `psmux-upstream-install-options.txt`, `psmux-upstream-build-requirements.txt` | Upstream distribution and build-option research |

Original dumps remain at
`C:\Users\matth\AppData\Local\CrashDumps\psmux.exe.<PID>.dmp` for PIDs
`20360`, `24480` and `14380`.

Primary upstream sources:

- [PR #882 and maintainer's fix explanation](https://github.com/psmux/psmux/pull/882).
- [Frame coalescing fix](https://github.com/psmux/psmux/commit/759bf78776e5cda3f86d8a67a8f8aa2ee2ce95ce).
- [Pinned revision with clipboard/bell followup](https://github.com/psmux/psmux/commit/063ca7026eb2b7b91a74d3f858bdec3dfc841dbb).
- [GitHub Releases](https://github.com/psmux/psmux/releases).
- [WinGet 3.4.0 manifest](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/m/marlocarlo/psmux/3.4.0/marlocarlo.psmux.installer.yaml).
- [Official Scoop manifest](https://raw.githubusercontent.com/psmux/scoop-psmux/master/bucket/psmux.json).
- [Upstream installer script](https://raw.githubusercontent.com/psmux/psmux/master/scripts/install.ps1).
- [Pinned isolated client-memory regression](https://raw.githubusercontent.com/psmux/psmux/063ca7026eb2b7b91a74d3f858bdec3dfc841dbb/tests/test_client_frame_backpressure.py).
- [Cargo installation options](https://doc.rust-lang.org/cargo/commands/cargo-install.html).
