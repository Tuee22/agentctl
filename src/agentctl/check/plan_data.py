# Copyright (c) 2026 agentctl contributors.
"""Immutable plan declarations and shared, nonexecuting Markdown parsing."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Sprint:
    """One sprint parsed independently of its status."""

    identifier: str
    tag: str
    text: str


@dataclass(frozen=True, slots=True)
class Phase:
    """A phase and the sprint blocks it contains."""

    number: int
    path: Path
    text: str
    sprints: tuple[Sprint, ...]


def field(text: str, name: str) -> str:
    """Read one exact bold field, returning empty for an absent field."""
    match = re.search(r"^\*\*" + re.escape(name) + r"\*\*: (.*)$", text, re.MULTILINE)
    if match is None:
        return ""
    return str(match.group(1))


def section(text: str, name: str, *, level: int = 2) -> str:
    """Read a section up to the next heading of the same or lower level."""
    match = re.search(
        r"^"
        + "#" * level
        + " "
        + re.escape(name)
        + r"\n([\s\S]*?)(?=^#{1,"
        + str(level)
        + r"} |\Z)",
        text,
        re.MULTILINE,
    )
    if match is None:
        return ""
    return str(match.group(1)).strip()


def phase_text(path: Path, text: str) -> Phase | None:
    """Parse one named phase from supplied text without reading the filesystem."""
    name = re.fullmatch(r"phase-(\d+)-[a-z-]+\.md", path.name)
    if name is None:
        return None
    matches = tuple(
        re.finditer(r"^### Sprint (\d+\.\d+): [^\n]+ \[([^\]]+)\]$", text, re.MULTILINE)
    )
    sprints = tuple(
        Sprint(
            match[1],
            match[2],
            text[
                match.end() : matches[index + 1].start()
                if index + 1 < len(matches)
                else text.find("\n## Remaining Work", match.end())
            ],
        )
        for index, match in enumerate(matches)
    )
    return Phase(int(name[1]), path, text, sprints)


def phases(root: Path) -> tuple[Phase, ...]:
    """Parse phase files by numeric identity, retaining malformed metadata."""
    found = tuple(
        parsed
        for path in (root / "DEVELOPMENT_PLAN").glob("phase-*.md")
        if (parsed := phase_text(path, path.read_text(encoding="utf-8"))) is not None
    )
    return tuple(sorted(found, key=lambda phase: phase.number))


def table(text: str) -> tuple[tuple[str, ...], ...]:
    """Parse Markdown table cells, keeping only non-separator data rows."""
    return tuple(
        tuple(str(cell).strip() for cell in re.split(r"(?<!\\)\|", line.strip("|")))
        for line in text.splitlines()
        if line.startswith("| ") and not re.fullmatch(r"[| :\-]+", line)
    )
