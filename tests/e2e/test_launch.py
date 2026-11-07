# Copyright (c) 2026 agentctl contributors.
"""Launch decisions observed on private native servers and nonce-bound actors."""

import base64
import hashlib
import shlex
import shutil
from pathlib import Path

import pytest

from agentctl.process import Output
from tests.harness.launch import observe_mux, prepare
from tests.harness.oracle import Store, assert_oracle, freeze, read_homes
from tests.harness.oracle import load as load_oracle
from tests.harness.passthrough import warm
from tests.harness.terminal import attached_seed, await_client, await_exit, terminal
from tests.harness.tmux import PrivateMux, pane_identifier

FORWARDED = ("x;", "#{pane_id}", "$(id)", "", "one\ntwo", "λ日")
FLAGS = {
    "claude": ["--dangerously-skip-permissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox", "--no-daemon"],
}
EXIT_STATUS = 3
INITIAL_RECORDS = 2


def _warning(root: Path, filename: str, identifier: str, output: Output) -> None:
    """Compare caller stderr and status with the independent effective oracle row."""
    store = load_oracle(root / "tests/oracles" / filename, read_homes(root))
    assert isinstance(store, Store), store
    expected = next(
        row.expected for row in store.effective if row.identifier == identifier
    )
    actual = freeze({"exit": output.code, "lines": output.stderr.splitlines()})
    assert_oracle(
        lambda _: actual,
        None,
        expected,
        row_id="launch failure warning differs from oracle",
    )


def _absent(mux: PrivateMux, name: str) -> None:
    """Use the native server rather than an observer's opinion of session absence."""
    assert mux.raw("has-session", "-t", "=" + name).code != 0, (
        "failed launch left its session behind"
    )


@pytest.mark.evidence("observer")
def test_creates_named_session_with_flags_last(mux_server: PrivateMux) -> None:
    """The actual pane sees literal argv, caller keys and the canonical folder."""
    for agent in ("claude", "codex"):
        case = prepare(mux_server, agent)
        output = case.invoke(FORWARDED)
        assert output.code == 0, output
        records = case.records()
        probes = [record for record in records if record["session"] is None]
        launches = [record for record in records if record["session"] is not None]
        assert len(probes) == 1
        assert len(launches) == 1
        record = launches[0]
        assert record["argv"] == [*FORWARDED, *FLAGS[agent]], (
            "launched argv differs from required argument assembly"
        )
        assert Path(str(record["cwd"])).resolve() == case.folder.resolve(), (
            "launch did not preserve the caller folder"
        )
        name = "api-" + agent
        assert record["session"] == name
        keys = record["env_keys"]
        assert isinstance(keys, list)
        assert {"CLAUDE_CONFIG_DIR", "CODEX_HOME", "CALLER_ONLY"} <= set(keys), (
            "launch lost caller environment"
        )
        assert "SERVER_ONLY" not in keys
        target = "=" + name + ":"
        options = mux_server.raw("show-options", "-t", target)
        encoded = (
            base64.urlsafe_b64encode(str(case.folder.resolve()).encode())
            .decode()
            .rstrip("=")
        )
        identity = [
            shlex.split(line)
            for line in options.stdout.splitlines()
            if line.startswith("@")
        ]
        assert ["@agentctl_owner", "agentctl"] in identity
        assert ["@agentctl_agent", agent] in identity
        assert ["@agentctl_folder", encoded] in identity
        assert not list(Path(case.environment["AGENTCTL_STATE_DIR"]).rglob("spec.json"))


@pytest.mark.evidence("observer")
def test_instant_exit_relays_output_and_leaves_nothing(mux_server: PrivateMux) -> None:
    """A real exit 3 is relayed after the observer proves its session existed."""
    case = prepare(mux_server, "claude", disposition="3")
    output = case.invoke()
    assert "ready:" + case.nonce in output.stderr, (
        "instant exit output was not relayed to stderr"
    )
    assert output.code == EXIT_STATUS, output
    assert "exited with status 3 during startup" in output.stderr
    records = case.records()
    assert any(record["session"] == "api-claude" for record in records)
    assert mux_server.raw("has-session", "-t", "=api-claude").code != 0, (
        "instant exit kept its session"
    )


@pytest.mark.evidence("real")
def test_no_tty_prints_attach_command(mux_server: PrivateMux) -> None:
    """A pipe caller leaves an actual running session and receives its attach line."""
    case = prepare(mux_server, "claude")
    output = case.invoke()
    assert output.code == 0, "no-TTY launch tried to attach"
    name = "psmux" if mux_server.family == "Windows" else "tmux"
    assert output.stdout == name + " attach-session -t =api-claude\n"
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0
    assert len(case.records()) == INITIAL_RECORDS


@pytest.mark.evidence("real")
def test_attach_under_pty(mux_server: PrivateMux) -> None:
    """A real native PTY caller attaches one client to its created agent session."""
    caller = warm(prepare(mux_server, "claude"))
    with terminal(caller, ("claude",)) as driver:
        await_client(mux_server, driver, "api-claude")
        records = caller.case.records()
        assert len(records) == INITIAL_RECORDS
        assert any(record["session"] == "api-claude" for record in records)


@pytest.mark.evidence("real")
def test_inside_tmux_switches_client(mux_server: PrivateMux) -> None:
    """A caller inside the private server switches its existing client's identity."""
    caller = warm(prepare(mux_server, "claude"))
    with attached_seed(caller) as (seed, driver):
        before = await_client(mux_server, driver, "seed")
        (caller.case.folder / "launch").write_text("launch", encoding="utf-8")
        after = await_client(mux_server, driver, "api-claude")
        assert after[0] == before[0], "inside launch created a nested client"
        assert len(caller.case.records()) == INITIAL_RECORDS
        await_exit(seed)


@pytest.mark.evidence("observer")
def test_rerun_reattaches_without_preflight(mux_server: PrivateMux) -> None:
    """A rerun retains its native identity with no agent available on its PATH."""
    case = prepare(mux_server, "claude")
    first = case.invoke()
    assert first.code == 0, first
    before = case.records()
    assert len(before) == INITIAL_RECORDS
    target = "=api-claude" + ("" if mux_server.family == "Windows" else ":")
    identity = mux_server.raw("display-message", "-p", "-t", target, "#{session_id}")
    assert identity.code == 0, identity.stderr
    binaries = mux_server.scope / "mux-only"
    binaries.mkdir()
    name = "psmux.exe" if mux_server.family == "Windows" else "tmux"
    shutil.copy2(mux_server.executable, binaries / name)
    folder = (
        Path(str(case.folder).swapcase())
        if mux_server.family == "Windows"
        else case.folder
    )
    rerun = case.invoke(
        ("not-applied",),
        folder=folder,
        changes={"PATH": str(binaries), "AGENTCTL_FAKE_AUTH_EXIT": "1"},
    )
    assert rerun.code == 0, "reattachment reran preflight or recreated the session"
    assert "arguments given were not applied" in rerun.stderr
    assert "=api-claude" in rerun.stdout
    assert case.records() == before, "reattachment launched or probed another agent"
    assert (
        mux_server.raw("display-message", "-p", "-t", target, "#{session_id}").stdout
        == identity.stdout
    ), "reattachment replaced the original session"


@pytest.mark.evidence("real")
def test_same_basename_other_folder_gets_hash_form(mux_server: PrivateMux) -> None:
    """Two real folders get separate native sessions and both can be reattached."""
    case = prepare(mux_server, "claude")
    first = case.invoke()
    assert first.code == 0, first
    before = len(case.records())
    other = case.folder.parent / "other" / "api"
    other.mkdir(parents=True)
    second = case.invoke(folder=other)
    assert second.code == 0, second
    canonical = str(other.resolve())
    folded = canonical.casefold() if mux_server.family == "Windows" else canonical
    digest = hashlib.sha256(folded.encode("utf-8")).hexdigest()[:8]
    hashed = "api-" + digest + "-claude"
    assert "=" + hashed in second.stdout, "same-basename folders shared a session"
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0
    assert mux_server.raw("has-session", "-t", "=" + hashed).code == 0
    assert len(case.records()) == before + INITIAL_RECORDS
    complete = case.records()
    assert case.invoke().code == 0
    assert case.invoke(folder=other).code == 0
    assert case.records() == complete


@pytest.mark.evidence("real")
def test_dead_leftover_pane_is_replaced(mux_server: PrivateMux) -> None:
    """A genuinely dead owned pane is replaced under its original session name."""
    case = prepare(mux_server, "claude")
    old = mux_server.actor("api-claude", disposition="3")
    assert mux_server.exit_status(old) == EXIT_STATUS
    previous = old.record()["pid"]
    encoded = (
        base64.urlsafe_b64encode(str(case.folder.resolve()).encode())
        .decode()
        .rstrip("=")
    )
    for key, value in (
        ("owner", "agentctl"),
        ("agent", "claude"),
        ("folder", encoded),
        ("pane", pane_identifier(old.pane)),
    ):
        result = mux_server.command(
            "set-identity", session=old.session, key=key, value=value
        )
        assert result["code"] == 0, result
    output = case.invoke()
    assert output.code == 0, output
    launches = [record for record in case.records() if record["session"] == old.session]
    assert len(launches) == 1, "dead pane was reattached"
    pane = launches[0]["pane"]
    assert isinstance(pane, str)
    assert launches[0]["pid"] != previous, "dead process was reattached"
    live = mux_server.raw("display-message", "-p", "-t", pane, "#{pane_dead}")
    assert live.code == 0, live.stderr
    assert live.stdout.strip() == "0"


@pytest.mark.evidence("observer")
def test_preflight_failure_leaves_nothing(root: Path, mux_server: PrivateMux) -> None:
    """Refused login, absent agent and logged-out probe create nothing."""
    case = prepare(mux_server, "claude")
    refused = case.invoke(("auth", "login"))
    _warning(root, "auth_status.toml", "login-refusal.warning.claude.0", refused)
    _absent(mux_server, "api-claude")
    assert case.records() == []
    binaries = mux_server.scope / "without-agent"
    binaries.mkdir()
    mux_name = "psmux.exe" if mux_server.family == "Windows" else "tmux"
    shutil.copy2(mux_server.executable, binaries / mux_name)
    missing = case.invoke(changes={"PATH": str(binaries)})
    _warning(
        root,
        "preflight.toml",
        "preflight.warning." + mux_server.family.lower() + ".claude.missing",
        missing,
    )
    _absent(mux_server, "api-claude")
    assert case.records() == []
    logged_out = case.invoke(changes={"AGENTCTL_FAKE_AUTH_EXIT": "1"})
    _warning(root, "auth_status.toml", "auth.warning.claude.logged-out", logged_out)
    _absent(mux_server, "api-claude")
    probes = case.records()
    assert len(probes) == 1
    assert probes[0]["argv"] == ["auth", "status"]
    assert probes[0]["session"] is None
    assert not list(Path(case.environment["AGENTCTL_STATE_DIR"]).rglob("spec.json"))
    positive = case.invoke()
    assert positive.code == 0, positive
    assert mux_server.raw("has-session", "-t", "=api-claude").code == 0
    assert any(record["session"] == "api-claude" for record in case.records())


@pytest.mark.evidence("real")
def test_failed_discovery_leaves_no_native_session(mux_server: PrivateMux) -> None:
    """The genuine backend distinguishes absence after failure from an owned session."""
    case = prepare(mux_server, "claude")
    suffix = ".exe" if mux_server.family == "Windows" else ""
    (Path(case.environment["PATH"]) / ("claude" + suffix)).unlink()
    failed = case.invoke()
    assert failed.code != 0, "failed discovery exited successfully"
    _absent(mux_server, "api-claude")
    positive = mux_server.actor("api-claude")
    assert mux_server.raw("has-session", "-t", "=" + positive.session).code == 0


@pytest.mark.evidence("observer")
def test_hostile_folder_name_runs_nothing(mux_server: PrivateMux) -> None:
    """A literal command-substitution folder reaches only the spec and native cwd."""
    observer = observe_mux(prepare(mux_server, "claude"))
    case = observer.case
    positive = case.invoke()
    assert positive.code == 0, positive
    assert any(record["session"] == "api-claude" for record in case.records())
    creates = observer.creates()
    assert len(creates) == 1, "multiplexer invocation observer saw no positive create"
    assert all("-c" not in arguments for arguments in creates), (
        "native invocation moved caller data onto mux argv"
    )
    marker = "sentinel-" + case.nonce.rsplit(".", maxsplit=1)[-1]
    folder = case.folder.parent / ("project-#(touch " + marker + ")")
    folder.mkdir()
    output = case.invoke(folder=folder)
    creates = observer.creates()
    assert len(creates) == INITIAL_RECORDS
    assert all("-c" not in arguments for arguments in creates), (
        "native invocation moved caller data onto mux argv"
    )
    assert output.code == 0, output
    launches = [
        record
        for record in case.records()
        if record["session"] is not None
        and Path(str(record["cwd"])).resolve() == folder.resolve()
    ]
    assert len(launches) == 1, "hostile folder did not remain literal"
    name = launches[0]["session"]
    assert isinstance(name, str)
    assert all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in name
    )
    assert not list(mux_server.scope.rglob(marker)), (
        "folder text reached multiplexer expansion"
    )
