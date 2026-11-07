# Design Rationale

**Status**: Reference only
**Supersedes**: N/A

> **Purpose**: Preserve the request this plan answers, record every decision with its provenance,
> explain why the design has its shape rather than the alternatives, and record where every item of
> the concept note went.

This file explains; it does not instruct. The phase files say what each phase builds, and
[development_plan_standards.md](development_plan_standards.md) says how the plan is governed. This is
the one plan file that names shapes the project does not build, because naming a rejected shape is
how a reader avoids reintroducing it. The request block and the decision rows are anchors that
requirement quotes and oracle provenance point at, so both are append-only: a later answer is
appended to the block, and a revised decision is a new row that names the row it revises.

## Originating Request

This block preserves, verbatim, the user's request, the four planning answers and the concept-note
excerpts the user adopted, and every requirement quote in [00-overview.md](00-overview.md#requirements)
is an exact substring of it.

````text
[request]
please review agentctl-plan.md and show me a plan to write DEVELOPMENT_PLAN/ and documents/ based on this concept. when you're done delete agentctl-plan.md. look at adjacent projects like ~/prodbox ~/hostbootstrap ~/amoebius ~/infernix ~/jitML and base this project's development_plan_standards.md and documentation_standards.md on similar principles, written to be appropriate for this project. phases should have strict validation criteria that cannot be spoofed and which an agent can validate automatically without human input. note that pipx is the only host dependency that's required here. agentctl is a click application using pytest. the check command should run ruff, ty (strict) and the entire test suite. codex and claude are both commands. each of these require a mandatory name for the tmux session which should be based on the folder the command calls it from. any additional command parameters are passed through to either codex or claude. at the end, claude always includes "--dangerously-skip-permissions" and codex always includes "--dangerously-bypass-approvals-and-sandbox --no-daemon". in addition to being the interface layer to the haskell binary, the pipx tool also a) idempotently installs ghcup in the manner appropriate for the OS in question, b) installs cabal c) builds the haskell binary. everything after that is done by the haskell binary (with the click tool's commands passing through to it). the user shouldn't need to call the haskell binary directly. haskell is responsible for ensuring tmux/psmux are available, that claude / codex is available, and that the session is logged in. if any of these are not the case tmux should be closed and a warning message printed. in the case that the session is not logged in, agentctl should instruct the user to do so themselves with the appropriate command (eg claude auth login). note we do not log in from the claude/codex REPL, we always log in as a discrete claude/codex auth command, which the use should be instructed to type themselves.

[question 1] For `agentctl claude` / `agentctl codex`, how should the mandatory tmux/psmux session name be formed? (You said it's mandatory and based on the folder the command is run from.)
[answer 1] Auto from folder (Recommended) — No name argument. The name is derived from the invoking folder plus the agent, e.g. `api-claude` / `api-codex` (sanitized; a short path hash disambiguates two different folders with the same basename). Every argument passes through to the agent. Re-running in the same folder re-attaches to that folder's session.

[question 2] agentctl-plan.md also describes list/attach/stop, adopting existing panes, TOML profiles, and a recovery supervisor (watch/pause/logs, overload detection, backoff retries). Which of these should DEVELOPMENT_PLAN's phases cover beyond the launcher core you specified (toolchain bootstrap, claude/codex launch with preflight checks, check)?
[answer 2] Full concept (Recommended) — Launcher core first, then session management (list/attach/stop), then the supervisor/recovery phases (overload classifier, backoff state machine, safe send-keys, watch/pause/logs). Passthrough args replace TOML profiles.

[question 3] `agentctl check` runs ruff, ty (strict) and the entire test suite. How much of the Haskell side should that single command also gate?
[answer 3] Also fourmolu + hlint — As above, plus Haskell formatter and linter checks (agentctl installs fourmolu/hlint via ghcup/cabal). Stricter, but the first run is much heavier. ("Above" is the recommended option: ruff check + ruff format --check + ty check + the whole pytest suite. That suite also builds the Haskell binary with -Werror through the same bootstrap path users get, and runs its cabal test-suite. One command, one verdict.)

[question 4] GHC needs OS-level prerequisites that ghcup can't install itself: a C toolchain plus libgmp/libffi/ncurses on Linux, and Xcode Command Line Tools on macOS (Windows is self-contained through ghcup's bundled MSYS2). When one is missing, what should agentctl do?
[answer 4] Install with consent — Ask interactively, then run the OS package manager itself (apt/dnf/pacman with sudo, or xcode-select --install).

[concept excerpts adopted by answer 2, verbatim from agentctl-plan.md]
- Start Codex or Claude with named profiles, preferred CLI arguments, working directories, and project defaults.
- List, attach, detach, and stop sessions; adopt pre-existing panes without taking ownership.
- Supervise capacity/overload failures without changing the selected model.
- Provide status, logs, manual pause/unwatch, conservative exponential-backoff retries.
- Work with tmux on macOS/Linux and psmux on native Windows.
- Keep session management usable when the supervisor is not running.

```sh
agentctl start api
agentctl start codex --name auth-refactor --cwd ~/src/api
agentctl start claude --profile opus -- --verbose
agentctl list
agentctl status
agentctl attach auth-refactor
agentctl adopt %3 --agent codex
agentctl watch auth-refactor
agentctl unwatch auth-refactor
agentctl pause auth-refactor
agentctl resume-watch auth-refactor
agentctl logs auth-refactor
agentctl stop auth-refactor
agentctl supervisor run
```

These commands are proposed, not currently implemented. `resume-watch` means resume supervision, not resume the agent's goal.

**Independent properties:** a session may be managed, supervised, and human-attached independently. Unwatching does not terminate the agent; adopted sessions are not killed by stopping the supervisor.

State progression: `MONITORING → SUSPECTED_FAILURE → CONFIRM_IDLE → BACKOFF → RECOVERY_SENT → VERIFY → MONITORING/ESCALATE`.

1. Match a fresh, recognizable capacity/overload error and a safe input-ready prompt; unchanged output alone does not imply idleness.
2. Never send input during active work, approval dialogs, or partially typed user input.
3. Fingerprint errors to avoid retrying stale scrollback; require a new transition before another injection.
4. Wait for acknowledgement after a retry. An unchanged screen is not evidence of success.
5. Distinguish transient overload from usage limits, authentication errors, context exhaustion, and crashes.
6. Use bounded exponential backoff with jitter; allow indefinite retries only for explicitly classified transient capacity errors, with escalating notifications.
7. Log each observation, decision, attempt, and result. Support manual pause and opt-out.
8. Never automatically switch models or restart arbitrary crashed processes.
9. Encourage durable project checkpoints: completed steps, pending work, tests, and partially completed edits. Conversational recovery is not guaranteed to restore an interrupted internal tool call.

[governance clarification]
update the plan and standards so that git commits and other forms of human intervention will not be blockers for closing gates. all validation criteria should be something agents can perform automatically
````

The user approved the plan built from these answers before this suite was written.

## Decisions

Every row is a decision the phases build to, and an oracle row that rests on a decision cites its id.
Provenance is `answer:N` for the user's answer N in the [Originating Request](#originating-request),
`decision:planner` for a planner default the user approved with the plan, or `tool:` followed by a
verified tool fact, recorded with its version and source in
[external_tool_facts.md](../documents/reference/external_tool_facts.md).

| ID | Decision | Provenance | Owning phase |
|---|---|---|---|
| D-01 | Session names come from the invoking folder plus the agent, such as `api-claude` and `api-codex`. There is no name argument, every argument passes through to the agent, and re-running in the same folder re-attaches to that folder's session. | `answer:1` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-02 | The plan covers the full concept: the launcher core first, then session management (list, attach, stop), then the recovery supervisor (overload classifier, backoff state machine, safe send-keys, watch, pause, logs). Passthrough ARGS replace TOML profiles. | `answer:2` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-03 | `agentctl check` also gates the Haskell side. Its legs are `ruff check`, `ruff format --check`, `ty`, `fourmolu`, `hlint`, `cabal build` (`-Werror`, tests enabled), `cabal test` and the entire pytest suite, and agentctl installs fourmolu and hlint itself. | `answer:3` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-04 | GHC's OS prerequisites are probed. When one is missing, agentctl asks interactively and then runs the OS package manager itself: apt, dnf or pacman with sudo, or `xcode-select --install`. | `answer:4` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-05 | R1 reads "pipx is the only host dependency" as: the build chain needs only pipx and its Python. agentctl installs the OS build prerequisites (with consent), ghcup, GHC and cabal. tmux or psmux and the agent CLIs are runtime prerequisites: the core binary checks them and prints the OS-specific install command, and never installs them. | `decision:planner` | [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) |
| D-06 | Sessions live on the user's normal tmux server, and in psmux's default namespace, so `tmux ls` shows them. agentctl uses no private socket or namespace. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-07 | A session name is `<base>-<agent>`. The base is the canonical (realpath) folder basename, sanitised: characters outside `[A-Za-z0-9_-]` map to `-`, runs of `-` collapse, and the result is never empty, never starts with `-` and never contains `__`. | `tool:` tmux format-expands the `-s` value and rewrites `:` and `.` differently across versions, and psmux uses `__` as its namespace separator | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-08 | A different folder with the same base gets the hash form `<base>-<8 hex of sha256(canonical path, UTF-8; case-folded on Windows)>-<agent>`. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-09 | Managed-session identity lives in tmux session options (`@agentctl_agent`, `@agentctl_folder`, `@agentctl_owner`), so re-running in the same folder finds and re-attaches its session. No on-disk registry holds managed sessions. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-10 | ARGS pass verbatim. User copies of the mandatory flags, and codex's `--yolo` alias, are removed; then the mandatory flags are appended at the end, or immediately before the first bare `--`. | `tool:` codex exits 2 on a repeated flag, `--yolo` is an alias of its bypass flag, and both CLIs read what follows `--` as positional | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-11 | There are no subcommand tables. An agent-side rejection of its argv is caught by instant-exit capture: remain-on-exit holds the pane during a startup window, the pane output is relayed, the session is closed, and agentctl exits with the agent's status. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-12 | Login-shaped ARGS are refused before any session exists: claude `auth login…`, `setup-token` and any `/login` token; codex `login…`. | `decision:planner` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-13 | Re-attach skips preflight. ARGS given while the session exists produce a notice that they were not applied, and a dead leftover pane is replaced. With no TTY, agentctl creates or reuses the session, prints the attach command and exits 0. When `$TMUX` is set, agentctl targets that server with `switch-client`. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-14 | The pane runs the trampoline `agentctl-core pane-exec <spec>`. The spec file is 0600 in a 0700 dir under `state`, holds argv, cwd and the caller's environment, and is deleted after reading. On POSIX the trampoline calls `execve`, so `#{pane_pid}` is the agent; on Windows it runs the agent as a child and writes a status file. No user text reaches tmux or psmux parsing, and environment values stay off the multiplexer command line. | `tool:` tmux format-expands `-s` and `-c` values, ends a command at an argv element with a trailing `;`, and gives a pane the environment its server started with; psmux reports `#{pane_dead_status}` as 0 always | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-15 | Preflight checks the multiplexer, then the agent, then auth. On failure no session is created, the warning reaches the user's own terminal, and the exit is non-zero. | `decision:planner` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-16 | Auth checks use exit codes only: 0 is logged in, 1 is logged out, and anything else, or a timeout, is `check failed`. | `tool:` `claude auth status` and `codex login status` exit 0 when logged in and 1 when not, and codex's wording changes between versions | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-17 | Trust and bypass-warning dialogs are never answered, by agentctl or by tests. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-18 | An existing ghcup at or above 0.1.50.2 is reused, never replaced or upgraded. | `decision:planner` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-19 | With no ghcup present, agentctl downloads the pinned 0.2.6.2 through Python urllib from `downloads.haskell.org/~ghcup/0.2.6.2/` and verifies the published SHA-256. It never runs the official bootstrap script and never edits rc files. | `tool:` the bootstrap script verifies no checksum and edits rc files whenever `BOOTSTRAP_HASKELL_ADJUST_BASHRC` is non-empty | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-20 | GHC 9.12.4 is installed with `ghcup install ghc` and no `--set`, and cabal 3.16.1.0 with `--no-set`. Paths come from `ghcup whereis`, warm runs verify them with `--numeric-version`, and the user's default symlinks never change. | `tool:` `ghcup install cabal` changes the default unless `--no-set` is passed, while `ghcup install ghc` does not | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-21 | The probed prerequisites are the C compiler and linker, `-lgmp`, curl or wget, CA certificates and make. | `tool:` GHC 9.12.4 bundles libffi, and ghcup has no internal downloader | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-22 | Interactive runs ask for consent, then use sudo. Non-interactive runs, check included, never prompt: they use `sudo -n`, or the global flag `agentctl --assume-yes`. | `decision:planner` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-23 | The Cabal project is package data at `src/agentctl/haskell/`, with no hatchling force-include. | `tool:` hatchling copies force-included files into editable wheels as a snapshot and ignores `.gitignore` while walking them | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-24 | The binary is built into `cache/build/<digest>`, where the digest covers its sources and pins, and is published atomically into `data/bin/<digest>`. It is never put on PATH and refuses direct invocation without the handoff protocol. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-25 | The handshake is a protocol version plus the command list, with no CPP and no embedded digest. Binary identity is the sha256 of the `cabal list-bin` output. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-26 | `src/agentctl/paths.py` decides every per-user dir (`cache`, `data`, `state`) and honours XDG overrides on every OS, starting with the check lock; the handoff passes those same dirs to the binary in [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md). | `tool:` Python's platformdirs and Haskell's `getXdgDirectory` disagree on macOS and Windows | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-27 | `agentctl check` needs a PEP 610 editable install of this checkout, made with `pipx install --editable '.[dev]'` or `uv tool install --editable '.[dev]'`. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-28 | The dev tools are the `dev` extra, not a dependency group. | `tool:` pipx has no PEP 735 dependency-group support | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-29 | Python is at least 3.12. The pins are click 8.5.0, ruff 0.17.3, ty 0.0.95 and pytest 9.2.0, with coverage pinned in Sprint 0.2. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-30 | ty runs with `all = "error"`, `respect-type-ignore-comments = false`, error-on-warning, `--python sys.executable` and an isolated config home. | `tool:` ty has no strict switch, merges a user-level config file, and does not discover a pipx venv on its own | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-31 | ruff runs with `select = ["ALL"]`, ignoring the formatter conflicts D203, D213 and COM812. S603 and S606 are allowed only in `src/agentctl/process.py`. | `tool:` ruff's formatter conflicts with D203, D213 and COM812 when every rule is selected | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-32 | pytest runs with `strict = true` and `filterwarnings = ["error"]`. The final tool configs are co-designed in Sprint 0.2 by running the pinned tools, then frozen by `tests/oracles/lint_config.toml`. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-33 | `agentctl check` takes no arguments, runs from a scrubbed environment allowlist, and fails if any step or leg fails or does not run. The warm-run budget is about 15 minutes. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-34 | check and its children run with `PYTHONPYCACHEPREFIX` under the run dir, so the write-guard excludes only `.git`. | `decision:planner` | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| D-35 | Tests adapt only to login state, multiplexer kind, OS family and toolchain provenance. Tool absence is tested only with constructed PATHs, and check fails when the lane of any Done self-verifying phase is unmet on the host running it. | `decision:planner` | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| D-36 | Live tests, in Sprint 6.2, Sprint 8.3 and Sprint 10.4, branch on login state and never send input. They accept `TrustDialog`, `BypassWarning` or `IdlePrompt` as a live agent, check on Linux that `/proc/<pane_pid>/cmdline` ends with the mandatory flags (an npm-installed codex runs as `node` with `codex.js`), and run in a fixed folder under the real state dir with `DISABLE_AUTOUPDATER=1`. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-37 | Live `IdlePrompt` classification counts as proven only when the user has already trusted the live folder; otherwise it is listed as not proven. | `decision:planner` | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| D-38 | Screen fixtures carry the provenance `captured`, through a capture `AGENTS.md` sanctions because capturing `Working`, `PartialInput` or dialog screens spends the user's quota, or `documented`, from official docs or changelogs with the URL. Classes backed only by `documented` fixtures are listed as not proven. | `decision:planner` | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| D-39 | `supervisor run` reads no config file. Its timing flags default to the concept note's values (poll 5 s, initial delay 30 s, max delay 900 s, multiplier 2, jitter 0.2), and the recovery text is a per-agent constant. It runs in the foreground, and nothing auto-starts it. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-40 | The supervisor re-captures and re-classifies immediately before `send-keys -l`, and aborts if the screen changed. Notifications go to the supervisor's stderr and to JSONL `notify` records. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-41 | A registry exists only for adopted panes. `stop` on an adopted pane forgets it and prints a notice; it never kills. | `decision:planner` | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| D-42 | On Windows, agents resolve to native `.exe` files, and `.cmd` and `.bat` shims are refused with a remedy. PATHEXT resolution is tested as values on every host. | `tool:` a `.cmd` started through CreateProcessW has its arguments re-parsed by cmd.exe | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-43 | Agents never `git add`, `git commit` or `git push`. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-44 | There is no CI. The gate of record is `agentctl check`, run by an agent on the declared host. | `decision:planner` | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| D-45 | There is no distribution phase: a tag install needs a user release, and the digest-keyed cache never overwrites a binary. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-46 | There is no uninstall command; [installation.md](../documents/operations/installation.md) documents removing agentctl's per-user dirs. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-47 | The user's commit points are: after this governed suite; after [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md), when the request-derived oracles are frozen before any product code; and at each phase close. | `decision:planner` | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| D-48 | The claude recovery text is exactly `Continue the interrupted task from the last completed step.`; the codex recovery text is exactly `Continue the interrupted task from the last saved checkpoint.`. These plain-text constants are planner choices, not claims of provider recovery. The agent-table rows of `tests/oracles/launch_argv.toml` freeze them before product code; the agent table owns them. | `decision:planner` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-49 | Supersedes D-47: commits and human intervention are never gate-closure or phase-advancement prerequisites. Every validation criterion is executable automatically by an agent. User commits and reviews remain optional, agents still never stage, commit, push or move HEAD, and the ratchet uses the available baseline with its historical limits disclosed. | `request:` governance clarification in Originating Request | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| D-50 | P7 reserves 10 GiB for a missing GHC, 1 GiB for a missing cabal and 4 GiB of cache for a cold toolchain. These conservative policy budgets combine when both directories share a filesystem; answering pins reserve nothing. | `decision:planner` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-51 | The clean recipe uses the non-root `agentctl` account with NOPASSWD sudo. Stage A starts at Ubuntu 24.04 with python3, pipx and sudo, records independent absence, installs a wheel and requires the first `--assume-yes list` to end at missing tmux. Stage B adds tmux, git and both official native agent installers, installs editable dev and runs plain check. | `decision:planner` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-52 | The first handoff protocol is version 1. Its handshake names the thirteen Haskell-owned public commands, excluding Python's check command; the JSONL evaluator answers unknown or malformed cases with an invalid-case error object. The project pins the Hackage index in cabal.project. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-53 | Style tools are Fourmolu 0.19.0.1 and HLint 3.10, with ghc-lib-parser constrained to 9.12.2.20250421 so both use the GHC 9.12 parser family. They build together with two concurrent Cabal jobs, the project's index pin and the pinned GHC. The style digest length-prefixes the ordered name and version pairs ghc, fourmolu, hlint and ghc_lib_parser. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-54 | Amends the parser constraint of D-53 to ghc-lib-parser 9.12.3.20251228. This release uses GHC.Boot.TH.Ppr rather than the GHC.Internal.TH.Ppr module absent from GHC 9.12.4; the remaining style versions and digest rule are unchanged. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-55 | The binary digest length-prefixes sorted source path/body pairs, then the raw pin bytes and the ghcup asset's platform prefix, using eight-byte big-endian lengths. Source directories are excluded from the hash; source symlinks and special entries are refused. Builds hold a per-digest cache lock and publication holds a per-digest lock under data/locks, outside immutable bin entries, so concurrent publishers cannot replace one another. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-56 | Python tool-leg commands and check's enclosing execution each have a one-hour deadline. This accommodates the complete suite and fresh native-build mutant controls without changing assertions, coverage or kill criteria; the short default for individual process calls is unchanged. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-57 | The multiplexer floors are tmux 3.2 and psmux 3.4.0. Tmux accepts one lowercase release suffix; psmux accepts a three-component release with optional parenthesised build metadata. Windows candidates contain only psmux.exe. Linux remedies are apt for Debian/Ubuntu, dnf for Fedora/RHEL-family and pacman for Arch; unknown distributions receive a package-manager-neutral tmux remedy. Darwin uses brew and Windows uses winget. These value cases are authored before their kernels; session-name acceptance appends independent cases anchored on D-07. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-58 | The adapter's typed vocabulary has only the actions in its command table. Pane ids are percent-prefixed ASCII digits; identity keys are closed and their values are nonempty ASCII letters, digits, underscores, dashes or percent signs. Invalid decoded commands are refused. Tmux signal status takes precedence as 128 plus a positive signal; psmux uses only its spec status file. Missing or negative status is unavailable rather than success. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-59 | The native filesystem ABI snapshots at most 32 MiB from an opened regular file. POSIX observes owner and permission bits through descriptors, without following a final symlink. Windows observes owner SID and DACL: current-user, LocalSystem and builtin-Administrators allow entries are private; other effective allow entries, a null DACL, unsupported ACE forms and reparse points are refused. Its privacy result maps to 0600/0700 for the common pure policy; this is a permission model, never a claim of POSIX ownership on Windows. Haskell remains unconditional and C selects only the native API bindings, compiling with warnings as errors. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-60 | Preflight resolution traverses PATH directories in order and, on Windows, PATHEXT entries in order with case-insensitive filename matching. The first executable match decides: `.exe` qualifies and another extension requires the native installer, without falling through to a later candidate. Relative PATH entries are joined to an absolute caller directory; POSIX matches case-sensitively. Preflight warning hints use `agentctl: install it with: ` followed by the agent table or multiplexer remedy. The independent cases are chosen from the launch contract and tool facts, without claiming historical protection for uncommitted data. | `decision:planner` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| D-61 | A dead tmux pane without a published status requests a non-terminating SIGCHLD notification through AgentCtl.Process. The runner obtains the positive server pid from the checked backend's live session formats; callers never supply a pid. This addresses missing notifications consistent with libutempter's temporary handler replacement during terminal accounting. The original status and deadline remain mandatory, and psmux continues using its status file. | `tool:` libutempter temporarily restores the default SIGCHLD handler; a private-server trace and notification probe confirm the lost exit-3 status becomes available after reaping | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-62 | The public transport preserves each command tail before command parsing. The handoff uses execve on Linux and Darwin, and an inherited-stream child on Windows whose status becomes the public command status. Global consent remains outside the raw tail. | `decision:planner` | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| D-63 | Extends D-09 with `@agentctl_status`, the launch trampoline's private status-file path encoded as unpadded base64url UTF-8. Session queries use that file for a retained dead psmux pane rather than assuming a POSIX status variable. The typed identity key is `status-file`; the previously rejected `status` key stays invalid. Shared identity codecs belong to `AgentCtl.Session.Identity`. List and status print tab-separated rows whose folder column is a JSON string, preserving arbitrary path characters without splitting a row. | `decision:planner` | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| D-64 | Adoption stores only socket, pane, pid and agent in the private `<state>/adopted.json` registry. Its tmux endpoint is the reported socket string; its psmux endpoint is a JSON array of the backend tag, reported namespace string and stable session id. Revalidation compares that endpoint, pane and pid before using an entry. Session and command hints are displayed but never prove identity. State preparation verifies application-directory ownership and refuses a final link before making it private; the existing strict private-directory predicate is unchanged. An exclusive Windows state-root handle confines ACL tightening to that root. | `decision:planner` | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| D-65 | Screen normalization converts CRLF and bare CR to LF, strips trailing spaces and tabs, removes trailing blank lines and retains the final 100 lines without a trailing newline. Typed error blocks retain surrounding text separately; their fingerprint is lowercase hexadecimal SHA-256 over normalized UTF-8 error content alone. The evaluator exposes these pure kernels as screen-normalise and error-fingerprint. | `decision:planner` | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| D-66 | Composer suggestions require visual evidence. Capture records stable cursor coordinates and viewport dimensions before and after plain joined text and an unjoined ANSI-styled viewport. A nonempty composer becomes logically empty only when its prompt, start cursor and explicit faint suggestion style agree; plain or ambiguous nonempty text stays PartialInput. Capture retries changing cursor snapshots within its existing deadline. | `decision:planner` | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| D-67 | Screen expectations are fixture-directory class names, with sibling TOML provenance and explicit overload baselines for precedence twins. Documented examples retain an official HTTPS source and a note that they are illustrative, while captured records require a version and exact command. Per-agent marker tables share conservative precedence and latest-line selection; an explicit agent dispatcher selects the status classifier. The private live terminal excludes NO_COLOR for that invocation to observe faint hints, without changing stored agent settings or authentication. | `decision:planner` | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| D-68 | The recovery machine carries generic ordered fingerprint identities so native fingerprints and independent oracle aliases use one kernel. Attempts use arbitrary-precision integers. The seeded generator advances a Word64 by multiplication with 6364136223846793005 and addition of 1442695040888963407; its high 53 bits supply the jitter fraction. Backoff policies require finite positive initial delay, multiplier greater than one, maximum at least initial and jitter in [0, 1). Both the exponential base and final jittered delay are capped. | `decision:planner` | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| D-69 | A scheduled wait carries its retry record, including notification eligibility. An explicit confirmation notification and the wait may name the same record; the pure notification projection returns that notice once per decision. A fresh overload in VERIFY schedules the next attempt with the wait action the transition oracle requires, and its policy-eligible notice remains present. The evaluator exposes actual control-action labels, while deadline controls also inspect the resulting notices. | `decision:planner` | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| D-70 | Watch intent carries a monotonic registry revision and a revision on each entry. Effective changes advance both, so a pause and resume between polls still require a new baseline without resetting unrelated targets. Watch and resume require a current managed or adopted target; pause and unwatch may disable an existing stale entry. Repeats preserve revisions, watching an already paused entry preserves its pause, and an absent unwatch is a harmless notice. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-71 | Supervisor and watch locks use native open handles, POSIX flock or Windows LockFileEx, on private owned regular files in a private locks directory. Files are retained and never renamed or unlinked while locking; PID publication updates the locked inode. A leading newline reserves byte zero for the Windows lock, leaving the following PID readable by a contender. Supervisor contention refuses immediately; watch updates wait at most five seconds and reload intent inside the lock. Stop handlers set a flag and restore prior handlers on scope exit; POSIX accepts SIGINT/SIGTERM, Windows also accepts console Ctrl+C/Ctrl+Break. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-72 | The send guard compares overload class, a present equal fingerprint and text normalised by AgentCtl.Observe.Normalize, the same function used for plain native captures. Line-ending and trailing-space redraws can compare equal; escape bytes inside plain text remain content and require refusal. This tightens the initial illustrative ANSI guard row before the guard implementation; styled viewport evidence remains separate from plain capture text. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-73 | Per-target supervisor memory retains handled fingerprints for the process lifetime, including across pause, unwatch and rewatch. Dropping an open incident marks its fingerprint handled and records ended, without claiming recovery. A changed watch revision establishes a baseline and handles its visible error; a paused or absent entry requests neither capture nor machine step. The interpreter commits a planned recovery-sent state only after delivery; a changed guard is stepped from the prior state instead. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-74 | Log records contain the five common fields and the exact fields of their kind; observations contain class, fingerprint and machine state, never captured text. Decision states and actions describe the proposed pure step, and an attempt outcome records whether its conditional send happened. A stale watch entry whose agent cannot be resolved at startup emits only a disappearance notification with agent unknown; it cannot authorize observation or input. Known targets retain their agent identity through closure. The JSONL reader accepts only a complete valid prefix while a writer holds the supervisor lock; an unterminated tail after the writer exits is corruption, not a record to ignore. Selection compares the complete target name and returns a non-zero result with the target-specific no-records message when empty. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-75 | Each target gets at most one guard/send offer in a poll. Delivery commits the proposed recovery-sent state only on sent. An aborted guard steps its actual fresh observation from the prior memory; if that step proposes another send, its proposal is logged and delivery waits until the next poll, preserving the prior unhandled state. An identity change without a safe fresh capture ends and handles the old incident and resets the baseline revision. A failed command handles the incident, enters escalation and records unresolved with a notification; it cannot retry a possibly partial input. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-76 | Native stop acceptance sends SIGINT and SIGTERM to an owned supervisor on POSIX. Windows uses a second private multiplexer console and a test-only native fixture: Ctrl+C reaches its same-console child, and Ctrl+Break reaches its child's process group after checking the supervisor-lock PID belongs to that console. Each test requires the actual child to exit before cleanup, then verifies lock reuse and unchanged managed and adopted pane identities. Linux does not supply Windows console evidence; native Windows acceptance runs the same automatic tests. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-77 | The supervisor releases the watch lock and yields twenty milliseconds between protected polling sections. Watch commands retry contention every ten milliseconds within their five-second bound, so polling offers waiting commands a turn even when native work exceeds the requested poll interval. Guard and send remain in one protected section; a successful pause cannot be followed by its old pending send. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-78 | Scripted delivery acceptance uses the compiled fake multiplexer relay as a boundary observer. After a real flushed send decision it can hold the selected guard capture while an independently rendered pane changes, or refuse the selected literal command before forwarding it. It forwards genuine native captures and all other commands unchanged, publishes nonce-bound generations, and bounds every hold. This test-only capability supplies no screen output and adds no production supervisor option or hook. | `decision:planner` | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| D-79 | Amends the execution budgets in D-33 and D-56: each complete Python tool leg has a two-hour resource budget, and the enclosing gate reserves eight complete leg budgets for bootstrap and the full pipeline. Individual native and process deadlines, complete collection, assertions, coverage and named mutation-kill criteria remain mandatory. A resource bound accommodates the complete constructive suite; it does not remove or relax a validation criterion. | `decision:planner` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| D-80 | The closing agent launches the clean recipe's Stage B with Docker's `--init` option, providing automatic reaping of orphaned native children. The image command is plain `agentctl check`, and tests require every owned observer PID to disappear after teardown. Container execution supplies the same init responsibility as a native host. | `decision:planner` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| D-81 | Amends the version grammar in D-57: native psmux `-V` also emits a tmux compatibility banner followed by the psmux version line. Both lines must name the same three-component release, and the psmux floor still applies. A tmux-only alias, inconsistent banner or extra output does not establish a psmux capability. Independent rows preserve the observed release output and its negative controls. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-82 | Amends the remain-on-exit command in D-58: its typed value carries the validated session and pane. Native psmux pane-option routing needs the exact session-qualified target, while tmux retains its pane-id target. Enabling and unsetting remain-on-exit use the same checked identity. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-83 | A successful psmux create command leaves its per-session server alive after the client exits. Its client runs outside a process-tree job, while bounded queries, authentication probes and direct process controls retain tree ownership. This lifetime rule belongs to the typed command, not to an environment flag or host-test branch. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-84 | Amends the session-option target grammar in D-58: both native backends use the exact session component `=NAME:` when setting or listing managed session options. Psmux bare option listings without the colon select a different scope; session values may be quoted, and identity readers compare the exact decoded names and values. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-85 | Amends pane identity in D-58: psmux allocates pane ids per session. Native Windows targets therefore retain the exact session component as `=SESSION:.%id`, including session-table and adoption identifiers; tmux retains its global pane ids. A bare Windows pane id resolves only when exactly one eligible session contains it; ambiguity refuses without taking ownership or sending input. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-86 | The compiled client relay waits only for the forwarded client, preserving the genuine backend server's lifetime. The Windows trampoline waits for its direct program child; detached sessions created from inside a pane do not extend that wait. Bounded queries retain process-tree ownership. Native Windows observer input is polled for readiness so cancellation and stop-file completion require no additional terminal input. | `decision:planner` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| D-87 | Internal Python tool processes use UTF-8 mode and UTF-8 standard streams on every host. Gate-owned argv and environment paths use forward-slash spelling, preserving the portable command grammar independently of the native path separator. | `decision:planner` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| D-88 | The gate preserves the published `CODEX_SQLITE_HOME` runtime location alongside `CODEX_HOME`. A native client can retain its existing configuration and authentication while placing SQLite state on a native filesystem. Unknown Codex-prefixed environment controls remain excluded, and isolated probes retain their private location allowlist. | `decision:planner` | [Phase 0 ? Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |

## Design Justification

### The permanent pipx click app and a thin Python layer

`agentctl` is installed once with `pipx install` and stays installed: it is the only command the user
runs, the click application the request names (R2), and every command except `check` passes through
it, raw, to the core binary (R6). Python does only what must happen before a binary exists, plus what
the request assigns it: it decides the per-user dirs, provisions the OS prerequisites (with consent),
ghcup, GHC and cabal, builds the bundled binary when its digest is absent, and runs `check`. It
implements no launch, session or supervisor behaviour. Otherwise two layers implement one contract
and drift apart, and "the user shouldn't need to call the haskell binary directly" holds only by
convention. The concept note's `pipx run` leaves no permanent wrapper, so after it there is no
`agentctl` to pass anything through.

### A Haskell core

The request gives everything after bootstrap to the Haskell binary, and that work is decisions with
safety consequences: argv assembly, preflight, screen classification, recovery transitions and the
send discipline. Haskell expresses them as pure functions over closed types, so an unhandled screen
class or recovery state is a compile error rather than a runtime surprise. `Ready` is opaque: only a
passing preflight constructs it, so a launch that skips preflight does not compile, and a compile-fail
fixture matched by GHC diagnostic code, paired with a compiling twin, keeps it that way. Every spawn
goes through one runner, `AgentCtl.Process`, the only importer of `System.Process`. Otherwise "no
session is created when a check fails" rests on every caller remembering to check.

### The pane trampoline

The pane runs `agentctl-core pane-exec <spec>`, never the agent's own argv. tmux format-expands `-s`
and `-c` values (`#(…)` runs a shell command), ends a command at any argv element with a trailing
`;`, and gives a pane the environment its server started with, not the caller's. Putting the agent's
argv on tmux's command line hands user text to that parser; adding the caller's environment with `-e`
puts every secret on the tmux client's command line; and without `-e` the pane gets the server's
start-time environment, so preflight and the agent can see different config dirs. The spec file carries argv, cwd and the caller's environment out of band: it is
0600 in a 0700 dir under `state`, and the trampoline deletes it after reading. On POSIX the trampoline
calls `execve`, so `#{pane_pid}` is the agent and a live test can read its argv from `/proc`. On
Windows it runs the agent as a child and writes a status file, because psmux reports
`#{pane_dead_status}` as 0 always and instant-exit capture needs the agent's real exit status.

### Exit-code-only auth checks, and dialogs left to the user

`claude auth status` and `codex login status` exit 0 when logged in and 1 when not, while their output
differs: claude prints JSON by default, and codex writes only to stderr, in wording that changes
between versions. Preflight therefore reads exit codes only, and treats any other exit, or a timeout,
as `check failed` with its own warning, so a usage error or a hung probe never tells a logged-in user
to log in again. The remedy is a command the user types, such as `claude auth login` or `codex login`;
agentctl never runs one. The bypass-permissions warning and the workspace-trust dialog are the user's
consent: accepting the warning writes `skipDangerousModePermissionPrompt` into the user's settings,
and accepting trust records it in `~/.claude.json`. agentctl or a test that answered them would give
that consent on the user's behalf, so the classifier recognises `TrustDialog` and `BypassWarning`, the
supervisor never sends while one is showing, and live tests accept either as a live agent.

### ghcup reuse, a pinned download and never `--set`

An existing ghcup at or above 0.1.50.2 is reused as it is, because replacing or upgrading it changes a
tool the user owns, and 0.1.50.2 is a version the real tests exercise. With no ghcup present, agentctl
downloads the pinned 0.2.6.2 binary with urllib and checks the SHA-256 published beside it; a mismatch
installs nothing. The official bootstrap script verifies no checksum, edits shell rc files whenever
`BOOTSTRAP_HASKELL_ADJUST_BASHRC` is non-empty (`0` included), and outside minimal mode runs
`ghcup set ghc`. `ghcup install cabal` changes the user's default cabal unless `--no-set` is passed, so
GHC is installed with `ghcup install ghc 9.12.4` and cabal with `--no-set`, and both are invoked by
the absolute paths `ghcup whereis` prints. Warm runs check those paths with `--numeric-version` and do
not call ghcup at all. Otherwise the `ghc` and `cabal` the user runs from PATH silently change version.

### The Cabal project as package data, and the digest-keyed cache

The Cabal project lives at `src/agentctl/haskell/`, inside the Python package, so ordinary hatchling
selection ships it in the wheel and sdist, and an editable install sees every edit. hatchling
`force-include` would copy a snapshot into editable wheels, so check would build stale sources, and
its directory walk ignores `.gitignore`, so it would ship `dist-newstyle/`. The binary is built into
`cache/build/<digest>`, where the digest covers the bundled sources and the pins, and is published
atomically into `data/bin/<digest>`. A digest hit skips the build, and any source or pin change
produces a new path. Nothing is ever overwritten, so a stale binary never runs after an edit, a
running `.exe` never needs replacing on Windows, and no upgrade-rollback machinery exists. The
handshake carries only the protocol version and the command list; binary identity is the sha256 of the
`cabal list-bin` output, so check knows the binary it tests is the one cabal built from this tree.

### The editable-install identity check

`agentctl check` refuses to run unless the running distribution's PEP 610 `direct_url.json` says
editable, its url is the checkout root, and `agentctl.__file__` is under `<root>/src/agentctl`
(precondition P1). Otherwise an older or non-editable install runs its own code against this tree's
tests and can pass, which is the stale-install trap hostbootstrap § G documents. Any PEP 610 editable
installer qualifies, `pipx install --editable '.[dev]'` or `uv tool install --editable '.[dev]'`, and
the dev tools are the `dev` extra because pipx has no dependency-group support.

### Sessions on the user's normal tmux server

Sessions live on the user's default tmux server, so `tmux ls`, the user's key bindings and the status
line all see them, and a launch from inside the user's tmux is a `switch-client` on that same server.
A private socket hides sessions from `tmux ls` and turns every attach from inside the user's tmux into
tmux nested inside tmux. The server's start-time environment does not matter, because the trampoline
carries the caller's. Tests never touch this server: they run tmux on a private server under
`TMUX_TMPDIR` with `TMUX` unset, kill that server only after asserting its socket is under the run
dir, and the containment step scans the user's server for the run's nonce.

### Verbatim passthrough, instant-exit capture and login refusals

ARGS reach the agent verbatim. The only edits are mechanical: user copies of the mandatory flags, and
codex's `--yolo`, are removed because codex exits 2 on a repeated flag, and the flags go last, or just
before the first bare `--`, because both CLIs read what follows `--` as positional. A subcommand
allow/deny table would have to follow every CLI release (claude's native install updates itself in
the background), would break check whenever a CLI changes, and would refuse invocations the agent
accepts. When the agent itself rejects its argv, as `claude auth status --dangerously-skip-permissions`
does with "unknown option", instant-exit capture shows the user the agent's own message: remain-on-exit
holds the pane during a startup window, the output is relayed to the user's terminal, the session is
closed, and agentctl exits with the agent's status. Without it, tmux reports success for a pane whose
command exits at once, and the session simply vanishes. The one table is the login refusal: claude
`auth login…`, `setup-token` and any `/login` token, and codex `login…`, are refused before a session
exists, because passing them through would make agentctl run a login (R13).

### No supervisor config file

`supervisor run` takes timing flags whose defaults are the concept note's values, and the recovery text
is a per-agent constant. A config file is a second input surface with its own schema, validation and
trust rule for project-local copies, and no requirement asks for one: the user replaced configuration
with passthrough. A configurable recovery text is also exactly the path by which `/model` or `/login`
text would reach `send-keys` (R19). The supervisor runs in the foreground and nothing auto-starts it,
so it never outlives the user's intent.

### Lanes and host-acceptance phases

Every phase declares one lane from the closed table in
[§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes). Self-verifying phases,
on the `any-host`, `mux-host` and `agent-host` lanes, are re-proved by every check run, and check fails
when the lane of a Done phase is unmet on the host, so a host missing tmux or an agent cannot pass by
skipping. Tests adapt only to login state, multiplexer kind, OS family and toolchain provenance, and
tool absence is tested with constructed PATHs. What no self-verifying run can produce on demand (a
logged-in agent, a pristine host, macOS, Windows with psmux) is `owed` to exactly one of four
host-acceptance phases, each closed by an EVIDENCE line whose tree digest the validator recomputes.
Otherwise a degraded host passes the gate, and a live confirmation that no phase owns is claimed by
implication.

### The ratchet and automatic closure

Oracle, mutant and requirement rows only grow against HEAD, and tool config only tightens. Agents
never commit, so the gate never moves that baseline. An existing HEAD protects only the rows and
configuration it contains; an unborn repository has no historical baseline. An oracle absent from HEAD
could be edited together with its subject before a run, and an evidence row proves its tree is current,
not that a run happened. Independent provenance, two-sided controls, mutants and run-integrity guards
provide executable evidence within that ceiling. D-49 supersedes the human commit checkpoints of D-47:
commits and reviews are optional, and neither is needed to close a gate or proceed to product work.
[§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure) owns the rule. Native hosts and
existing authentication remain automatically observed lane capabilities, never manual attestations.

### No CI and no distribution phase

Agents never push, so CI could judge a change only after the user pushes it, and a workflow file would
be a second definition of the gate that drifts from `agentctl check`. The gate of record is `agentctl check`, run
by an agent on the declared host. The concept note's distribution milestone is dropped: a tag install
needs a release only the user can make, and upgrade rollback and running-`.exe` replacement never
arise, because the digest-keyed cache writes a new path for every build. Removing agentctl is
`pipx uninstall agentctl` plus deleting its per-user dirs, as
[installation.md](../documents/operations/installation.md) documents.

## Rejected Alternatives

- The ephemeral `pipx run` installer and a Python-free runtime — every command passes through the
  click app (R2, R6), so it must stay installed; after a `pipx run` there is no `agentctl` left to
  pass through, and the user would have to call the binary directly.
- A binary installed into a user bin directory on PATH — it is a second command surface the user calls
  directly (R6), bypassing the digest check that keeps the binary matched to its sources; the binary
  stays in `data/bin/<digest>` and refuses direct invocation without the handoff protocol.
- TOML profiles and project config — passthrough ARGS replace profiles (answer 2) and the folder
  supplies the working directory and session name (answer 1); a project-local file would also let a
  cloned repository change what agentctl launches, which is why the concept note needed a trust rule
  for it.
- A `start` command with `--name`, `--cwd` or `--profile`, and a detach command — the folder supplies
  the name and working directory and ARGS pass verbatim, so the flags have nothing left to carry, and
  the multiplexer's own key binding already detaches.
- The official ghcup bootstrap script — it verifies no checksum, edits shell rc files whenever
  `BOOTSTRAP_HASKELL_ADJUST_BASHRC` is non-empty (`0` included), and outside minimal mode runs
  `ghcup set ghc`; agentctl downloads the pinned binary and checks its published SHA-256 itself.
- `ghcup --set` and `ghcup run` — `--set` changes the `ghc` the user runs from PATH, and
  `ghcup install cabal` does the same for cabal unless `--no-set` is passed; `ghcup run` leaves a bin
  dir behind under ghcup's tmp dir and on Windows reports a child's failure as its own exit code 28.
  Absolute `ghcup whereis` paths need neither.
- GPG verification of ghcup downloads — gpg would be a second host dependency (R1), and the pinned
  SHA-256 already refuses any other bytes.
- An on-disk registry for managed sessions — it lists ghosts when a session ends outside agentctl and
  drifts from the server after a restart; tmux session options (`@agentctl_*`) live and die with their
  session, so only adopted panes, which agentctl does not own, have a registry.
- A dedicated tmux socket — its sessions are invisible to `tmux ls` and to the user's bindings, and
  attaching from inside the user's tmux nests one tmux inside another; on the user's server the same
  move is a `switch-client`.
- Passing env with `tmux -e` — every value, secrets included, sits on the tmux client's command line
  where other processes can read it, and leaving it out gives the pane the environment its server
  started with; the trampoline's 0600 spec file carries the caller's environment instead.
- Subcommand allow/deny tables — they must follow every CLI release, so they break `agentctl check`
  whenever a CLI changes and refuse invocations the agent accepts; instant-exit capture relays the
  agent's own rejection, and only the login refusals (R13) form a table.
- A supervisor config file — no requirement asks for one, the user replaced configuration with
  passthrough, and a configurable recovery text is the channel through which `/model` or `/login` text
  would reach `send-keys` (R19).
- OS service integration, supervisor reconnection, external alerts and lifecycle hooks — no
  requirement asks for them; `supervisor run` runs in the foreground, nothing auto-starts it, and its
  notifications go to its stderr and the JSONL log.
- A CPP-embedded digest handshake — a digest the binary reports about itself is a subject self-report,
  which never counts as evidence; the digest-keyed path and the sha256 of the `cabal list-bin` output
  identify the binary independently, and the handshake carries only the protocol version and the
  command list.
- Fake executables or mocks offered as evidence of real CLI behaviour — the fake agent proves only what
  agentctl sent (`observer`), and a mock proves only the mock; real behaviour comes from logged-out
  real CLIs, `--help` canaries with a negative control, and the `owed` live confirmations.
- Tests that adapt to tool absence or to being offline — a host without tmux, an agent or the network
  would then pass the gate by taking the "absent" branch; tool absence is tested with constructed
  PATHs, and lanes are preconditions that check enforces.
- Hand-typed counts and dated closure narratives — they drift from the tree and nothing re-checks
  them; status derives from what exists, and the lane summary prints the only evidence line.
- CI workflows — agents never push, so a workflow judges a change only after the user pushes it, and
  it is a second definition of the gate drifting from `agentctl check`; `tree.forbidden-surfaces`
  refuses `.github/workflows`.
- A distribution/uninstall phase — a tag install needs a release only the user can make, and upgrade
  rollback and running-`.exe` replacement never arise because the digest-keyed cache never overwrites
  a binary; removal is `pipx uninstall agentctl` plus agentctl's per-user dirs, as
  [installation.md](../documents/operations/installation.md) documents.
- Installer flags (`--upgrade`, `--uninstall`, `--install-ghcup`, `--dry-run`, `--verbose`) — upgrade
  is a pipx reinstall, provisioning is automatic and idempotent, and consent for privileged steps is
  `--assume-yes`.
- uv or poetry as host dependencies — R1 allows pipx only; agentctl requires neither, and
  `uv tool install --editable` is accepted only as an alternative editable installer for `check` (P1).
- MSYS2 bootstrap on Windows — the official PowerShell bootstrap installs MSYS2, sets user-scope
  environment variables, appends to the user PATH and creates desktop shortcuts; agentctl downloads
  the pinned `x86_64-mingw64-ghcup-0.2.6.2.exe` instead, and MSYS2 serves only Haskell packages that
  ship configure scripts.

## Concept-Note Disposition

`agentctl-plan.md` is the concept note this plan replaces. Each row maps one part of it: Concept
section is the note's heading, Excerpt a verbatim fragment, Disposition one of adopted, adapted,
rejected or deferred-to-phase, and Destination the file that owns the item in this plan. The note is not part
of the governed tree, so this table is the record of where every item went. Its completeness is
checked once, before the note is deleted, and no phase can re-check it afterwards
([Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md)).

| ID | Concept section | Excerpt | Disposition | Destination | Reason |
|---|---|---|---|---|---|
| CN-01 | Executive decision | "Build a native Haskell CLI to manage Codex and Claude Code in tmux (macOS/Linux) and psmux (Windows), with a separate recovery supervisor." | adopted | [00-overview.md](00-overview.md#architecture) | The request keeps the Haskell core for everything after bootstrap, and answer 2 keeps the supervisor as its own foreground command. |
| CN-02 | Executive decision | "provisions GHCup/GHC/Cabal as needed, compiles the Haskell program locally, and installs it in a user-owned directory" | adapted | [python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) | Python provisions ghcup, GHC and cabal (R3, R4) and builds the bundled sources host-native into per-user dirs it decides (R5); only sources ship, and the published binary is never on PATH (R6). |
| CN-03 | Executive decision | "Python is not needed to run the resulting executable." | rejected | [Rejected Alternatives](#rejected-alternatives) | The click app is the permanent interface that every command passes through (R2, R6), so it is installed with `pipx install`, not run once through `pipx run`. |
| CN-04 | Executive decision | "cannot literally guarantee ghcup is the only host dependency" | adapted | [00-overview.md](00-overview.md#requirements) | R1 reads the request's "pipx is the only host dependency" as the build chain needing only pipx and its Python (D-05); a git-based install spec needs git, while a local tree needs none. |
| CN-05 | Product scope | "Start Codex or Claude with named profiles, preferred CLI arguments, working directories, and project defaults." | adapted | [launch_contract.md](../documents/architecture/launch_contract.md) | `agentctl claude` and `agentctl codex` start the agent in the invoking folder with the user's ARGS verbatim (R7, R9); named profiles and project defaults give way to passthrough (answer 2). |
| CN-06 | Product scope | "List, attach, detach, and stop sessions; adopt pre-existing panes without taking ownership." | adapted | [sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | list, attach, stop and status (R16) and adopt (R17.1) all work with no supervisor running, as the bullet "Keep session management usable when the supervisor is not running." asks; detaching stays the multiplexer's own key binding. |
| CN-07 | Product scope | "Supervise capacity/overload failures without changing the selected model." | adopted | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | R18 and R19; the status, logs, pause, unwatch and backoff bullet becomes status (R16), R18.5, R18.6 and R18.4. |
| CN-08 | Product scope | "Work with tmux on macOS/Linux and psmux on native Windows." | adopted | [multiplexer_adapter.md](../documents/architecture/multiplexer_adapter.md) | R7 and R12.1, with the floors tmux 3.2 and psmux 3.4.0; real psmux is confirmed by [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md). |
| CN-09 | Proposed CLI | "agentctl start codex --name auth-refactor --cwd ~/src/api" | adapted | [launch_contract.md](../documents/architecture/launch_contract.md) | `start` becomes `agentctl codex` or `agentctl claude` run from the folder, which supplies the working directory and the mandatory name (answer 1, R8); `--profile opus -- --verbose` becomes plain passthrough (R9), and `start api` has no project table to read. |
| CN-10 | Proposed CLI | "`resume-watch` means resume supervision, not resume the agent's goal." | adopted | [cli_reference.md](../documents/reference/cli_reference.md) | list, status, attach, adopt, watch, unwatch, pause, resume-watch, logs, stop and supervisor run keep their names, sessions are addressed by their folder-derived names, and each command is documented as the contract its owning phase builds. |
| CN-11 | Architecture | "CLI → configuration / session registry → tmux-compatible backend → Codex/Claude" | adapted | [00-overview.md](00-overview.md#architecture) | There is no configuration layer, managed identity lives in tmux session options rather than a registry, and each pane runs the trampoline, which becomes the agent. |
| CN-12 | Architecture | "a session may be managed, supervised, and human-attached independently" | adopted | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | R17: unwatching or stopping the supervisor never kills a session; R17.1: an adopted pane is never owned. |
| CN-13 | Architecture | "Suggested Haskell modules:" | adapted | [system-components.md](system-components.md) | The Cabal project is package data at `src/agentctl/haskell/` with `agentctl-core.cabal`, its `AgentCtl.*` modules follow the phases with no `Config` module, and `cabal.project` pins `index-state` in place of a committed freeze file. |
| CN-14 | Architecture | "Prefer pure classification and transition functions, typed algebraic states/errors, and effects at the boundaries." | adopted | [code_standards.md](../documents/engineering/code_standards.md) | Pure kernels carry the `value` evidence and `AgentCtl.Process` is the one runner; the suggested libraries are fixed by the pinned toolchain and `index-state`, and no TOML parser is needed because agentctl reads no configuration file. |
| CN-15 | Architecture | "Start with atomic on-disk metadata and a supervisor lock; use SQLite only if concurrent access justifies it." | adopted | [files_and_state.md](../documents/reference/files_and_state.md) | The `state` dir holds atomic files: launch specs, the adopted registry, the watch set, the JSONL log and locks; nothing needs SQLite. |
| CN-16 | Terminal compatibility | "tmux capture-pane -p -t %3 -S -100" | adopted | [multiplexer_adapter.md](../documents/architecture/multiplexer_adapter.md) | The typed command vocabulary covers pane listing, capture and literal `send-keys -l`, decodes output as explicit UTF-8, and is proven on a private tmux server; direct argv execution, the note's "Prefer direct argv execution over shell concatenation where supported.", is the pane trampoline, which keeps the agent's argv off the multiplexer's command line entirely. |
| CN-17 | Terminal compatibility | "Test session creation, argv handling, Unicode/ANSI output, pane IDs, input safety, and command availability on actual Windows psmux versions." | deferred-to-phase | [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md) | Real psmux needs a Windows host; psmux command rendering is tested as values on every host. |
| CN-18 | Terminal compatibility | "Treat `pane_current_command` as a hint, not proof of process identity." | adopted | [sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | adopt identifies a pane by more than its command name, and pane ids are re-checked against the live server, as "Revalidate pane IDs after server restarts." asks. |
| CN-19 | Configuration | "[profiles.codex]" | rejected | [Rejected Alternatives](#rejected-alternatives) | The `[defaults]`, `[profiles.*]` and `[projects.*]` tables give way to passthrough ARGS (answer 2); with no project-local configuration, "Require trust before executing project-local configuration from untrusted repositories." has nothing to guard. |
| CN-20 | Configuration | "Allow agent-specific recovery commands, configured per profile and tested against installed CLI versions." | adapted | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | The recovery text is a per-agent constant, the `[recovery]` values become the defaults of the `supervisor run` timing flags (D-39), and no single text such as `continue` is assumed right for both agents. |
| CN-21 | Supervisor safety contract | "MONITORING → SUSPECTED_FAILURE → CONFIRM_IDLE → BACKOFF → RECOVERY_SENT → VERIFY → MONITORING/ESCALATE" | adopted | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) | The pure transition function encodes rules 1 to 4 and 6: a fresh error plus an input-ready prompt, no send during work, dialogs or partial input (R18.2), fingerprint gating (R18.3), a changed screen as the only acknowledgement, and bounded backoff with jitter (R18.4); R18 closes in [Phase 10 — Recovery supervisor](phase-10-supervisor.md). |
| CN-22 | Supervisor safety contract | "Distinguish transient overload from usage limits, authentication errors, context exhaustion, and crashes." | adopted | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) | R18.1, over screen fixtures with provenance; a class backed only by `documented` fixtures is listed as not proven. |
| CN-23 | Supervisor safety contract | "Log each observation, decision, attempt, and result. Support manual pause and opt-out." | adopted | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) | R18.5 and R18.6; rule 8, "Never automatically switch models or restart arbitrary crashed processes.", is R19, closed in the same phase, and escalating notifications go to the supervisor's stderr and JSONL `notify` records. |
| CN-24 | Supervisor safety contract | "Encourage durable project checkpoints" | adopted | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | Stated as a limit of supervision: a recovery text cannot restore an interrupted tool call, so projects keep their own checkpoints. |
| CN-25 | Source-only distribution | "Source-only distribution" | adapted | [binary_build.md](../documents/engineering/binary_build.md) | The wheel and sdist carry the Cabal project as package data and the binary is compiled on the host; no binary is committed or published. |
| CN-26 | User-facing one-line install | "Example using a pinned GitHub tag (replace `USER`):" | rejected | [Rejected Alternatives](#rejected-alternatives) | `pipx run` leaves no permanent wrapper to pass commands through, so agentctl is a permanent `pipx install`, and the binary is never installed separately (R6). |
| CN-27 | User-facing one-line install | "For hosts without Git, test an installable GitHub source archive spec:" | adapted | [installation.md](../documents/operations/installation.md) | A `pipx install` of a local tree needs no git, and [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) runs one on a host without git; installs from an immutable tag, SHA or archive URL need a release the user publishes, and no phase proves them. |
| CN-28 | Installer steps | "Detect ghcup; if missing, provision it via a documented, authenticated platform-specific mechanism when explicitly allowed." | adapted | [toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | Steps 1, 3 and 4: host facts feed a pure provisioning plan; an existing ghcup at or above 0.1.50.2 is reused, otherwise the pinned 0.2.6.2 is downloaded and checked by SHA-256 by default, since it needs no privilege; privileged package-manager runs need consent (answer 4); `--no-set` and `ghcup whereis` paths keep the user's selection without `ghcup run`. |
| CN-29 | Installer steps | "Compile the **same pinned Haskell source revision** as the Python installer." | adopted | [binary_build.md](../documents/engineering/binary_build.md) | Steps 2, 5, 6, 7 and 9: the sources are package data, a digest hit is the verified matching install, and a build runs under a lock in `cache/build/<digest>` and is published atomically into `data/bin/<digest>` once the handshake answers; the digest in the path stands in for a manifest, and nothing is replaced, so a running `.exe` or agent is never disturbed, as "Updates should not restart active agents." asks. |
| CN-30 | Installer steps | "Install into a user-owned executable directory and report PATH requirements." | rejected | [Rejected Alternatives](#rejected-alternatives) | The binary is never on PATH, because `agentctl` is the only command the user runs (R6); the installer flags `--upgrade`, `--uninstall`, `--install-ghcup`, `--dry-run` and `--verbose` are rejected with it. |
| CN-31 | Installer steps | "Uninstall only files owned by agentctl; never remove shared GHCup toolchains, caches, project data, or tmux sessions." | adapted | [installation.md](../documents/operations/installation.md) | There is no uninstall command (D-46): the user runs `pipx uninstall agentctl` and removes agentctl's per-user dirs, leaving ghcup, GHC, cabal and every session alone. |
| CN-32 | Python installer engineering rules | "**Required:** `pyproject.toml`, `uv`, `ruff`, `ty`, strict typing" | adapted | [code_standards.md](../documents/engineering/code_standards.md) | Adopted with ruff `select = ["ALL"]`, ty `all = "error"` and `src.suppression-ban`, except `uv`, which is not a host dependency (R1); custom `.pyi` stubs exist only for a dependency without types, and click 8.5.0 ships its own; immutability, expressions and `Result` types are adopted. |
| CN-33 | Packaging and development | "Suggested layout:" | adapted | [system-components.md](system-components.md) | One package, `src/agentctl/`, holds the Cabal project, and `tests/` sits at the root; there is no `installer/` tree, no `uv.lock` and no `.github/workflows/ci.yml` (D-44). |
| CN-34 | Packaging and development | "Example `pyproject.toml` (validate configuration keys against pinned tool versions):" | adapted | [quality_gate.md](../documents/engineering/quality_gate.md) | The project is `agentctl`, needs Python at least 3.12 and declares the `dev` extra (D-28); tool configs are co-designed with the pinned tools in Sprint 0.2 and frozen by `tests/oracles/lint_config.toml`; ty uses `all = "error"` because it has no strict key; the uv commands become legs of `agentctl check`, and check, not CI, enforces zero suppressions. |
| CN-35 | Packaging and development | "explicitly include Haskell sources" | adapted | [binary_build.md](../documents/engineering/binary_build.md) | The Haskell sources are package data under `src/agentctl/haskell/`, so ordinary hatchling selection includes them and no force-include rule exists (D-23). |
| CN-36 | Packaging and development | "CI must test the *built source distribution*, not just imports from the checkout." | deferred-to-phase | [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) | Stage A installs a copied tree without `--editable`, so a built wheel, not the checkout, provisions the toolchain and builds the binary. |
| CN-37 | Strict typing | "Fully annotate public functions, returns, callbacks, and important interfaces." | adopted | [code_standards.md](../documents/engineering/code_standards.md) | All six bullets; ty with every rule an error and ignore comments disrespected, plus ruff `select = ["ALL"]`, enforce their mechanical part. |
| CN-38 | Functional style | "Prefer pure functions from immutable values to immutable values." | adopted | [code_standards.md](../documents/engineering/code_standards.md) | All six bullets; side effects live in I/O adapters, and `src/agentctl/process.py` is the only module that spawns. |
| CN-39 | Result types, not expected exceptions | "Use a small typed local result abstraction rather than adding a dependency" | adapted | [code_standards.md](../documents/engineering/code_standards.md) | `src/agentctl/result.py` holds `Ok` and `Err` in Python 3.12 type-parameter syntax, and each module declares its own error union; narrow catching at I/O boundaries and the CLI's conversion of a `Result` into an exit code are adopted. |
| CN-40 | Testing and quality gates | "Integration tests: mocked ghcup/Cabal subprocesses" | adapted | [testing.md](../documents/engineering/testing.md) | Pure tests become the `value` class; a mocked subject is never evidence, so integration tests use the real pinned tools in test-owned scopes, the spawn audit as observer, and constructed PATHs for missing tools; the security bullet becomes argv-injection rows through the whole stack and a wrong SHA-256 that installs nothing. |
| CN-41 | Testing and quality gates | "Packaging tests: build sdist/wheel; install using pipx/uv in a clean environment; verify bundled Haskell sources." | deferred-to-phase | [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) | Stage A's clean container installs with pipx alone and builds from the bundled sources. |
| CN-42 | Testing and quality gates | "Cross-platform CI: macOS, Linux, Windows" | adapted | [development_plan_standards.md](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes) | There is no CI: the same `agentctl check` runs on every lane, and macOS and Windows confirmations are owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md) and [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md). |
| CN-43 | Testing and quality gates | "Acceptance: running the installer twice preserves the same working binary" | adopted | [binary_build.md](../documents/engineering/binary_build.md) | A digest hit reuses the published binary and a failed build publishes nothing; "no global GHC selection changes" is R4, closed in [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md); no binary is ever committed. |
| CN-44 | Milestones | "**0.1 — Distribution and session management:**" | adapted | [00-overview.md](00-overview.md#phase-responsibilities) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) through [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) build it in dependency order, without profiles or a distribution phase; milestone 0.2, recovery, is [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) through [Phase 10 — Recovery supervisor](phase-10-supervisor.md). |
| CN-45 | Milestones | "**0.3 — Unattended reliability:**" | adapted | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) | Robust failure simulations become its scenario matrix, agent-version recognition the provenance on screen fixtures, and safe upgrades the digest-keyed cache; supervisor reconnection, external alerts and lifecycle hooks are [rejected](#rejected-alternatives). |
| CN-46 | Open decisions and validation checklist | "Choose the supported GHC/Cabal versions after compiling on all three platforms." | adapted | [toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | Settled in [Decisions](#decisions) as GHC 9.12.4 and cabal 3.16.1.0 (D-20), so no oracle waits on it; "Decide whether ghcup provisioning is opt-in or default" is settled as default, because the pinned download is SHA-256-verified and needs no privilege; compiling on macOS and Windows is owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md) and [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md). |
| CN-47 | Open decisions and validation checklist | "Confirm native Windows GHCup/MSYS2 prerequisites and psmux command compatibility." | deferred-to-phase | [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md) | The pinned `ghcup.exe` path, which needs no MSYS2 bootstrap, and real psmux are confirmed on a Windows host. |
| CN-48 | Open decisions and validation checklist | "Confirm pipx can install the selected GitHub archive packaging layout without Git." | deferred-to-phase | [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) | Stage A installs a local tree on a host without git, which also covers "Verify source packaging"; upgrade rollback and running-`.exe` replacement never arise with digest-keyed paths ([binary_build.md](../documents/engineering/binary_build.md)); an archive URL and immutable-release integrity need a published release, and no phase proves them. |
| CN-49 | Open decisions and validation checklist | "Determine reliable recovery commands and safe idle-state markers for actual Codex and Claude releases." | deferred-to-phase | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) | The agent table owns the literal recovery texts (D-48); [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) owns idle markers from screen fixtures with provenance. Live `IdlePrompt` classification counts only in a folder the user has trusted (D-37); that a recovery text resumes a real overload is proven by no phase. |
| CN-50 | Open decisions and validation checklist | "Decide on a supervisor start strategy: separate tmux/psmux session initially; optional OS service integration later." | adapted | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | Settled: `agentctl supervisor run` runs in the foreground wherever the user starts it, nothing auto-starts it, and OS service integration is rejected. |
| CN-51 | Open decisions and validation checklist | "**Definition of done:**" | adapted | [README.md](README.md#exit-definition) | The plan's exit is every phase Done; the install is a permanent `pipx install`, privileged provisioning happens only with consent, and Python stays at runtime as the interface (R6). |

## Related

- [00-overview.md](00-overview.md#requirements) — the requirements table whose quotes are substrings
  of the Originating Request.
- [development_plan_standards.md](development_plan_standards.md#k-requirement-anchoring) — § K anchors
  requirements on this file, and § P defines the automatic closure recorded in D-49.
- [README.md](README.md) — the status table, and the supersession of `agentctl-plan.md` that the
  disposition table completes.
- [system-components.md](system-components.md) — the inventory of the modules and tools these
  decisions shape.
- [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) — records unwanted shapes still
  standing, while this file explains shapes the design never builds.
- [external_tool_facts.md](../documents/reference/external_tool_facts.md) — the verified facts behind
  every `tool:` provenance.
