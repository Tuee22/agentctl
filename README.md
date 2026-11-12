# agentctl

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Introduce the source-built terminal-agent launcher and its governed installation and validation.

agentctl exposes one pipx-installed Click command for launching and managing Claude and Codex in terminal
multiplexer sessions, with optional conservative recovery supervision.

The Python package carries source resources and bootstraps the Haskell application locally. Haskell owns
runtime dependency preparation and session behavior: Debian Linux uses supported APT-managed tmux; Windows
builds a pinned private psmux with its private toolchain and isolated registry. Claude and Codex are installed
by the user and checked before a fresh launch. See [installation](documents/operations/installation.md).

## Commands

- `agentctl claude [ARGS...]` and `agentctl codex [ARGS...]` launch or reattach by folder.
- `agentctl list`, `status`, `attach`, `stop` and `adopt` manage sessions and explicit external adoption.
- `agentctl watch`, `unwatch`, `pause`, `resume-watch`, `logs` and `supervisor run` control opt-in recovery.
- `agentctl check` is the sole development gate, reporting complete phase/lane evidence and overall health.

The [CLI reference](documents/reference/cli_reference.md) defines arguments and refusals.
The [development plan](DEVELOPMENT_PLAN/README.md) records which target contracts have qualifying evidence;
the [deletion ledger](DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md) records standing migration work.

## Contributing and Validation

Install the editable checkout with its dev extra through pipx and follow [AGENTS.md](AGENTS.md).
Python follows project-owned strict functional standards; Haskell owns runtime provisioning.
Never stage, commit, push or move HEAD as an agent.

On Windows, Linux validation may use a dedicated right-sized Debian WSL2 instance with all Linux dependencies
and a verified bind mount of the live Windows checkout. Native Windows and macOS evidence remain separate.
Read the [validation runbook](documents/operations/validation_runbook.md) before preparing resources.

## Related

- [documents](documents/README.md) — canonical product contracts.
- [development plan](DEVELOPMENT_PLAN/README.md) — execution and status.
- [code standards](documents/engineering/code_standards.md) — source discipline.
- [quality gate](documents/engineering/quality_gate.md) — validation and evidence.
