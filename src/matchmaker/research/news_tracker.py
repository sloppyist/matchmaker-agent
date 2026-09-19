"""
Active news tracking for web3 sector.
Monitors RSS feeds and news sources for relevant case studies and implementations.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx

from matchmaker.config import settings
from matchmaker.llm.client import get_llm_client
from matchmaker.research.case_studies import CaseStudyIngester

logger = logging.getLogger(__name__)


# Default RSS feeds for web3 news
DEFAULT_NEWS_SOURCES = [
    # Major crypto/blockchain news
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "type": "rss"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml", "type": "rss"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed", "type": "rss"},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "type": "rss"},
    
    # Solana-specific
    {"name": "Solana News", "url": "https://solana.com/news/rss.xml", "type": "rss"},
    
    # Tech/business with crypto coverage
    {"name": "TechCrunch Crypto", "url": "https://techcrunch.com/tag/cryptocurrency/feed/", "type": "rss"},
    {"name": "Forbes Crypto", "url": "https://www.forbes.com/crypto-blockchain/feed/", "type": "rss"},
]

# Keywords that indicate a real implementation/case study (not just price news)
IMPLEMENTATION_KEYWORDS = [
    "launches", "deployed", "implements", "pilots", "testing", "rolls out",
    "partnership", "integrates", "adoption", "government", "enterprise",
    "real-world", "use case", "case study", "proof of concept", "POC",
    "ministry", "municipality", "university", "hospital", "bank",
    "supply chain", "credentials", "voting", "election", "payments",
    "remittances", "identity", "traceability", "transparency",
]

# Keywords to filter OUT (price speculation, trading news)
EXCLUDE_KEYWORDS = [
    "price prediction", "price analysis", "technical analysis",
    "bullish", "bearish", "pump", "dump", "moon", "whale",
    "trading volume", "market cap", "all-time high", "ATH",
    "memecoin", "airdrop eligibility", "token sale",
]


@dataclass
class NewsArticle:
    """A news article from RSS or API."""
    
    title: str
    url: str
    source: str
    published: Optional[datetime] = None
    summary: str = ""
    content_hash: str = ""
    
    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.url.encode()).hexdigest()[:16]


@dataclass
class NewsSource:
    """A news source configuration."""
    
    name: str
    url: str
    type: str = "rss"  # rss, api
    enabled: bool = True
    last_checked: Optional[datetime] = None
    check_interval_minutes: int = 60


RELEVANCE_CHECK_PROMPT = """You are filtering web3/blockchain news articles to find REAL IMPLEMENTATIONS and CASE STUDIES.

We want to track actual deployments, pilots, and real-world use cases - NOT price speculation or trading news.

Article Title: {title}
Article Summary: {summary}
Source: {source}

Is this article about a REAL IMPLEMENTATION or CASE STUDY? Consider:
- Government/enterprise adopting blockchain
- New product/service launch solving a real problem
- Partnership for real-world deployment
- Pilot program or proof of concept
- University, hospital, municipality using blockchain

Respond with JSON:
{{
    "is_relevant": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "problem_domain": "one of: Credentials & Verification, Public Procurement & Transparency, Supply Chain & Traceability, Payments & Remittances, Identity & Data Management, Civic Participation & Governance, Incentive Systems & Behavior Change, Rights & Revenue Distribution, Funding & Treasury Management, Other, Not Applicable"
}}

Return ONLY valid JSON."""


class NewsTracker:
    """
    Actively tracks web3 news sources and identifies relevant case studies.
    """

    def __init__(self, sources: list[dict] = None):
        self.sources = [NewsSource(**s) for s in (sources or DEFAULT_NEWS_SOURCES)]
        self.llm = get_llm_client()
        self.case_study_ingester = CaseStudyIngester()
        self._seen_urls: set[str] = set()
        self._db = None

    @property
    def db(self):
        """Lazy load database connection."""
        if self._db is None:
            from matchmaker.db.problems import ProblemDatabase
            self._db = ProblemDatabase(skip_test=True)
        return self._db

    def _init_tracking_table(self):
        """Create table to track seen articles."""
        with self.db._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tracked_articles (
                        id SERIAL PRIMARY KEY,
                        url TEXT UNIQUE,
                        title TEXT,
                        source TEXT,
                        is_relevant BOOLEAN,
                        problem_domain TEXT,
                        ingested BOOLEAN DEFAULT FALSE,
                        case_study_id INTEGER,
                        checked_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS tracked_articles_url_idx ON tracked_articles (url);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS tracked_articles_relevant_idx ON tracked_articles (is_relevant);
                """)
                conn.commit()

    def _is_already_seen(self, url: str) -> bool:
        """Check if we've already processed this URL."""
        if url in self._seen_urls:
            return True
        
        try:
            with self.db._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM tracked_articles WHERE url = %s", (url,))
                    if cur.fetchone():
                        self._seen_urls.add(url)
                        return True
        except Exception:
            pass
        return False

    def _mark_as_seen(self, article: NewsArticle, is_relevant: bool, problem_domain: str = None, case_study_id: int = None):
        """Mark an article as processed."""
        self._seen_urls.add(article.url)
        
        try:
            self._init_tracking_table()
            with self.db._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tracked_articles (url, title, source, is_relevant, problem_domain, ingested, case_study_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO UPDATE SET
                            is_relevant = EXCLUDED.is_relevant,
                            problem_domain = EXCLUDED.problem_domain,
                            ingested = EXCLUDED.ingested,
                            case_study_id = EXCLUDED.case_study_id
                        """,
                        (article.url, article.title, article.source, is_relevant, problem_domain, case_study_id is not None, case_study_id),
                    )
                    conn.commit()
        except Exception as e:
            logger.warning(f"Could not mark article as seen: {e}")

    async def fetch_rss(self, source: NewsSource) -> list[NewsArticle]:
        """Fetch articles from an RSS feed."""
        articles = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(source.url, follow_redirects=True)
                response.raise_for_status()
                
                # Parse RSS XML
                root = ElementTree.fromstring(response.content)
                
                # Handle both RSS 2.0 and Atom formats
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
                
                for item in items[:20]:  # Limit to recent 20 articles
                    # RSS 2.0 format
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    pub_date_elem = item.find("pubDate")
                    
                    # Atom format fallback
                    if link_elem is None:
                        link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                        if link_elem is not None:
                            url = link_elem.get("href", "")
                        else:
                            continue
                    else:
                        url = link_elem.text or ""
                    
                    if title_elem is None:
                        title_elem = item.find("{http://www.w3.org/2005/Atom}title")
                    
                    title = title_elem.text if title_elem is not None else ""
                    summary = desc_elem.text if desc_elem is not None else ""
                    
                    # Clean HTML from summary
                    if summary:
                        summary = re.sub(r'<[^>]+>', '', summary)[:500]
                    
                    if title and url:
                        articles.append(NewsArticle(
                            title=title,
                            url=url,
                            source=source.name,
                            summary=summary,
                        ))
                        
        except Exception as e:
            logger.error(f"Error fetching RSS from {source.name}: {e}")
        
        return articles

    def quick_filter(self, article: NewsArticle) -> bool:
        """Quick keyword-based filter before LLM check."""
        text = f"{article.title} {article.summary}".lower()
        
        # Exclude if contains trading/speculation keywords
        for keyword in EXCLUDE_KEYWORDS:
            if keyword.lower() in text:
                return False
        
        # Include if contains implementation keywords
        for keyword in IMPLEMENTATION_KEYWORDS:
            if keyword.lower() in text:
                return True
        
        # Default: check with LLM if unclear
        return True  # Let LLM decide

    async def check_relevance(self, article: NewsArticle) -> tuple[bool, float, str, str]:
        """Use LLM to check if article is a relevant case study."""
        prompt = RELEVANCE_CHECK_PROMPT.format(
            title=article.title,
            summary=article.summary[:500] if article.summary else "No summary available",
            source=article.source,
        )
        
        try:
            response = self.llm.generate(prompt=prompt, temperature=0.1, max_tokens=300)
            
            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()
            
            import json
            data = json.loads(response)
            
            return (
                data.get("is_relevant", False),
                data.get("confidence", 0.0),
                data.get("reason", ""),
                data.get("problem_domain", "Other"),
            )
        except Exception as e:
            logger.error(f"Error checking relevance: {e}")
            return False, 0.0, str(e), "Other"

    async def process_article(self, article: NewsArticle) -> Optional[int]:
        """Process a single article - check relevance and ingest if appropriate."""
        # Skip if already seen
        if self._is_already_seen(article.url):
            return None
        
        # Quick keyword filter
        if not self.quick_filter(article):
            self._mark_as_seen(article, is_relevant=False, problem_domain="Not Applicable")
            logger.debug(f"Filtered out (keywords): {article.title}")
            return None
        
        # LLM relevance check
        is_relevant, confidence, reason, domain = await self.check_relevance(article)
        
        if not is_relevant or confidence < 0.6:
            self._mark_as_seen(article, is_relevant=False, problem_domain=domain)
            logger.debug(f"Filtered out (LLM): {article.title} - {reason}")
            return None
        
        # Ingest as case study
        logger.info(f"Found relevant article: {article.title}")
        try:
            case_study = await self.case_study_ingester.ingest_from_url(article.url, article.source)
            case_study_id = self.case_study_ingester.save_case_study(case_study)
            self._mark_as_seen(article, is_relevant=True, problem_domain=domain, case_study_id=case_study_id)
            logger.info(f"Ingested case study: {case_study.title} (ID: {case_study_id})")
            return case_study_id
        except Exception as e:
            logger.error(f"Error ingesting article: {e}")
            self._mark_as_seen(article, is_relevant=True, problem_domain=domain)
            return None

    async def check_source(self, source: NewsSource) -> list[int]:
        """Check a single news source for new articles."""
        if not source.enabled:
            return []
        
        logger.info(f"Checking news source: {source.name}")
        
        if source.type == "rss":
            articles = await self.fetch_rss(source)
        else:
            logger.warning(f"Unknown source type: {source.type}")
            return []
        
        source.last_checked = datetime.now()
        
        ingested_ids = []
        for article in articles:
            case_study_id = await self.process_article(article)
            if case_study_id:
                ingested_ids.append(case_study_id)
        
        return ingested_ids

    async def check_all_sources(self) -> dict[str, list[int]]:
        """Check all enabled news sources."""
        results = {}
        
        for source in self.sources:
            try:
                ingested = await self.check_source(source)
                results[source.name] = ingested
            except Exception as e:
                logger.error(f"Error checking {source.name}: {e}")
                results[source.name] = []
        
        return results

    async def run_continuous(self, interval_minutes: int = 60):
        """Run continuous news monitoring."""
        logger.info(f"Starting continuous news tracking (interval: {interval_minutes} min)")
        self._init_tracking_table()
        
        while True:
            try:
                results = await self.check_all_sources()
                
                total_ingested = sum(len(ids) for ids in results.values())
                if total_ingested > 0:
                    logger.info(f"Ingested {total_ingested} new case studies")
                else:
                    logger.info("No new relevant articles found")
                
            except Exception as e:
                logger.error(f"Error in news tracking loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(interval_minutes * 60)

    def get_tracking_stats(self) -> dict:
        """Get statistics about tracked articles."""
        try:
            self._init_tracking_table()
            with self.db._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE is_relevant) as relevant,
                            COUNT(*) FILTER (WHERE ingested) as ingested,
                            COUNT(DISTINCT source) as sources
                        FROM tracked_articles
                    """)
                    row = cur.fetchone()
                    
                    cur.execute("""
                        SELECT source, COUNT(*) as count, COUNT(*) FILTER (WHERE is_relevant) as relevant
                        FROM tracked_articles
                        GROUP BY source
                        ORDER BY count DESC
                    """)
                    by_source = [{"source": r[0], "total": r[1], "relevant": r[2]} for r in cur.fetchall()]
                    
                    return {
                        "total_checked": row[0],
                        "relevant": row[1],
                        "ingested": row[2],
                        "sources_tracked": row[3],
                        "by_source": by_source,
                    }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}


async def run_news_tracker(interval_minutes: int = 60):
    """Run the news tracker as a background service."""
    tracker = NewsTracker()
    await tracker.run_continuous(interval_minutes)


def check_news_now() -> dict:
    """Run a single news check (for CLI)."""
    tracker = NewsTracker()
    results = asyncio.run(tracker.check_all_sources())
    return results
