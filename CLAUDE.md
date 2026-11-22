# Claude Entry Point

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Import the authoritative repository policy and state its Windows-to-Linux validation prerequisites.

Follow [AGENTS.md](AGENTS.md), including no staging, commits, pushes or moved HEAD. On Windows, use a dedicated agentctl Debian VirtualBox VM for Linux validation, sized with host headroom and dedicated storage, aiming to avoid resource contention with other projects. Proof of cross-project CPU, memory or storage isolation is not a validation prerequisite. Install and configure all required dependencies and agents in the VM; use host credentials in restricted VM storage as permitted by AGENTS.md. Expose and bind mount the live host repository, verifying source identity, byte census and bidirectional visibility and recording its filesystem semantics; copies and clones cannot substitute. Keep outputs on dedicated VM storage and leave other projects and sessions undisturbed. Follow applicable non-WSL-specific requirements in the [validation runbook](documents/operations/validation_runbook.md). Guest evidence is Linux evidence, never native Windows or macOS evidence. Use targeted checks for small changes and reserve the complete `agentctl check` for significant milestones, including phase closure.

@AGENTS.md
