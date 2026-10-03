"""Audit events (ADR-007).

The table is append-only (database triggers reject UPDATE, DELETE and
TRUNCATE). NOT YET IMPLEMENTED: the hash chain (prev_hash/hash) and the
insert-only database role. Both are roadmap Task 3 for 5-6 October.
"""
import json
from typing import Any

from sqlalchemy import Connection, text


def record_event(conn: Connection, user_id: int | None, event_type: str, payload: dict[str, Any]) -> int:
    return conn.execute(
        text(
            "INSERT INTO audit_events (user_id, event_type, payload) "
            "VALUES (:user_id, :event_type, CAST(:payload AS jsonb)) RETURNING id"
        ),
        {"user_id": user_id, "event_type": event_type, "payload": json.dumps(payload, default=str)},
    ).scalar_one()
