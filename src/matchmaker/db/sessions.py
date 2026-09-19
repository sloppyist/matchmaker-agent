"""PostgreSQL session storage for conversation persistence."""

import json
import logging
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Generator, Optional

import psycopg

from matchmaker.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """A conversation session with a user."""

    id: str
    platform: str  # "telegram" or "whatsapp"
    user_id: str
    state: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat() if self.created_at else None
        d["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return d


class SessionStore:
    """PostgreSQL storage for conversation sessions."""

    def __init__(self, conn_string: Optional[str] = None, skip_test: bool = True):
        self.conn_string = conn_string or settings.database_url

        if not skip_test:
            self._test_connection()

    @contextmanager
    def _get_connection(self) -> Generator[psycopg.Connection, None, None]:
        """Get database connection with context manager."""
        conn = None
        try:
            conn = psycopg.connect(self.conn_string)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def _test_connection(self) -> None:
        """Test database connection and setup."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    logger.info("Session store connection successful")

                    cur.execute("""
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'sessions'
                    """)
                    if not cur.fetchone():
                        logger.warning("Sessions table not found, creating...")
                        self.create_schema()
        except Exception as e:
            logger.error(f"Session store connection failed: {e}")
            raise

    def create_schema(self) -> None:
        """Create database schema for sessions."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        state JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS sessions_platform_user_idx
                    ON sessions (platform, user_id);
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS proposals (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT REFERENCES sessions(id),
                        problem_statement TEXT,
                        design_proposal TEXT,
                        final_rfs TEXT,
                        status TEXT DEFAULT 'draft',
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS proposals_session_idx ON proposals (session_id);
                """)

                conn.commit()
                logger.info("Session schema created successfully")

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, platform, user_id, state, created_at, updated_at
                    FROM sessions WHERE id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if row:
                    return ConversationSession(
                        id=row[0],
                        platform=row[1],
                        user_id=row[2],
                        state=row[3] or {},
                        created_at=row[4],
                        updated_at=row[5],
                    )
                return None

    def get_or_create_session(
        self, platform: str, user_id: str
    ) -> ConversationSession:
        """Get existing session or create new one."""
        session_id = f"{platform}:{user_id}"

        existing = self.get_session(session_id)
        if existing:
            return existing

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (id, platform, user_id, state)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET updated_at = NOW()
                    RETURNING id, platform, user_id, state, created_at, updated_at
                    """,
                    (session_id, platform, user_id, json.dumps({})),
                )
                row = cur.fetchone()
                conn.commit()

                if row:
                    return ConversationSession(
                        id=row[0],
                        platform=row[1],
                        user_id=row[2],
                        state=row[3] or {},
                        created_at=row[4],
                        updated_at=row[5],
                    )
                raise RuntimeError("Failed to create session")

    def update_session_state(self, session_id: str, state: dict[str, Any]) -> None:
        """Update session state."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sessions
                    SET state = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (json.dumps(state, default=str), session_id),
                )
                conn.commit()

    def save_proposal(
        self,
        session_id: str,
        problem_statement: str,
        design_proposal: Optional[str] = None,
        final_rfs: Optional[str] = None,
        status: str = "draft",
    ) -> int:
        """Save a proposal to the database."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO proposals (session_id, problem_statement, design_proposal, final_rfs, status)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (session_id, problem_statement, design_proposal, final_rfs, status),
                )
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else -1

    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
                conn.commit()
