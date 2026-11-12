# Claude Entry Point

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Import the authoritative repository policy and state its Windows-to-Linux validation prerequisites.

Follow [AGENTS.md](AGENTS.md), including no staging, commits, pushes or moved HEAD. On Windows, Linux validation may use only a dedicated agentctl Debian WSL2 instance with verified right-sized CPU, memory and storage budgets, all needed Linux dependencies including pipx/dev tooling, and a real bind mount of the live host repository that exposes unstaged/untracked changes in both directions. A cloned/copied checkout or commit cannot bridge host and guest. Keep outputs on owned Linux storage, verify effective workload limits and mount semantics, do not disturb global WSL settings or existing distributions, and follow the [validation runbook](documents/operations/validation_runbook.md). WSL evidence is Linux evidence, never native Windows or macOS evidence.

@AGENTS.md
