# Copyright (c) 2026 agentctl contributors.
"""Scripted native supervisor scenarios bind every outcome to actual target panes."""

import time
from pathlib import Path

import pytest

from tests.e2e.test_adopt import no_options, pane_facts
from tests.harness.launch import observe_mux, prepare
from tests.harness.sessions import rows
from tests.harness.supervisor import (
    StopKind,
    log_records,
    observe_polls,
    received_bytes,
    scripted_target,
    supervisor,
    wait_backoff,
    wait_observation,
    wait_received,
    wait_records,
    wait_transition,
)
from tests.harness.supervisor_barrier import (
    drive_guard,
    guarded_target,
    supervisor_barrier,
)
from tests.harness.supervisor_cases import (
    assert_all_decisions,
    assert_decisions,
    receiving_controls,
    require_receivers,
    scenario,
)
from tests.harness.supervisor_signals import signal_supervisor, wait_stopped
from tests.harness.tmux import PrivateMux


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("kind", ["interrupt", "terminate"])
def test_stop_supervisor_keeps_sessions(
    root: Path, mux_server: PrivateMux, kind: StopKind
) -> None:
    """Both native stop requests release the lock and preserve both ownership kinds."""
    expected = scenario(root, "stop-" + kind, "both")
    managed = [
        scripted_target(mux_server, root, agent, (("IdlePrompt", {"kind": "stay"}),))
        for agent in ("claude", "codex")
    ]
    case = managed[0].case
    foreign = [mux_server.actor("foreign-" + agent) for agent in ("claude", "codex")]
    targets = [target.target for target in managed]
    panes = [target.pane for target in managed]
    for actor, agent in zip(foreign, ("claude", "codex"), strict=True):
        record = actor.record()
        assert record["pane"] == actor.pane
        assert record["session"] == actor.session
        assert record["nonce"] == actor.nonce
        no_options(mux_server, actor.session)
        assert case.command("adopt", (actor.pane, "--agent", agent)).code == 0
        targets.append(actor.pane)
        panes.append(actor.pane)
    before = {pane: pane_facts(mux_server, pane) for pane in panes}
    for target in targets:
        assert case.command("watch", (target,)).code == 0
    previous_runs: set[str] = set()
    for _ in range(2):
        with signal_supervisor(case, kind) as running:
            assert running.alive()
            observed_runs: set[str] = set()
            for target in targets:
                observations = wait_records(running, target, "observation")
                observed_runs.update(str(row["run"]) for row in observations)
                assert all(row["run"] not in previous_runs for row in observations)
                assert {row["agent"] for row in observations} == {
                    "claude" if target in {targets[0], targets[2]} else "codex"
                }
            contender = case.command("supervisor", ("run",))
            assert contender.code != 0
            assert "by pid " in contender.stderr
            running.request_stop(kind)
            output = wait_stopped(running)
            assert output.code == expected["exit"], output
            previous_runs.update(observed_runs)
        assert {pane: pane_facts(mux_server, pane) for pane in panes} == before
        current = rows(case.command("list"))
        for target in targets:
            assert current[target]["STATE"] == "alive"
            assert current[target]["WATCHED"] == "yes"
        for actor in foreign:
            no_options(mux_server, actor.session)


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("agent", ["claude", "codex"])
@pytest.mark.parametrize("final", ["Working", "IdlePrompt", "Overloaded"])
def test_overload_backoff_recovery_verify(
    root: Path, mux_server: PrivateMux, agent: str, final: str
) -> None:
    """A single real delivery recovers only on changed work or an idle prompt."""
    expected = scenario(root, "recovery-" + final.lower(), agent)
    text = expected["received"]
    assert isinstance(text, str)
    recovery = text.encode("utf-8")
    trigger = mux_server.scope / "begin-overload"
    target = scripted_target(
        mux_server,
        root,
        agent,
        (
            ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
            ("Overloaded", {"kind": "input", "bytes": len(recovery)}),
            (final, {"kind": "stay"}),
        ),
    )
    assert target.case.command("watch", (target.target,)).code == 0
    with supervisor(target.case) as running:
        wait_observation(running, target.target, "IdlePrompt")
        trigger.touch()
        wait_received(target.case.records_directory, target.case.nonce, recovery)
        results = wait_records(running, target.target, "result")
        assert [record["outcome"] for record in results] == [expected["result"]]
        current = wait_records(running, target.target, "observation")
        wait_records(running, target.target, "observation", len(current) + 2)
        running.finish()
    records = log_records(target.case)
    attempts = [row for row in records if row["kind"] == "attempt"]
    assert [row["outcome"] for row in attempts] == expected["attempts"]
    assert received_bytes(target.case.records_directory, target.case.nonce) == recovery
    observations = [row for row in records if row["kind"] == "observation"]
    assert observations[-1]["state"] == expected["final_state"]
    assert_decisions(root, target)


@pytest.mark.evidence("observer")
@pytest.mark.parametrize(
    "category", ["UsageLimit", "AuthError", "ContextExhausted", "Exited", "LoginScreen"]
)
def test_terminal_classes_escalate_without_send(
    root: Path, mux_server: PrivateMux, category: str
) -> None:
    """Terminal classes reach both notification sinks without typing into an agent."""
    trigger = mux_server.scope / "terminal-screen"
    targets = [
        scripted_target(
            mux_server,
            root,
            agent,
            (
                ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
                (category, {"kind": "stay"}),
            ),
        )
        for agent in ("claude", "codex")
    ]
    controls = receiving_controls(root, mux_server, trigger)
    case = targets[0].case
    for target in (*targets, *controls):
        assert case.command("watch", (target.target,)).code == 0
        if category == "Exited" and target in targets:
            retained = mux_server.raw(
                "set-option", "-p", "-t", target.pane, "remain-on-exit", "on"
            )
            assert retained.code == 0, retained
    with supervisor(case) as running:
        for target in (*targets, *controls):
            wait_observation(running, target.target, "IdlePrompt")
        trigger.touch()
        if category == "Exited":
            for target in targets:
                (target.case.records_directory / "stop").touch()
        for target in targets:
            expected = scenario(root, "terminal-" + category.lower(), target.case.agent)
            wait_observation(running, target.target, category)
            notice = wait_records(running, target.target, "notify")[0]
            assert notice["level"] == expected["level"]
            assert notice["message"] == expected["message"]
            results = wait_records(running, target.target, "result")
            assert [row["outcome"] for row in results] == [expected["result"]]
        require_receivers(root, controls)
        output = running.finish()
    for target in targets:
        expected = scenario(root, "terminal-" + category.lower(), target.case.agent)
        text = expected["received"]
        assert isinstance(text, str)
        assert received_bytes(
            target.case.records_directory, target.case.nonce
        ) == text.encode("utf-8")
        assert f"agentctl: {target.target}: {expected['message']}" in output.stderr
        attempts = [
            row
            for row in log_records(case)
            if row["target"] == target.target and row["kind"] == "attempt"
        ]
        assert attempts == expected["attempts"]
        assert_all_decisions(root, case)


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_screen_change_aborts_send(
    root: Path, mux_server: PrivateMux, agent: str
) -> None:
    """A real guard refuses changed text with an identical class and fingerprint."""
    trigger = mux_server.scope / "guard-overload"
    guarded = guarded_target(root, mux_server, agent, trigger)
    target = guarded.target
    controls = receiving_controls(root, mux_server, trigger)
    barrier = supervisor_barrier(target.case)
    case = barrier.case
    for watched in (target, *controls):
        assert case.command("watch", (watched.target,)).code == 0
    with supervisor(case) as running:
        for watched in (target, *controls):
            wait_observation(running, watched.target, "IdlePrompt")
        barrier.arm("guard", target)
        trigger.touch()
        drive_guard(running, barrier, guarded)
        require_receivers(root, controls)
        wait_observation(running, target.target, "PartialInput")
        running.finish()
    expected = scenario(root, "changed-guard", agent)
    text = expected["received"]
    assert isinstance(text, str)
    assert (
        received_bytes(target.case.records_directory, target.case.nonce)
        == text.encode()
    )
    assert [
        row["outcome"]
        for row in log_records(case)
        if row["target"] == target.target and row["kind"] == "attempt"
    ] == expected["attempts"]
    assert_all_decisions(root, case)


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_failed_send_closes_unresolved(
    root: Path, mux_server: PrivateMux, agent: str
) -> None:
    """A refused native literal records failure and cannot retry partial input."""
    trigger = mux_server.scope / "failed-overload"
    target = scripted_target(
        mux_server,
        root,
        agent,
        (
            ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
            ("Overloaded", {"kind": "stay"}),
        ),
    )
    controls = receiving_controls(root, mux_server, trigger)
    barrier = supervisor_barrier(target.case)
    case = barrier.case
    for watched in (target, *controls):
        assert case.command("watch", (watched.target,)).code == 0
    with supervisor(case) as running:
        for watched in (target, *controls):
            wait_observation(running, watched.target, "IdlePrompt")
        barrier.arm("fail", target)
        trigger.touch()
        wait_backoff(running, target.target)
        wait_transition(running, target.target, "RECOVERY_SENT")
        barrier.wait("fail", target)
        result = wait_records(running, target.target, "result")[0]
        expected = scenario(root, "failed-command", agent)
        assert result["outcome"] == expected["result"]
        require_receivers(root, controls)
        observe_polls(running, target.target, 3)
        output = running.finish()
    text = expected["received"]
    assert isinstance(text, str)
    assert (
        received_bytes(target.case.records_directory, target.case.nonce)
        == text.encode()
    )
    assert [
        row["outcome"]
        for row in log_records(case)
        if row["target"] == target.target and row["kind"] == "attempt"
    ] == expected["attempts"]
    assert f"agentctl: {target.target}: recovery send failed" in output.stderr
    barrier.observer.arguments()
    assert_all_decisions(root, case)


@pytest.mark.evidence("observer")
@pytest.mark.parametrize(
    "category",
    [
        "Working",
        "ApprovalDialog",
        "PartialInput",
        "TrustDialog",
        "BypassWarning",
        "baseline",
    ],
)
def test_unsafe_screens_never_sent(
    root: Path, mux_server: PrivateMux, category: str
) -> None:
    """Unsafe screens and old overloads stay untouched beside both receivers."""
    trigger = mux_server.scope / "unsafe-screen"
    targets = []
    name = "stale-baseline" if category == "baseline" else "unsafe-" + category.lower()
    for agent in ("claude", "codex"):
        if category == "baseline":
            frames = (("Overloaded", {"kind": "stay"}),)
        else:
            filename = (
                "overload-precedence.txt"
                if category in {"Working", "ApprovalDialog", "PartialInput"}
                else "documented.txt"
            )
            screen = category + "/" + filename
            if category in {"TrustDialog", "BypassWarning"}:
                fixtures = root / "tests/fixtures/screens" / agent
                combined = mux_server.scope / f"unsafe-{category}-{agent}.txt"
                combined.write_text(
                    (fixtures / "Overloaded/documented.txt").read_text(encoding="utf-8")
                    + "\n"
                    + (fixtures / screen).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                screen = str(combined)
            frames = (
                ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
                (screen, {"kind": "stay"}),
            )
        targets.append(scripted_target(mux_server, root, agent, frames))
    controls = receiving_controls(root, mux_server, trigger)
    case = targets[0].case
    for target in (*targets, *controls):
        assert case.command("watch", (target.target,)).code == 0
    with supervisor(case) as running:
        for target in (*targets, *controls):
            baseline = (
                "Overloaded"
                if target in targets and category == "baseline"
                else "IdlePrompt"
            )
            wait_observation(running, target.target, baseline)
        trigger.touch()
        for target in targets:
            expected = scenario(root, name, target.case.agent)
            observed = expected["class"]
            assert isinstance(observed, str)
            wait_observation(running, target.target, observed)
        require_receivers(root, controls)
        for target in targets:
            observe_polls(running, target.target, 3)
        running.finish()
    for target in targets:
        expected = scenario(root, name, target.case.agent)
        text = expected["received"]
        assert isinstance(text, str)
        assert (
            received_bytes(target.case.records_directory, target.case.nonce)
            == text.encode()
        )
        assert [
            row
            for row in log_records(case)
            if row["target"] == target.target and row["kind"] == "attempt"
        ] == expected["attempts"]
        assert_all_decisions(root, case)


@pytest.mark.evidence("observer")
def test_paused_target_never_sent(root: Path, mux_server: PrivateMux) -> None:
    """Pause stops capture, and resume handles the visible overload baseline."""
    trigger = mux_server.scope / "paused-overload"
    targets = [
        scripted_target(
            mux_server,
            root,
            agent,
            (
                ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
                ("Overloaded", {"kind": "stay"}),
            ),
        )
        for agent in ("claude", "codex")
    ]
    controls = receiving_controls(root, mux_server, trigger)
    observer = observe_mux(targets[0].case)
    case = observer.case
    for target in (*targets, *controls):
        assert case.command("watch", (target.target,)).code == 0
    with supervisor(case) as running:
        for target in (*targets, *controls):
            wait_observation(running, target.target, "IdlePrompt")
        for target in targets:
            assert case.command("pause", (target.target,)).code == 0
        before = observer.arguments()
        captured_before = {
            target.pane: sum(
                argv[:1] == ["capture-pane"] and target.pane in argv for argv in before
            )
            for target in targets
        }
        assert all(captured_before.values())
        trigger.touch()
        began = time.monotonic()
        for control in controls:
            wait_backoff(running, control.target)
        for control in controls:
            wait_records(running, control.target, "attempt")
        require_receivers(root, controls)
        while time.monotonic() < began + 0.9:
            assert running.alive()
            time.sleep(0.01)
        after = observer.arguments()
        for target in targets:
            captured_after = sum(
                argv[:1] == ["capture-pane"] and target.pane in argv for argv in after
            )
            assert captured_after == captured_before[target.pane]
            assert not any(
                row["kind"] == "observation"
                and row["target"] == target.target
                and row["class"] == "Overloaded"
                for row in log_records(case)
            )
            assert case.command("resume-watch", (target.target,)).code == 0
            wait_observation(running, target.target, "Overloaded")
        for target in targets:
            observe_polls(running, target.target, 3)
        running.finish()
    for target in targets:
        expected = scenario(root, "pause-resume", target.case.agent)
        text = expected["received"]
        assert isinstance(text, str)
        assert (
            received_bytes(target.case.records_directory, target.case.nonce)
            == text.encode()
        )
        assert [
            row
            for row in log_records(case)
            if row["target"] == target.target and row["kind"] == "attempt"
        ] == expected["attempts"]
        assert_all_decisions(root, case)


@pytest.mark.evidence("observer")
def test_forbidden_actions_never_taken(root: Path, mux_server: PrivateMux) -> None:
    """A real crash stays dead while auth and login panes stay alive and untouched."""
    crashing = prepare(mux_server, "claude", disposition="wait-exit-3")
    assert crashing.invoke().code == 0
    crash = rows(crashing.command("status", ("api-claude",)))["api-claude"]
    original_crash = pane_facts(mux_server, crash["PANE"])
    retained = mux_server.raw(
        "set-option", "-p", "-t", crash["PANE"], "remain-on-exit", "on"
    )
    assert retained.code == 0, retained
    trigger = mux_server.scope / "forbidden-screens"
    targets = [
        scripted_target(
            mux_server,
            root,
            agent,
            (
                ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
                (category, {"kind": "stay"}),
            ),
        )
        for agent, category in (("claude", "AuthError"), ("codex", "LoginScreen"))
    ]
    identities = {
        target.pane: pane_facts(mux_server, target.pane) for target in targets
    }
    controls = receiving_controls(root, mux_server, trigger)
    observer = observe_mux(crashing)
    case = observer.case
    for name in ("api-claude", *(target.target for target in (*targets, *controls))):
        assert case.command("watch", (name,)).code == 0
    with supervisor(case) as controller:
        wait_observation(controller, "api-claude", "Unknown")
        for target in (*targets, *controls):
            wait_observation(controller, target.target, "IdlePrompt")
        (crashing.records_directory / "stop").touch()
        trigger.touch()
        wait_observation(controller, "api-claude", "Exited")
        for target, category in zip(targets, ("AuthError", "LoginScreen"), strict=True):
            wait_observation(controller, target.target, category)
        for control in controls:
            wait_backoff(controller, control.target)
            wait_transition(controller, control.target, "RECOVERY_SENT")
            wait_records(controller, control.target, "attempt")
        require_receivers(root, controls)
        controller.finish()
    expected = scenario(root, "forbidden-native", "both")
    _assert_forbidden_native(mux_server, crash["PANE"], original_crash[0])
    launched = [row for row in crashing.records() if row["pane"] == crash["PANE"]]
    assert len(launched) == expected["crash_launches"]
    text = expected["live_received"]
    assert isinstance(text, str)
    for target in targets:
        assert pane_facts(mux_server, target.pane) == identities[target.pane]
        assert (
            received_bytes(target.case.records_directory, target.case.nonce)
            == text.encode()
        )
        assert_all_decisions(root, case)
    verbs = expected["forbidden_verbs"]
    tokens = expected["forbidden_tokens"]
    assert isinstance(verbs, list)
    assert isinstance(tokens, list)
    for argv in observer.arguments():
        assert argv
        assert argv[0] not in verbs
        assert not any(str(token) in " ".join(argv) for token in tokens)


def _assert_forbidden_native(mux: PrivateMux, pane: str, original_pid: int) -> None:
    """Require the retained crash beside the independently unchanged live pids."""
    output = mux.raw("display-message", "-p", "-t", pane, "#{pane_pid}|#{pane_dead}")
    assert output.code == 0, output
    assert output.stdout.strip() == str(original_pid) + "|1"
