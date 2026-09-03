"""Database inspection and retrieval script.

Retrieves and prints all stored session records from the configured database backend
(PostgreSQL when DB_BACKEND=postgres and DATABASE_URL is set, or SQLite).
Can be run directly via `python tests/test_get_db_data.py` or through pytest.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import config

DB_BACKEND = getattr(config, "DB_BACKEND", os.getenv("DB_BACKEND", "sqlite")).lower().strip()
DATABASE_URL = getattr(config, "DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
SQLITE_DB_PATH = getattr(config, "SQLITE_DB_PATH", PROJECT_ROOT / "data" / "sessions.db")


def get_all_db_data() -> List[Dict[str, Any]]:
    """Retrieve all session rows from the active database."""
    records: List[Dict[str, Any]] = []

    if DB_BACKEND == "postgres" and DATABASE_URL:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM sessions ORDER BY created_at DESC;")
                rows = cur.fetchall()
                records = [dict(r) for r in rows]
        finally:
            conn.close()
    else:
        if not SQLITE_DB_PATH.exists():
            return []
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC;")
            records = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    return records


def print_db_summary(records: List[Dict[str, Any]]) -> None:
    """Print formatted summary of all retrieved session records."""
    backend_name = "PostgreSQL" if (DB_BACKEND == "postgres" and DATABASE_URL) else "SQLite"
    target_info = DATABASE_URL if backend_name == "PostgreSQL" else str(SQLITE_DB_PATH)

    print(f"\n{'='*70}")
    print(f"DATABASE SESSION INSPECTOR")
    print(f"Backend: {backend_name}")
    print(f"Target:  {target_info}")
    print(f"Total Sessions: {len(records)}")
    print(f"{'='*70}\n")

    if not records:
        print("No session records found in the database.")
        return

    for idx, r in enumerate(records, start=1):
        dialogue = json.loads(r.get("dialogue_window") or "[]")
        attempted = json.loads(r.get("attempted_steps") or "[]")
        facts = json.loads(r.get("confirmed_facts") or "{}")

        print(f"[{idx}] Session ID: {r.get('session_id')}")
        print(f"    Identified Model:     {r.get('identified_model') or 'None'}")
        print(f"    Turns Count:          {r.get('turns_count', 0)}")
        print(f"    Pending Confirmation: {r.get('pending_confirmation') or 'None'}")
        print(f"    Reported Issue:       {r.get('reported_issue') or 'None'}")
        print(f"    Is Escalated:         {bool(r.get('is_escalated', 0))}")
        print(f"    Is Resolved:          {bool(r.get('is_resolved', 0))}")
        print(f"    Created At:           {r.get('created_at')}")
        print(f"    Updated At:           {r.get('updated_at')}")
        print(f"    Attempted Steps ({len(attempted)}): {attempted}")
        print(f"    Confirmed Facts:      {facts}")
        print(f"    Messages ({len(dialogue)}):")
        for m in dialogue:
            role = m.get("role", "unknown").upper()
            msg_content = m.get("content", "").replace("\n", " ")
            if len(msg_content) > 80:
                msg_content = msg_content[:77] + "..."
            print(f"      - [{role}]: {msg_content}")
        print(f"{'-'*70}")


def test_get_db_data():
    """Pytest-compatible test verifying database retrieval executes without error."""
    records = get_all_db_data()
    assert isinstance(records, list)


if __name__ == "__main__":
    data = get_all_db_data()
    print_db_summary(data)
