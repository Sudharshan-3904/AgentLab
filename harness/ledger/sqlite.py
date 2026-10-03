"""SQLite-backed event ledger with JSONL stream export capability."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from harness.core.events import Event, EventType


class SQLiteEventLedger:
    """Manages persistence and retrieval of execution events using SQLite."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_schema()

    def _create_schema(self) -> None:
        """Create events table and appropriate query indexes."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    execution_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    correlation_id TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_execution_id ON events (execution_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type ON events (type)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_correlation ON events (correlation_id)"
            )

    def append(self, event: Event) -> None:
        """Insert a new event into the ledger."""
        payload_str = json.dumps(event.payload)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO events (
                    event_id, execution_id, timestamp, type, source, correlation_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.execution_id,
                    event.timestamp,
                    event.type.value if isinstance(event.type, EventType) else str(event.type),
                    event.source,
                    event.correlation_id,
                    payload_str,
                ),
            )

    def get_events(
        self,
        execution_id: str,
        event_type: Optional[EventType | str] = None,
    ) -> List[Event]:
        """Query events for an execution, optionally filtered by event type."""
        type_filter = event_type.value if isinstance(event_type, EventType) else event_type

        cursor = self._conn.cursor()
        if type_filter:
            cursor.execute(
                """
                SELECT event_id, execution_id, timestamp, type, source, correlation_id, payload_json
                FROM events
                WHERE execution_id = ? AND type = ?
                ORDER BY id ASC
                """,
                (execution_id, type_filter),
            )
        else:
            cursor.execute(
                """
                SELECT event_id, execution_id, timestamp, type, source, correlation_id, payload_json
                FROM events
                WHERE execution_id = ?
                ORDER BY id ASC
                """,
                (execution_id,),
            )

        events: List[Event] = []
        for row in cursor.fetchall():
            event_id, exec_id, ts, ev_type, source, corr_id, payload_raw = row
            events.append(
                Event(
                    event_id=event_id,
                    execution_id=exec_id,
                    timestamp=ts,
                    type=EventType(ev_type),
                    source=source,
                    correlation_id=corr_id,
                    payload=json.loads(payload_raw),
                )
            )
        return events

    def get_by_correlation_id(self, correlation_id: str) -> List[Event]:
        """Query all events associated with a correlation ID."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT event_id, execution_id, timestamp, type, source, correlation_id, payload_json
            FROM events
            WHERE correlation_id = ?
            ORDER BY id ASC
            """,
            (correlation_id,),
        )
        events: List[Event] = []
        for row in cursor.fetchall():
            event_id, exec_id, ts, ev_type, source, corr_id, payload_raw = row
            events.append(
                Event(
                    event_id=event_id,
                    execution_id=exec_id,
                    timestamp=ts,
                    type=EventType(ev_type),
                    source=source,
                    correlation_id=corr_id,
                    payload=json.loads(payload_raw),
                )
            )
        return events

    def export_jsonl(self, execution_id: str, target_file: str | Path) -> int:
        """Export events for an execution to an append-only JSONL file."""
        events = self.get_events(execution_id)
        target_path = Path(target_file)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            for event in events:
                f.write(event.model_dump_json() + "\n")
        return len(events)

    def close(self) -> None:
        """Close database connection."""
        self._conn.close()
