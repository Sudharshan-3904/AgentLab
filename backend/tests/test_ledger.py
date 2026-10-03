"""Tests for SQLiteEventLedger."""

import json
from pathlib import Path
import pytest
from harness.core.events import Event, EventType
from harness.ledger.sqlite import SQLiteEventLedger


def test_sqlite_ledger_append_and_get_events():
    ledger = SQLiteEventLedger(":memory:")
    ev1 = Event.create(
        execution_id="exec-101",
        type=EventType.TASK_RECEIVED,
        source="task_intake",
        payload={"objective": "Test ledger"},
    )
    ev2 = Event.create(
        execution_id="exec-101",
        type=EventType.SKILL_LOADED,
        source="skill_manager",
        payload={"skill": "planning"},
    )
    ledger.append(ev1)
    ledger.append(ev2)

    events = ledger.get_events("exec-101")
    assert len(events) == 2
    assert events[0].type == EventType.TASK_RECEIVED
    assert events[1].type == EventType.SKILL_LOADED

    # Filter by type
    filtered = ledger.get_events("exec-101", event_type=EventType.SKILL_LOADED)
    assert len(filtered) == 1
    assert filtered[0].payload["skill"] == "planning"

    ledger.close()


def test_sqlite_ledger_correlation_id_query():
    ledger = SQLiteEventLedger(":memory:")
    ev1 = Event.create(
        execution_id="exec-102",
        type=EventType.TOOL_REQUEST,
        source="tool_manager",
        payload={"tool": "file_reader"},
        correlation_id="corr-999",
    )
    ev2 = Event.create(
        execution_id="exec-102",
        type=EventType.TOOL_RESPONSE,
        source="tool_manager",
        payload={"status": "success"},
        correlation_id="corr-999",
    )
    ledger.append(ev1)
    ledger.append(ev2)

    by_corr = ledger.get_by_correlation_id("corr-999")
    assert len(by_corr) == 2
    assert by_corr[0].type == EventType.TOOL_REQUEST
    assert by_corr[1].type == EventType.TOOL_RESPONSE

    ledger.close()


def test_sqlite_ledger_export_jsonl(tmp_path: Path):
    db_file = tmp_path / "ledger.db"
    jsonl_file = tmp_path / "export.jsonl"

    ledger = SQLiteEventLedger(db_file)
    ev = Event.create(
        execution_id="exec-103",
        type=EventType.TASK_RECEIVED,
        source="task_intake",
        payload={"task": "Export check"},
    )
    ledger.append(ev)

    count = ledger.export_jsonl("exec-103", jsonl_file)
    assert count == 1
    assert jsonl_file.exists()

    with open(jsonl_file, "r", encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["execution_id"] == "exec-103"
        assert data["type"] == "TASK_RECEIVED"

    ledger.close()
