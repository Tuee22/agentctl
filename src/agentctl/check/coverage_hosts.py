# Copyright (c) 2026 agentctl contributors.
"""Declared host classes for sources whose execution is confined to one host."""

import re
import tomllib
from dataclasses import dataclass

from agentctl.foundation import Err, Family, Ok, Result

HOSTS = frozenset({"Linux", "Darwin", "Windows", "WSL"})
SOURCE = re.compile(r"src/agentctl/(?:[a-z0-9_]+/)*[a-z0-9_]+\.py")


@dataclass(frozen=True, slots=True)
class HostSource:
    """One source file and the host classes that can execute its native paths."""

    path: str
    hosts: frozenset[str]


def parse(text: str) -> Result[tuple[HostSource, ...], str]:
    """Parse the closed manifest, refusing unknown hosts, paths and duplicates."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err("invalid coverage host manifest: " + str(exc))
    match document:
        case {"version": 1, "source": list() as values, **extra} if not extra:
            pass
        case _:
            return Err("invalid coverage host manifest fields")
    parsed = tuple(_source(value) for value in values)
    sources = tuple(item.value for item in parsed if isinstance(item, Ok))
    paths = tuple(source.path for source in sources)
    if not values or len(sources) != len(values) or len(set(paths)) != len(paths):
        return Err("invalid or duplicate coverage host source")
    return Ok(sources)


def _source(value: object) -> Result[HostSource, str]:
    """Accept one canonical first-party path and a non-empty known host set."""
    match value:
        case {"path": str() as path, "hosts": list() as hosts, **extra} if (
            not extra
            and SOURCE.fullmatch(path) is not None
            and hosts
            and all(isinstance(host, str) and host in HOSTS for host in hosts)
            and len(set(hosts)) == len(hosts)
        ):
            return Ok(HostSource(path, frozenset(str(host) for host in hosts)))
        case _:
            return Err("invalid coverage host source")


def foreign(sources: tuple[HostSource, ...], family: Family) -> tuple[str, ...]:
    """Name declared sources that this host family cannot execute.

    A WSL-only source is foreign to every native family, including ordinary Linux.
    Undeclared sources are measured on every host.
    """
    return tuple(
        sorted(source.path for source in sources if family not in source.hosts)
    )


def missing(
    sources: tuple[HostSource, ...], present: frozenset[str]
) -> tuple[str, ...]:
    """Name declared sources that are absent from the observed source census."""
    return tuple(
        sorted(source.path for source in sources if source.path not in present)
    )
