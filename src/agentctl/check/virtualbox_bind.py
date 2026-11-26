# Copyright (c) 2026 agentctl contributors.
"""Windows pre-gate binding of the live checkout to the dedicated VirtualBox guest.

Run before ``agentctl check`` in the guest. It performs a fresh two-way nonce
exchange through the shared folder, confirms the guest peer has exited, joins
the host and guest source census digests and writes one receipt into the
guest's Linux state directory. It never stages, commits or copies sources.
"""

import base64
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from agentctl.check import binding_challenge, virtualbox_binding
from agentctl.check.evidence import source_census
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Output, run

GUEST_PYTHON = "~/.local/share/pipx/venvs/agentctl/bin/python"
VBOXMANAGE = Path("C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
NEWLINE = "\n"
ARGUMENTS = 9
MAX_VM_INFO = 1_048_576
SHARE_FIELD = re.compile(
    r"SharedFolder(Name|Path)(Transient|Machine)Mapping([1-9][0-9]*)"
)


@dataclass(frozen=True, slots=True)
class Target:
    """The dedicated VM, its SSH endpoint and the bound guest checkout."""

    root: Path
    vm: str
    share: str
    guest_root: str
    ssh: tuple[str, ...]


def ssh_command(key: Path, known_hosts: Path, port: int, user: str) -> tuple[str, ...]:
    """Build a batch SSH prefix with strict host-key checking."""
    return (
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts.as_posix()}",
        "-i",
        key.as_posix(),
        "-p",
        str(port),
        f"{user}@127.0.0.1",
    )


def _guest(
    target: Target,
    script: str,
    stdin: str | None = None,
    *,
    peer_nonce: str | None = None,
) -> Result[Output, str]:
    """Run a guest program, exposing a peer nonce in the remote process argv."""
    if peer_nonce is not None and re.fullmatch(r"[0-9a-f]{32}", peer_nonce) is None:
        return Err("invalid guest peer nonce")
    result = run(
        [
            *target.ssh,
            GUEST_PYTHON,
            "-I",
            "-c",
            _encoded(script),
            *((peer_nonce,) if peer_nonce is not None else ()),
        ],
        cwd=target.root,
        env=os.environ,
        timeout=600,
        input_text=stdin,
    )
    return Err(result.error.message) if isinstance(result, Err) else Ok(result.value)


def _encoded(script: str) -> str:
    """Quote a guest program as shell-inert base64 for the remote command line."""
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return f"'import base64; exec(base64.b64decode(\"{payload}\"))'"


def _answer_script(guest_root: str) -> str:
    """Answer the host's challenge with the application's own peer operation."""
    return (
        "from pathlib import Path; import sys; "
        "from agentctl.check.binding_challenge import answer; "
        f"r = answer(Path({guest_root!r}), sys.argv[1]); "
        "print(getattr(r, 'error', 'ok')); "
        "sys.exit(0 if r.__class__.__name__ == 'Ok' else 1)"
    )


def _absence_script(nonce: str, proc_root: str = "/proc") -> str:
    """Report whether any guest process still names the challenge nonce."""
    return (
        "import os, sys; me = str(os.getpid()); hits = []; unknown = False\n"
        f"root = {proc_root!r}\n"
        "for pid in os.listdir(root):\n"
        "    if pid.isdigit() and pid != me:\n"
        "        try: text = open(os.path.join(root, pid, 'cmdline'), 'rb').read()\n"
        "        except FileNotFoundError: continue\n"
        "        except OSError: unknown = True; continue\n"
        f"        if {nonce!r}.encode() in text: hits.append(pid)\n"
        "print('unknown' if unknown else 'active' if hits else 'stopped')\n"
        "sys.exit(1 if unknown else 0)"
    )


def vm_uuid(text: str, name: str) -> Result[str, str]:
    """Read the UUID of the named VM from machine-readable VBoxManage output."""
    names = re.findall(r'^name="([^"]*)"$', text, re.MULTILINE)
    uuids = re.findall(r'^UUID="([0-9a-f-]{36})"$', text, re.MULTILINE)
    if names != [name] or len(uuids) != 1:
        return Err("cannot identify the dedicated VirtualBox VM")
    return Ok(str(uuids[0]))


def _shared_folder_path(text: str, share: str) -> Result[str, str]:
    """Decode one named share from complete, paired machine-readable fields."""
    if (
        not text.endswith("\n")
        or len(text) > MAX_VM_INFO
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", share) is None
    ):
        return Err("invalid VirtualBox shared-folder observation")
    rows = tuple(line.partition("=") for line in text.splitlines())
    selected = tuple(
        (key, value)
        for key, separator, value in rows
        if separator and key.startswith(("SharedFolderName", "SharedFolderPath"))
    )
    try:
        decoded = tuple(
            (SHARE_FIELD.fullmatch(key), json.loads(value)) for key, value in selected
        )
        if any(match is None or not isinstance(value, str) for match, value in decoded):
            return Err("invalid VirtualBox shared-folder field")
        fields = tuple(
            ((match.group(2), match.group(3), match.group(1)), value)
            for match, value in decoded
            if match is not None and isinstance(value, str)
        )
    except (ValueError, UnicodeError):
        return Err("cannot decode VirtualBox shared-folder mapping")
    return _paired_share(fields, share)


def _paired_share(
    fields: tuple[tuple[tuple[str, str, str], str], ...], share: str
) -> Result[str, str]:
    """Select the one complete name and path pair for the named share."""
    keys = tuple(key for key, _value in fields)
    if len(keys) != len(set(keys)):
        return Err("duplicate VirtualBox shared-folder field")
    mappings = dict(fields)
    slots = frozenset((kind, index) for kind, index, _field in keys)
    if any(
        (kind, index, field) not in mappings
        for kind, index in slots
        for field in ("Name", "Path")
    ):
        return Err("incomplete VirtualBox shared-folder mapping")
    matches = tuple(
        mappings[kind, index, "Path"]
        for kind, index in slots
        if mappings[kind, index, "Name"] == share
    )
    if len(matches) != 1:
        return Err("missing or ambiguous VirtualBox shared folder")
    return Ok(matches[0])


def shared_folder(text: str, share: str, root: Path) -> Result[None, str]:
    """Require one unambiguous VM mapping to the observed local checkout."""
    observed = _shared_folder_path(text, share)
    if isinstance(observed, Err):
        return observed
    try:
        mapped = Path(observed.value)
        if (
            not root.is_absolute()
            or not mapped.is_absolute()
            or ".." in mapped.parts
            or root.is_symlink()
            or root.is_junction()
            or mapped.resolve(strict=True) != root.resolve(strict=True)
            or not root.is_dir()
        ):
            return Err("VirtualBox shared folder does not name the checkout")
        return Ok(None)
    except (OSError, RuntimeError, ValueError):
        return Err("cannot inspect VirtualBox shared-folder mapping")


def _peer(target: Target, nonce: str) -> Result[None, str]:
    """Run the guest's answer operation for one challenge."""
    answered = _guest(target, _answer_script(target.guest_root), peer_nonce=nonce)
    if isinstance(answered, Err):
        return answered
    return (
        Ok(None)
        if answered.value.code == 0
        else Err("guest answer failed: " + answered.value.stdout.strip())
    )


def _stopped(target: Target, nonce: str) -> Result[bool, str]:
    """Confirm no guest process still carries the challenge nonce."""
    observed = _guest(target, _absence_script(nonce))
    if isinstance(observed, Err):
        return observed
    return Ok(observed.value.code == 0 and observed.value.stdout.strip() == "stopped")


def _guest_facts(target: Target) -> Result[virtualbox_binding.GuestFacts, str]:
    """Observe the guest's census, mount, capacity and dependencies."""
    observed = _guest(
        target,
        "import sys; from agentctl.check.virtualbox_binding import main; "
        f"sys.exit(main(('observe', {target.guest_root!r}, {target.share!r})))",
    )
    if isinstance(observed, Err):
        return observed
    if observed.value.code != 0:
        return Err("guest facts command failed: " + observed.value.stderr.strip())
    return virtualbox_binding.decode_facts_json(observed.value.stdout)


def bind(target: Target) -> Result[virtualbox_binding.Receipt, str]:
    """Exchange nonces, join census digests and return the receipt to store."""
    exchanged = binding_challenge.exchange(
        target.root,
        lambda nonce: _peer(target, nonce),
        lambda nonce: _stopped(target, nonce),
    )
    if isinstance(exchanged, Err):
        return exchanged
    host = source_census(target.root)
    if isinstance(host, Err):
        return Err(host.error.message)
    facts = _guest_facts(target)
    if isinstance(facts, Err):
        return facts
    digest = virtualbox_binding.census_digest(host.value)
    if (digest, len(host.value)) != (facts.value.census, facts.value.entries):
        return Err("host and guest source censuses differ")
    return Ok(
        virtualbox_binding.Receipt(
            exchanged.value,
            target.vm,
            target.share,
            target.root.as_posix(),
            target.guest_root,
            facts.value,
        )
    )


def store(target: Target, receipt: virtualbox_binding.Receipt) -> Result[None, str]:
    """Write the receipt atomically into the guest's private state directory."""
    script = (
        "import os, sys; from pathlib import Path\n"
        "from agentctl.foundation_paths import directories\n"
        "state = directories('Linux', os.environ, Path.home()).state\n"
        "state.mkdir(mode=0o700, parents=True, exist_ok=True)\n"
        f"path = state / {virtualbox_binding.RECEIPT_NAME!r}\n"
        "staged = path.with_suffix('.tmp')\n"
        "staged.write_text(sys.stdin.read(), encoding='utf-8')\n"
        "os.chmod(staged, 0o600); os.replace(staged, path); print(path)"
    )
    stored = _guest(target, script, virtualbox_binding.encode(receipt))
    if isinstance(stored, Err):
        return stored
    return Ok(None) if stored.value.code == 0 else Err("cannot store binding receipt")


def observe_vm(root: Path, vm: str, share: str) -> Result[str, str]:
    """Join a named VM to its current shared-folder mapping."""
    shown = run(
        [str(VBOXMANAGE), "showvminfo", vm, "--machinereadable"],
        cwd=root,
        env=os.environ,
    )
    if isinstance(shown, Err) or shown.value.code:
        return Err("cannot observe the VirtualBox VM")
    uuid = vm_uuid(shown.value.stdout, vm)
    if isinstance(uuid, Err):
        return uuid
    mapping = shared_folder(shown.value.stdout, share, root)
    return mapping if isinstance(mapping, Err) else uuid


def main(argv: tuple[str, ...]) -> int:
    """``ROOT VM SHARE GUEST_ROOT KEY KNOWN_HOSTS PORT USER``."""
    if len(argv) != ARGUMENTS - 1:
        sys.stdout.write((main.__doc__ or "") + NEWLINE)
        return 2
    root, vm, share, guest_root, key, known, port, user = argv
    uuid = observe_vm(Path(root), vm, share)
    if isinstance(uuid, Err):
        sys.stdout.write(uuid.error + NEWLINE)
        return 1
    target = Target(
        Path(root),
        uuid.value,
        share,
        guest_root,
        ssh_command(Path(key), Path(known), int(port), user),
    )
    receipt = bind(target)
    if isinstance(receipt, Err):
        sys.stdout.write("binding failed: " + receipt.error + NEWLINE)
        return 1
    after = observe_vm(Path(root), vm, share)
    if isinstance(after, Err) or after.value != uuid.value:
        sys.stdout.write("binding failed: VirtualBox mapping changed" + NEWLINE)
        return 1
    stored = store(target, receipt.value)
    if isinstance(stored, Err):
        sys.stdout.write(stored.error + NEWLINE)
        return 1
    sys.stdout.write(virtualbox_binding.encode(receipt.value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
