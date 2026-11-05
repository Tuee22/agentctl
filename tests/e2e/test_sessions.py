# Copyright (c) 2026 agentctl contributors.
"""Session handlers consume actual ownership, liveness and folder facts."""

import base64
import shutil
import time
from dataclasses import replace
from pathlib import Path

import pytest

from tests.harness.launch import observe_mux, prepare
from tests.harness.oracle import Store, assert_oracle, freeze, read_homes
from tests.harness.oracle import load as load_oracle
from tests.harness.passthrough import warm
from tests.harness.sessions import rows
from tests.harness.terminal import (
    attached_seed,
    await_client,
    await_exit,
    clients,
    terminal,
)
from tests.harness.tmux import PrivateMux

EXIT_STATUS = 3
ROW_REASON = "session rows differ from ownership oracle"
STOP_REASON = "session stop plan differs from ownership oracle"
ATTACH_REASON = "session attach selected another target"


@pytest.mark.evidence("real")
def test_list_shows_only_managed(mux_server: PrivateMux) -> None:
    """A foreign session stays foreign with no options or incomplete identity."""
    claude = prepare(mux_server, "claude")
    codex = prepare(mux_server, "codex")
    assert rows(claude.command("list")) == {}
    assert claude.invoke().code == 0
    assert codex.invoke().code == 0
    foreign = mux_server.actor("foreign")
    observed = rows(claude.command("list"))
    assert set(observed) == {"api-claude", "api-codex"}, (
        ROW_REASON + ": session list included a foreign session"
    )
    actual = mux_server.raw("list-sessions", "-F", "#{session_name}")
    assert actual.code == 0
    assert set(actual.stdout.splitlines()) == {"api-claude", "api-codex", "foreign"}
    target = "=foreign" + ("" if mux_server.family == "Windows" else ":")
    encoded = (
        base64.urlsafe_b64encode(str(claude.folder.resolve()).encode())
        .decode()
        .rstrip("=")
    )
    for key, value in (
        ("@agentctl_agent", "claude"),
        ("@agentctl_folder", encoded),
        ("@agentctl_pane", foreign.pane),
    ):
        assert mux_server.raw("set-option", "-t", target, key, value).code == 0
    assert set(rows(claude.command("list"))) == {"api-claude", "api-codex"}, (
        ROW_REASON + ": session list included a foreign session"
    )
    assert mux_server.raw("has-session", "-t", "=foreign").code == 0
    assert claude.command("status", ("foreign",)).code != 0
    assert claude.command("status", ("missing",)).code != 0
    assert mux_server.raw("kill-session", "-t", "=api-claude").code == 0
    assert set(rows(codex.command("list"))) == {"api-codex"}
    assert mux_server.raw("has-session", "-t", "=foreign").code == 0


@pytest.mark.evidence("real")
def test_status_reports_dead_pane(mux_server: PrivateMux) -> None:
    """A controlled post-startup exit retains its actual status and original pid."""
    case = prepare(mux_server, "claude", disposition="wait-exit-3")
    assert case.invoke().code == 0
    before = rows(case.command("status", ("api-claude",)))["api-claude"]
    assert before["STATE"] == "alive"
    assert (
        mux_server.raw(
            "set-option", "-p", "-t", before["PANE"], "remain-on-exit", "on"
        ).code
        == 0
    )
    (case.records_directory / "stop").write_text("exit", encoding="utf-8")
    deadline = time.monotonic() + 10
    dead = mux_server.raw("display-message", "-p", "-t", before["PANE"], "#{pane_dead}")
    while dead.stdout.strip() != "1" and time.monotonic() < deadline:
        time.sleep(0.01)
        dead = mux_server.raw(
            "display-message", "-p", "-t", before["PANE"], "#{pane_dead}"
        )
    assert dead.code == 0, dead
    assert dead.stdout.strip() == "1", dead
    after = rows(case.command("status", ("api-claude",)))["api-claude"]
    assert after["STATE"] == "dead", ROW_REASON + ": dead pane reported as alive"
    assert int(after["EXIT"]) == EXIT_STATUS
    assert after["PID"] == before["PID"]


@pytest.mark.evidence("real")
def test_status_defaults_to_current_folder(mux_server: PrivateMux) -> None:
    """Both agents match the canonical folder, rather than its basename alone."""
    claude = prepare(mux_server, "claude")
    codex = replace(prepare(mux_server, "codex"), folder=claude.folder)
    other = prepare(mux_server, "claude")
    assert claude.invoke().code == 0
    assert codex.invoke().code == 0
    assert other.invoke().code == 0
    observed = rows(claude.command("status"))
    assert set(observed) == {"api-claude", "api-codex"}, (
        ROW_REASON + ": session status selected another folder"
    )
    assert {row["FOLDER"] for row in observed.values()} == {
        str(claude.folder.resolve())
    }
    alias = claude.folder / "inside"
    alias.mkdir()
    assert rows(claude.command("status", folder=alias / "..")) == observed
    selected = rows(other.command("status"))
    assert len(selected) == 1
    assert next(iter(selected.values()))["FOLDER"] == str(other.folder.resolve())
    assert set(selected).isdisjoint(observed)


@pytest.mark.evidence("real")
def test_list_requires_mux_but_not_agent(root: Path, mux_server: PrivateMux) -> None:
    """Manage without agents and retain the established missing-multiplexer warning."""
    case = prepare(mux_server, "claude")
    backend_only = case.folder / "backend-only"
    backend_only.mkdir()
    name = "psmux.exe" if mux_server.family == "Windows" else "tmux"
    shutil.copy2(mux_server.executable, backend_only / name)
    for agent in ("claude", "codex"):
        assert shutil.which(agent, path=str(backend_only)) is None
    assert rows(case.command("list", changes={"PATH": str(backend_only)})) == {}
    assert case.invoke().code == 0
    assert set(rows(case.command("list", changes={"PATH": str(backend_only)}))) == {
        "api-claude"
    }
    empty = case.folder / "empty-path"
    empty.mkdir()
    refused = case.command("list", changes={"PATH": str(empty)})
    store = load_oracle(root / "tests/oracles/preflight.toml", read_homes(root))
    assert isinstance(store, Store), store
    identifier = "preflight.warning." + mux_server.family.lower() + ".mux-missing"
    expected = next(
        row.expected for row in store.effective if row.identifier == identifier
    )
    actual = freeze({"exit": refused.code, "lines": refused.stderr.splitlines()})
    assert_oracle(
        lambda _: actual,
        None,
        expected,
        row_id="session mux warning differs from oracle",
    )
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0


@pytest.mark.evidence("real")
def test_stop_kills_only_the_named_managed_session(mux_server: PrivateMux) -> None:
    """Stopping one real session leaves the other agent and its pid unchanged."""
    claude = prepare(mux_server, "claude")
    codex = prepare(mux_server, "codex")
    assert claude.invoke().code == 0
    assert codex.invoke().code == 0
    before = rows(codex.command("status", ("api-codex",)))["api-codex"]
    assert claude.command("stop", ("api-claude",)).code == 0, STOP_REASON
    assert mux_server.raw("has-session", "-t", "=api-claude").code != 0
    assert mux_server.raw("has-session", "-t", "=api-codex").code == 0, STOP_REASON
    after = rows(codex.command("status", ("api-codex",)))["api-codex"]
    assert after["STATE"] == "alive", STOP_REASON
    assert after["PID"] == before["PID"], STOP_REASON


@pytest.mark.evidence("real")
def test_stop_refuses_foreign_session(mux_server: PrivateMux) -> None:
    """A foreign pane survives refusal beside a successfully stopped managed one."""
    case = prepare(mux_server, "claude")
    assert case.invoke().code == 0
    foreign = mux_server.actor("foreign")
    before = mux_server.raw("display-message", "-p", "-t", foreign.pane, "#{pane_pid}")
    assert before.code == 0
    refused = case.command("stop", ("foreign",))
    assert refused.code != 0, STOP_REASON
    assert "nothing was stopped" in refused.stderr
    assert mux_server.raw("has-session", "-t", "=foreign").code == 0, STOP_REASON
    after = mux_server.raw("display-message", "-p", "-t", foreign.pane, "#{pane_pid}")
    assert after.code == 0
    assert after.stdout == before.stdout
    assert case.command("stop", ("api-claude",)).code == 0, STOP_REASON
    assert mux_server.raw("has-session", "-t", "=foreign").code == 0, STOP_REASON


@pytest.mark.evidence("observer")
def test_stop_never_prefix_matches(mux_server: PrivateMux) -> None:
    """Native presence and relayed client argv require exact, owned stop targets."""
    observer = observe_mux(prepare(mux_server, "claude"))
    case = observer.case
    assert case.invoke().code == 0
    assert case.command("stop", ("api",)).code != 0, STOP_REASON
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0
    assert not [argv for argv in observer.arguments() if argv[:1] == ["kill-session"]]
    assert case.command("stop", ("api-claude",)).code == 0, STOP_REASON
    stopped = [argv for argv in observer.arguments() if argv[:1] == ["kill-session"]]
    assert stopped == [["kill-session", "-t", "=api-claude"]], STOP_REASON
    assert mux_server.raw("has-session", "-t", "=api-claude").code != 0


@pytest.mark.evidence("real")
def test_attach_without_tty_prints_command(mux_server: PrivateMux) -> None:
    """The resolved managed session stays alive and receives no console client."""
    case = prepare(mux_server, "claude")
    assert case.invoke().code == 0
    output = case.command("attach", ("api-claude",))
    backend = "psmux" if mux_server.family == "Windows" else "tmux"
    assert output.code == 0, ATTACH_REASON
    assert output.stdout == backend + " attach-session -t =api-claude\n", ATTACH_REASON
    assert clients(mux_server) == ()
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0
    assert case.command("attach", ("missing",)).code != 0
    for command in ("list", "status", "attach", "stop"):
        help_text = case.command(command, ("--help",))
        assert help_text.code == 0, help_text
        assert "agentctl" in help_text.stdout


@pytest.mark.evidence("real")
def test_attach_and_switch_under_pty(mux_server: PrivateMux) -> None:
    """The real public CLI attaches, then switches the same existing native client."""
    caller = warm(prepare(mux_server, "claude"))
    assert caller.case.invoke().code == 0
    with terminal(caller, ("attach", "api-claude")) as driver:
        await_client(mux_server, driver, "api-claude", reason=ATTACH_REASON)
        attached = rows(caller.case.command("status", ("api-claude",)))
        assert attached["api-claude"]["CLIENTS"] == "1"
    assert clients(mux_server) == ()
    with attached_seed(caller, ("attach", "api-claude")) as (seed, driver):
        before = await_client(mux_server, driver, "seed", reason=ATTACH_REASON)
        (caller.case.folder / "launch").write_text("attach", encoding="utf-8")
        after = await_client(mux_server, driver, "api-claude", reason=ATTACH_REASON)
        assert after[0] == before[0], ATTACH_REASON
        await_exit(seed)
