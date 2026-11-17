# Claude Entry Point

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Import the authoritative repository policy and state its Windows-to-Linux validation prerequisites.

Follow [AGENTS.md](AGENTS.md), including no staging, commits, pushes or moved HEAD. On Windows, use a dedicated agentctl Debian Hyper-V VM for Linux validation, with measured and verified CPU, memory, swap and storage budgets, host headroom and isolation from other projects. Install and configure all required dependencies and agents in the VM; use host credentials in restricted VM storage as permitted by AGENTS.md. Expose and bind mount the live host repository, verifying source identity, bidirectional visibility and filesystem semantics; copies and clones cannot substitute. Keep outputs on dedicated VM storage and leave other projects and sessions undisturbed. Follow applicable non-WSL-specific requirements in the [validation runbook](documents/operations/validation_runbook.md). Guest evidence is Linux evidence, never native Windows or macOS evidence. Use targeted checks for small changes and reserve the complete `agentctl check` for significant milestones, including phase closure.

@AGENTS.md
