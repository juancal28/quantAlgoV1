"""
Test the full strategy creation pipeline with manually inserted articles.

NOT part of the application — manual testing only.

Pipeline:
  1. Insert news articles into Postgres
  2. Score sentiment with FinBERT
  3. Embed and upsert into Qdrant
  4. Query KB to verify documents are accessible
  5. RAG agent proposes a strategy update
  6. Validate the proposal
  7. Submit for approval (status=pending_approval)

Usage:
    python sandbox/test_strategy_pipeline.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Suppress noisy output before any imports
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TQDM_DISABLE"] = "1"  # suppress FinBERT weight loading bars
os.environ["APP_ENV"] = "sandbox"  # prevent SQLAlchemy echo=True (dev sets echo)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

# Allow importing from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must import config early to trigger TRADING_MODE check
from core.config import get_settings

ARTICLES = [
    {
        "title": "NVIDIA beats Q4 earnings expectations as data center revenue surges 80%",
        "content": (
            "NVIDIA Corporation reported fourth-quarter results that significantly "
            "exceeded Wall Street expectations, with revenue of $38.1 billion, up 78% "
            "year over year. Data center revenue hit $33.9 billion, driven by massive "
            "demand for AI training and inference GPUs. CEO Jensen Huang said the company "
            "is seeing 'incredible demand' for its Blackwell architecture across cloud "
            "providers, enterprises, and sovereign AI initiatives. Gross margins expanded "
            "to 73.5%. The company guided Q1 revenue of $43 billion, above the $41 billion "
            "consensus. NVDA shares rallied 8% in after-hours trading. Analysts at Goldman "
            "Sachs raised their price target to $185, citing sustained AI infrastructure "
            "spending momentum."
        ),
        "source": "reuters",
        "source_url": "https://reuters.com/test/nvda-earnings-q4-2026",
        "tickers": ["NVDA"],
        "minutes_ago": 60,
    },
    {
        "title": "S&P 500 hits record high as tech earnings fuel broad market rally",
        "content": (
            "The S&P 500 index closed at a new all-time high on Thursday, driven by strong "
            "technology earnings and easing inflation expectations. The SPY ETF gained 1.2% "
            "on the session, with the QQQ Nasdaq-100 tracker up 1.8%. Big tech names led "
            "the advance, with Microsoft, Apple, and Meta all posting gains above 2%. "
            "Bond yields fell as investors priced in a more dovish Federal Reserve stance, "
            "with the 10-year Treasury yield dropping to 4.15%. Market breadth was positive, "
            "with 380 S&P 500 components advancing. Volatility collapsed, with the VIX "
            "falling below 14 for the first time since December."
        ),
        "source": "bloomberg",
        "source_url": "https://bloomberg.com/test/sp500-record-high-feb-2026",
        "tickers": ["SPY", "QQQ", "MSFT", "AAPL", "META"],
        "minutes_ago": 45,
    },
    {
        "title": "Apple announces $100B buyback program as iPhone sales stabilize",
        "content": (
            "Apple Inc. announced a record $100 billion share repurchase authorization "
            "following better-than-expected fiscal Q1 results. iPhone revenue came in at "
            "$71.2 billion, beating the $69 billion consensus, as the iPhone 17 Pro cycle "
            "showed stronger-than-anticipated demand in China. Services revenue grew 16% "
            "to $26.3 billion, continuing its margin-accretive growth trajectory. CFO Luca "
            "Maestri noted that the installed base of active devices reached 2.4 billion. "
            "AAPL shares rose 3.5% in extended trading. JPMorgan reiterated its Overweight "
            "rating with a $260 price target."
        ),
        "source": "cnbc",
        "source_url": "https://cnbc.com/test/apple-buyback-q1-2026",
        "tickers": ["AAPL", "JPM"],
        "minutes_ago": 30,
    },
    {
        "title": "Amazon Web Services revenue growth accelerates to 22%, beating estimates",
        "content": (
            "Amazon.com reported Q4 results with AWS revenue growth accelerating to 22% "
            "year over year, reaching $28.8 billion and surpassing analyst estimates of "
            "$27.4 billion. CEO Andy Jassy attributed the acceleration to AI workload "
            "migration and new generative AI services. Operating margins for AWS expanded "
            "to 33.4%, the highest in three years. Overall company revenue of $185 billion "
            "also beat expectations. AMZN shares surged 5% after hours. The company "
            "announced plans to invest $80 billion in AI infrastructure over 2026, "
            "signaling confidence in sustained cloud and AI demand growth."
        ),
        "source": "wsj",
        "source_url": "https://wsj.com/test/amazon-aws-q4-2026",
        "tickers": ["AMZN"],
        "minutes_ago": 90,
    },
]

STRATEGY_NAME = "sentiment_momentum_v1"


async def run_pipeline():
    from sqlalchemy.ext.asyncio import AsyncSession

    from core.storage.db import get_session

    settings = get_settings()

    print("=" * 70)
    print("STRATEGY CREATION PIPELINE TEST")
    print("=" * 70)
    print(f"  Strategy:    {STRATEGY_NAME}")
    print(f"  Embeddings:  {settings.EMBEDDINGS_PROVIDER}")
    print(f"  Sentiment:   {settings.SENTIMENT_PROVIDER}")
    print(f"  LLM:         {settings.LLM_MODEL}")
    print()

    async for session in get_session():
        await _run_steps(session)


async def _run_steps(session):
    from core.ingestion.dedupe import compute_content_hash
    from core.storage.models import NewsDocument

    # ------------------------------------------------------------------
    # STEP 1: Insert articles
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 1: Insert news articles into Postgres")
    print("=" * 70)

    now = datetime.now(timezone.utc)
    doc_ids: list[str] = []

    for article in ARTICLES:
        content_hash = compute_content_hash(article["content"])

        # Check if already inserted (idempotent re-runs)
        from core.storage.repos import news_repo

        existing = await news_repo.get_by_source_url(session, article["source_url"])
        if existing:
            doc_ids.append(str(existing.id))
            print(f"  [exists] {article['title'][:60]}...")
            continue

        doc_id = uuid.uuid4()
        doc = NewsDocument(
            id=doc_id,
            source=article["source"],
            source_url=article["source_url"],
            title=article["title"],
            published_at=now - timedelta(minutes=article["minutes_ago"]),
            fetched_at=now,
            content=article["content"],
            content_hash=content_hash,
            metadata_={"tickers": article["tickers"]},
        )
        session.add(doc)
        doc_ids.append(str(doc_id))
        print(f"  [new]    {article['title'][:60]}...")

    await session.commit()
    print(f"\n  Inserted/found {len(doc_ids)} articles")
    print()

    # ------------------------------------------------------------------
    # STEP 2: Score sentiment
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 2: Score sentiment (FinBERT)")
    print("=" * 70)

    from apps.mcp_server.schemas import SentimentInput
    from apps.mcp_server.tools.sentiment import score_sentiment

    sent_result = await score_sentiment(session, SentimentInput(doc_ids=doc_ids))
    print(f"  Scored {sent_result.scored} documents")

    # Show scores
    for doc_id_str in doc_ids:
        doc = await session.get(NewsDocument, uuid.UUID(doc_id_str))
        if doc:
            print(f"  {doc.title[:50]:50s}  score={doc.sentiment_score:+.3f}  label={doc.sentiment_label}")
    print()

    # ------------------------------------------------------------------
    # STEP 3: Embed and upsert to Qdrant
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 3: Embed and upsert into Qdrant")
    print("=" * 70)

    from apps.mcp_server.schemas import EmbedInput
    from apps.mcp_server.tools.kb import embed_and_upsert_docs

    embed_result = await embed_and_upsert_docs(session, EmbedInput(doc_ids=doc_ids))
    print(f"  Upserted {embed_result.upserted_chunks} chunks")
    print()

    # ------------------------------------------------------------------
    # STEP 4: Query KB to verify
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 4: Query knowledge base")
    print("=" * 70)

    from apps.mcp_server.schemas import QueryInput
    from apps.mcp_server.tools.kb import query_kb

    query_result = await query_kb(QueryInput(query="tech earnings AI revenue growth", top_k=10))
    print(f"  Retrieved {len(query_result.results)} results:")
    for r in query_result.results[:5]:
        print(f"    score={r.score:.3f}  {r.title[:55]}  sentiment={r.sentiment_score}")
    print()

    if len(query_result.results) < 3:
        print("  WARNING: Fewer than 3 results. RAG agent will return confidence=0.0")
        print("  (This is expected with mock embeddings if the collection was empty)")
    print()

    # ------------------------------------------------------------------
    # STEP 5: RAG agent proposes strategy
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 5: RAG agent proposes strategy update")
    print("=" * 70)

    from apps.mcp_server.schemas import ProposeStrategyInput
    from apps.mcp_server.tools.strategy import propose_strategy

    try:
        proposal_result = await propose_strategy(
            session, ProposeStrategyInput(strategy_name=STRATEGY_NAME, recent_minutes=240)
        )
        proposal = proposal_result.proposal
        print(f"  Confidence: {proposal.get('confidence', 'N/A')}")
        print(f"  Changed fields: {proposal.get('changed_fields', [])}")
        print(f"  Cited doc IDs: {len(proposal.get('cited_doc_ids', []))}")
        print(f"  Rationale: {proposal.get('rationale', 'N/A')[:200]}")
        print()

        new_definition = proposal.get("new_definition", {})
        if new_definition:
            import json
            print("  Proposed definition:")
            print("  " + json.dumps(new_definition, indent=2).replace("\n", "\n  "))
        print()
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  Falling back to a manual strategy definition...")
        proposal = None
        new_definition = {
            "name": STRATEGY_NAME,
            "universe": ["SPY", "QQQ", "NVDA", "AAPL"],
            "signals": [
                {"type": "news_sentiment", "lookback_minutes": 240, "threshold": 0.65, "direction": "long"},
                {"type": "volatility_filter", "max_vix": 25},
            ],
            "rules": {
                "rebalance_minutes": 60,
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
                "exits": [{"type": "time_stop", "minutes": 360}],
            },
        }
        print(f"  Using fallback definition with universe: {new_definition['universe']}")
        print()

    if not new_definition:
        print("  No definition produced. Aborting.")
        return

    # ------------------------------------------------------------------
    # STEP 6: Validate
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 6: Validate strategy definition")
    print("=" * 70)

    from apps.mcp_server.schemas import ValidateStrategyInput
    from apps.mcp_server.tools.strategy import validate_strategy_tool

    val_result = await validate_strategy_tool(
        ValidateStrategyInput(definition_json=new_definition)
    )
    print(f"  Valid: {val_result.valid}")
    if val_result.errors:
        for err in val_result.errors:
            print(f"    - {err}")
    print()

    if not val_result.valid:
        print("  Strategy failed validation. Not submitting.")
        print("  You may need to adjust the definition to pass validation rules.")
        return

    # ------------------------------------------------------------------
    # STEP 7: Submit for approval
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 7: Submit for approval")
    print("=" * 70)

    from apps.mcp_server.schemas import SubmitStrategyInput
    from apps.mcp_server.tools.strategy import submit_strategy

    submit_result = await submit_strategy(
        session,
        SubmitStrategyInput(
            strategy_name=STRATEGY_NAME,
            definition_json=new_definition,
            reason="Pipeline test: RAG agent proposal based on today's news articles",
            backtest_metrics=None,
        ),
    )
    print(f"  Strategy version ID: {submit_result.strategy_version_id}")
    print(f"  Status: {submit_result.status}")
    print()
    print("  >> Strategy submitted for approval!")
    print()
    print(f"  To approve, run:")
    print(f"    curl -X POST http://localhost:8000/strategies/{STRATEGY_NAME}/approve/{submit_result.strategy_version_id}")
    print()
    print(f"  To view in API:")
    print(f"    curl http://localhost:8000/strategies/{STRATEGY_NAME}/versions")


def main():
    # Windows requires SelectorEventLoop for async psycopg
    import sys as _sys
    if _sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()
