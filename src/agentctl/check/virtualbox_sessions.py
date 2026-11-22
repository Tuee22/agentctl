# Copyright (c) 2026 agentctl contributors.
"""Parse VirtualBox guest-control session listings without asserting provenance."""

import re
from dataclasses import dataclass
from functools import reduce
from uuid import UUID

from agentctl.foundation import Err, Ok, Result

MAX_OUTPUT = 65536
MAX_SESSIONS = 256
MAX_NUMBER = 2147483647
MIN_LISTING_LINES = 3
FIRST_PRINTABLE = 32
LAST_PRINTABLE = 126
SESSION = re.compile(
    r"Session #([0-9]{1,3})\s+ID=([0-9]{1,10})\s+User=(\S+)\s+"
    r"Status=\[([^\]\r\n]+)\]\s+Name=(.+)"
)
TOTAL = re.compile(r"Total guest sessions: ([0-9]{1,3})")


@dataclass(frozen=True, slots=True)
class Session:
    """One reported session, not an authenticated process registration."""

    number: int
    identifier: int
    user: str
    status: str
    name: str


def _session(line: str) -> Result[Session, str]:
    """Decode one complete printable native listing row."""
    match SESSION.fullmatch(line):
        case None:
            return Err("malformed VirtualBox guest session")
        case match:
            number, identifier, user, status, name = match.groups()
            if (
                any(
                    not FIRST_PRINTABLE <= ord(character) <= LAST_PRINTABLE
                    for character in user + status + name
                )
                or int(identifier) <= 0
                or int(identifier) > MAX_NUMBER
                or str(int(number)) != number
                or str(int(identifier)) != identifier
            ):
                return Err("invalid VirtualBox guest session values")
            return Ok(Session(int(number), int(identifier), user, status, name))


def _append(
    accumulated: Result[tuple[Session, ...], str], item: Result[Session, str]
) -> Result[tuple[Session, ...], str]:
    """Accumulate only fully decoded rows in their original order."""
    match (accumulated, item):
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok(values), Ok(value)):
            return Ok((*values, value))


def parse(text: str) -> Result[tuple[Session, ...], str]:
    """Require an unambiguous complete listing, retaining all other sessions."""
    if text == "No active guest sessions found\n":
        return Ok(())
    if not text.endswith("\n") or len(text) > MAX_OUTPUT:
        return Err("incomplete VirtualBox guest session listing")
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if len(lines) < MIN_LISTING_LINES or lines[0] != "Active guest sessions:":
        return Err("invalid VirtualBox guest session listing")
    return _counted(lines)


def _counted(lines: tuple[str, ...]) -> Result[tuple[Session, ...], str]:
    """Join every parsed row to the reported session count."""
    total = TOTAL.fullmatch(lines[-1])
    if total is None:
        return Err("missing VirtualBox guest session count")
    count = total.group(1)
    if str(int(count)) != count or not 1 <= int(count) <= MAX_SESSIONS:
        return Err("invalid VirtualBox guest session count")
    parsed = tuple(_session(line) for line in lines[1:-1])
    match reduce(_append, parsed, Ok(())):
        case Ok(sessions):
            if (
                len(sessions) != int(count)
                or tuple(value.number for value in sessions)
                != tuple(range(len(sessions)))
                or len({value.identifier for value in sessions}) != len(sessions)
            ):
                return Err("ambiguous VirtualBox guest session listing")
            return Ok(sessions)
        case Err():
            return Err("malformed VirtualBox guest session listing")


def owned(
    sessions: tuple[Session, ...], identifier: str, host_pid: int
) -> Result[Session | None, str]:
    """Identify an exact VBoxManage session name without authorizing cleanup."""
    match host_pid:
        case bool():
            return Err("invalid guest-control host PID")
    try:
        vm = str(UUID(identifier))
    except (ValueError, AttributeError, TypeError):
        return Err("invalid VirtualBox VM identifier")
    if not 1 <= host_pid <= MAX_NUMBER:
        return Err("invalid guest-control host PID")
    name = f"[{host_pid}] VBoxManage Guest Control [{vm}] - run"
    matches = tuple(session for session in sessions if session.name == name)
    match matches:
        case ():
            return Ok(None)
        case (session,):
            return Ok(session)
        case _:
            return Err("ambiguous owned guest-control session")
