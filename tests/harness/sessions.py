# Copyright (c) 2026 agentctl contributors.
"""Independent parsing of the fixed public session table and its text cells."""

import json

from agentctl.process import Output
from tests.harness.screens import ScreenClass

HEADER = (
    "NAME",
    "AGENT",
    "FOLDER",
    "STATE",
    "EXIT",
    "CLIENTS",
    "PANE",
    "PID",
    "KIND",
    "SESSION",
    "COMMAND",
)
TEXT_COLUMNS = ("FOLDER", "SESSION", "COMMAND")


def text_cell(value: str) -> str:
    """Decode the documented JSON string without borrowing the subject's codec."""
    decoded: object = json.loads(value)
    assert isinstance(decoded, str)
    return decoded


def rows(output: Output) -> dict[str, dict[str, str]]:
    """Retain every base-column assertion while reading adoption's extra hints."""
    assert output.code == 0, output
    lines = output.stdout.splitlines()
    assert lines, output
    header = tuple(lines[0].split("\t"))
    assert header in {
        (*HEADER, "WATCHED", "PAUSED"),
        (*HEADER, "SCREEN", "WATCHED", "PAUSED"),
    }, output
    records = []
    for line in lines[1:]:
        values = line.split("\t")
        assert len(values) == len(header), line
        record = dict(zip(header, values, strict=True))
        if "SCREEN" in record:
            assert record["SCREEN"] in {kind.value for kind in ScreenClass}
        assert record["WATCHED"] in {"yes", "no"}
        assert record["PAUSED"] in {"yes", "no"}
        assert record["PAUSED"] != "yes" or record["WATCHED"] == "yes"
        records.append(
            {**record, **{column: text_cell(record[column]) for column in TEXT_COLUMNS}}
        )
    assert len({row["NAME"] for row in records}) == len(records)
    return {row["NAME"]: row for row in records}
