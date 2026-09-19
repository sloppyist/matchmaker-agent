"""PostgreSQL RAG database with pgvector for solution matching."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional

import psycopg
from sentence_transformers import SentenceTransformer

from matchmaker.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Solution:
    """A solution from the ecosystem database."""

    id: int
    name: str
    description: str
    category: str
    tags: list[str]
    url: Optional[str]
    chains: list[str] = None  # e.g., ["solana", "ethereum", "polygon"]
    similarity: float = 0.0

    def __post_init__(self):
        if self.chains is None:
            self.chains = []


class RAGDatabase:
    """PostgreSQL database with pgvector for RAG-based solution matching."""

    def __init__(
        self,
        conn_string: Optional[str] = None,
        embedding_model: Optional[str] = None,
        skip_test: bool = True,
    ):
        self.conn_string = conn_string or settings.database_url
        model_name = embedding_model or settings.embedding_model
        self.embedding_dim = settings.embedding_dimension
        self._model: Optional[SentenceTransformer] = None
        self._model_name = model_name

        if not skip_test:
            self._test_connection()

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

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
                    logger.info("Database connection successful")

                    cur.execute("""
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'solutions'
                    """)
                    if not cur.fetchone():
                        logger.warning("Solutions table not found, creating...")
                        self.create_schema()
                    else:
                        logger.info("Solutions table found")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def create_schema(self) -> None:
        """Create database schema for solutions and conversations."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS solutions (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        category TEXT,
                        tags TEXT[],
                        chains TEXT[] DEFAULT ARRAY[]::TEXT[],
                        url TEXT,
                        embedding vector({self.embedding_dim}),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS solutions_embedding_idx
                    ON solutions USING hnsw (embedding vector_cosine_ops);
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS solutions_category_idx ON solutions (category);
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS solutions_tags_idx ON solutions USING gin(tags);
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS solutions_chains_idx ON solutions USING gin(chains);
                """)

                conn.commit()
                logger.info("Database schema created successfully")

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return self.model.encode(text).tolist()

    def add_solution(
        self,
        name: str,
        description: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        chains: Optional[list[str]] = None,
        url: Optional[str] = None,
    ) -> int:
        """Add a solution to the database."""
        embedding = self.embed(f"{name} {description}")
        tags = tags or []
        chains = [c.lower() for c in (chains or [])]

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO solutions (name, description, category, tags, chains, url, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (name, description, category, tags, chains, url, embedding),
                )
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else -1

    def search_solutions(
        self,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.3,
        category: Optional[str] = None,
        chain: Optional[str] = None,
    ) -> list[Solution]:
        """
        Search for similar solutions using vector similarity.
        
        Args:
            query: Search query text
            limit: Max results to return
            similarity_threshold: Minimum similarity score (0-1)
            category: Filter by category (optional)
            chain: Filter by blockchain/ecosystem (optional, e.g., 'solana', 'ethereum')
                   If None, returns multi-chain results (default behavior)
        """
        query_embedding = self.embed(query)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Build query with optional filters
                base_query = """
                    SELECT id, name, description, category, tags, chains, url,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM solutions
                    WHERE 1 - (embedding <=> %s::vector) > %s
                """
                params = [query_embedding, query_embedding, similarity_threshold]

                if category:
                    base_query += " AND category = %s"
                    params.append(category)

                if chain:
                    base_query += " AND %s = ANY(chains)"
                    params.append(chain.lower())

                base_query += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, limit])

                cur.execute(base_query, params)

                rows = cur.fetchall()
                return [
                    Solution(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        category=row[3] or "",
                        tags=row[4] or [],
                        chains=row[5] or [],
                        url=row[6],
                        similarity=row[7],
                    )
                    for row in rows
                ]

    def get_all_solutions(self, limit: int = 100, chain: Optional[str] = None) -> list[Solution]:
        """Get all solutions from the database, optionally filtered by chain."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if chain:
                    cur.execute(
                        """
                        SELECT id, name, description, category, tags, chains, url
                        FROM solutions
                        WHERE %s = ANY(chains)
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (chain.lower(), limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, name, description, category, tags, chains, url
                        FROM solutions
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
                return [
                    Solution(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        category=row[3] or "",
                        tags=row[4] or [],
                        chains=row[5] or [],
                        url=row[6],
                    )
                    for row in rows
                ]
