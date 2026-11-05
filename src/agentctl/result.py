# Copyright (c) 2026 agentctl contributors.
"""Explicit success and anticipated failure values."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """A successfully computed value."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """An anticipated failure at an effect boundary."""

    error: E


type Result[T, E] = Ok[T] | Err[E]
