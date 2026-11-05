# Copyright (c) 2026 agentctl contributors.
"""Documentation rules with closed metadata, local links and root shapes."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md")
METADATA_BODY_PARTS = 2
DOCUMENT_ROOT_DEPTH = 2
CATEGORY_DEPTH = 3
CATEGORIES = frozenset({"architecture", "engineering", "operations", "reference"})
RULES = (
    "metadata",
    "structure",
    "taxonomy",
    "links",
    "owning-phase",
    "no-status",
    "phase-citation",
    "binary-unnamed",
    "enforcement-cited",
    "root-entry",
)
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
NODE = re.compile(
    r"tests/(?:unit|integration|e2e|live|governance)/test_\w+\.py::test_\w+|haskell:agentctl-core-test/[^\s`|]+"
)


def unfenced(text: str) -> str:
    """Mask fenced examples, respecting the opening delimiter's length."""
    fence = ""
    lines: list[str] = []
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            if re.fullmatch(
                r"\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line
            ):
                fence = ""
            lines.append("")
        elif marker:
            fence = marker[1]
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


def slug(heading: str) -> str:
    """Compute the documentation standard's heading fragment."""
    return re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")


def pages(root: Path) -> tuple[Path, ...]:
    """Enumerate governed documents, including existing root documents."""
    return (
        *sorted((root / "documents").rglob("*.md")),
        *(root / name for name in ROOT_FILES if (root / name).is_file()),
    )


def _metadata(text: str, *, root_page: bool) -> bool:
    """Check the exact metadata prefix rather than arbitrary later fields."""
    owner = "" if root_page else r"\*\*Owning phase\*\*: \[[^\n]+\]\([^\n]+\)\n"
    return (
        re.match(
            r"\A# [^\n]+\n\n\*\*Status\*\*: "
            r"(?:Authoritative source|Reference only|Deprecated)\n"
            r"\*\*Supersedes\*\*: (?:N/A|`[^`]+`)\n"
            + owner
            + r"\n> \*\*Purpose\*\*: \S",
            text,
        )
        is not None
        and len(re.findall(r"^# ", unfenced(text), re.MULTILINE)) == 1
    )


def _links(path: Path, text: str) -> bool:
    """Resolve every local link and anchor without consulting the network."""
    for _label, raw in LINK.findall(text):
        target, _separator, fragment = unquote(raw).partition("#")
        if "://" in target or target.startswith("mailto:"):
            return False
        destination = (path.parent / target).resolve() if target else path
        if not destination.is_file():
            return False
        if fragment:
            headings = re.findall(
                r"^#{1,6} (.+)$",
                unfenced(destination.read_text(encoding="utf-8")),
                re.MULTILINE,
            )
            if fragment not in {slug(heading) for heading in headings}:
                return False
    return True


def _owner(root: Path, text: str) -> bool:
    """Join owning-phase link labels to existing phase titles."""
    match = re.search(
        r"^\*\*Owning phase\*\*: \[([^\]]+)\]\(([^)]+)\)$", text, re.MULTILINE
    )
    if match is None:
        return False
    filename = Path(match[2]).name
    phase = root / "DEVELOPMENT_PLAN" / filename
    if not re.fullmatch(r"phase-\d+-[a-z-]+\.md", filename) or not phase.is_file():
        return False
    title = phase.read_text(encoding="utf-8").splitlines()[0]
    return re.sub(r"^# Phase \d+ — ", "", title) == match[1]


def _enforcement(text: str) -> bool:
    """Require a test citation in each paragraph, list item or table row claim."""
    blocks = re.split(r"\n\s*\n|\n(?=\||- |\d+\. )", text)
    for block in blocks:
        claim = re.search(
            r"(?:`agentctl check`|\b(?:check|test|validator)\b|"
            r"`(?:src|docs|plan|config)\.[^`]+`)"
            r"(?: (?:\w+|`[^`]+`)){0,2} (?:enforces?|rejects?|refuses?|fails?)\b",
            block,
            re.IGNORECASE,
        )
        if claim and NODE.search(block) is None:
            return False
    return True


def _root_entry(root: Path) -> bool:
    """Require the root index links and a single imported agent policy."""
    if not all((root / name).is_file() for name in ROOT_FILES):
        return False
    readme = (root / "README.md").read_text(encoding="utf-8")
    destinations = {target for _label, target in LINK.findall(readme)}
    if not {"DEVELOPMENT_PLAN/README.md", "documents/README.md"} <= destinations:
        return False
    for name in ROOT_FILES:
        text = (root / name).read_text(encoding="utf-8")
        status = "Authoritative source" if name == "AGENTS.md" else "Reference only"
        if f"**Status**: {status}\n" not in text:
            return False
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    remainder = re.split(
        r"^> \*\*Purpose\*\*: [^\n]+\n", claude, maxsplit=1, flags=re.MULTILINE
    )
    return (
        len(remainder) == METADATA_BODY_PARTS
        and re.fullmatch(
            r"\s*[^\n]*\[AGENTS\.md\]\(AGENTS\.md\)[^\n]*\n\n@AGENTS\.md\s*",
            remainder[1],
        )
        is not None
    )


def _invalid_metadata(text: str, *, root_page: bool) -> bool:
    """Detect violations of docs.metadata."""
    bad = not _metadata(text, root_page=root_page)
    return bool(bad)


def _invalid_structure(relative: Path, prose: str, *, root_page: bool) -> bool:
    """Detect violations of docs.structure."""
    headings = re.findall(r"^## (.+)$", prose, re.MULTILINE)
    bad = not root_page and (
        not headings
        or headings[-1] != "Related"
        or ("architecture" in relative.parts and headings[0] != "TL;DR")
    )
    return bool(bad)


def _invalid_taxonomy(relative: Path, path: Path, *, root_page: bool) -> bool:
    """Detect violations of docs.taxonomy."""
    bad = not root_page and (
        not re.fullmatch(r"(?:README|[a-z][a-z_]+)\.md", path.name)
        or (
            len(relative.parts) == DOCUMENT_ROOT_DEPTH
            and path.name not in {"README.md", "documentation_standards.md"}
        )
        or (
            len(relative.parts) > DOCUMENT_ROOT_DEPTH
            and (
                relative.parts[1] not in CATEGORIES
                or len(relative.parts) != CATEGORY_DEPTH
            )
        )
    )
    return bool(bad)


def _invalid_links(path: Path, prose: str) -> bool:
    """Detect violations of docs.links."""
    bad = not _links(path, prose)
    return bool(bad)


def _invalid_owning_phase(root: Path, prose: str, *, root_page: bool) -> bool:
    """Detect violations of docs.owning-phase."""
    bad = not root_page and not _owner(root, prose)
    return bool(bad)


def _invalid_no_status(prose: str) -> bool:
    """Detect violations of docs.no-status."""
    bad = any(
        re.search(r"\b(?:Planned|Active|Done)\b", line)
        and re.search(r"\]\([^)]*phase-\d+-", line)
        for line in prose.splitlines()
    )
    return bool(bad)


def _invalid_phase_citation(prose: str) -> bool:
    """Detect violations of docs.phase-citation."""
    bad = re.search(r"\b(?:phase|sprint)\s+\d", prose, re.IGNORECASE) is not None
    return bool(bad)


def _invalid_binary_unnamed(text: str, *, user_page: bool) -> bool:
    """Detect violations of docs.binary-unnamed."""
    bad = user_page and "agentctl-core" in text
    return bool(bad)


def _invalid_enforcement_cited(prose: str) -> bool:
    """Detect violations of docs.enforcement-cited."""
    bad = not _enforcement(prose)
    return bool(bad)


def _page_invalid(root: Path, path: Path, rule: str) -> bool:
    """Apply one page rule outside the filesystem enumeration loop."""
    text = path.read_text(encoding="utf-8")
    prose = unfenced(text)
    relative = path.relative_to(root)
    root_page = len(relative.parts) == 1
    user_page = relative.parts[0] == "README.md" or relative.parts[:2] in (
        ("documents", "operations"),
        ("documents", "reference"),
    )
    return {
        "metadata": lambda: _invalid_metadata(text, root_page=root_page),
        "structure": lambda: _invalid_structure(relative, prose, root_page=root_page),
        "taxonomy": lambda: _invalid_taxonomy(relative, path, root_page=root_page),
        "links": lambda: _invalid_links(path, prose),
        "owning-phase": lambda: _invalid_owning_phase(root, prose, root_page=root_page),
        "no-status": lambda: _invalid_no_status(prose),
        "phase-citation": lambda: _invalid_phase_citation(prose),
        "binary-unnamed": lambda: _invalid_binary_unnamed(text, user_page=user_page),
        "enforcement-cited": lambda: _invalid_enforcement_cited(prose),
    }[rule]()


def check(root: Path, rule: str) -> tuple[str, ...]:
    """Evaluate one named documentation rule on the given repository tree."""
    violations: tuple[str, ...] = ()
    governed = pages(root)
    if rule == "links":
        governed += tuple(sorted((root / "DEVELOPMENT_PLAN").glob("*.md")))
    if rule == "root-entry":
        phase = root / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
        required = (
            not phase.exists()
            or "Root entry documents [Planned]" not in phase.read_text(encoding="utf-8")
        )
        return (
            ("docs.root-entry: root entry documents",)
            if (required or any((root / name).exists() for name in ROOT_FILES))
            and not _root_entry(root)
            else ()
        )
    if rule == "taxonomy" and (root / "docs").exists():
        violations += ("docs.taxonomy: docs/",)
    for path in governed:
        if _page_invalid(root, path, rule):
            violations += (f"docs.{rule}: {path.relative_to(root).as_posix()}",)
    return violations


def validate(root: Path) -> tuple[str, ...]:
    """Run the complete documentation rule registry."""
    return tuple(problem for rule in RULES for problem in check(root, rule))
