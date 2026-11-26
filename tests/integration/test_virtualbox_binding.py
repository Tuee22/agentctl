# Copyright (c) 2026 agentctl contributors.
"""The live checkout's pre-gate VirtualBox binding receipt and its refusals."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import binding_challenge, steps, virtualbox_bind, virtualbox_binding
from agentctl.check.evidence import Entry, source_census
from agentctl.check.lanes import HostFacts, phase_lane_host
from agentctl.check.phase_reports import containing_mount, parse_mountinfo
from agentctl.check.virtualbox_binding import (
    GuestFacts,
    Receipt,
    census_digest,
    decode,
    decode_facts,
    encode,
    facts_json,
    meminfo,
    mount_line,
    observe_guest,
    platform_family,
    verify_capacity,
    verify_identity,
    virtualbox_guest,
)
from agentctl.foundation import Err, Ok
from agentctl.foundation_paths import directories
from agentctl.foundation_process import finish, run, start_protocol, stop

pytestmark = pytest.mark.evidence("observer")

SHARE = "agentctl-src"
MOUNT = (
    "76 29 0:37 / /srv/agentctl rw,nodev,relatime shared:22 - vboxsf agentctl-src "
    "rw,uid=1000"
)
DEPENDENCIES = (
    ("gcc", "14.2.0"),
    ("git", "git version 2.47.3"),
    ("pipx", "1.7.1"),
    ("python", "Python 3.13.5"),
    ("tmux", "tmux 3.5a"),
)
FACTS = GuestFacts("a" * 64, 3, MOUNT, 4, 1000, 10, 50, DEPENDENCIES)
RECEIPT = Receipt(
    "0" * 32,
    "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8",
    SHARE,
    "C:/Users/example/agentctl",
    "/srv/agentctl",
    FACTS,
)


def _product() -> str:
    """Read the DMI product name a VirtualBox guest reports, if any."""
    path = Path("/sys/class/dmi/id/product_name")
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _shared_checkout(root: Path) -> bool:
    """Observe the kernel's containing mount independently of the gate helper."""
    records = parse_mountinfo(Path("/proc/self/mountinfo").read_text(encoding="utf-8"))
    assert isinstance(records, Ok)
    selected = containing_mount(root.as_posix(), records.value)
    assert isinstance(selected, Ok)
    return selected.value.filesystem == "vboxsf"


def _receipt() -> Receipt:
    """Read the stored receipt from the guest user's private state directory."""
    path = (
        directories("Linux", os.environ, Path.home()).state
        / virtualbox_binding.RECEIPT_NAME
    )
    assert path.is_file(), "pre-gate VirtualBox binding receipt is missing"
    parsed = decode(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def _native_linux_claims_no_share(root: Path) -> None:
    """Outside a VirtualBox guest, the checkout is not a VirtualBox shared folder."""
    mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    assert isinstance(mount_line(mountinfo, root.as_posix(), SHARE), Err)


def test_shared_checkout_identity(root: Path) -> None:
    """In the guest, the live census and mount equal the pre-gate exchange."""
    family = platform_family()
    if family != "Linux":
        refused = observe_guest(root, SHARE, family)
        assert isinstance(refused, Err), "foreign host minted guest binding facts"
        assert "only inside the Linux guest" in refused.error
    elif virtualbox_guest(_product()):
        receipt = _receipt()
        observed = observe_guest(root, receipt.share, family)
        assert isinstance(observed, Ok), observed
        assert verify_identity(receipt, root.as_posix(), observed.value) == Ok(None)
    else:
        _native_linux_claims_no_share(root)


def test_gate_qualifies_current_virtualbox_binding(root: Path, tmp_path: Path) -> None:
    """The gate checks actual shared source bytes and private binding evidence."""
    family = platform_family()
    candidate = tmp_path / "binding.json"
    if family != "Linux" or not _shared_checkout(root):
        assert virtualbox_binding.check_shared_checkout(root, family, candidate) == Ok(
            None
        )
    else:
        receipt = _receipt()
        candidate.write_text(encode(receipt), encoding="utf-8")
        candidate.chmod(0o600)
        assert virtualbox_binding.check_shared_checkout(root, family, candidate) == Ok(
            None
        ), "current shared checkout binding was rejected"
        wrong_source = replace(receipt, facts=replace(receipt.facts, census="0" * 64))
        candidate.write_text(encode(wrong_source), encoding="utf-8")
        assert isinstance(
            virtualbox_binding.check_shared_checkout(root, family, candidate), Err
        ), "stale shared checkout binding was accepted"
        wrong_capacity = replace(
            receipt, facts=replace(receipt.facts, cpus=receipt.facts.cpus + 1)
        )
        candidate.write_text(encode(wrong_capacity), encoding="utf-8")
        assert isinstance(
            virtualbox_binding.check_shared_checkout(root, family, candidate), Err
        ), "changed guest allocation was accepted"
        candidate.write_text(encode(receipt), encoding="utf-8")
        candidate.chmod(0o644)
        assert isinstance(
            virtualbox_binding.check_shared_checkout(root, family, candidate), Err
        ), "public binding receipt was accepted"
        candidate.chmod(0o600)
        linked = tmp_path / "linked.json"
        linked.symlink_to(candidate)
        assert isinstance(
            virtualbox_binding.check_shared_checkout(root, family, linked), Err
        ), "linked binding receipt was accepted"
        assert isinstance(
            virtualbox_binding.check_shared_checkout(root, family, tmp_path / "absent"),
            Err,
        ), "missing binding receipt was accepted"


def test_native_phase_lane_uses_observed_debian_host(record_host: HostFacts) -> None:
    """Join the real kernel and Debian release to the phase's base host lane."""
    if platform_family() == "Linux" and virtualbox_guest(_product()):
        release = Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
        assert "ID=debian" in release
        assert record_host.family == "Linux"
        assert record_host.debian, "actual Debian identity was not observed"
        assert phase_lane_host("linux", record_host), "actual Debian lane was rejected"
    elif record_host.family != "Linux":
        assert not record_host.debian, "foreign host was recorded as Debian"
    else:
        lines = Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
        ids = tuple(line for line in lines if line.startswith("ID="))
        assert record_host.debian == (ids in (("ID=debian",), ('ID="debian"',)))


def test_gate_preflight_refuses_missing_shared_binding(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual gate context refuses a shared checkout with no binding receipt."""
    family = platform_family()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "private-state"))
    issues = steps.inspect_context(root, tmp_path, family)
    binding = tuple(item for item in issues if item.startswith("VirtualBox binding:"))
    if family == "Linux" and _shared_checkout(root):
        assert binding, "gate accepted a missing shared binding"
    else:
        assert not binding, "native checkout required a VirtualBox binding"


def test_private_binding_receipt_refuses_links_and_public_files(tmp_path: Path) -> None:
    """Private receipt reading refuses changed permissions, links and bad data."""
    candidate = tmp_path / "binding.json"
    if os.name == "nt":
        assert virtualbox_binding.check_shared_checkout(
            tmp_path, "Windows", candidate
        ) == Ok(None)
    else:
        candidate.write_text(encode(RECEIPT), encoding="utf-8")
        candidate.chmod(0o600)
        reader = virtualbox_binding.__dict__["_private_receipt"]
        assert reader(candidate) == Ok(RECEIPT)
        candidate.chmod(0o644)
        assert isinstance(reader(candidate), Err), "public binding receipt was accepted"
        candidate.chmod(0o600)
        symlink = tmp_path / "symbolic.json"
        symlink.symlink_to(candidate)
        assert isinstance(reader(symlink), Err), "symbolic binding receipt was accepted"
        hardlink = tmp_path / "hard.json"
        os.link(candidate, hardlink)
        assert isinstance(reader(candidate), Err), (
            "hardlinked binding receipt was accepted"
        )
        hardlink.unlink()
        candidate.write_text("invalid", encoding="utf-8")
        assert isinstance(reader(candidate), Err), (
            "malformed binding receipt was accepted"
        )


def test_shared_binding_rechecks_actual_checkout_bytes(tmp_path: Path) -> None:
    """A current receipt fails when the observed source tree or mount changes."""
    if os.name == "nt":
        assert virtualbox_binding.check_shared_checkout(
            tmp_path, "Windows", tmp_path
        ) == Ok(None)
    else:
        root = tmp_path / "checkout"
        root.mkdir()
        source = root / "fresh.txt"
        source.write_bytes(b"original")
        census = source_census(root)
        assert isinstance(census, Ok)
        mount = f"76 29 0:37 / {root.as_posix()} rw - vboxsf {SHARE} rw"
        receipt = replace(
            RECEIPT,
            guest_root=root.as_posix(),
            facts=replace(
                FACTS,
                census=census_digest(census.value),
                entries=len(census.value),
                mount=mount,
            ),
        )
        check = virtualbox_binding.__dict__["_shared_checkout_identity"]
        assert check(root, mount + "\n", receipt) == Ok(None)
        source.write_bytes(b"changed")
        assert isinstance(check(root, mount + "\n", receipt), Err), (
            "changed checkout bytes were accepted"
        )
        source.write_bytes(b"original")
        assert isinstance(
            check(root, mount.replace(SHARE, "other") + "\n", receipt), Err
        ), "foreign shared mount was accepted"


def test_guest_binding_rechecks_actual_allocation(tmp_path: Path) -> None:
    """Compare the real guest allocation to the stored pre-gate observation."""
    if platform_family() != "Linux" or not virtualbox_guest(_product()):
        assert virtualbox_binding.check_shared_checkout(
            tmp_path, "Windows", tmp_path
        ) == Ok(None)
    else:
        receipt = _receipt()
        check = virtualbox_binding.__dict__["_shared_guest_capacity"]
        assert check(receipt) == Ok(None)
        changed = replace(
            receipt, facts=replace(receipt.facts, cpus=receipt.facts.cpus + 1)
        )
        assert isinstance(check(changed), Err), "changed guest allocation was accepted"


def test_capacity_and_dependency_receipt(root: Path) -> None:
    """In the guest, the allocation and dependencies equal the receipt."""
    family = platform_family()
    if family != "Linux":
        assert isinstance(observe_guest(root, SHARE, family), Err)
    elif virtualbox_guest(_product()):
        receipt = _receipt()
        observed = observe_guest(root, receipt.share, family)
        assert isinstance(observed, Ok), observed
        assert verify_capacity(receipt, observed.value) == Ok(None)
        assert receipt.facts.storage_free_bytes > 0
    else:
        _native_linux_claims_no_share(root)


def test_receipt_round_trip_and_refusals() -> None:
    """Encoding round-trips, and malformed or extended receipts are refused."""
    assert decode(encode(RECEIPT)) == Ok(RECEIPT)
    assert decode_facts(json.loads(facts_json(FACTS))) == Ok(FACTS)
    value = json.loads(encode(RECEIPT))
    refused = (
        "not json",
        json.dumps({**value, "extra": 1}),
        json.dumps({**value, "nonce": "XYZ"}),
        json.dumps({**value, "vm": "not-a-uuid"}),
        json.dumps({**value, "share": "bad share"}),
        json.dumps({**value, "guest_root": "relative"}),
        json.dumps({**value, "source": ""}),
        json.dumps({**value, "facts": {**value["facts"], "entries": 0}}),
        json.dumps({**value, "facts": {**value["facts"], "cpus": True}}),
        json.dumps({**value, "facts": {**value["facts"], "dependencies": {}}}),
        json.dumps({**value, "facts": {**value["facts"], "mount": "a\nb"}}),
    )
    accepted = tuple(text for text in refused if not isinstance(decode(text), Err))
    assert accepted == (), "invalid binding receipt accepted"


def test_binding_json_refuses_ambiguous_values(tmp_path: Path) -> None:
    """Both the stored receipt and real guest response reject ambiguous JSON."""
    encoded = encode(RECEIPT)
    duplicate = encoded.replace('"nonce": ', '"nonce": "foreign", "nonce": ', 1)
    assert isinstance(decode(duplicate), Err), "duplicate binding field was accepted"
    nested = encoded.replace('"cpus": ', '"cpus": 999, "cpus": ', 1)
    assert isinstance(decode(nested), Err), "duplicate guest fact was accepted"
    boolean = json.loads(encoded)
    boolean["version"] = True
    assert isinstance(decode(json.dumps(boolean)), Err), "boolean version was accepted"
    for root in (
        "/srv/../agentctl",
        "/srv//agentctl",
        "/srv/./agentctl",
        "//srv/agentctl",
    ):
        invalid = json.dumps({**json.loads(encoded), "guest_root": root})
        assert isinstance(decode(invalid), Err), "noncanonical guest root was accepted"
    facts = facts_json(FACTS)
    ambiguous = facts.replace('"cpus": ', '"cpus": 999, "cpus": ', 1)
    target = virtualbox_bind.Target(
        tmp_path,
        RECEIPT.vm,
        SHARE,
        "/srv/agentctl",
        (sys.executable, "-c", "import sys; print(sys.argv[1])", ambiguous),
    )
    observed = virtualbox_bind.__dict__["_guest_facts"](target)
    assert isinstance(observed, Err), "ambiguous guest facts were accepted"


def test_identity_and_capacity_refuse_changes() -> None:
    """Changed roots, censuses, mounts, capacity and dependencies are refused."""
    assert verify_identity(RECEIPT, "/srv/agentctl", FACTS) == Ok(None)
    assert verify_identity(RECEIPT, "/other", FACTS) == Err(
        "binding receipt names a different guest root"
    )
    assert verify_identity(RECEIPT, "/srv/agentctl", replace(FACTS, entries=4)) == Err(
        "source census changed since the binding exchange"
    )
    assert verify_identity(RECEIPT, "/srv/agentctl", replace(FACTS, mount="x")) == Err(
        "source mount changed since the binding exchange"
    )
    assert verify_capacity(RECEIPT, FACTS) == Ok(None)
    assert verify_capacity(RECEIPT, replace(FACTS, cpus=2)) == Err(
        "guest capacity changed since the binding exchange"
    )
    changed = replace(FACTS, dependencies=(("gcc", "13"), *DEPENDENCIES[1:]))
    assert verify_capacity(RECEIPT, changed) == Err(
        "guest dependencies changed since the binding exchange"
    )


def test_mount_and_meminfo_values() -> None:
    """Only one vboxsf entry for the exact share and root is accepted."""
    assert mount_line(MOUNT, "/srv/agentctl", SHARE) == Ok(MOUNT)
    assert isinstance(mount_line(MOUNT, "/srv/other", SHARE), Err)
    assert isinstance(mount_line(MOUNT + "\n" + MOUNT, "/srv/agentctl", SHARE), Err)
    assert isinstance(mount_line(MOUNT, "/srv/agentctl", "other-share"), Err)
    assert isinstance(
        mount_line(MOUNT.replace("vboxsf", "ext4"), "/srv/agentctl", SHARE), Err
    )
    unseparated = MOUNT.replace(" - ", " + ")
    assert mount_line(unseparated, "/srv/agentctl", SHARE) == Err(
        "malformed mountinfo entry"
    )
    assert meminfo("MemTotal:  1000 kB\n", "MemTotal") == Ok(1000)
    assert isinstance(meminfo("MemTotal: x kB\n", "MemTotal"), Err)
    assert isinstance(meminfo("", "SwapTotal"), Err)
    assert virtualbox_guest("VirtualBox\n")
    assert not virtualbox_guest("Standard PC")


def test_census_digest_binds_paths_kinds_and_bytes() -> None:
    """Any path, kind or payload change alters the digest."""
    base = (Entry("a", "file", (b"x",)), Entry("d", "directory", ()))
    digest = census_digest(base)
    assert census_digest(tuple(reversed(base))) == digest
    assert census_digest((Entry("a", "file", (b"y",)), base[1])) != digest
    assert census_digest((Entry("b", "file", (b"x",)), base[1])) != digest
    assert census_digest((Entry("a", "symlink", (b"x",)), base[1])) != digest


def test_guest_observer_refusals(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foreign hosts, absent roots, absent shares and unreadable storage fail."""
    assert isinstance(observe_guest(root, SHARE, "Windows"), Err)
    if platform_family() == "Linux":
        assert isinstance(observe_guest(tmp_path / "missing", SHARE, "Linux"), Err)
        empty = tmp_path / "empty"
        empty.mkdir()
        unshared = observe_guest(empty, SHARE, "Linux")
        assert isinstance(unshared, Err)
        assert "not exactly one mount point" in unshared.error
        monkeypatch.setenv("HOME", str(tmp_path / "absent-home"))
        unreadable = observe_guest(empty, SHARE, "Linux")
        assert isinstance(unreadable, Err)
        assert "cannot read guest facts" in unreadable.error
    else:
        assert isinstance(observe_guest(root, SHARE, "Darwin"), Err)


def test_dependency_version_query_failures(tmp_path: Path) -> None:
    """A missing tool or failing query is reported rather than recorded."""
    version = virtualbox_binding.__dict__["_version"]
    missing = version(("agentctl-definitely-missing-tool",), tmp_path)
    assert isinstance(missing, Err)
    assert "is unavailable" in missing.error
    failing = version((sys.executable, "-c", "raise SystemExit(3)"), tmp_path)
    assert failing == Err(sys.executable + " version query failed")
    found = version((sys.executable, "--version"), tmp_path)
    assert isinstance(found, Ok)
    assert found.value.startswith("Python ")


def test_module_entry_points(root: Path, tmp_path: Path) -> None:
    """The guest entry point prints usage, refusal or facts as one line."""
    usage = run(
        [sys.executable, "-m", "agentctl.check.virtualbox_binding"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(usage, Ok)
    assert (usage.value.code, usage.value.stdout) == (2, "usage: observe ROOT SHARE\n")
    refused = virtualbox_binding.main(("observe", str(tmp_path / "missing"), SHARE))
    assert refused == 1
    if platform_family() == "Linux" and virtualbox_guest(_product()):
        assert virtualbox_binding.main(("observe", root.as_posix(), SHARE)) == 0


def test_host_binding_values(tmp_path: Path) -> None:
    """The host tool binds guest facts to a successful actual child command."""
    prefix = virtualbox_bind.ssh_command(Path("/k"), Path("/h"), 44223, "agentctl")
    assert prefix[-1] == "agentctl@127.0.0.1"
    assert "StrictHostKeyChecking=yes" in prefix
    assert "BatchMode=yes" in prefix
    text = 'name="vm"\nUUID="9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"\n'
    assert virtualbox_bind.vm_uuid(text, "vm") == Ok(RECEIPT.vm)
    assert isinstance(virtualbox_bind.vm_uuid(text, "other"), Err)
    assert isinstance(virtualbox_bind.vm_uuid(text + text, "vm"), Err)
    payload = facts_json(FACTS)
    program = "import sys; print(sys.argv[1]); sys.stderr.write('guest failure'); "
    successful = virtualbox_bind.Target(
        tmp_path,
        RECEIPT.vm,
        SHARE,
        "/srv/agentctl",
        (sys.executable, "-c", program + "sys.exit(0)", payload),
    )
    facts = virtualbox_bind.__dict__["_guest_facts"]
    assert facts(successful) == Ok(FACTS)
    failed = replace(
        successful,
        ssh=(sys.executable, "-c", program + "sys.exit(3)", payload),
    )
    assert facts(failed) == Err("guest facts command failed: guest failure"), (
        "failed guest facts command was accepted"
    )


def test_host_share_mapping_binds_checkout(tmp_path: Path) -> None:
    """A host mapping must identify one exact, existing checkout directory."""
    checkout = tmp_path / "checkout"
    foreign = tmp_path / "foreign"
    checkout.mkdir()
    foreign.mkdir()
    name = 'SharedFolderNameTransientMapping1="agentctl-src"\n'
    path = "SharedFolderPathTransientMapping1=" + json.dumps(str(checkout)) + "\n"
    assert virtualbox_bind.shared_folder(name + path, SHARE, checkout) == Ok(None)
    wrong = "SharedFolderPathTransientMapping1=" + json.dumps(str(foreign)) + "\n"
    for text in (
        name + wrong,
        name,
        path,
        name + path + name,
        name
        + path
        + name.replace("Mapping1", "Mapping2")
        + path.replace("Mapping1", "Mapping2"),
        name + path.replace("Mapping1", "Mapping0"),
    ):
        assert isinstance(virtualbox_bind.shared_folder(text, SHARE, checkout), Err), (
            "foreign or ambiguous shared-folder mapping accepted"
        )


def test_host_binding_rechecks_shared_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mapping that changes during the nonce exchange is not stored."""
    observations = iter((Ok(RECEIPT.vm), Err("mapping changed")))
    monkeypatch.setattr(
        virtualbox_bind, "observe_vm", lambda *_args: next(observations)
    )
    monkeypatch.setattr(virtualbox_bind, "bind", lambda _target: Ok(RECEIPT))
    monkeypatch.setattr(
        virtualbox_bind,
        "store",
        lambda *_args: pytest.fail("changed mapping was stored"),
    )
    argv = (
        str(tmp_path),
        "vm",
        SHARE,
        "/srv/agentctl",
        "key",
        "known",
        "44223",
        "agentctl",
    )
    assert virtualbox_bind.main(argv) == 1, "changed VM mapping was accepted"
    assert "VirtualBox mapping changed" in capsys.readouterr().out


def test_guest_process_absence_refuses_unreadable_entries(tmp_path: Path) -> None:
    """A process scan refuses unreadable entries while preserving active detection."""
    proc = tmp_path / "proc"
    proc.mkdir()
    process = proc / "1"
    process.mkdir()
    command = process / "cmdline"
    nonce = "a" * 32
    script = virtualbox_bind.__dict__["_absence_script"](nonce, proc.as_posix())

    def observe() -> tuple[int, str]:
        result = run([sys.executable, "-c", script], cwd=tmp_path, env=os.environ)
        assert isinstance(result, Ok), result
        return result.value.code, result.value.stdout.strip()

    command.write_bytes(b"other")
    assert observe() == (0, "stopped")
    command.write_bytes(b"peer\x00" + nonce.encode())
    assert observe() == (0, "active")
    command.unlink()
    command.mkdir()
    assert observe() == (1, "unknown"), "unreadable guest process was accepted"


def test_guest_peer_nonce_is_visible_until_exit(tmp_path: Path) -> None:
    """The actual peer argv carries the nonce searched by the termination observer."""
    nonce = "b" * 32
    wrapper = (
        "import sys; program = sys.argv[4][1:-1]; "
        "sys.argv = ['peer', *sys.argv[5:]]; exec(program)"
    )
    target = virtualbox_bind.Target(
        tmp_path,
        RECEIPT.vm,
        SHARE,
        tmp_path.as_posix(),
        (sys.executable, "-c", wrapper),
    )
    assert binding_challenge.begin(tmp_path, nonce) == Ok(None)
    peer = virtualbox_bind.__dict__["_peer"]
    assert peer(target, nonce) == Ok(None), "guest peer nonce was not passed in argv"
    assert binding_challenge.finish(tmp_path, nonce) == Ok(None)
    accepting = replace(target, ssh=(sys.executable, "-c", "pass"))
    guest = virtualbox_bind.__dict__["_guest"]
    assert isinstance(guest(accepting, "pass", peer_nonce="bad nonce"), Err), (
        "invalid guest peer nonce accepted"
    )

    if sys.platform == "linux":
        # Hold the same encoded-program/nonce argv shape open while inspecting /proc.
        script = "import sys; print('ready', flush=True); sys.stdin.read()"
        encoded = virtualbox_bind.__dict__["_encoded"](script)[1:-1]
        child = start_protocol(
            [sys.executable, "-I", "-c", encoded, nonce],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(child, Ok), child
        try:
            assert child.value.handle.stdout is not None
            assert child.value.handle.stdout.readline() == b"ready\n"
            observer = virtualbox_bind.__dict__["_absence_script"](nonce)
            active = run([sys.executable, "-c", observer], cwd=tmp_path, env=os.environ)
            assert isinstance(active, Ok), active
            assert (active.value.code, active.value.stdout.strip()) == (0, "active"), (
                "live guest peer was reported stopped"
            )
        except BaseException as exc:
            cleanup = stop(child.value)
            if isinstance(cleanup, Err):
                exc.add_note("peer cleanup failed: " + cleanup.error.message)
            raise
        terminated = finish(child.value, input_text="release", timeout=5)
        if isinstance(terminated, Err):
            cleanup = stop(child.value)
            assert isinstance(terminated, Ok), (
                f"peer termination failed: {terminated}; cleanup: {cleanup}"
            )
        stopped = run([sys.executable, "-c", observer], cwd=tmp_path, env=os.environ)
        assert isinstance(stopped, Ok), stopped
        assert (stopped.value.code, stopped.value.stdout.strip()) == (0, "stopped")
