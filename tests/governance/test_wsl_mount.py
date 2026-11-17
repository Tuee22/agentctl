# Copyright (c) 2026 agentctl contributors.
"""Mount facts must describe the complete visible kernel hierarchies."""

import pytest

from agentctl.check.wsl_mount import DeviceIdentity, validate
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

MOUNTS = (
    "1 0 8:1 / / rw - ext4 /dev/root rw\n"
    "2 1 0:5 / /proc rw - proc proc rw,hidepid=0\n"
    "3 1 0:29 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
)
PROC = DeviceIdentity(0, 5, 11)
CGROUP = DeviceIdentity(0, 29, 22)
PATH = "/sys/fs/cgroup"


def test_mount_requires_complete_visible_native_hierarchies() -> None:
    """Refuse a wrong filesystem, partial hierarchy, device or hidden PIDs."""
    assert isinstance(validate(MOUNTS, PATH, PROC, CGROUP), Ok)
    wrong_fs = MOUNTS.replace("- cgroup2 cgroup", "- tmpfs cgroup")
    assert isinstance(validate(wrong_fs, PATH, PROC, CGROUP), Err), (
        "non-cgroup filesystem was accepted"
    )
    partial = MOUNTS.replace("0:29 / /sys/fs/cgroup", "0:29 /sub /sys/fs/cgroup")
    assert isinstance(validate(partial, PATH, PROC, CGROUP), Err), (
        "partial cgroup hierarchy was accepted"
    )
    assert isinstance(validate(MOUNTS, PATH, PROC, DeviceIdentity(0, 30, 22)), Err), (
        "mismatched mount device was accepted"
    )
    for option in ("hidepid", "hidepid=", "hidepid=2", "hidepid=invisible"):
        hidden = MOUNTS.replace("hidepid=0", option)
        assert isinstance(validate(hidden, PATH, PROC, CGROUP), Err), (
            "hidden process namespace was accepted"
        )
    assert isinstance(
        validate(MOUNTS.replace("hidepid=0", "hidepid=off"), PATH, PROC, CGROUP), Ok
    )
    assert isinstance(
        validate(MOUNTS + MOUNTS.splitlines(keepends=True)[2], PATH, PROC, CGROUP), Err
    )
