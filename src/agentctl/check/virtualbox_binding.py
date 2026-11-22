# Copyright (c) 2026 agentctl contributors.
"""Pre-gate VirtualBox source-binding receipts and their in-guest verification.

A receipt binds a fresh two-way nonce exchange to one complete source census
digest, the guest's shared-folder bind mount, capacity and dependency facts. A
local receipt proves currency against the live checkout, not an authenticated
historical run; its honest ceiling is documented in the validation runbook.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from agentctl.check.evidence import Entry, source_census
from agentctl.check.wsl_guest_sample import affinity
from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_process import run

RECEIPT_NAME = "virtualbox-binding.json"
DEPENDENCIES = (
    ("python", ("python3", "--version")),
    ("pipx", ("pipx", "--version")),
    ("git", ("git", "--version")),
    ("tmux", ("tmux", "-V")),
    ("gcc", ("gcc", "-dumpfullversion")),
)
HEX32 = re.compile(r"[0-9a-f]{32}")
HEX64 = re.compile(r"[0-9a-f]{64}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHARE = re.compile(r"[A-Za-z0-9_-]{1,64}")
MOUNT_FIELDS = 10
MOUNT_TAIL = 2
MEMINFO_FIELDS = 3
MAX_TEXT = 4096
VIRTUALBOX_PRODUCT = "VirtualBox"
NEWLINE = "\n"


@dataclass(frozen=True, slots=True)
class GuestFacts:
    """Facts the Linux guest observes about its bound checkout and capacity."""

    census: str
    entries: int
    mount: str
    cpus: int
    memory_kib: int
    swap_kib: int
    storage_free_bytes: int
    dependencies: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Receipt:
    """One pre-gate binding exchange joined to host and guest observations."""

    nonce: str
    vm: str
    share: str
    source: str
    guest_root: str
    facts: GuestFacts


def census_digest(entries: tuple[Entry, ...]) -> str:
    """Hash sorted entries with length-prefixed paths, kinds and payloads."""
    digest = hashlib.sha256()
    for entry in sorted(entries):
        for field in (entry.path.encode("utf-8"), entry.kind.encode("ascii")):
            digest.update(len(field).to_bytes(8, "big") + field)
        digest.update(len(entry.payloads).to_bytes(8, "big"))
        for payload in entry.payloads:
            digest.update(len(payload).to_bytes(8, "big") + payload)
    return digest.hexdigest()


def mount_line(mountinfo: str, root: str, share: str) -> Result[str, str]:
    """Return the single mountinfo entry binding ``root`` to the named share."""
    matches = tuple(
        line
        for line in mountinfo.splitlines()
        if len(line.split()) >= MOUNT_FIELDS and line.split()[4] == root
    )
    if len(matches) != 1:
        return Err("source root is not exactly one mount point")
    fields = matches[0].split()
    if "-" not in fields:
        return Err("malformed mountinfo entry")
    tail = fields[fields.index("-") + 1 :]
    if len(tail) < MOUNT_TAIL or tail[0] != "vboxsf" or tail[1] != share:
        return Err("source root is not the expected VirtualBox shared folder")
    return Ok(matches[0])


def _facts_value(facts: GuestFacts) -> dict[str, object]:
    """Represent facts with a dependency mapping for JSON transport."""
    return {**asdict(facts), "dependencies": dict(facts.dependencies)}


def encode(receipt: Receipt) -> str:
    """Serialize a receipt with sorted keys for byte-stable storage."""
    value = {
        "version": 1,
        "nonce": receipt.nonce,
        "vm": receipt.vm,
        "share": receipt.share,
        "source": receipt.source,
        "guest_root": receipt.guest_root,
        "facts": _facts_value(receipt.facts),
    }
    return json.dumps(value, sort_keys=True) + NEWLINE


def facts_json(facts: GuestFacts) -> str:
    """Serialize guest facts for the pre-gate host's transport."""
    return json.dumps(_facts_value(facts), sort_keys=True)


def _text(value: object) -> bool:
    """Accept bounded single-line printable text."""
    return isinstance(value, str) and 0 < len(value) <= MAX_TEXT and value.isprintable()


def _count(value: int, *, minimum: int) -> bool:
    """Accept a genuine integer at or above its lower bound."""
    return not isinstance(value, bool) and value >= minimum


def decode_facts(value: object) -> Result[GuestFacts, str]:
    """Parse guest facts, refusing missing, extra or ill-typed fields."""
    match value:
        case {
            "census": str() as census,
            "entries": int() as entries,
            "mount": str() as mount,
            "cpus": int() as cpus,
            "memory_kib": int() as memory,
            "swap_kib": int() as swap,
            "storage_free_bytes": int() as storage,
            "dependencies": dict() as dependencies,
            **extra,
        } if (
            not extra
            and HEX64.fullmatch(census) is not None
            and _count(entries, minimum=1)
            and _text(mount)
            and _count(cpus, minimum=1)
            and _count(memory, minimum=1)
            and _count(swap, minimum=0)
            and _count(storage, minimum=1)
            and set(dependencies) == {name for name, _argv in DEPENDENCIES}
            and all(_text(item) for item in dependencies.values())
        ):
            return Ok(
                GuestFacts(
                    census,
                    entries,
                    mount,
                    cpus,
                    memory,
                    swap,
                    storage,
                    tuple(sorted((str(k), str(v)) for k, v in dependencies.items())),
                )
            )
        case _:
            return Err("invalid guest binding facts")


def decode(text: str) -> Result[Receipt, str]:
    """Parse a closed version-1 receipt."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return Err("binding receipt is not JSON")
    match value:
        case {
            "version": 1,
            "nonce": str() as nonce,
            "vm": str() as vm,
            "share": str() as share,
            "source": str() as source,
            "guest_root": str() as guest_root,
            "facts": facts,
            **extra,
        } if (
            not extra
            and HEX32.fullmatch(nonce) is not None
            and UUID.fullmatch(vm) is not None
            and SHARE.fullmatch(share) is not None
            and _text(source)
            and guest_root.startswith("/")
            and _text(guest_root)
        ):
            parsed = decode_facts(facts)
            if isinstance(parsed, Err):
                return parsed
            return Ok(Receipt(nonce, vm, share, source, guest_root, parsed.value))
        case _:
            return Err("invalid binding receipt")


def verify_identity(
    receipt: Receipt, root: str, observed: GuestFacts
) -> Result[None, str]:
    """Require the live census and mount to equal the pre-gate exchange's view."""
    if receipt.guest_root != root:
        return Err("binding receipt names a different guest root")
    if (observed.census, observed.entries) != (
        receipt.facts.census,
        receipt.facts.entries,
    ):
        return Err("source census changed since the binding exchange")
    if observed.mount != receipt.facts.mount:
        return Err("source mount changed since the binding exchange")
    return Ok(None)


def verify_capacity(receipt: Receipt, observed: GuestFacts) -> Result[None, str]:
    """Require the same guest allocation and dependency versions as the receipt."""
    expected = receipt.facts
    if (observed.cpus, observed.memory_kib, observed.swap_kib) != (
        expected.cpus,
        expected.memory_kib,
        expected.swap_kib,
    ):
        return Err("guest capacity changed since the binding exchange")
    if observed.dependencies != expected.dependencies:
        return Err("guest dependencies changed since the binding exchange")
    return Ok(None)


def meminfo(text: str, key: str) -> Result[int, str]:
    """Read one kibibyte field from /proc/meminfo."""
    values = tuple(
        line.split()[1]
        for line in text.splitlines()
        if line.startswith(key + ":") and len(line.split()) == MEMINFO_FIELDS
    )
    if len(values) != 1 or not values[0].isdigit():
        return Err("cannot read " + key)
    return Ok(int(values[0]))


def _version(argv: tuple[str, ...], cwd: Path) -> Result[str, str]:
    """Run one dependency's version query and keep its first output line."""
    result = run(list(argv), cwd=cwd, env=os.environ, timeout=30)
    if isinstance(result, Err):
        return Err(argv[0] + " is unavailable: " + result.error.message)
    lines = (result.value.stdout + result.value.stderr).strip().splitlines()
    if result.value.code or not lines or not _text(lines[0]):
        return Err(argv[0] + " version query failed")
    return Ok(lines[0])


def virtualbox_guest(product: str) -> bool:
    """Recognize the DMI product name VirtualBox reports to its guests."""
    return product.strip() == VIRTUALBOX_PRODUCT


def observe_guest(root: Path, share: str, family: Family) -> Result[GuestFacts, str]:
    """Observe the bound checkout, mount, capacity and dependencies in the guest."""
    if family != "Linux":
        return Err("VirtualBox binding facts are observed only inside the Linux guest")
    entries = source_census(root)
    if isinstance(entries, Err):
        return Err(entries.error.message)
    try:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        memory_text = Path("/proc/meminfo").read_text(encoding="utf-8")
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        storage = shutil.disk_usage(Path.home()).free
    except (OSError, UnicodeError) as exc:
        return Err("cannot read guest facts: " + str(exc))
    mount = mount_line(mountinfo, root.as_posix(), share)
    memory = meminfo(memory_text, "MemTotal")
    swap = meminfo(memory_text, "SwapTotal")
    cpus = affinity(status)
    versions = tuple((name, _version(argv, root)) for name, argv in DEPENDENCIES)
    match mount, memory, swap, cpus:
        case Ok(line), Ok(total), Ok(swap_total), Ok(allowed) if all(
            isinstance(value, Ok) for _name, value in versions
        ):
            return Ok(
                GuestFacts(
                    census_digest(entries.value),
                    len(entries.value),
                    line,
                    len(allowed),
                    total,
                    swap_total,
                    storage,
                    tuple(
                        sorted(
                            (name, value.value)
                            for name, value in versions
                            if isinstance(value, Ok)
                        )
                    ),
                )
            )
        case _:
            return Err(
                "; ".join(
                    item.error
                    for item in (
                        mount,
                        memory,
                        swap,
                        cpus,
                        *(value for _name, value in versions),
                    )
                    if isinstance(item, Err)
                )
            )


FAMILIES: dict[str, Family] = {"Windows": "Windows", "Darwin": "Darwin"}


def platform_family() -> Family:
    """Name the running family without importing later host adapters."""
    return FAMILIES.get(platform.system(), "Linux")


def main(argv: tuple[str, ...]) -> int:
    """Guest entry point: ``observe ROOT SHARE`` prints facts as one JSON line."""
    match argv:
        case ("observe", root, share):
            facts = observe_guest(Path(root), share, platform_family())
            if isinstance(facts, Err):
                sys.stdout.write(facts.error + NEWLINE)
                return 1
            sys.stdout.write(facts_json(facts.value) + NEWLINE)
            return 0
        case _:
            sys.stdout.write("usage: observe ROOT SHARE" + NEWLINE)
            return 2


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
