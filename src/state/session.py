from __future__ import annotations
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Optional, Any, List, Union

from src.core.config import SQLITE_DB_PATH
from src.core.models import SessionState, ChatMessage, DiagnosticSession
from src.core.logging import logger

_UNSET = object()

# To store / retrieve / update session states used for memory
# Check issue on attempted_steps and reported_issue
class SessionStateManager:
    _db_path: Path = SQLITE_DB_PATH
    _initialized: bool = False

    @classmethod
    def _init_db_once(cls) -> None:
        if cls._initialized:
            return
        cls._db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(cls._db_path), check_same_thread=False)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        identified_model TEXT,
                        attempted_steps TEXT,
                        pending_confirmation TEXT,
                        dialogue_window TEXT,
                        created_at REAL,
                        updated_at REAL,
                        reported_issue TEXT,
                        confirmed_facts TEXT,
                        turns_count INTEGER DEFAULT 0,
                        is_escalated INTEGER DEFAULT 0,
                        is_resolved INTEGER DEFAULT 0
                    )
                """)
        cls._initialized = True

    @classmethod
    def _row_to_state(cls, row: sqlite3.Row) -> SessionState:
        dialogue_raw = json.loads(row["dialogue_window"] or "[]")
        dialogue_window = [ChatMessage(**msg) for msg in dialogue_raw]
        attempted_steps = json.loads(row["attempted_steps"] or "[]")
        confirmed_facts = json.loads(row["confirmed_facts"] or "{}")

        return SessionState(
            session_id=row["session_id"],
            identified_model=row["identified_model"],
            attempted_steps=attempted_steps,
            pending_confirmation=row["pending_confirmation"],
            dialogue_window=dialogue_window,
            created_at=row["created_at"] or time.time(),
            updated_at=row["updated_at"] or time.time(),
            reported_issue=row["reported_issue"],
            confirmed_facts=confirmed_facts,
            turns_count=row["turns_count"] or 0,
            is_escalated=bool(row["is_escalated"]),
            is_resolved=bool(row["is_resolved"]),
        )

    @classmethod
    def get_or_create(cls, session_id: str) -> SessionState:
        cls._init_db_once()
        with closing(sqlite3.connect(str(cls._db_path), check_same_thread=False)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row is not None:
                return cls._row_to_state(row)

        new_state = SessionState(session_id=session_id)
        cls.update_session(new_state)
        logger.debug(f"Created new session in SQLite: {session_id}")
        return new_state

    @classmethod
    def get_session(cls, session_id: str) -> SessionState:
        return cls.get_or_create(session_id)

    @classmethod
    def record_turn(
        cls,
        session: SessionState,
        user_message: str,
        assistant_response: str,
        step_executed: Optional[str] = None,
        max_window_turns: int = 4
    ) -> SessionState:
        now = time.time()
        user_msg = ChatMessage(role="user", content=user_message, timestamp=now)
        asst_msg = ChatMessage(role="assistant", content=assistant_response, timestamp=now)

        session.dialogue_window.append(user_msg)
        session.dialogue_window.append(asst_msg)

        # Last n turns * 2 = total messages
        max_msgs = max_window_turns * 2
        if len(session.dialogue_window) > max_msgs:
            session.dialogue_window = session.dialogue_window[-max_msgs:]

        if step_executed and step_executed not in session.attempted_steps:
            session.attempted_steps.append(step_executed)

        session.updated_at = now
        cls.update_session(session)
        return session

    @classmethod
    def add_turn(
        cls,
        session_id: Union[str, SessionState],
        user_message: str,
        assistant_response: str,
        step_executed: Optional[str] = None,
        max_window_turns: int = 4
    ) -> SessionState:
        if isinstance(session_id, SessionState):
            state = session_id
        else:
            state = cls.get_or_create(session_id)
        return cls.record_turn(state, user_message, assistant_response, step_executed, max_window_turns)

    @classmethod
    def update_slots(
        cls,
        session_id: Union[str, SessionState],
        identified_model: Optional[str] = None,
        pending_confirmation: Any = _UNSET
    ) -> SessionState:
        if isinstance(session_id, SessionState):
            state = session_id
        else:
            state = cls.get_or_create(session_id)
        if identified_model is not None:
            state.identified_model = identified_model
        if pending_confirmation is not _UNSET:
            state.pending_confirmation = pending_confirmation
        state.updated_at = time.time()
        cls.update_session(state)
        return state

    @classmethod
    def build_prompt_context(cls, session_id: Union[str, SessionState]) -> dict:
        if isinstance(session_id, SessionState):
            state = session_id
        else:
            state = cls.get_or_create(session_id)
        return {
            "identified_model": state.identified_model or "Unknown (Needs identification)",
            "attempted_steps": state.attempted_steps,
            "pending_confirmation": state.pending_confirmation, # Factory reset
            "recent_messages": [msg.model_dump() for msg in state.dialogue_window],
        }

    @classmethod
    def update_session(cls, session: SessionState) -> None:
        cls._init_db_once()
        session.updated_at = time.time()
        dialogue_json = json.dumps([msg.model_dump() for msg in session.dialogue_window])
        attempted_json = json.dumps(session.attempted_steps)
        confirmed_json = json.dumps(session.confirmed_facts)

        with closing(sqlite3.connect(str(cls._db_path), check_same_thread=False)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO sessions (
                        session_id, identified_model, attempted_steps, pending_confirmation,
                        dialogue_window, created_at, updated_at, reported_issue,
                        confirmed_facts, turns_count, is_escalated, is_resolved
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        identified_model = excluded.identified_model,
                        attempted_steps = excluded.attempted_steps,
                        pending_confirmation = excluded.pending_confirmation,
                        dialogue_window = excluded.dialogue_window,
                        updated_at = excluded.updated_at,
                        reported_issue = excluded.reported_issue,
                        confirmed_facts = excluded.confirmed_facts,
                        turns_count = excluded.turns_count,
                        is_escalated = excluded.is_escalated,
                        is_resolved = excluded.is_resolved
                """, (
                    session.session_id,
                    session.identified_model,
                    attempted_json,
                    session.pending_confirmation,
                    dialogue_json,
                    session.created_at,
                    session.updated_at,
                    session.reported_issue,
                    confirmed_json,
                    session.turns_count,
                    int(session.is_escalated),
                    int(session.is_resolved),
                ))

    @classmethod
    def clear_session(cls, session_id: str) -> None:
        cls._init_db_once()
        with closing(sqlite3.connect(str(cls._db_path), check_same_thread=False)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    @classmethod
    def reset_all(cls) -> None:
        cls._init_db_once()
        with closing(sqlite3.connect(str(cls._db_path), check_same_thread=False)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions")


SessionManager = SessionStateManager
