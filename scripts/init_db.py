import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import DB_BACKEND, DATABASE_URL, SQLITE_DB_PATH
from src.state.session import SessionStateManager


def init_database():
    print(f"Configured DB_BACKEND: {DB_BACKEND}")
    if DB_BACKEND == "postgres":
        print(f"Connecting to PostgreSQL at {DATABASE_URL}...")
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
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
                        is_resolved INTEGER DEFAULT 0
                    );
                """)
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public';
                """)
                tables = [r[0] for r in cur.fetchall()]
        conn.close()
        print(f"PostgreSQL initialization complete! Public tables found: {tables}")
    else:
        print(f"Initializing SQLite database at {SQLITE_DB_PATH}...")
        SessionStateManager._init_db_once()
        print("SQLite initialization complete!")


if __name__ == "__main__":
    init_database()
