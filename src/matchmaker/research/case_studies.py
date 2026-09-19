"""
Case study ingestion module.
Fetches, parses, and adds real-world implementations to the RAG database.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

from matchmaker.config import settings
from matchmaker.llm.client import get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class CaseStudy:
    """A real-world implementation or case study."""

    id: Optional[int] = None
    title: str = ""
    url: str = ""
    source: str = ""  # e.g., "Forbes", "CoinDesk", "Official Announcement"
    date_published: Optional[str] = None
    
    # Extracted structured data
    entity: str = ""  # Who implemented it (e.g., "Bolivia Electoral Authority")
    location: str = ""  # Country/region
    problem_domain: str = ""  # Maps to our problem domains
    use_case: str = ""  # Specific use case it addresses
    
    summary: str = ""  # Brief summary of what was implemented
    technology_stack: list[str] = None  # e.g., ["solana", "anchor"]
    chains: list[str] = None  # Blockchain ecosystems used
    
    outcomes: str = ""  # Results/impact if known
    status: str = "announced"  # announced, pilot, production, discontinued
    
    tags: list[str] = None
    raw_content: str = ""  # Original fetched content
    content_hash: str = ""  # For deduplication
    
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.technology_stack is None:
            self.technology_stack = []
        if self.chains is None:
            self.chains = []
        if self.tags is None:
            self.tags = []


CASE_STUDY_EXTRACTION_PROMPT = """You are a research analyst extracting structured information from articles about blockchain/technology implementations.

Given the article content below, extract the following information in JSON format:

{
    "title": "Title of the case study/implementation",
    "entity": "Organization that implemented this (government, company, NGO)",
    "location": "Country or region",
    "problem_domain": "One of: Credentials & Verification, Public Procurement & Transparency, Supply Chain & Traceability, Payments & Remittances, Identity & Data Management, Civic Participation & Governance, Incentive Systems & Behavior Change, Rights & Revenue Distribution, Funding & Treasury Management, Other",
    "use_case": "Specific problem being solved (e.g., 'Election Transparency', 'Diploma Verification')",
    "summary": "2-3 sentence summary of what was implemented and why",
    "technology_stack": ["list", "of", "technologies", "used"],
    "chains": ["blockchain", "ecosystems", "e.g.", "solana", "ethereum"],
    "outcomes": "Results or expected impact (if mentioned)",
    "status": "One of: announced, pilot, production, discontinued",
    "tags": ["relevant", "tags", "for", "search"]
}

If information is not available in the article, use empty string or empty list.
Return ONLY valid JSON, no other text.

Article content:
"""


class CaseStudyIngester:
    """Ingests case studies from URLs and adds them to the RAG database."""

    def __init__(self):
        self.llm = get_llm_client()
        self._db = None

    @property
    def db(self):
        """Lazy load database connection."""
        if self._db is None:
            from matchmaker.db.problems import ProblemDatabase
            self._db = ProblemDatabase(skip_test=True)
        return self._db

    async def fetch_url(self, url: str) -> str:
        """Fetch content from a URL."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; MatchmakerBot/1.0; +https://matchmaker-agent.local)"
            }
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    def extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML content."""
        # Simple extraction - strip HTML tags
        import re
        
        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Truncate to reasonable length for LLM
        return text[:8000]

    def extract_case_study_info(self, content: str, url: str, source: str = "") -> CaseStudy:
        """Use LLM to extract structured case study information."""
        prompt = CASE_STUDY_EXTRACTION_PROMPT + content

        try:
            response = self.llm.generate(
                prompt=prompt,
                temperature=0.1,  # Low temperature for structured extraction
                max_tokens=1000,
            )
            
            # Parse JSON response
            # Handle potential markdown code blocks
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()
            
            data = json.loads(response)
            
            # Create content hash for deduplication
            content_hash = hashlib.sha256(content[:2000].encode()).hexdigest()[:16]
            
            return CaseStudy(
                title=data.get("title", ""),
                url=url,
                source=source,
                entity=data.get("entity", ""),
                location=data.get("location", ""),
                problem_domain=data.get("problem_domain", "Other"),
                use_case=data.get("use_case", ""),
                summary=data.get("summary", ""),
                technology_stack=data.get("technology_stack", []),
                chains=[c.lower() for c in data.get("chains", [])],
                outcomes=data.get("outcomes", ""),
                status=data.get("status", "announced"),
                tags=data.get("tags", []),
                raw_content=content[:5000],
                content_hash=content_hash,
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise ValueError(f"Could not extract structured data from content: {e}")
        except Exception as e:
            logger.error(f"Error extracting case study info: {e}")
            raise

    async def ingest_from_url(self, url: str, source: str = "") -> CaseStudy:
        """
        Fetch a URL, extract case study information, and return structured data.
        
        Args:
            url: URL to fetch
            source: Source name (e.g., "Forbes", "CoinDesk")
            
        Returns:
            CaseStudy with extracted information
        """
        logger.info(f"Fetching case study from: {url}")
        
        # Fetch content
        html = await self.fetch_url(url)
        
        # Extract text
        text = self.extract_text_from_html(html)
        
        if not source:
            # Try to extract source from URL
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            source = domain.replace("www.", "").split(".")[0].title()
        
        # Extract structured info
        case_study = self.extract_case_study_info(text, url, source)
        
        logger.info(f"Extracted case study: {case_study.title}")
        return case_study

    def save_case_study(self, case_study: CaseStudy) -> int:
        """Save a case study to the database."""
        from matchmaker.db.problems import ProblemDatabase
        
        db = ProblemDatabase(skip_test=True)
        
        with db._get_connection() as conn:
            with conn.cursor() as cur:
                # Ensure case_studies table exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS case_studies (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT UNIQUE,
                        source TEXT,
                        date_published TEXT,
                        entity TEXT,
                        location TEXT,
                        problem_domain TEXT,
                        use_case TEXT,
                        summary TEXT,
                        technology_stack TEXT[],
                        chains TEXT[],
                        outcomes TEXT,
                        status TEXT DEFAULT 'announced',
                        tags TEXT[],
                        raw_content TEXT,
                        content_hash TEXT,
                        embedding vector(384),
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS case_studies_embedding_idx
                    ON case_studies USING hnsw (embedding vector_cosine_ops);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS case_studies_domain_idx ON case_studies (problem_domain);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS case_studies_chains_idx ON case_studies USING gin(chains);
                """)
                
                # Generate embedding
                embedding_text = f"{case_study.title} {case_study.summary} {case_study.use_case}"
                embedding = db.embed(embedding_text)
                
                # Insert case study
                cur.execute(
                    """
                    INSERT INTO case_studies (
                        title, url, source, entity, location, problem_domain,
                        use_case, summary, technology_stack, chains, outcomes,
                        status, tags, raw_content, content_hash, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        outcomes = EXCLUDED.outcomes,
                        status = EXCLUDED.status,
                        embedding = EXCLUDED.embedding
                    RETURNING id
                    """,
                    (
                        case_study.title,
                        case_study.url,
                        case_study.source,
                        case_study.entity,
                        case_study.location,
                        case_study.problem_domain,
                        case_study.use_case,
                        case_study.summary,
                        case_study.technology_stack,
                        case_study.chains,
                        case_study.outcomes,
                        case_study.status,
                        case_study.tags,
                        case_study.raw_content,
                        case_study.content_hash,
                        embedding,
                    ),
                )
                result = cur.fetchone()
                conn.commit()
                
                case_study.id = result[0] if result else -1
                logger.info(f"Saved case study with ID: {case_study.id}")
                return case_study.id

    def search_case_studies(
        self,
        query: str,
        limit: int = 5,
        chain: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> list[CaseStudy]:
        """Search case studies by similarity."""
        from matchmaker.db.problems import ProblemDatabase
        
        db = ProblemDatabase(skip_test=True)
        query_embedding = db.embed(query)
        
        with db._get_connection() as conn:
            with conn.cursor() as cur:
                base_query = """
                    SELECT id, title, url, source, entity, location, problem_domain,
                           use_case, summary, technology_stack, chains, outcomes,
                           status, tags, created_at,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM case_studies
                    WHERE 1 - (embedding <=> %s::vector) > 0.2
                """
                params = [query_embedding, query_embedding]
                
                if chain:
                    base_query += " AND %s = ANY(chains)"
                    params.append(chain.lower())
                
                if domain:
                    base_query += " AND problem_domain = %s"
                    params.append(domain)
                
                base_query += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, limit])
                
                try:
                    cur.execute(base_query, params)
                    rows = cur.fetchall()
                except Exception:
                    # Table might not exist yet
                    return []
                
                return [
                    CaseStudy(
                        id=row[0],
                        title=row[1],
                        url=row[2],
                        source=row[3],
                        entity=row[4],
                        location=row[5],
                        problem_domain=row[6],
                        use_case=row[7],
                        summary=row[8],
                        technology_stack=row[9] or [],
                        chains=row[10] or [],
                        outcomes=row[11],
                        status=row[12],
                        tags=row[13] or [],
                        created_at=row[14],
                    )
                    for row in rows
                ]


async def ingest_case_study_from_url(url: str, source: str = "") -> CaseStudy:
    """
    Convenience function to ingest a case study from a URL.
    
    Usage:
        case_study = await ingest_case_study_from_url(
            "https://www.forbes.com/...",
            source="Forbes"
        )
    """
    ingester = CaseStudyIngester()
    case_study = await ingester.ingest_from_url(url, source)
    ingester.save_case_study(case_study)
    return case_study
