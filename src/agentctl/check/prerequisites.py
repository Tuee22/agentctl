# Copyright (c) 2026 agentctl contributors.
"""Non-interactive OS prerequisite readiness after dependency validation."""

from dataclasses import dataclass

from agentctl.bootstrap import prereqs
from agentctl.hostfacts import HostContext, read_distribution
from agentctl.paths import Family
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class PrerequisiteReadiness:
    """Whether prerequisites are present or installable without a terminal prompt."""

    ready: bool
    assume_yes: bool
    is_root: bool
    passwordless: bool
    family: Family = "Linux"
    verified_packages: bool = True


def prerequisite_precondition(facts: PrerequisiteReadiness) -> tuple[str, ...]:
    """Require P9; a missing macOS GUI prerequisite is never installed by check."""
    allowed = facts.ready or (
        facts.family != "Darwin"
        and facts.verified_packages
        and prereqs.consented(assume_yes=facts.assume_yes, accepted=False)
        and (facts.is_root or facts.passwordless)
    )
    return (
        ()
        if allowed
        else (
            (
                "P9: install GHC's OS prerequisites with the printed commands, or use "
                "--assume-yes as root or with passwordless sudo; "
                "on macOS install the Xcode Command Line Tools outside check"
            ),
        )
    )


def prerequisite_proposal(
    context: HostContext, family: Family
) -> Result[tuple[prereqs.PrerequisiteAction, ...], prereqs.PrerequisiteError]:
    """Gather only the distro metadata needed to print verified remediation argv."""
    distribution = None
    if family == "Linux":
        parsed = read_distribution(context.os_release)
        if isinstance(parsed, Err):
            return Err(
                prereqs.PrerequisiteError(
                    "prerequisite-probe-failed", parsed.error.message
                )
            )
        distribution = parsed.value
    return prereqs.proposal(
        prereqs.PackageHost(
            family, distribution, is_root=context.is_root, assume_yes=context.assume_yes
        )
    )


def inspect_prerequisites(
    context: HostContext,
    examine: prereqs.Examine = prereqs.probe,
    attempt: prereqs.Invoke = prereqs.invoke,
) -> tuple[str, ...]:
    """Observe P9 without prompting, installing packages or opening the Xcode GUI."""
    family = context.family
    if family not in {"Linux", "Darwin", "Windows"}:
        return ("P9: use Linux, macOS or Windows",)
    observed = examine(context)
    if isinstance(observed, Err):
        return ("P9: " + observed.error.remedy,)
    if not prereqs.complete(family, observed.value):
        return ("P9: the OS prerequisite probe was incomplete",)
    if all(item.ready for item in observed.value):
        return ()
    selected = prerequisite_proposal(context, family)
    verified = isinstance(selected, Ok)
    passwordless = False
    if verified and context.assume_yes and not context.is_root and family == "Linux":
        passwordless = prereqs.successful(attempt(("sudo", "-n", "true"), context))
    problems = prerequisite_precondition(
        PrerequisiteReadiness(
            ready=False,
            assume_yes=context.assume_yes,
            is_root=context.is_root,
            passwordless=passwordless,
            family=family,
            verified_packages=verified,
        )
    )
    if isinstance(selected, Err):
        return (*problems, "P9 remedy: " + selected.error.remedy)
    remedies = tuple(
        "P9 remedy: " + line
        for action in selected.value
        for line in prereqs.command_lines(action)
    )
    return (*problems, *remedies) if problems else ()
