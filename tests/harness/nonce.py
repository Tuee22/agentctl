# Copyright (c) 2026 agentctl contributors.
"""Fresh observer identities derived from the current check run."""

import secrets


def fresh(run_nonce: str) -> str:
    """Distinguish each observer actor within its originating check run."""
    return run_nonce + "." + secrets.token_hex(16)
