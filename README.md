# Matchmaker Agent

Multi-agent system that autonomously interviews local actors to uncover "shadow problems," cross-references them with existing solutions (RAG), and generates formal "Request for Solutions" (RFS) proposals for student builders.

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│   Ethnographer  │───▶│   Analyst    │───▶│    Scout    │
│   (Interview)   │    │  (Synthesize)│    │    (RAG)    │
└─────────────────┘    └──────────────┘    └─────────────┘
                                                  │
                                                  ▼
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│  Human Handoff  │◀───│   Designer   │◀───│             │
│   (if rejected) │    │ (Propose)    │    └─────────────┘
└─────────────────┘    └──────────────┘
                              │ (if confirmed)
                              ▼
                       ┌──────────────┐
                       │   Architect  │
                       │  (Generate)  │
                       └──────────────┘
```

### Agents

1. **Ethnographer**: Conducts empathetic interviews to uncover hidden pain points
2. **Analyst**: Synthesizes transcripts into structured problem statements
3. **Scout**: Searches PostgreSQL/pgvector database for existing solutions
4. **Designer**: Proposes solution concepts for user confirmation
5. **Architect**: Generates formal RFS or Connection documents

## Features

- **Multi-channel**: Telegram bot + WhatsApp (via Twilio)
- **Problem-Domain RAG**: Database organized by problem categories, use cases, and briefs
- **LLM Flexibility**: OpenRouter or local LLM support
- **RAG Search**: PostgreSQL with pgvector (HNSW index)
- **Human-in-the-Loop**: Interrupts for user input during interview and design confirmation
- **Persistence**: PostgreSQL for sessions and proposals

### Problem-Domain Approach

The RAG is structured around **recurring problem patterns**, not generic blockchain project listings:

- **Problem Domains**: High-level categories (Credentials, Payments, Supply Chain, etc.)
- **Use Cases**: Specific problems with existing solutions and potential approaches
- **Briefs**: Detailed documents for specific actors working on specific problems

This ensures the agent matches users to **relevant solutions for their specific problem**, whether blockchain-based or traditional.

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- OpenRouter API key OR local LLM (Ollama, vLLM, etc.)

### Installation

```bash
# Clone and install
cd matchmaker-agent
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Database Setup

```bash
# Option 1: Using the setup script
chmod +x scripts/setup_db.sh
./scripts/setup_db.sh

# Option 2: Manual SQL
psql -U postgres -f scripts/setup_db.sql

# Then create tables via CLI
matchmaker setup-db
```

### Configuration

```bash
# Copy example env file
cp .env.example .env

# Edit with your settings
nano .env
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `openrouter` or `local` |
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (from @BotFather) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID (for WhatsApp) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |

### Seed Problem Database

Populate the RAG database with problem domains and use cases:

```bash
matchmaker seed
```

This seeds **9 problem domains** and **14+ use cases** including:
- **Credentials & Verification**: University diplomas, HSE certifications
- **Public Procurement**: Public works budgeting, welfare distribution
- **Payments & Remittances**: Cross-border transfers, crypto-fiat integration
- **Rights & Revenue**: Ticketing, music royalties
- **Civic Participation**: Voting, participatory budgeting
- **Incentive Systems**: Recycling rewards
- **Supply Chain**: Health supply tracking
- **Funding & Treasury**: NGO sustainability, SME crypto treasuries

## Usage

### Interactive CLI (Testing)

```bash
matchmaker interactive
```

### Telegram Bot

```bash
matchmaker telegram
```

### WhatsApp (API Server)

```bash
matchmaker server
```

Configure the webhook URL in Twilio: `https://your-domain.com/whatsapp/webhook`

## Commands

| Command | Description |
|---------|-------------|
| `matchmaker telegram` | Run Telegram bot |
| `matchmaker server` | Run API server (WhatsApp webhook) |
| `matchmaker interactive` | Interactive CLI session |
| `matchmaker setup-db` | Create database schema |
| `matchmaker seed` | Seed problem domains and use cases |
| `matchmaker ingest <url>` | Ingest a case study from a URL |
| `matchmaker case-studies` | List all ingested case studies |
| `matchmaker track-news` | Check all news sources once for case studies |
| `matchmaker track-news-continuous` | Run continuous news monitoring |
| `matchmaker news-stats` | Show news tracking statistics |

## Bot Commands

Users can send these commands via Telegram/WhatsApp:

- `/start` - Begin conversation
- `/restart` - Reset and start over
- `/status` - Check conversation progress

## Project Structure

```
matchmaker-agent/
├── src/matchmaker/
│   ├── agents/           # LangGraph agents and workflow
│   │   ├── graph.py      # Graph definition
│   │   ├── nodes.py      # Agent implementations
│   │   ├── prompts.py    # System prompts
│   │   └── state.py      # State schema
│   ├── db/               # Database modules
│   │   ├── rag.py        # pgvector RAG database
│   │   └── sessions.py   # Session persistence
│   ├── interfaces/       # Messaging interfaces
│   │   ├── base.py       # Message handler
│   │   ├── telegram.py   # Telegram bot
│   │   └── whatsapp.py   # WhatsApp/Twilio
│   ├── llm/              # LLM client
│   │   └── client.py     # OpenRouter/local LLM
│   ├── cli.py            # CLI entry point
│   ├── config.py         # Settings
│   └── server.py         # FastAPI server
├── scripts/
│   ├── setup_db.sh       # Database setup script
│   └── setup_db.sql      # SQL schema
├── specs.md              # Original specifications
├── .env.example          # Environment template
├── pyproject.toml        # Project configuration
└── requirements.txt      # Dependencies
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linting
ruff check src/

# Run tests
pytest
```

## Active News Tracking

The agent **actively monitors web3 news sources** to discover new case studies and implementations:

```bash
# Check all news sources once
matchmaker track-news

# Run continuous monitoring (checks every 60 minutes)
matchmaker track-news-continuous

# Custom interval (every 30 minutes)
matchmaker track-news-continuous --interval 30

# View tracking statistics
matchmaker news-stats
```

### Default News Sources

The tracker monitors these RSS feeds by default:
- **CoinDesk**, **The Block**, **Decrypt**, **Cointelegraph** (general crypto)
- **Solana News** (Solana-specific)
- **TechCrunch Crypto**, **Forbes Crypto** (mainstream tech)

### How It Works

1. **Fetch**: Pulls latest articles from RSS feeds
2. **Quick Filter**: Keyword-based filtering (excludes price speculation, includes implementation keywords)
3. **LLM Relevance Check**: Determines if article is a real implementation/case study
4. **Extract & Store**: Parses structured data and saves to database
5. **Scout Integration**: Case studies appear in agent's problem analysis

### Relevance Filtering

The tracker filters for **real implementations**, not trading news:

✅ **Included**: Government adopting blockchain, enterprise deployments, pilots, partnerships, real-world use cases

❌ **Excluded**: Price predictions, technical analysis, trading volume, memecoins, airdrops

## Manual Case Study Ingestion

You can also manually ingest specific articles:

```bash
# Ingest from a URL
matchmaker ingest "https://www.forbes.com/sites/boazsobrado/2025/11/11/bolivia-tests-election-tool-on-solana-to-reinforce-democracy/" --source Forbes

# List all case studies
matchmaker case-studies
```

The ingester:
1. Fetches the article content
2. Uses LLM to extract structured data (entity, location, problem domain, chains, etc.)
3. Stores in the database with vector embeddings for semantic search
4. Scout agent automatically includes relevant case studies when analyzing problems

### Programmatic Ingestion

```python
import asyncio
from matchmaker.research.case_studies import ingest_case_study_from_url

# Ingest and save
case_study = asyncio.run(ingest_case_study_from_url(
    "https://example.com/article",
    source="Source Name"
))

print(f"Saved: {case_study.title}")
print(f"Entity: {case_study.entity}")
print(f"Domain: {case_study.problem_domain}")
print(f"Chains: {case_study.chains}")
```

## Adding to the Problem Database

### Adding a Use Case

```python
from matchmaker.db.problems import ProblemDatabase

db = ProblemDatabase()

# First ensure domain exists
db.add_domain(
    name="Credentials & Verification",
    description="Problems related to verifying qualifications...",
    keywords=["diploma", "certificate", "verification"]
)

# Add use case
db.add_use_case(
    domain_name="Credentials & Verification",
    name="Professional License Verification",
    problem_statement="Professionals must re-verify licenses across jurisdictions...",
    current_practices="Manual verification, siloed databases",
    blockchain_justification="Portable, verifiable credentials reduce friction",
    existing_solutions=[
        {"name": "Dock.io", "type": "blockchain", "description": "Verifiable credentials"},
        {"name": "State licensing boards", "type": "traditional", "description": "Current system"}
    ],
    potential_approaches=[
        {"name": "Cross-State License Passport", "description": "ZK proofs for license validity"}
    ],
    tags=["licensing", "credentials", "professional"],
    chains=["solana", "ethereum"]
)
```

### Searching Use Cases

```python
# Search by problem description
results = db.search_use_cases(
    query="verifying employee training certifications",
    limit=5
)

# Filter by ecosystem
results = db.search_use_cases(
    query="cross-border payments for remittances",
    chain="solana"
)
```

## Local LLM Setup

To use a local LLM instead of OpenRouter:

1. Start your local LLM server (e.g., Ollama):
   ```bash
   ollama serve
   ollama pull llama3.2
   ```

2. Update `.env`:
   ```
   LLM_PROVIDER=local
   LOCAL_LLM_URL=http://localhost:11434/v1
   LOCAL_LLM_MODEL=llama3.2
   ```

## License

MIT
