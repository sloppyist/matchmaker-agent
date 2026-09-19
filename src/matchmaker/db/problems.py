"""PostgreSQL database for problem domains, use cases, and briefs."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

import psycopg
from sentence_transformers import SentenceTransformer

from matchmaker.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProblemDomain:
    """A high-level problem category."""

    id: int
    name: str  # e.g., "Credentials & Verification"
    description: str
    keywords: list[str]  # For matching during interviews


@dataclass
class UseCase:
    """A specific problem pattern with existing and potential solutions."""

    id: int
    domain_id: int
    name: str  # e.g., "University Diploma Verification"
    problem_statement: str  # The actual problem being solved
    current_practices: str  # How actors currently handle this
    blockchain_justification: Optional[str]  # Why blockchain might help (or not)
    existing_solutions: list[dict]  # Both blockchain and non-blockchain
    potential_approaches: list[dict]  # Novel concepts that could be built
    implementation_complexity: str  # Low/Medium/High
    tags: list[str]
    chains: list[str]  # Relevant blockchain ecosystems
    similarity: float = 0.0


@dataclass
class Brief:
    """A detailed document for a specific actor working on a specific problem."""

    id: int
    use_case_id: int
    title: str
    entity: str  # The organization/actor this brief is for
    author: str
    version: str
    context: str  # Full problem context
    assessment: str  # Analysis and recommendations
    implementation: str  # How to proceed
    content_hash: Optional[str]  # For document integrity
    similarity: float = 0.0


class ProblemDatabase:
    """PostgreSQL database for problem-domain focused RAG."""

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

    def create_schema(self) -> None:
        """Create database schema for problem-domain RAG."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Problem domains (categories)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS problem_domains (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT NOT NULL,
                        keywords TEXT[],
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                # Use cases (specific problem patterns)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS use_cases (
                        id SERIAL PRIMARY KEY,
                        domain_id INTEGER REFERENCES problem_domains(id),
                        name TEXT NOT NULL,
                        problem_statement TEXT NOT NULL,
                        current_practices TEXT,
                        blockchain_justification TEXT,
                        existing_solutions JSONB DEFAULT '[]',
                        potential_approaches JSONB DEFAULT '[]',
                        implementation_complexity TEXT,
                        tags TEXT[],
                        chains TEXT[],
                        embedding vector({self.embedding_dim}),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                # Briefs (detailed documents for specific actors)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS briefs (
                        id SERIAL PRIMARY KEY,
                        use_case_id INTEGER REFERENCES use_cases(id),
                        title TEXT NOT NULL,
                        entity TEXT NOT NULL,
                        author TEXT,
                        version TEXT DEFAULT '0.1',
                        context TEXT,
                        assessment TEXT,
                        implementation TEXT,
                        content_hash TEXT,
                        embedding vector({self.embedding_dim}),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)

                # Indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS use_cases_embedding_idx
                    ON use_cases USING hnsw (embedding vector_cosine_ops);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS briefs_embedding_idx
                    ON briefs USING hnsw (embedding vector_cosine_ops);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS use_cases_domain_idx ON use_cases (domain_id);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS use_cases_tags_idx ON use_cases USING gin(tags);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS use_cases_chains_idx ON use_cases USING gin(chains);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS briefs_entity_idx ON briefs (entity);
                """)

                conn.commit()
                logger.info("Problem database schema created successfully")

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return self.model.encode(text).tolist()

    # Domain operations
    def add_domain(self, name: str, description: str, keywords: list[str] = None) -> int:
        """Add a problem domain."""
        keywords = keywords or []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO problem_domains (name, description, keywords)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
                    RETURNING id
                    """,
                    (name, description, keywords),
                )
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else -1

    def get_domain_by_name(self, name: str) -> Optional[ProblemDomain]:
        """Get a domain by name."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, description, keywords FROM problem_domains WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
                if row:
                    return ProblemDomain(id=row[0], name=row[1], description=row[2], keywords=row[3] or [])
                return None

    # Use case operations
    def add_use_case(
        self,
        domain_name: str,
        name: str,
        problem_statement: str,
        current_practices: str = "",
        blockchain_justification: str = "",
        existing_solutions: list[dict] = None,
        potential_approaches: list[dict] = None,
        implementation_complexity: str = "Medium",
        tags: list[str] = None,
        chains: list[str] = None,
    ) -> int:
        """Add a use case to a domain."""
        import json

        # Get or create domain
        domain = self.get_domain_by_name(domain_name)
        if not domain:
            raise ValueError(f"Domain '{domain_name}' not found. Create it first.")

        # Create embedding from problem statement + name
        embedding_text = f"{name} {problem_statement}"
        embedding = self.embed(embedding_text)

        existing_solutions = existing_solutions or []
        potential_approaches = potential_approaches or []
        tags = tags or []
        chains = [c.lower() for c in (chains or [])]

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO use_cases (
                        domain_id, name, problem_statement, current_practices,
                        blockchain_justification, existing_solutions, potential_approaches,
                        implementation_complexity, tags, chains, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        domain.id,
                        name,
                        problem_statement,
                        current_practices,
                        blockchain_justification,
                        json.dumps(existing_solutions),
                        json.dumps(potential_approaches),
                        implementation_complexity,
                        tags,
                        chains,
                        embedding,
                    ),
                )
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else -1

    def search_use_cases(
        self,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.25,
        domain_name: Optional[str] = None,
        chain: Optional[str] = None,
    ) -> list[UseCase]:
        """Search for relevant use cases based on a problem description."""
        query_embedding = self.embed(query)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                base_query = """
                    SELECT uc.id, uc.domain_id, uc.name, uc.problem_statement,
                           uc.current_practices, uc.blockchain_justification,
                           uc.existing_solutions, uc.potential_approaches,
                           uc.implementation_complexity, uc.tags, uc.chains,
                           1 - (uc.embedding <=> %s::vector) as similarity
                    FROM use_cases uc
                    JOIN problem_domains pd ON uc.domain_id = pd.id
                    WHERE 1 - (uc.embedding <=> %s::vector) > %s
                """
                params = [query_embedding, query_embedding, similarity_threshold]

                if domain_name:
                    base_query += " AND pd.name = %s"
                    params.append(domain_name)

                if chain:
                    base_query += " AND %s = ANY(uc.chains)"
                    params.append(chain.lower())

                base_query += " ORDER BY uc.embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, limit])

                cur.execute(base_query, params)
                rows = cur.fetchall()

                return [
                    UseCase(
                        id=row[0],
                        domain_id=row[1],
                        name=row[2],
                        problem_statement=row[3],
                        current_practices=row[4] or "",
                        blockchain_justification=row[5],
                        existing_solutions=row[6] or [],
                        potential_approaches=row[7] or [],
                        implementation_complexity=row[8] or "Medium",
                        tags=row[9] or [],
                        chains=row[10] or [],
                        similarity=row[11],
                    )
                    for row in rows
                ]

    # Brief operations
    def add_brief(
        self,
        use_case_name: str,
        title: str,
        entity: str,
        author: str = "",
        version: str = "0.1",
        context: str = "",
        assessment: str = "",
        implementation: str = "",
    ) -> int:
        """Add a brief for a specific use case and entity."""
        import hashlib

        # Find use case
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM use_cases WHERE name = %s", (use_case_name,))
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Use case '{use_case_name}' not found.")
                use_case_id = row[0]

        # Create embedding from full brief content
        full_content = f"{title} {entity} {context} {assessment}"
        embedding = self.embed(full_content)
        content_hash = hashlib.sha256(full_content.encode()).hexdigest()[:16]

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO briefs (
                        use_case_id, title, entity, author, version,
                        context, assessment, implementation, content_hash, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        use_case_id,
                        title,
                        entity,
                        author,
                        version,
                        context,
                        assessment,
                        implementation,
                        content_hash,
                        embedding,
                    ),
                )
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else -1

    def search_briefs(
        self,
        query: str,
        limit: int = 3,
        similarity_threshold: float = 0.25,
        entity: Optional[str] = None,
    ) -> list[Brief]:
        """Search for relevant briefs."""
        query_embedding = self.embed(query)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                base_query = """
                    SELECT id, use_case_id, title, entity, author, version,
                           context, assessment, implementation, content_hash,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM briefs
                    WHERE 1 - (embedding <=> %s::vector) > %s
                """
                params = [query_embedding, query_embedding, similarity_threshold]

                if entity:
                    base_query += " AND entity ILIKE %s"
                    params.append(f"%{entity}%")

                base_query += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, limit])

                cur.execute(base_query, params)
                rows = cur.fetchall()

                return [
                    Brief(
                        id=row[0],
                        use_case_id=row[1],
                        title=row[2],
                        entity=row[3],
                        author=row[4] or "",
                        version=row[5] or "0.1",
                        context=row[6] or "",
                        assessment=row[7] or "",
                        implementation=row[8] or "",
                        content_hash=row[9],
                        similarity=row[10],
                    )
                    for row in rows
                ]

    def get_all_domains(self) -> list[ProblemDomain]:
        """Get all problem domains."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, description, keywords FROM problem_domains ORDER BY name")
                rows = cur.fetchall()
                return [
                    ProblemDomain(id=row[0], name=row[1], description=row[2], keywords=row[3] or [])
                    for row in rows
                ]
