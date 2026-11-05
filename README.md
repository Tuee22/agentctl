# agentctl

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Introduce agentctl and direct readers to its commands, contracts and development plan.

agentctl manages terminal coding agents. Its Python application provides a single entry point and a quality gate for the editable checkout.

Install from this checkout with `pipx install --editable '.[dev]'` or `uv tool install --editable '.[dev]'`, using Python 3.12 or later. Run `agentctl check` from the checkout root to validate it.

Run `agentctl claude [ARGS...]` or `agentctl codex [ARGS...]` from a project folder to start or reattach its named multiplexer session. Agent arguments pass through unchanged, with the mandatory permission flags added. The first launch provisions the pinned Haskell toolchain and builds the core binary when needed. See the [command reference](documents/reference/cli_reference.md) for argument and authentication rules.

`agentctl status` includes each pane's current screen class.

Use `agentctl list` to list managed sessions and adopted panes, `agentctl status [NAME]` to inspect them, and `agentctl attach NAME` or `agentctl stop NAME` to attach to or end a managed session. `agentctl adopt PANE --agent claude|codex` registers an existing pane; stopping an adopted pane only forgets its registration and leaves it running.

Use `agentctl watch NAME|%ID` to enable recovery supervision, `agentctl pause NAME|%ID` to pause it, `agentctl resume-watch NAME|%ID` to resume it, and `agentctl unwatch NAME|%ID` to opt out. Run `agentctl supervisor run` in the foreground to supervise watched targets and `agentctl logs NAME|%ID` to read a target's decision log. Stopping the supervisor leaves agent sessions running. See the [supervisor contract](documents/architecture/supervisor_contract.md) for recovery conditions and safety rules.

The [development plan](DEVELOPMENT_PLAN/README.md) records implementation progress and validation requirements. The [documentation index](documents/README.md) links the contracts, engineering guides and command reference.
