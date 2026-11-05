# Agent Working Rules

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define the single working policy for agents changing this repository.

Follow the execution order and closure rules in the [development plan](DEVELOPMENT_PLAN/README.md) and its [standards](DEVELOPMENT_PLAN/development_plan_standards.md). Work the lowest Active phase first, then the lowest eligible Planned phase. Update the phase, its sprints and the status table as work proceeds. Validate a phase before advancing.

`agentctl check` is the only gate. Run it from the editable checkout with the dev extra installed. Focused tests and static tools help development but do not close work. Never add skips, expected failures, suppressions or alternate workflow runners; never weaken an oracle or mutant to obtain a pass. Apply the [code standards](documents/engineering/code_standards.md) and keep documents aligned with their implementations.

Never run `git add`, `git commit` or `git push`, or move HEAD. Commits and human review are optional and never prerequisites for gate closure or phase advancement. Use the current gate's executable evidence, update the plan and continue without requesting a human checkpoint. Never call the core binary or cabal directly; the application and its gate own those invocations. Never run login commands or send login keystrokes.

Tests use private multiplexer servers and test-owned XDG directories. Kill a private server only after checking its endpoint lies inside the run directory. Never modify the user's credentials, agent configuration, shell profiles, toolchain selection or running sessions. Check never prompts and tests never run package managers or sudo.

Live acceptance launches real agents only in `<state>/live-acceptance/`, with automatic updating disabled. Ordinary check runs send no live input and answer no trust, bypass-warning or approval dialog.

Every validation criterion must be executable without human intervention. Detect host capabilities and authentication state automatically; never request a login, answered dialog, manual inspection or fixture capture to obtain a gate pass. Preserve native-host and live-evidence requirements and report unavailable lanes honestly.

The sole screen-fixture capture procedure is optional and outside gate closure. It uses a private multiplexer server, a logged-in agent in that fixed live folder and an explicitly requested capture. Record the agent version, exact capture command, evidence span and `captured` provenance beside the saved screen. A capture requiring agent input needs explicit user authorization because it can consume provider quota. Without that authorization, use documented fixtures with their source URL, or capture only an already visible screen without sending input. Keep documented-only screen classes outside live-confirmation claims.
