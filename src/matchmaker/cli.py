"""CLI interface for Matchmaker Agent."""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_telegram():
    """Run the Telegram bot."""
    from matchmaker.interfaces.telegram import run_telegram_bot

    run_telegram_bot()


def run_server():
    """Run the FastAPI server (for WhatsApp webhook)."""
    from matchmaker.server import run_server

    run_server()


def run_setup_db():
    """Set up the database schema."""
    from matchmaker.db.problems import ProblemDatabase
    from matchmaker.db.sessions import SessionStore

    logger.info("Setting up database schema...")

    problem_db = ProblemDatabase(skip_test=True)
    problem_db.create_schema()
    logger.info("Problem database schema created")

    session_store = SessionStore(skip_test=True)
    session_store.create_schema()
    logger.info("Session store schema created")

    logger.info("Database setup complete!")


def run_interactive():
    """Run an interactive CLI session for testing."""
    from langchain_core.messages import HumanMessage

    from matchmaker.agents.graph import create_matchmaker_graph

    print("\n🤝 Matchmaker Agent - Interactive Mode")
    print("=" * 50)
    print("Type your messages to interact with the agent.")
    print("Commands: /quit, /restart, /status")
    print("=" * 50 + "\n")

    graph = create_matchmaker_graph()
    config = {"configurable": {"thread_id": "cli-session"}}

    # Start the conversation
    print("Agent: Starting interview...")
    result = graph.invoke(
        {"messages": [HumanMessage(content="[Starting interview]")]},
        config,
    )

    # Print initial response
    if result.get("messages"):
        for msg in result["messages"]:
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"\nAgent: {msg.content}\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "/quit":
                print("\nGoodbye!")
                break

            if user_input.lower() == "/restart":
                graph = create_matchmaker_graph()
                config = {"configurable": {"thread_id": "cli-session"}}
                print("\n[Conversation restarted]\n")
                result = graph.invoke(
                    {"messages": [HumanMessage(content="[Starting interview]")]},
                    config,
                )
                if result.get("messages"):
                    for msg in result["messages"]:
                        if hasattr(msg, "type") and msg.type == "ai":
                            print(f"\nAgent: {msg.content}\n")
                continue

            if user_input.lower() == "/status":
                state = graph.get_state(config)
                if state.values:
                    print(f"\nStatus: {state.values.get('status', 'unknown')}")
                    print(f"Interview turns: {state.values.get('interview_turns', 0)}\n")
                else:
                    print("\nNo active conversation\n")
                continue

            # Process message
            result = graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config,
            )

            # Print responses
            if result.get("messages"):
                for msg in result["messages"]:
                    if hasattr(msg, "type") and msg.type == "ai":
                        print(f"\nAgent: {msg.content}\n")

            # Check if complete
            if result.get("status") == "complete":
                print("\n[Conversation complete]")
                print("Type /restart to start a new conversation or /quit to exit.\n")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            print(f"\nError: {e}\n")


def seed_problems():
    """Seed the database with problem domains and use cases."""
    from matchmaker.data.problem_domains import PROBLEM_DOMAINS, USE_CASES
    from matchmaker.db.problems import ProblemDatabase

    logger.info("Seeding problem database...")
    logger.info(f"Domains: {len(PROBLEM_DOMAINS)}, Use cases: {len(USE_CASES)}")

    db = ProblemDatabase(skip_test=True)

    # Add domains first
    domain_count = 0
    for domain in PROBLEM_DOMAINS:
        try:
            db.add_domain(
                name=domain["name"],
                description=domain["description"],
                keywords=domain.get("keywords", []),
            )
            logger.info(f"Added domain: {domain['name']}")
            domain_count += 1
        except Exception as e:
            logger.warning(f"Could not add domain {domain['name']}: {e}")

    # Add use cases
    usecase_count = 0
    for uc in USE_CASES:
        try:
            db.add_use_case(
                domain_name=uc["domain"],
                name=uc["name"],
                problem_statement=uc["problem_statement"],
                current_practices=uc.get("current_practices", ""),
                blockchain_justification=uc.get("blockchain_justification", ""),
                existing_solutions=uc.get("existing_solutions", []),
                potential_approaches=uc.get("potential_approaches", []),
                implementation_complexity=uc.get("implementation_complexity", "Medium"),
                tags=uc.get("tags", []),
                chains=uc.get("chains", []),
            )
            logger.info(f"Added use case: {uc['name']}")
            usecase_count += 1
        except Exception as e:
            logger.warning(f"Could not add use case {uc['name']}: {e}")

    logger.info(f"Seeding complete! Added {domain_count} domains, {usecase_count} use cases.")


def ingest_case_study(url: str, source: str = ""):
    """Ingest a case study from a URL."""
    import asyncio
    from matchmaker.research.case_studies import CaseStudyIngester

    logger.info(f"Ingesting case study from: {url}")

    async def run():
        ingester = CaseStudyIngester()
        case_study = await ingester.ingest_from_url(url, source)
        
        print(f"\n📰 Extracted Case Study:")
        print(f"   Title: {case_study.title}")
        print(f"   Entity: {case_study.entity}")
        print(f"   Location: {case_study.location}")
        print(f"   Domain: {case_study.problem_domain}")
        print(f"   Use Case: {case_study.use_case}")
        print(f"   Chains: {', '.join(case_study.chains)}")
        print(f"   Status: {case_study.status}")
        print(f"\n   Summary: {case_study.summary}")
        
        # Save to database
        case_id = ingester.save_case_study(case_study)
        print(f"\n✅ Saved to database with ID: {case_id}")
        return case_study

    return asyncio.run(run())


def list_case_studies():
    """List all case studies in the database."""
    from matchmaker.research.case_studies import CaseStudyIngester

    ingester = CaseStudyIngester()
    
    # Search with empty query to get all
    case_studies = ingester.search_case_studies("", limit=50)
    
    if not case_studies:
        print("No case studies found. Use 'matchmaker ingest <url>' to add some.")
        return
    
    print(f"\n📚 Case Studies ({len(case_studies)} found):\n")
    for cs in case_studies:
        chains = ', '.join(cs.chains) if cs.chains else 'N/A'
        print(f"  [{cs.id}] {cs.title}")
        print(f"      Entity: {cs.entity} | Location: {cs.location}")
        print(f"      Domain: {cs.problem_domain} | Chains: {chains}")
        print(f"      URL: {cs.url}")
        print()


def track_news_once():
    """Run a single news check across all sources."""
    from matchmaker.research.news_tracker import NewsTracker
    import asyncio

    print("\n🔍 Checking news sources for relevant case studies...\n")
    
    tracker = NewsTracker()
    results = asyncio.run(tracker.check_all_sources())
    
    total_ingested = 0
    for source, ids in results.items():
        if ids:
            print(f"  ✅ {source}: Ingested {len(ids)} new case studies")
            total_ingested += len(ids)
        else:
            print(f"  ⏭️  {source}: No new relevant articles")
    
    print(f"\n📊 Total: {total_ingested} new case studies ingested")
    
    # Show stats
    stats = tracker.get_tracking_stats()
    if "total_checked" in stats:
        print(f"\n📈 Tracking Stats:")
        print(f"   Total articles checked: {stats['total_checked']}")
        print(f"   Relevant articles: {stats['relevant']}")
        print(f"   Ingested as case studies: {stats['ingested']}")


def track_news_continuous(interval: int = 60):
    """Run continuous news tracking."""
    from matchmaker.research.news_tracker import run_news_tracker
    import asyncio

    print(f"\n🔄 Starting continuous news tracking (interval: {interval} minutes)")
    print("   Press Ctrl+C to stop\n")
    
    try:
        asyncio.run(run_news_tracker(interval))
    except KeyboardInterrupt:
        print("\n\nStopped news tracking.")


def show_news_stats():
    """Show news tracking statistics."""
    from matchmaker.research.news_tracker import NewsTracker

    tracker = NewsTracker()
    stats = tracker.get_tracking_stats()
    
    if "error" in stats:
        print(f"Error: {stats['error']}")
        return
    
    print("\n📊 News Tracking Statistics\n")
    print(f"   Total articles checked: {stats.get('total_checked', 0)}")
    print(f"   Relevant articles: {stats.get('relevant', 0)}")
    print(f"   Ingested as case studies: {stats.get('ingested', 0)}")
    print(f"   Sources tracked: {stats.get('sources_tracked', 0)}")
    
    if stats.get('by_source'):
        print("\n   By Source:")
        for s in stats['by_source']:
            print(f"     {s['source']}: {s['total']} checked, {s['relevant']} relevant")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Matchmaker Agent - Multi-agent problem discovery system"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Telegram bot
    subparsers.add_parser("telegram", help="Run the Telegram bot")

    # Server (WhatsApp webhook)
    subparsers.add_parser("server", help="Run the API server (for WhatsApp)")

    # Database setup
    subparsers.add_parser("setup-db", help="Set up database schema")

    # Seed problem domains
    subparsers.add_parser("seed", help="Seed database with problem domains and use cases")

    # Interactive CLI
    subparsers.add_parser("interactive", help="Run interactive CLI session")

    # Ingest case study
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a case study from a URL")
    ingest_parser.add_argument("url", help="URL of the article/case study")
    ingest_parser.add_argument("--source", "-s", default="", help="Source name (e.g., Forbes, CoinDesk)")

    # List case studies
    subparsers.add_parser("case-studies", help="List all ingested case studies")

    # News tracking
    subparsers.add_parser("track-news", help="Check news sources once for new case studies")
    
    track_continuous_parser = subparsers.add_parser("track-news-continuous", help="Continuously monitor news sources")
    track_continuous_parser.add_argument("--interval", "-i", type=int, default=60, help="Check interval in minutes (default: 60)")
    
    subparsers.add_parser("news-stats", help="Show news tracking statistics")

    args = parser.parse_args()

    if args.command == "telegram":
        run_telegram()
    elif args.command == "server":
        run_server()
    elif args.command == "setup-db":
        run_setup_db()
    elif args.command == "seed":
        seed_problems()
    elif args.command == "interactive":
        run_interactive()
    elif args.command == "ingest":
        ingest_case_study(args.url, args.source)
    elif args.command == "case-studies":
        list_case_studies()
    elif args.command == "track-news":
        track_news_once()
    elif args.command == "track-news-continuous":
        track_news_continuous(args.interval)
    elif args.command == "news-stats":
        show_news_stats()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
