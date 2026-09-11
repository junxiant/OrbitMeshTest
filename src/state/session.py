from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Optional, Any, List, Union

from src.core.config import SQLITE_DB_PATH, DB_BACKEND, DATABASE_URL
from src.core.models import SessionState, ChatMessage, DiagnosticSession
from src.core.logging import logger

_UNSET = object()


class SessionConcurrencyError(RuntimeError):
    """Raised when an optimistic locking check detects a concurrent state conflict."""


# Session State Management: Supports PostgreSQL and SQLite
class SessionStateManager:
    _db_path: Path = SQLITE_DB_PATH
    _initialized: bool = False
    _init_lock: threading.Lock = threading.Lock()
    _pg_pool: Optional[Any] = None
    _use_postgres: bool = False

    @classmethod
    def is_postgres(cls) -> bool:
        return DB_BACKEND == "postgres" and bool(DATABASE_URL) and cls._use_postgres

    @classmethod
    @contextmanager
    def _get_pg_conn(cls):
        if cls._pg_pool is None:
            raise RuntimeError("PostgreSQL connection pool is not initialized")
        conn = cls._pg_pool.getconn()
        try:
            yield conn
        finally:
            cls._pg_pool.putconn(conn)

    @classmethod
    def _init_db_once(cls) -> None:
        if cls._initialized:
            return
        with cls._init_lock:
            if cls._initialized:
                return
            if DB_BACKEND == "postgres" and bool(DATABASE_URL):
                try:
                    from psycopg2 import pool
                    cls._pg_pool = pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=int(os.getenv("DB_POOL_MAX", "10")),
                        dsn=DATABASE_URL,
                    )
                    with cls._get_pg_conn() as conn:
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    CREATE TABLE IF NOT EXISTS sessions (
                                        session_id VARCHAR(255) PRIMARY KEY,
                                        identified_model VARCHAR(255),
                                        attempted_steps TEXT,
                                        pending_confirmation VARCHAR(255),
                                        dialogue_window TEXT,
                                        created_at DOUBLE PRECISION,
                                        updated_at DOUBLE PRECISION,
                                        reported_issue TEXT,
                                        confirmed_facts TEXT,
                                        turns_count INTEGER DEFAULT 0,
                                        is_escalated INTEGER DEFAULT 0,
                                        is_resolved INTEGER DEFAULT 0,
                                        version INTEGER DEFAULT 1
                                    );
                                    CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at);
                                    ALTER TABLE sessions ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
                                """)
                    cls._use_postgres = True
                    cls._initialized = True
                    logger.info(f"Initialized PostgreSQL session storage with ThreadedConnectionPool: {DATABASE_URL}")
                    return
                except Exception as e:
                    cls._use_postgres = False
                    if cls._pg_pool:
                        try:
                            cls._pg_pool.closeall()
                        except Exception:
                            pass
                        cls._pg_pool = None
                    logger.warning(f"Failed to connect to PostgreSQL ({e}). Falling back to SQLite at {cls._db_path}")

            cls._db_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
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
                            is_resolved INTEGER DEFAULT 0,
                            version INTEGER DEFAULT 1
                        );
                        CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at);
                    """)
                    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
                    if "version" not in cols:
                        conn.execute("ALTER TABLE sessions ADD COLUMN version INTEGER DEFAULT 1")
            cls._initialized = True

    @classmethod
    def _row_to_state(cls, row: Union[sqlite3.Row, dict]) -> SessionState:
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
            version=int(row["version"]) if ("version" in (row.keys() if hasattr(row, "keys") else []) and row["version"] is not None) else 1,
        )

    @classmethod
    def get_or_create(cls, session_id: str) -> SessionState:
        cls._init_db_once()
        if cls.is_postgres():
            try:
                from psycopg2.extras import RealDictCursor
                with cls._get_pg_conn() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("SELECT * FROM sessions WHERE session_id = %s", (session_id,))
                        row = cur.fetchone()
                        if row is not None:
                            return cls._row_to_state(row)
            except Exception as e:
                logger.error(f"Error fetching session from PostgreSQL: {e}. Falling back to SQLite.")

        with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row is not None:
                return cls._row_to_state(row)

        new_state = SessionState(session_id=session_id)
        cls.update_session(new_state)
        logger.debug(f"Created new session: {session_id}")
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
        max_window_turns: int = 4,
        max_retries: int = 3,
    ) -> SessionState:
        now = time.time()
        user_msg = ChatMessage(role="user", content=user_message, timestamp=now)
        asst_msg = ChatMessage(role="assistant", content=assistant_response, timestamp=now)

        for attempt in range(max_retries):
            latest = cls.get_or_create(session.session_id)

            merged_dialogue = list(latest.dialogue_window)
            merged_dialogue.append(user_msg)
            merged_dialogue.append(asst_msg)

            max_msgs = max_window_turns * 2
            if len(merged_dialogue) > max_msgs:
                merged_dialogue = merged_dialogue[-max_msgs:]

            merged_steps = list(latest.attempted_steps)
            if step_executed and step_executed not in merged_steps:
                merged_steps.append(step_executed)
            for step in session.attempted_steps:
                if step not in merged_steps:
                    merged_steps.append(step)

            latest.dialogue_window = merged_dialogue
            latest.attempted_steps = merged_steps
            latest.identified_model = session.identified_model or latest.identified_model
            if session.pending_confirmation is not _UNSET:
                latest.pending_confirmation = session.pending_confirmation
            latest.confirmed_facts = {**latest.confirmed_facts, **session.confirmed_facts}
            latest.reported_issue = session.reported_issue or latest.reported_issue
            latest.is_escalated = session.is_escalated or latest.is_escalated
            latest.is_resolved = session.is_resolved or latest.is_resolved
            latest.turns_count = max(latest.turns_count, session.turns_count) + 1
            latest.updated_at = now

            try:
                cls.update_session(latest, check_version=True)
                session.dialogue_window = latest.dialogue_window
                session.attempted_steps = latest.attempted_steps
                session.identified_model = latest.identified_model
                session.pending_confirmation = latest.pending_confirmation
                session.confirmed_facts = latest.confirmed_facts
                session.turns_count = latest.turns_count
                session.version = latest.version
                return session
            except SessionConcurrencyError:
                if attempt == max_retries - 1:
                    cls.update_session(latest, check_version=False)
                    session.version = latest.version
                    return session
                time.sleep(0.05 * (attempt + 1))
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
            "pending_confirmation": state.pending_confirmation,
            "recent_messages": [msg.model_dump() for msg in state.dialogue_window],
        }

    @classmethod
    def update_session(cls, session: SessionState, check_version: bool = False) -> None:
        cls._init_db_once()
        session.updated_at = time.time()
        dialogue_json = json.dumps([msg.model_dump() for msg in session.dialogue_window])
        attempted_json = json.dumps(session.attempted_steps)
        confirmed_json = json.dumps(session.confirmed_facts)

        if check_version:
            # Optimistic locking conditional update
            current_version = session.version
            next_version = current_version + 1
            params_update = (
                session.identified_model,
                attempted_json,
                session.pending_confirmation,
                dialogue_json,
                session.updated_at,
                session.reported_issue,
                confirmed_json,
                session.turns_count,
                int(session.is_escalated),
                int(session.is_resolved),
                next_version,
                session.session_id,
                current_version,
            )

            if cls.is_postgres():
                try:
                    with cls._get_pg_conn() as conn:
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE sessions SET
                                        identified_model = %s,
                                        attempted_steps = %s,
                                        pending_confirmation = %s,
                                        dialogue_window = %s,
                                        updated_at = %s,
                                        reported_issue = %s,
                                        confirmed_facts = %s,
                                        turns_count = %s,
                                        is_escalated = %s,
                                        is_resolved = %s,
                                        version = %s
                                    WHERE session_id = %s AND version = %s
                                """, params_update)
                                if cur.rowcount == 0:
                                    raise SessionConcurrencyError(
                                        f"Optimistic lock conflict on PostgreSQL session '{session.session_id}' (version {current_version})."
                                    )
                    session.version = next_version
                    return
                except SessionConcurrencyError:
                    raise
                except Exception as e:
                    logger.error(f"Error updating session in PostgreSQL: {e}. Falling back to SQLite.")

            with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
                with conn:
                    cursor = conn.execute("""
                        UPDATE sessions SET
                            identified_model = ?,
                            attempted_steps = ?,
                            pending_confirmation = ?,
                            dialogue_window = ?,
                            updated_at = ?,
                            reported_issue = ?,
                            confirmed_facts = ?,
                            turns_count = ?,
                            is_escalated = ?,
                            is_resolved = ?,
                            version = ?
                        WHERE session_id = ? AND version = ?
                    """, params_update)
                    if cursor.rowcount == 0:
                        raise SessionConcurrencyError(
                            f"Optimistic lock conflict on SQLite session '{session.session_id}' (version {current_version})."
                        )
            session.version = next_version
            return

        # Upsert mode (inserts new session or resets version unconditionally)
        session.version += 1
        params = (
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
            session.version,
        )

        if cls.is_postgres():
            try:
                with cls._get_pg_conn() as conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO sessions (
                                    session_id, identified_model, attempted_steps, pending_confirmation,
                                    dialogue_window, created_at, updated_at, reported_issue,
                                    confirmed_facts, turns_count, is_escalated, is_resolved, version
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (session_id) DO UPDATE SET
                                    identified_model = EXCLUDED.identified_model,
                                    attempted_steps = EXCLUDED.attempted_steps,
                                    pending_confirmation = EXCLUDED.pending_confirmation,
                                    dialogue_window = EXCLUDED.dialogue_window,
                                    updated_at = EXCLUDED.updated_at,
                                    reported_issue = EXCLUDED.reported_issue,
                                    confirmed_facts = EXCLUDED.confirmed_facts,
                                    turns_count = EXCLUDED.turns_count,
                                    is_escalated = EXCLUDED.is_escalated,
                                    is_resolved = EXCLUDED.is_resolved,
                                    version = EXCLUDED.version
                            """, params)
                return
            except Exception as e:
                logger.error(f"Error updating session in PostgreSQL: {e}. Falling back to SQLite.")

        with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO sessions (
                        session_id, identified_model, attempted_steps, pending_confirmation,
                        dialogue_window, created_at, updated_at, reported_issue,
                        confirmed_facts, turns_count, is_escalated, is_resolved, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        is_resolved = excluded.is_resolved,
                        version = excluded.version
                """, params)

    @classmethod
    def clear_session(cls, session_id: str) -> None:
        cls._init_db_once()
        if cls.is_postgres():
            try:
                with cls._get_pg_conn() as conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
                return
            except Exception as e:
                logger.error(f"Error deleting session from PostgreSQL: {e}. Falling back to SQLite.")

        with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    @classmethod
    def reset_all(cls) -> None:
        cls._init_db_once()
        if cls.is_postgres():
            try:
                with cls._get_pg_conn() as conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM sessions")
                return
            except Exception as e:
                logger.error(f"Error resetting sessions in PostgreSQL: {e}. Falling back to SQLite.")

        with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions")


    @classmethod
    def delete_expired_sessions(cls, ttl_days: int = 30) -> int:
        """Delete inactive sessions older than ttl_days. Returns count of deleted records."""
        cls._init_db_once()
        cutoff = time.time() - (ttl_days * 86400.0)
        deleted_count = 0

        if cls.is_postgres():
            try:
                with cls._get_pg_conn() as conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM sessions WHERE updated_at < %s", (cutoff,))
                            deleted_count = cur.rowcount
                logger.info(f"Deleted {deleted_count} expired sessions older than {ttl_days} days from PostgreSQL.")
                return deleted_count
            except Exception as e:
                logger.error(f"Error pruning expired sessions from PostgreSQL: {e}. Falling back to SQLite.")

        with closing(sqlite3.connect(str(cls._db_path), timeout=30.0, check_same_thread=False)) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
                deleted_count = cursor.rowcount
        logger.info(f"Deleted {deleted_count} expired sessions older than {ttl_days} days from SQLite.")
        return deleted_count

SessionManager = SessionStateManager
