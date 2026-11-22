# Copyright (c) 2026 agentctl contributors.
"""Compare explicit guest and loopback SSH host-key values without attestation."""

import base64
import binascii
import hmac
from dataclasses import dataclass

from agentctl.foundation import Err, Ok, Result

ALGORITHM = "ssh-ed25519"
PREFIX = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
KEY_BYTES = 32
MAX_LINE = 1024
MAX_PORT = 65535
FIRST_PRINTABLE = 32
LAST_PRINTABLE = 126


@dataclass(frozen=True, slots=True)
class PublicKey:
    """The complete, structurally validated RFC 4253 public-key blob."""

    blob: bytes


def _key(algorithm: str, encoded: str) -> Result[PublicKey, str]:
    """Accept only canonical Ed25519 SSH key blobs with exactly 32 key bytes."""
    try:
        blob = base64.b64decode(encoded, validate=True)
        if (
            algorithm != ALGORITHM
            or len(blob) != len(PREFIX) + KEY_BYTES
            or not blob.startswith(PREFIX)
            or base64.b64encode(blob).decode("ascii") != encoded
        ):
            return Err("invalid SSH host key")
        return Ok(PublicKey(blob))
    except (binascii.Error, ValueError, UnicodeError):
        return Err("invalid SSH host key encoding")


def _line(text: str) -> Result[str, str]:
    """Require a single bounded, printable ASCII record with one final newline."""
    if (
        not text.endswith("\n")
        or len(text) > MAX_LINE
        or any(
            not FIRST_PRINTABLE <= ord(character) <= LAST_PRINTABLE
            for character in text[:-1]
        )
    ):
        return Err("invalid SSH host key record")
    return Ok(text[:-1])


def guest_key(text: str) -> Result[PublicKey, str]:
    """Decode one guest public-key file without trusting the file's provenance."""
    match _line(text):
        case Err() as error:
            return error
        case Ok(line):
            match line.split(maxsplit=2):
                case [algorithm, encoded] | [algorithm, encoded, _]:
                    return _key(algorithm, encoded)
                case _:
                    return Err("invalid guest SSH host key record")


def known_key(text: str, port: int) -> Result[PublicKey, str]:
    """Decode exactly one literal IPv4-loopback known-host entry for this port."""
    match port:
        case bool():
            return Err("invalid SSH host port")
    if not 1 <= port <= MAX_PORT:
        return Err("invalid SSH host port")
    match _line(text):
        case Err() as error:
            return error
        case Ok(line):
            match line.split():
                case [endpoint, algorithm, encoded] if (
                    endpoint == f"[127.0.0.1]:{port}"
                ):
                    return _key(algorithm, encoded)
                case _:
                    return Err("invalid known-host endpoint or record")


def compare(guest: str, known: str, port: int) -> Result[PublicKey, str]:
    """Join exact key bytes; separate process and file observations prove provenance."""
    match (guest_key(guest), known_key(known, port)):
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok(first), Ok(second)):
            return (
                Ok(first)
                if hmac.compare_digest(first.blob, second.blob)
                else Err("guest and known-host keys differ")
            )
