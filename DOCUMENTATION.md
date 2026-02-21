# Quant News-RAG Trading System — Documentation

> A modular, paper-first quantitative trading system that ingests financial news, builds a vector knowledge base, uses a RAG agent to propose strategy updates, backtests them, and executes paper trades.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Build Status](#3-build-status)
4. [Prerequisites & Setup](#4-prerequisites--setup)
5. [Configuration Reference](#5-configuration-reference)
6. [Data Flow: How Market Data Gets In](#6-data-flow-how-market-data-gets-in)
7. [Data Flow: How News Gets In](#7-data-flow-how-news-gets-in)
8. [How Trading Decisions Are Made](#8-how-trading-decisions-are-made)
9. [Paper Trading: Simulating With Fake Money](#9-paper-trading-simulating-with-fake-money)
10. [Backtesting: Testing Strategies Against History](#10-backtesting-testing-strategies-against-history)
11. [Safety Rails & Risk Controls](#11-safety-rails--risk-controls)
12. [API Reference](#12-api-reference)
13. [Day-to-Day Usage](#13-day-to-day-usage)
14. [Database Schema](#14-database-schema)
15. [Project File Map](#15-project-file-map)
16. [Build Phases — All Complete](#16-build-phases--all-complete)
17. [Future Phases: Quantitative Model Development](#17-future-phases-quantitative-model-development)
18. [Deployment Roadmap: Local → Railway](#18-deployment-roadmap-local--railway)
19. [Monitoring with Claude Desktop (Dual MCP Servers)](#19-monitoring-with-claude-desktop-dual-mcp-servers)
20. [Glossary](#20-glossary)

---

## 1. System Overview

This is **not** a manual stock-picking tool. It is an autonomous background system that:

1. **Continuously polls** financial news from RSS feeds
2. **Builds a searchable knowledge base** by chunking, embedding, and storing articles in a vector database (Qdrant)
3. **Scores sentiment** on every article using FinBERT (a finance-tuned language model)
4. **Uses a RAG (Retrieval-Augmented Generation) agent** to read recent news and propose trading strategy adjustments — every proposal must cite specific articles
5. **Validates** proposed strategies against strict risk limits
6. **Backtests** strategies on 1+ year of historical data before they can be activated
7. **Requires human approval** — the AI never auto-activates a strategy
8. **Paper trades** approved strategies with $100,000 of simulated money
9. **Enforces a circuit breaker** that halts all trading if daily losses exceed 2%

The only trading mode supported is **paper** (simulated). There is no live trading codepath. The system hard-exits at startup if `TRADING_MODE` is set to anything other than `paper`.

---

## 2. Architecture

### High-Level Data Flow

```
                    ┌─────────────┐
                    │  RSS Feeds  │
                    │  (Yahoo,    │
                    │  NewsAPI)   │
                    └──────┬──────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   NEWS INGESTION      │
               │                       │
               │  fetch → normalize    │
               │  → deduplicate        │
               │  → extract tickers    │
               │  → store in Postgres  │
               └───────────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
      ┌──────────┐  ┌──────────┐  ┌──────────┐
      │  Chunk   │  │ Sentiment│  │  Market  │
      │  + Embed │  │ Scoring  │  │  Data    │
      │  → Qdrant│  │ (FinBERT)│  │ (Alpaca) │
      └────┬─────┘  └────┬─────┘  └────┬─────┘
           │              │              │
           ▼              ▼              ▼
      ┌──────────────────────────────────────┐
      │           POSTGRES DATABASE          │
      │  news_documents | market_bars        │
      │  strategy_versions | pnl_snapshots   │
      └──────────────────┬───────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │     RAG AGENT       │
              │                     │
              │  queries Qdrant     │
              │  reads recent news  │
              │  proposes strategy  │
              │  cites sources      │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    VALIDATOR        │
              │                     │
              │  checks tickers     │
              │  checks risk limits │
              │  checks diff count  │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    BACKTESTER       │
              │                     │
              │  1-year in-sample   │
              │  90-day out-sample  │
              │  cost model         │
              └──────────┬──────────┘
                         │
                  passes thresholds?
                    │           │
                   YES          NO → discard
                    │
                    ▼
              ┌─────────────────────┐
              │  PENDING APPROVAL   │
              │  (waits for human)  │
              └──────────┬──────────┘
                         │
                  human approves?
                    │           │
                   YES          NO → archived
                    │
                    ▼
              ┌─────────────────────┐
              │   PAPER BROKER      │
              │                     │
              │  executes signals   │
              │  tracks positions   │
              │  records PnL        │
              │  circuit breaker    │
              └─────────────────────┘
```

### Service Boundaries

The codebase is split into four layers with strict dependency direction:

```
apps/api/          →  FastAPI REST layer. Thin wrappers only — no business logic.
apps/mcp_server/   →  MCP tool implementations. Calls core/ directly, never api/.
apps/scheduler/    →  Celery task queue. Runs the automated pipeline on timers.
core/              →  ALL business logic. Independently importable.

Dependency rule:
  apps/* → core/*   ✓  (apps can import from core)
  core/* → apps/*   ✗  (core NEVER imports from apps)
```

### Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Async throughout |
| API | FastAPI | REST endpoints with Pydantic v2 validation |
| Task Queue | Celery + Redis | Scheduled jobs with retries and visibility (Flower UI) |
| Database | PostgreSQL 16 | All persistent state (6 tables) |
| Migrations | Alembic | Schema versioning (async mode) |
| Vector DB | Qdrant | Semantic search over news embeddings |
| Embeddings | Pluggable (mock / OpenAI) | Controlled by `EMBEDDINGS_PROVIDER` env var |
| Sentiment | FinBERT (local) | Finance-tuned sentiment scoring |
| Market Data | Alpaca API / yfinance | Historical + real-time OHLCV bars |
| Backtesting | vectorbt / backtrader | Strategy simulation (adapter pattern, swappable) |
| Broker | PaperBroker (internal) or AlpacaPaperBroker | Simulated order execution. Controlled by `BROKER_PROVIDER` (`internal` or `alpaca`). |

---

## 3. Build Status

The project was built in 12 phases. All phases are complete:

| Phase | Description | Status |
|---|---|---|
| 1 | Scaffold + config + logging | **Complete** |
| 2 | Postgres models + Alembic migration | **Complete** |
| 3 | Market data ingestion | **Complete** |
| 4 | News ingestion (RSS, dedup, ticker extraction) | **Complete** |
| 5 | Chunking + embeddings + vectorstore | **Complete** |
| 5b | Sentiment scoring | **Complete** |
| 6 | MCP server tools 1–4 | **Complete** |
| 7 | RAG agent + strategy validator | **Complete** |
| 8 | Backtest engine + cost model | **Complete** |
| 9 | Strategy versioning + approval API | **Complete** |
| 10 | Paper broker + risk + circuit breaker | **Complete** |
| 11 | FastAPI endpoints + Celery scheduler | **Complete** |
| 12 | Tests + documentation | **Complete** |

**Summary:** 58 of 61 Python files are implemented (95%). 143 tests passing across 20 test files. The 3 remaining placeholders are `observability/metrics.py`, `observability/tracing.py`, and `provider_newsapi.py` (deferred to v2).

---

## 4. Prerequisites & Setup

### What You Need Installed

1. **Python 3.11+** — installed via `winget install Python.Python.3.11`
2. **Docker Desktop** — download from [docker.com](https://www.docker.com/products/docker-desktop/). Provides `docker` and `docker compose` for running Postgres, Redis, and Qdrant.
3. **Git** — for version control

### First-Time Setup

```bash
# 1. Clone the repo
git clone git@github.com:juancal28/quantAlgoV1.git
cd quantAlgoV1

# 2. Create and activate a virtual environment
python -m venv .venv
# On Windows (Git Bash):
source .venv/Scripts/activate
# On macOS/Linux:
source .venv/bin/activate

# 3. Install all dependencies (including dev tools)
pip install -e ".[dev]"

# 4. Copy the example env file and fill in your keys
cp .env.example .env
# Edit .env with your API keys (see Configuration Reference below)

# 5. Start the backing services
docker compose up -d
# This starts:
#   Postgres  → localhost:5432
#   Redis     → localhost:6379
#   Qdrant    → localhost:6333
#   Flower    → localhost:5555 (Celery monitoring UI)

# 6. Run the database migration
alembic upgrade head
# Creates all 6 tables in Postgres

# 7. Verify everything works
pytest
# Should show all tests passing
```

### API Keys You'll Need

| Service | Required? | How to Get |
|---|---|---|
| Alpaca | Optional (can use yfinance) | Free account at [alpaca.markets](https://alpaca.markets). Get API key + secret from the dashboard. |
| OpenAI | Optional (mock works for dev) | API key from [platform.openai.com](https://platform.openai.com). Only needed if `EMBEDDINGS_PROVIDER=openai`. |
| NewsAPI | Optional (RSS is default) | API key from [newsapi.org](https://newsapi.org). Only needed for the NewsAPI provider. |

For local development, you can run with **zero API keys** — the system defaults to `EMBEDDINGS_PROVIDER=mock` and `MARKET_DATA_PROVIDER=yfinance`.

---

## 5. Configuration Reference

All configuration is managed through environment variables loaded from a `.env` file via `core/config.py` (using `pydantic-settings`). **Never hardcode values.**

### Core Services

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `dev` | Environment name (`dev`, `test`, `prod`) |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/quant` | Postgres connection string |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector database URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for Celery task queue |

### News Ingestion

| Variable | Default | Description |
|---|---|---|
| `NEWS_POLL_INTERVAL_SECONDS` | `120` | How often to check for new articles (seconds) |
| `NEWS_SOURCES` | Yahoo Finance RSS | Comma-separated list of `type:url` sources |
| `MAX_DOCS_PER_POLL` | `50` | Max articles to fetch per polling cycle |
| `DEDUP_CONTENT_HASH` | `sha256` | Hashing algorithm for deduplication |

### Market Data

| Variable | Default | Description |
|---|---|---|
| `MARKET_DATA_PROVIDER` | `alpaca` | Data source: `alpaca` or `yfinance` |
| `ALPACA_API_KEY` | *(empty)* | Your Alpaca API key |
| `ALPACA_API_SECRET` | *(empty)* | Your Alpaca API secret |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | Alpaca API base URL (paper environment) |
| `MARKET_DATA_LOOKBACK_DAYS` | `365` | How many days of historical bars to fetch |
| `BAR_TIMEFRAME` | `1Day` | Bar granularity (`1Day`, `1Hour`, etc.) |

### Embeddings & Vector DB

| Variable | Default | Description |
|---|---|---|
| `EMBEDDINGS_PROVIDER` | `mock` | Embedding backend: `mock` (zero vectors for testing) or `openai` |
| `OPENAI_API_KEY` | *(empty)* | Required only if `EMBEDDINGS_PROVIDER=openai` |
| `VECTOR_COLLECTION` | `news` | Qdrant collection name |
| `VECTOR_SIZE` | `1536` | Embedding dimension (1536 for OpenAI text-embedding-3-small) |
| `CHUNK_SIZE_CHARS` | `1000` | Characters per text chunk |
| `CHUNK_OVERLAP_CHARS` | `150` | Character overlap between consecutive chunks |

### Sentiment

| Variable | Default | Description |
|---|---|---|
| `SENTIMENT_PROVIDER` | `finbert` | Sentiment engine: `finbert`, `llm`, or `mock` |

### Risk & Execution

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | **Only valid value in v1.** System hard-exits if set to anything else. |
| `PAPER_GUARD` | `true` | Double-check flag. Every broker method verifies this is `true`. |
| `PAPER_INITIAL_CASH` | `100000` | Starting simulated portfolio value ($) |
| `RISK_MAX_GROSS_EXPOSURE` | `1.0` | Max total portfolio exposure (1.0 = 100%) |
| `RISK_MAX_POSITION_PCT` | `0.10` | Max single position size (10% of portfolio) |
| `RISK_MAX_DAILY_LOSS_PCT` | `0.02` | Daily loss circuit breaker threshold (2%) |
| `RISK_MAX_TRADES_PER_HOUR` | `30` | Max trades per hour (rate limit) |
| `RISK_MAX_DATA_STALENESS_MINUTES` | `30` | Max age of market data before it's considered stale |

### Strategy Agent

| Variable | Default | Description |
|---|---|---|
| `STRATEGY_APPROVED_UNIVERSE` | `SPY,QQQ,AAPL,MSFT,AMZN,GOOGL,META,NVDA,BRK.B,JPM` | Only these tickers are allowed in strategies |
| `STRATEGY_MIN_CONFIDENCE` | `0.6` | Agent must have ≥60% confidence to propose a change |
| `STRATEGY_MAX_DIFF_FIELDS` | `3` | Max fields the agent can change per proposal |
| `STRATEGY_MAX_ACTIVATIONS_PER_DAY` | `4` | Max strategy activations in a 24-hour window |
| `STRATEGY_MIN_BACKTEST_DAYS` | `252` | Minimum backtest window (252 trading days ≈ 1 year) |
| `PENDING_APPROVAL_AUTO_APPROVE_MINUTES` | `0` | 0 = never auto-approve; N = auto-approve after N minutes |

### Broker

| Variable | Default | Description |
|---|---|---|
| `BROKER_PROVIDER` | `internal` | Paper broker backend: `internal` (built-in PaperBroker) or `alpaca` (AlpacaPaperBroker via Alpaca paper API) |

### Backtest Thresholds

A strategy must pass **all three** to be submitted for approval:

| Variable | Default | Meaning |
|---|---|---|
| `BACKTEST_MIN_SHARPE` | `0.5` | Minimum Sharpe ratio |
| `BACKTEST_MAX_DRAWDOWN` | `0.25` | Maximum drawdown (25%) |
| `BACKTEST_MIN_WIN_RATE` | `0.40` | Minimum win rate (40%) |

### Backtest Cost Model

| Variable | Default | Description |
|---|---|---|
| `BACKTEST_COMMISSION_PER_TRADE` | `1.0` | Fixed $ commission per trade |
| `BACKTEST_SLIPPAGE_BPS` | `5.0` | Slippage in basis points |
| `BACKTEST_SPREAD_BPS` | `2.0` | Bid-ask spread proxy in basis points |

---

## 6. Data Flow: How Market Data Gets In

### Source

Market data (OHLCV bars — Open, High, Low, Close, Volume) comes from one of two providers:

- **Alpaca Data API** (default) — requires a free Alpaca account. Provides clean, split-adjusted daily bars. Set `MARKET_DATA_PROVIDER=alpaca` and provide `ALPACA_API_KEY` + `ALPACA_API_SECRET`.
- **yfinance** (fallback) — free, no API key. Uses Yahoo Finance. Set `MARKET_DATA_PROVIDER=yfinance`. Good for development but less reliable for production.

### What Gets Fetched

The system fetches bars for every ticker in `STRATEGY_APPROVED_UNIVERSE`:
```
SPY, QQQ, AAPL, MSFT, AMZN, GOOGL, META, NVDA, BRK.B, JPM
```

For each ticker, it pulls the last `MARKET_DATA_LOOKBACK_DAYS` (default: 365) days of `BAR_TIMEFRAME` (default: `1Day`) bars.

### Where It's Stored

Every bar is stored in the `market_bars` Postgres table:

```
ticker      | timeframe | bar_time            | open   | high   | low    | close  | volume
─────────────────────────────────────────────────────────────────────────────────────────────
SPY         | 1Day      | 2025-02-18 14:30:00 | 598.12 | 601.45 | 597.30 | 600.82 | 45230100
AAPL        | 1Day      | 2025-02-18 14:30:00 | 232.50 | 234.10 | 231.80 | 233.75 | 31204500
```

A unique constraint on `(ticker, timeframe, bar_time)` prevents duplicates. Upserts skip rows that already exist.

### When It Runs

Market data is fetched:
- At system startup (backfill historical data)
- Before every backtest (ensure data is current)
- On a schedule via Celery (configurable)

---

## 7. Data Flow: How News Gets In

### The Ingestion Pipeline

Every `NEWS_POLL_INTERVAL_SECONDS` (default: 2 minutes), the system runs:

```
Step 1: FETCH
  └─ RSS fetcher hits configured feeds (Yahoo Finance by default)
  └─ Pulls up to MAX_DOCS_PER_POLL (50) articles

Step 2: NORMALIZE
  └─ Strips HTML tags
  └─ Standardizes encoding
  └─ Extracts title, content, published date, source URL

Step 3: DEDUPLICATE
  └─ Computes SHA-256 hash of normalized content
  └─ Checks content_hash against Postgres (unique index)
  └─ Checks source_url against Postgres (unique index)
  └─ Skips any article already seen

Step 4: EXTRACT TICKERS
  └─ Regex-based extraction of stock symbols from text
  └─ Matched against STRATEGY_APPROVED_UNIVERSE
  └─ Stored in the metadata JSON column: {"tickers": ["AAPL", "MSFT"]}

Step 5: STORE
  └─ Insert into news_documents table in Postgres
  └─ Returns list of new doc_ids

Step 6: CHUNK + EMBED
  └─ Each article split into ~1000-character chunks with 150-char overlap
  └─ Chunks are embedded (mock zeros in dev, OpenAI vectors in prod)
  └─ Vectors upserted into Qdrant with payload metadata:
     {doc_id, title, source, source_url, published_at, tickers,
      sentiment_score, sentiment_label, chunk_index, chunk_total}

Step 7: SCORE SENTIMENT
  └─ FinBERT scores each article: positive / negative / neutral + confidence
  └─ Scores saved to both Postgres (news_documents.sentiment_score) and
     Qdrant (payload.sentiment_score)
```

### Qdrant Vector DB Configuration

The vector collection uses:
- **Cosine distance** for similarity search
- **int8 scalar quantization** (keeps vectors in RAM for fast search)
- **1536 dimensions** (matching OpenAI text-embedding-3-small)

When the RAG agent needs to find relevant news, it embeds a query string and performs a cosine similarity search against all stored chunks.

---

## 8. How Trading Decisions Are Made

This system uses an **AI agent** to propose trading strategies, but with strict guardrails so no action is taken without validation and human approval.

### The Decision Pipeline

```
1. RAG AGENT runs
   └─ Receives: "What strategy updates are warranted by recent news?"
   └─ Queries Qdrant for relevant articles from the last N minutes
   └─ If fewer than 3 documents retrieved → returns confidence=0.0, proposes nothing
   └─ Otherwise, drafts a strategy proposal:
      {
        "new_definition": { ... strategy JSON ... },
        "rationale": "Based on [doc_id_1] and [doc_id_2], sentiment for tech...",
        "risks": "Concentrated in tech sector; VIX currently elevated",
        "expected_behavior": "Long bias on QQQ/AAPL when sentiment > 0.65",
        "confidence": 0.78,
        "cited_doc_ids": ["abc-123", "def-456", "ghi-789"],
        "changed_fields": ["signals[0].threshold", "universe"]
      }

2. VALIDATOR checks the proposal
   └─ Are all tickers in STRATEGY_APPROVED_UNIVERSE? → reject if not
   └─ Is max_position_pct ≤ RISK_MAX_POSITION_PCT (10%)? → reject if not
   └─ Are there unknown signal types? → reject
   └─ Are changed fields ≤ STRATEGY_MAX_DIFF_FIELDS (3)? → reject if too many
   └─ Is confidence ≥ STRATEGY_MIN_CONFIDENCE (0.6)? → reject if not

3. BACKTESTER runs (if validation passes)
   └─ In-sample: last 252 trading days
   └─ Out-of-sample: 90 days before the in-sample window
   └─ Must pass ALL thresholds:
      • Sharpe ratio > 0.5
      • Max drawdown < 25%
      • Win rate > 40%

4. SUBMIT FOR APPROVAL (if backtest passes)
   └─ Creates a new strategy_versions row with status="pending_approval"
   └─ Logs the event in strategy_audit_log
   └─ DOES NOT ACTIVATE — waits for human

5. HUMAN REVIEWS
   └─ GET /strategies → see all pending proposals
   └─ Review the rationale, cited sources, backtest metrics
   └─ POST /strategies/{name}/approve/{version_id} → activate
   └─ The previously active version is archived
```

### What a Strategy Looks Like

Strategies are defined as JSON:

```json
{
  "name": "sentiment_momentum_v1",
  "universe": ["SPY", "QQQ"],
  "signals": [
    {
      "type": "news_sentiment",
      "lookback_minutes": 240,
      "threshold": 0.65,
      "direction": "long"
    },
    {
      "type": "volatility_filter",
      "max_vix": 25
    }
  ],
  "rules": {
    "rebalance_minutes": 60,
    "max_positions": 5,
    "position_sizing": {
      "type": "equal_weight",
      "max_position_pct": 0.10
    },
    "exits": [
      {"type": "time_stop", "minutes": 360}
    ]
  }
}
```

This example says: "Go long SPY and QQQ when average news sentiment over the last 4 hours exceeds 0.65, as long as VIX is below 25. Equal-weight positions, max 5 positions, max 10% per position, exit after 6 hours."

---

## 9. Paper Trading: Simulating With Fake Money

### How It Works

Once a strategy is approved and set to `status=active`, the paper trading loop kicks in:

```
Every 1 minute during NYSE market hours (9:30 AM – 4:00 PM ET):

  1. CHECK MARKET HOURS
     └─ If market is closed → log warning, skip (no-op)
     └─ Uses exchange_calendars (XNYS) for accurate NYSE schedule
        including holidays and early closes

  2. EVALUATE SIGNALS
     └─ Active strategy's signals are evaluated against current data
     └─ Signal data uses ONLY data available at the bar's open
        (shifted by 1 bar to prevent lookahead bias)

  3. GENERATE ORDERS
     └─ Position sizing applied (equal_weight, max 10% per position)
     └─ Risk limits checked:
        • Gross exposure ≤ 100% of portfolio
        • Single position ≤ 10%
        • Trades this hour ≤ 30
        • Data staleness ≤ 30 minutes

  4. EXECUTE (SIMULATED)
     └─ PaperBroker fills orders instantly at current price
     └─ Applies slippage (5 bps) and commission ($1/trade)
     └─ Updates in-memory position ledger

  5. RECORD PnL
     └─ Snapshot written to pnl_snapshots table in Postgres:
        {strategy_name, date, realized_pnl, unrealized_pnl,
         gross_exposure, peak_pnl, positions}
     └─ This is PERSISTED, not just in memory

  6. CHECK CIRCUIT BREAKER
     └─ Loads today's pnl_snapshot from Postgres (not memory!)
     └─ If daily loss > RISK_MAX_DAILY_LOSS_PCT (2% of portfolio):
        → HALT all trading for the rest of the day
        → Log a critical warning
     └─ Circuit breaker state survives restarts because it's in the DB
```

### Broker Backend

Two paper broker implementations are available, controlled by `BROKER_PROVIDER`:

- **`internal`** (default) — Built-in `PaperBroker` that simulates orders in-memory with instant fills, slippage, and commission. No external API needed.
- **`alpaca`** — `AlpacaPaperBroker` that routes orders through Alpaca's paper trading API. Requires `ALPACA_API_KEY` and `ALPACA_API_SECRET`. Provides more realistic fill simulation via Alpaca's infrastructure.

Both brokers implement the same `BrokerBase` interface and are subject to `PAPER_GUARD` enforcement.

### Starting Capital

The paper broker starts with `PAPER_INITIAL_CASH` = **$100,000** by default. This is configurable in `.env`.

### What You Can Monitor

While paper trading is running:

```
GET /pnl/daily?strategy=sentiment_momentum_v1

Response:
{
  "snapshots": [
    {
      "date": "2025-02-18",
      "realized_pnl": 234.50,
      "unrealized_pnl": -120.30,
      "gross_exposure": 0.45,
      "peak_pnl": 450.00,
      "positions": {
        "SPY": {"shares": 50, "avg_cost": 598.12, "current_price": 600.82},
        "AAPL": {"shares": 30, "avg_cost": 232.50, "current_price": 233.75}
      }
    }
  ]
}
```

### Important: No Real Money

The `PAPER_GUARD=true` flag is checked in **every broker method**. If somehow a non-paper broker is instantiated while this flag is set, the system raises a `RuntimeError` immediately. Additionally, `TRADING_MODE=paper` is checked at startup — any other value causes a hard exit.

---

## 10. Backtesting: Testing Strategies Against History

### Purpose

Before any strategy can be activated, it must prove itself on historical data. The backtester simulates what would have happened if the strategy had been running over the past year.

### Two-Window Approach

Every strategy is tested on **two separate time periods**:

```
Timeline:
  ◄── 90 days ──►◄──────── 252 trading days (~1 year) ────────►  TODAY
  │  OUT-OF-SAMPLE  │              IN-SAMPLE                    │
  │  (sanity check)  │     (primary evaluation window)           │
```

1. **In-sample window** (252 trading days) — the primary test. The strategy must perform well here.
2. **Out-of-sample window** (90 days before in-sample) — a sanity check. If the strategy only works in-sample but fails out-of-sample, it's likely overfit.

Both windows must pass the activation thresholds.

### Cost Model

The backtester applies realistic trading costs:

| Cost | Default | Description |
|---|---|---|
| Commission | $1.00/trade | Fixed cost per trade |
| Slippage | 5 bps | Price impact (0.05% of trade value) |
| Spread | 2 bps | Bid-ask spread proxy (0.02% of trade value) |

These are configurable via env vars (`BACKTEST_COMMISSION_PER_TRADE`, `BACKTEST_SLIPPAGE_BPS`, `BACKTEST_SPREAD_BPS`).

### Activation Thresholds

A strategy must pass **all three** metrics to be eligible for approval:

| Metric | Threshold | What It Means |
|---|---|---|
| Sharpe Ratio | > 0.5 | Risk-adjusted return. 0.5 is moderate; >1.0 is good. |
| Max Drawdown | < 25% | Worst peak-to-trough decline. Must not lose more than 25%. |
| Win Rate | > 40% | Percentage of trades that are profitable. |

### Anti-Cheat: No Lookahead Bias

The backtester enforces a critical rule: **signals can only use data available at the bar's open.** Every time-series access is shifted by 1 bar, and every such shift is marked with the comment:

```python
# lookahead guard: shift(1)
```

This prevents the common backtesting mistake of accidentally using future data to make past decisions.

### Known Limitation

The system uses an ETF-heavy universe (SPY, QQQ, etc.). Survivorship bias is not corrected — we only test tickers that exist today. This is acceptable for v1 but noted as a limitation.

### Triggering a Backtest Manually

```
POST /strategies/{name}/backtest

Response:
{
  "metrics": {
    "cagr": 0.12,
    "sharpe": 0.85,
    "max_drawdown": 0.15,
    "win_rate": 0.52,
    "turnover": 2.3,
    "avg_trade_return": 0.003
  },
  "passed": true
}
```

---

## 11. Safety Rails & Risk Controls

### Hard Limits (Cannot Be Bypassed)

| Control | Implementation | Purpose |
|---|---|---|
| **TRADING_MODE=paper** | Checked at startup. Process exits if not `paper`. | No live trading in v1. |
| **PAPER_GUARD=true** | Checked in every broker method. `RuntimeError` if violated. | Defense-in-depth against live orders. |
| **No auto-activation** | Agent proposals always land in `pending_approval`. | Human must explicitly approve. |
| **Approved universe** | Validator rejects any ticker not in `STRATEGY_APPROVED_UNIVERSE`. | Prevents trading unknown instruments. |

### Dynamic Risk Controls

| Control | Default | Behavior |
|---|---|---|
| **Daily loss circuit breaker** | 2% of portfolio | Halts all trading for the rest of the day. State persisted in Postgres — survives restarts. |
| **Max gross exposure** | 100% | Portfolio cannot be more than 100% invested. |
| **Max position size** | 10% | No single position can exceed 10% of portfolio. |
| **Trade rate limit** | 30/hour | Prevents runaway order generation. |
| **Data staleness check** | 30 minutes | Won't trade on data older than 30 minutes. |
| **Max diff fields** | 3 per proposal | Agent can't change too many strategy parameters at once. |
| **Min confidence** | 60% | Agent won't propose changes unless it's reasonably confident. |
| **Max activations/day** | 4 | Limits how many times a strategy can be swapped per day. |

### Audit Trail

Every strategy action is logged in `strategy_audit_log`:

```
timestamp | strategy_name | action    | trigger   | before_definition | after_definition | rationale
──────────────────────────────────────────────────────────────────────────────────────────────────────
10:30 AM  | sent_mom_v1   | proposed  | agent     | {...}             | {...}            | "Based on..."
10:31 AM  | sent_mom_v1   | approved  | human     | null              | {...}            | null
10:31 AM  | sent_mom_v1   | activated | human     | null              | {...}            | null
```

---

## 12. API Reference

All endpoints are served by FastAPI at `http://localhost:8000` (default).

### Health & Monitoring

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` if the service is running |
| `GET` | `/runs/recent` | List recent pipeline runs with status |

### News

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/news/recent?minutes=120` | Fetch news articles from the last N minutes |

### Strategies

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/strategies` | List all strategies (all versions and statuses) |
| `GET` | `/strategies/{name}/active` | Get the currently active version of a strategy |
| `GET` | `/strategies/{name}/versions` | List all versions of a strategy |
| `POST` | `/strategies/{name}/approve/{version_id}` | **Approve and activate** a pending strategy version |
| `POST` | `/strategies/{name}/backtest` | Manually trigger a backtest for a strategy |

### PnL

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pnl/daily?strategy={name}` | Get daily PnL snapshots for a strategy |

### Pipeline

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/runs/news_cycle` | Manually trigger the full news→trade pipeline |

---

## 13. Day-to-Day Usage

### Starting the System

```bash
# Terminal 1: Start backing services
docker compose up -d

# Terminal 2: Start the API server
source .venv/Scripts/activate
uvicorn apps.api.main:app --reload

# Terminal 3: Start the Celery worker (runs the automated pipeline)
source .venv/Scripts/activate
celery -A apps.scheduler.worker worker --loglevel=info

# (Optional) Terminal 4: Open Flower to monitor Celery tasks
# Visit http://localhost:5555 in your browser
```

### What Happens Automatically

Once running, the system operates on two loops:

1. **News cycle** (every 2 minutes):
   - Fetches new articles
   - Embeds and scores them
   - RAG agent may propose a strategy update
   - If valid + backtested → submitted for your approval

2. **Paper trade tick** (every 1 minute, market hours only):
   - Evaluates active strategy signals
   - Executes simulated trades
   - Records PnL
   - Checks circuit breaker

### Your Role as Operator

1. **Check for pending strategies:**
   ```bash
   curl http://localhost:8000/strategies
   ```

2. **Review a proposal** — look at the rationale, cited articles, and backtest metrics

3. **Approve or ignore:**
   ```bash
   # Approve
   curl -X POST http://localhost:8000/strategies/sentiment_momentum_v1/approve/{version_id}

   # To reject, simply don't approve — it stays as pending_approval
   ```

4. **Monitor performance:**
   ```bash
   curl http://localhost:8000/pnl/daily?strategy=sentiment_momentum_v1
   ```

5. **Check pipeline health:**
   ```bash
   curl http://localhost:8000/runs/recent
   ```

---

## 14. Database Schema

Six tables in Postgres, all defined in `core/storage/models.py`:

### `news_documents`
Stores every ingested news article.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `source` | TEXT | e.g., "yahoo_rss" |
| `source_url` | TEXT | Unique index — prevents duplicate URLs |
| `title` | TEXT | Article headline |
| `published_at` | TIMESTAMPTZ | When the article was published |
| `fetched_at` | TIMESTAMPTZ | When we fetched it |
| `content` | TEXT | Full article text |
| `content_hash` | TEXT | SHA-256 of normalized content. Unique index — prevents duplicate content. |
| `metadata` | JSONB | `{"tickers": ["AAPL"], "author": "...", "tags": [...]}` |
| `sentiment_score` | FLOAT | -1.0 to 1.0 (set after FinBERT scoring) |
| `sentiment_label` | TEXT | `positive`, `negative`, or `neutral` |

### `market_bars`
OHLCV price data for backtesting and signal generation.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `ticker` | TEXT | e.g., "SPY" |
| `timeframe` | TEXT | e.g., "1Day" |
| `bar_time` | TIMESTAMPTZ | Bar timestamp |
| `open/high/low/close` | NUMERIC | Price data |
| `volume` | BIGINT | Trading volume |
| `fetched_at` | TIMESTAMPTZ | When we fetched it |

Unique constraint: `(ticker, timeframe, bar_time)`

### `strategy_versions`
Every version of every strategy, whether pending, active, or archived.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `name` | TEXT | Strategy name, e.g., "sentiment_momentum_v1" |
| `version` | INT | Incrementing version number |
| `status` | TEXT | `pending_approval`, `active`, or `archived` |
| `definition` | JSONB | The full strategy JSON spec |
| `created_at` | TIMESTAMPTZ | When the agent proposed it |
| `activated_at` | TIMESTAMPTZ | When a human approved it (null if never) |
| `approved_by` | TEXT | `"human"`, `"auto"`, or null |
| `reason` | TEXT | Why this version was created |
| `backtest_metrics` | JSONB | `{"sharpe": 0.85, "max_drawdown": 0.15, ...}` |

### `strategy_audit_log`
Immutable record of every strategy action for compliance.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `timestamp` | TIMESTAMPTZ | When the action happened |
| `strategy_name` | TEXT | Which strategy |
| `version_id` | UUID (FK) | Points to `strategy_versions.id` |
| `action` | TEXT | `proposed`, `approved`, `rejected`, `activated`, `archived` |
| `trigger` | TEXT | `agent`, `human`, or `scheduler` |
| `before_definition` | JSONB | Previous state (null for new) |
| `after_definition` | JSONB | New state |
| `backtest_metrics` | JSONB | Metrics at the time of the action |
| `llm_rationale` | TEXT | The agent's explanation |
| `diff_fields` | JSONB | List of fields that changed |

### `pnl_snapshots`
Daily PnL records per strategy. **Critical for circuit breaker — persisted in DB, not memory.**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `strategy_name` | TEXT | Which strategy |
| `snapshot_date` | DATE | The trading day |
| `realized_pnl` | NUMERIC | Closed-position profit/loss |
| `unrealized_pnl` | NUMERIC | Open-position mark-to-market |
| `gross_exposure` | NUMERIC | Total position value / portfolio value |
| `peak_pnl` | NUMERIC | Highest PnL this day (for drawdown tracking) |
| `positions` | JSONB | Current position details |
| `created_at` | TIMESTAMPTZ | Record creation time |

Unique constraint: `(strategy_name, snapshot_date)`

### `runs`
Log of every pipeline execution for observability.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `run_type` | TEXT | `ingest`, `embed`, `sentiment`, `agent_update`, `backtest`, `execution` |
| `started_at` | TIMESTAMPTZ | When the run started |
| `ended_at` | TIMESTAMPTZ | When it finished (null if still running) |
| `status` | TEXT | `running`, `ok`, `fail` |
| `details` | JSONB | Run-specific details (counts, errors, etc.) |

---

## 15. Project File Map

```
quantAlgoV1/
│
├── CLAUDE.md                          # Build spec + constraints (merged)
├── DOCUMENTATION.md                   # This file
├── README.md                          # Project overview and quickstart
├── pyproject.toml                     # Dependencies and project config
├── .env.example                       # Template for environment variables
├── docker-compose.yml                 # Postgres, Redis, Qdrant, Flower
├── alembic.ini                        # Alembic config (DB URL injected at runtime)
│
├── alembic/
│   ├── env.py                         # Async migration runner
│   └── versions/
│       └── 001_initial.py             # Creates all 6 tables
│
├── core/                              # ALL BUSINESS LOGIC LIVES HERE
│   ├── config.py                      # ✅ Settings via pydantic-settings
│   ├── logging.py                     # ✅ Structured JSON logging
│   ├── timeutils.py                   # ✅ NYSE market hours (exchange_calendars)
│   │
│   ├── storage/
│   │   ├── db.py                      # ✅ Async SQLAlchemy engine + session
│   │   ├── models.py                  # ✅ 6 ORM models
│   │   └── repos/
│   │       ├── news_repo.py           # ✅ News CRUD
│   │       ├── strategy_repo.py       # ✅ Strategy CRUD
│   │       ├── run_repo.py            # ✅ Run CRUD
│   │       ├── market_data_repo.py    # ✅ Market data upsert/query
│   │       └── pnl_repo.py           # ✅ PnL snapshot upsert/query
│   │
│   ├── ingestion/
│   │   ├── fetchers/
│   │   │   ├── base.py               # ✅ Fetcher interface
│   │   │   ├── rss.py                # ✅ RSS feed fetcher
│   │   │   ├── market_data.py        # ✅ Alpaca / yfinance fetcher
│   │   │   └── provider_newsapi.py   # 🔲 NewsAPI fetcher (deferred to v2)
│   │   ├── normalize.py              # ✅ Text normalization
│   │   ├── dedupe.py                 # ✅ SHA-256 deduplication
│   │   └── ticker_extract.py         # ✅ Regex ticker extraction
│   │
│   ├── kb/
│   │   ├── vectorstore.py            # ✅ Qdrant + FAISS mock
│   │   ├── chunking.py               # ✅ Deterministic text chunking
│   │   ├── embeddings.py             # ✅ Mock + OpenAI providers
│   │   ├── retrieval.py              # ✅ Query knowledge base
│   │   └── sentiment.py              # ✅ FinBERT / LLM scoring
│   │
│   ├── agent/
│   │   ├── rag_agent.py              # ✅ RAG agent
│   │   ├── prompts.py                # ✅ Versioned prompt constants
│   │   ├── strategy_language.py      # ✅ Strategy JSON spec
│   │   ├── validator.py              # ✅ Strategy validator
│   │   └── approval.py               # ✅ Approval gate
│   │
│   ├── strategies/
│   │   ├── base.py                   # ✅ Strategy interface
│   │   ├── registry.py               # ✅ Strategy registry
│   │   └── implementations/
│   │       ├── sentiment_momentum.py # ✅ Sentiment momentum strategy
│   │       └── event_risk_off.py     # ✅ Event risk-off strategy
│   │
│   ├── backtesting/
│   │   ├── engine.py                 # ✅ Backtesting engine (BuiltinEngine)
│   │   ├── metrics.py                # ✅ Metrics calculation
│   │   └── cost_model.py             # ✅ Trading cost model
│   │
│   ├── execution/
│   │   ├── broker_base.py            # ✅ Broker interface
│   │   ├── paper_broker.py           # ✅ Paper trading broker
│   │   ├── guard.py                  # ✅ PAPER_GUARD enforcement
│   │   ├── alpaca_paper.py           # ✅ Alpaca paper broker
│   │   ├── risk.py                   # ✅ Risk management + circuit breaker
│   │   └── position_sizing.py        # ✅ Position sizing
│   │
│   └── observability/
│       ├── metrics.py                # 🔲 App metrics (deferred to v2)
│       └── tracing.py                # 🔲 Distributed tracing (deferred to v2)
│
├── apps/                             # THIN WRAPPERS — NO BUSINESS LOGIC
│   ├── api/
│   │   ├── main.py                   # ✅ FastAPI app
│   │   ├── deps.py                   # ✅ Dependency injection
│   │   └── routers/
│   │       ├── health.py             # ✅ GET /health
│   │       ├── news.py               # ✅ GET /news/recent
│   │       ├── strategies.py         # ✅ Strategy CRUD + approval
│   │       ├── backtests.py          # ✅ POST /strategies/{name}/backtest
│   │       ├── runs.py               # ✅ GET /runs/recent, POST /runs/news_cycle
│   │       └── pnl.py               # ✅ GET /pnl/daily
│   │
│   ├── mcp_server/
│   │   ├── server.py                 # ✅ MCP stdio server
│   │   ├── schemas.py                # ✅ Tool schemas
│   │   └── tools/
│   │       ├── ingest.py             # ✅ ingest_latest_news
│   │       ├── kb.py                 # ✅ embed_and_upsert_docs, query_kb
│   │       ├── sentiment.py          # ✅ score_sentiment
│   │       ├── strategy.py           # ✅ propose/validate/submit strategy
│   │       ├── backtest.py           # ✅ run_backtest
│   │       ├── execution.py          # ✅ paper_trade_tick
│   │       └── monitoring.py         # ✅ 5 read-only monitoring tools
│   │
│   └── scheduler/
│       ├── worker.py                 # ✅ Celery worker config + beat schedule
│       └── jobs.py                   # ✅ Scheduled pipeline jobs (news_cycle, paper_trade_tick)
│
└── tests/                            # 143 tests across 20 test files
    ├── conftest.py                   # ✅ Fixtures (SQLite, mock config)
    ├── test_smoke.py                 # ✅ Import + config smoke tests
    ├── test_dedupe.py                # ✅ Deduplication logic
    ├── test_ticker_extract.py        # ✅ Ticker regex extraction
    ├── test_market_data.py           # ✅ Market data fetcher + repo
    ├── test_mcp_tools.py             # ✅ MCP pipeline tools
    ├── test_monitoring_tools.py      # ✅ MCP monitoring tools
    ├── test_strategy_validator.py    # ✅ Strategy validation rules
    ├── test_backtest_smoke.py        # ✅ Backtest engine + metrics
    ├── test_approval_gate.py         # ✅ Approval workflow
    ├── test_risk_circuit_breaker.py  # ✅ Circuit breaker + DB rehydration
    ├── test_paper_guard.py           # ✅ PAPER_GUARD enforcement
    ├── test_market_hours.py          # ✅ Market hours + no-op outside hours
    ├── test_api_strategies.py        # ✅ Strategy API endpoints
    ├── test_api_news.py              # ✅ News API endpoints
    ├── test_api_pnl.py               # ✅ PnL API endpoints
    ├── test_api_runs.py              # ✅ Runs API endpoints
    ├── test_api_backtests.py         # ✅ Backtest API endpoints
    ├── test_scheduler_jobs.py        # ✅ Celery task wiring
    └── test_alpaca_paper.py          # ✅ AlpacaPaperBroker + BROKER_PROVIDER

✅ = Implemented    🔲 = Placeholder (deferred to v2)
```

---

## 16. Build Phases — All Complete

All 12 build phases have been completed. The system is functionally complete and ready for local validation (Stage 1 of the deployment roadmap).

| Phase | What Was Built | Status |
|---|---|---|
| **1** | Scaffold + config + logging | **Complete** |
| **2** | Postgres models + Alembic migration | **Complete** |
| **3** | Market data fetcher (Alpaca + yfinance) | **Complete** |
| **4** | News ingestion (RSS fetch, normalize, dedup, ticker extract) | **Complete** |
| **5** | Chunking + embeddings + vectorstore | **Complete** |
| **5b** | Sentiment scoring (FinBERT / mock) | **Complete** |
| **6** | MCP tools 1–4 (ingest, embed, sentiment, query) | **Complete** |
| **7** | RAG agent + strategy language + validator + approval gate | **Complete** |
| **8** | Backtest engine + cost model + metrics | **Complete** |
| **9** | Strategy versioning + approval API | **Complete** |
| **10** | Paper broker + risk management + circuit breaker + PnL persistence | **Complete** |
| **11** | FastAPI endpoints (10 routes) + Celery scheduler (2 periodic tasks) | **Complete** |
| **12** | 143 tests across 20 test files + documentation polish | **Complete** |

**Deferred to v2:** `observability/metrics.py`, `observability/tracing.py` (Prometheus/OpenTelemetry), `provider_newsapi.py` (NewsAPI fetcher).

---

## 17. Future Phases: Quantitative Model Development

The v1 system has solid engineering infrastructure but limited mathematical depth. The following phases add the quantitative rigor expected at professional quant firms. Each phase builds on the previous one — implement in order.

### Phase 13: Alpha Research Framework & Factor Models

**Goal:** Replace ad-hoc signal thresholds with a statistically rigorous factor evaluation pipeline.

**New module:** `core/research/alpha.py`

**What to build:**

- **Information Coefficient (IC) / Rank IC**: For each signal, compute the Spearman rank correlation between the signal value at time *t* and the forward return at *t+1*. This is the industry-standard measure of signal quality. Track IC mean, IC standard deviation, and the **Information Ratio** (IC_mean / IC_std).
- **Factor decay analysis**: Compute IC at horizons 1d, 2d, 5d, 10d, 20d to measure how quickly a signal's predictive power decays. Store decay curves per signal type.
- **Cross-sectional momentum factor**: Replace the current rolling-return-on-open proxy with proper cross-sectional z-scores of returns across the universe. Go long the top decile, flat the bottom.
- **Sentiment factor construction**: Z-score FinBERT sentiment across tickers at each point in time. Test IC against forward returns. This turns the existing raw sentiment scores into a proper tradeable factor.

**Math involved:** Spearman's rho, z-score normalization, forward return calculation with proper lag alignment.

**New files:**
```
core/research/
  alpha.py              # IC/IR computation, factor decay
  factors.py            # Cross-sectional momentum, sentiment factor
tests/
  test_alpha_research.py
```

**New dependencies:** None beyond existing numpy/scipy.

**Why it matters for interviews:** Computing IC/IR is literally what quant researchers do daily. Being able to articulate "my sentiment signal has an IC of 0.03 with a half-life of 3 days" is the language firms speak.

---

### Phase 14: Statistical Validation & Backtest Integrity

**Goal:** Move beyond "Sharpe > 0.5" to statistically defensible strategy validation.

**New module:** `core/backtesting/statistical_tests.py`

**What to build:**

- **Sharpe ratio significance test**: Is the Sharpe ratio statistically different from zero? Compute `t = Sharpe * sqrt(N) / sqrt(1 + skew*Sharpe/2 + (kurt-3)*Sharpe²/4)` (the Lo (2002) adjusted Sharpe test). A Sharpe of 0.5 over 252 days has a t-stat of ~0.5, which is **not significant** — this is critical to understand.
- **Multiple hypothesis correction**: When testing multiple strategy variants, apply Bonferroni or Benjamini-Hochberg FDR correction to p-values. This demonstrates understanding of data mining vs. genuine research.
- **Walk-forward validation**: Replace the single 90-day OOS window with rolling walk-forward: train on [0, T], test on [T, T+k], slide forward by k days. Report the distribution of OOS Sharpe ratios, not just one number.
- **Bootstrap confidence intervals**: Resample daily returns with replacement (block bootstrap to preserve autocorrelation), recompute Sharpe/drawdown 10,000 times, report 95% CI.

**Enhanced metrics in `core/backtesting/metrics.py`:**
- **Sortino Ratio**: Like Sharpe but only penalizes downside deviation. `(R - Rf) / σ_downside`
- **Calmar Ratio**: `CAGR / MaxDrawdown`
- **Profit Factor**: `sum(winning_trades) / abs(sum(losing_trades))`
- **Tail Ratio**: `abs(95th percentile return / 5th percentile return)` — measures payoff asymmetry
- **Skewness and Kurtosis** of the return distribution

**Math involved:** t-statistics, FDR control, block bootstrap, combinatorial purged cross-validation.

**New files:**
```
core/backtesting/
  statistical_tests.py  # Significance tests, bootstrap, walk-forward
tests/
  test_statistical_tests.py
```

**New dependencies:** `statsmodels` (for statistical tests).

**Why it matters for interviews:** Every quant desk knows backtests lie. Showing you understand why (overfitting, multiple comparisons, look-ahead) and how to mitigate it (walk-forward, bootstrap CIs, hypothesis correction) separates you from candidates who just report a Sharpe number.

**Reference:** Andrew Lo, "The Statistics of Sharpe Ratios" (2002); Marcos López de Prado, *Advances in Financial Machine Learning* (2018).

---

### Phase 15: Portfolio Optimization

**Goal:** Replace equal-weight position sizing with mathematically optimal portfolio construction.

**New module:** `core/execution/portfolio_optimizer.py`

**What to build:**

- **Mean-Variance Optimization (Markowitz)**: Given expected returns (from signal scores) and a covariance matrix, solve for weights that maximize the Sharpe ratio. Use `scipy.optimize.minimize` with constraints (long-only, max position size from `RISK_MAX_POSITION_PCT`).
- **Minimum Variance Portfolio**: Useful when you trust your covariance estimate more than your return estimate (you almost always should). Minimize `w'Σw` subject to `sum(w) = 1`, `w >= 0`.
- **Risk Parity**: Allocate such that each position contributes equally to portfolio variance. Compute marginal risk contributions: `w_i * (Σw)_i / sqrt(w'Σw)`. Solve iteratively.
- **Black-Litterman**: Combine market-cap-implied equilibrium returns with your sentiment views. This is the theoretically correct framework for this system — you have views from news analysis and want to tilt away from market-cap weights.
- **Ledoit-Wolf shrinkage**: Use shrunk covariance estimation instead of sample covariance for stability with small sample sizes relative to the number of assets.

**Integration point:** Replace `compute_order_quantity()` in `core/execution/position_sizing.py` with optimizer output. The strategy definition's `position_sizing.type` field gains new valid values: `"mean_variance"`, `"min_variance"`, `"risk_parity"`, `"black_litterman"` (in addition to existing `"equal_weight"`).

**Math involved:** Quadratic programming, Lagrange multipliers, matrix operations, covariance estimation, shrinkage estimators.

**New files:**
```
core/execution/
  portfolio_optimizer.py   # MVO, min-var, risk parity, Black-Litterman
  covariance.py            # Ledoit-Wolf, sample cov, exponentially-weighted
tests/
  test_portfolio_optimizer.py
```

**New dependencies:** `cvxpy` (convex optimization — cleaner than scipy for constrained QP).

**Why it matters for interviews:** Mean-variance optimization is a classic interview topic at every quant firm. Being able to implement it from scratch (not just call a library) and discuss its limitations (estimation error, sensitivity to inputs) is expected.

---

### Phase 16: Time-Varying Volatility & Vol Targeting

**Goal:** Replace flat rolling-window volatility with proper time-series volatility models.

**New module:** `core/research/timeseries.py`

**What to build:**

- **GARCH(1,1) volatility model**: Fit `σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}` via maximum likelihood to get time-varying volatility estimates. Use for:
  - Volatility-targeted position sizing: scale position sizes inversely with predicted vol to maintain constant portfolio risk.
  - Improved VIX replacement: instead of using VIXY as a VIX proxy, compute realized + predicted vol directly from the price series.
- **Exponentially Weighted Moving Average (EWMA) volatility**: Faster alternative to GARCH. `σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}` with λ ≈ 0.94 (RiskMetrics standard).
- **Volatility regime classification**: Simple threshold-based (low/medium/high vol regimes) using GARCH output. Condition strategy behavior on regime — e.g., tighter position limits in high-vol regimes.
- **Stationarity testing**: ADF (Augmented Dickey-Fuller) test on every signal before using it. Non-stationary signals produce spurious backtest results. Auto-difference if needed.

**Integration point:** Add `"volatility_target"` as a new `position_sizing.type` in the strategy definition. When active, the optimizer scales weights by `target_vol / predicted_vol` each day.

**Math involved:** MLE for GARCH parameters, EWMA recursion, ADF/Phillips-Perron tests, regime classification.

**New files:**
```
core/research/
  timeseries.py          # GARCH, EWMA, stationarity tests
  volatility.py          # Vol targeting, regime detection
tests/
  test_timeseries.py
```

**New dependencies:** `arch` (GARCH models — better than statsmodels for this specific task).

**Why it matters for interviews:** Understanding that volatility clusters and modeling it properly (not just using a flat 20-day rolling window) shows time-series sophistication that most candidates lack.

---

### Phase 17: Risk Analytics & VaR/CVaR

**Goal:** Replace simple threshold-based risk checks with distributional risk modeling.

**New module:** `core/backtesting/risk_analytics.py`

**What to build:**

- **Value at Risk (VaR)** — three methods:
  - *Parametric*: Assume normal distribution, compute `VaR = μ - z_α · σ` where z_α is the normal quantile (e.g., 1.645 for 95% VaR).
  - *Historical*: Sort historical returns, take the 5th percentile (for 95% VaR). No distributional assumptions.
  - *Monte Carlo*: Simulate 10,000 return paths from a fitted distribution (e.g., GARCH-predicted vol + Student-t innovations), compute VaR from simulated distribution.
- **Conditional VaR (CVaR / Expected Shortfall)**: The mean of returns below the VaR threshold. More useful than VaR because it captures tail shape. Required by Basel III for bank risk reporting.
- **Drawdown distribution**: Compute max drawdown under Monte Carlo simulated paths to get a confidence interval (e.g., "95% CI for max drawdown is [8%, 22%]"), not just the single historical max.
- **Stress testing**: Define scenario shocks (e.g., "SPY drops 10% in one day", "correlation spike to 0.9") and compute portfolio impact under each scenario.

**Integration point:**
- Add VaR/CVaR to backtest output metrics alongside Sharpe/drawdown.
- Add VaR-based position limits: if portfolio 1-day 95% VaR exceeds a configurable threshold, reduce position sizes.
- Circuit breaker gains a VaR-based early warning: log a warning when estimated 1-day VaR exceeds 1.5x the daily loss limit.

**Math involved:** Quantile functions, conditional expectations, Monte Carlo simulation, copula-based stress testing.

**New files:**
```
core/backtesting/
  risk_analytics.py     # VaR, CVaR, drawdown distribution, stress tests
tests/
  test_risk_analytics.py
```

**New dependencies:** None beyond existing numpy/scipy.

**Why it matters for interviews:** Every risk desk uses VaR/CVaR. Understanding the differences between parametric, historical, and Monte Carlo VaR — and being able to explain why CVaR is superior — is table stakes.

---

### Phase 18: Regime Detection (Hidden Markov Models)

**Goal:** Detect bull/bear market regimes and condition strategy behavior on the current regime.

**New module:** `core/research/regime.py`

**What to build:**

- **2-state Hidden Markov Model (HMM)**: Fit a Gaussian HMM to daily returns with two hidden states (bull regime: positive mean + low vol; bear regime: negative mean + high vol). Use the Baum-Welch algorithm (EM) for parameter estimation and Viterbi algorithm for state decoding.
- **Regime-conditioned strategy execution**: Only trade momentum signals in the bull regime. Switch to risk-off (flat or defensive positions) in the bear regime. The regime state becomes a new signal type (`"type": "regime_filter"`) in the strategy definition.
- **Online regime detection**: After initial training on historical data, update regime probabilities in real-time as new bars arrive using the forward algorithm. No need to retrain the full model each tick.
- **Regime transition probabilities**: Expose the estimated transition matrix so the agent can reason about regime persistence (e.g., "the model estimates a 95% probability of staying in the current bull regime tomorrow").

**Integration point:** Add `"regime_filter"` as a new signal type in the strategy language. When present, the signal evaluator queries the regime model before evaluating other signals.

**Math involved:** EM algorithm, Viterbi decoding, forward-backward algorithm, Gaussian mixture emissions.

**New files:**
```
core/research/
  regime.py              # HMM training, online updates, regime classification
tests/
  test_regime.py
```

**New dependencies:** `hmmlearn` (Hidden Markov Models).

**Why it matters for interviews:** This is a differentiator. Most candidates can talk about momentum and mean-reversion. Few can implement a regime-switching model and explain why a momentum strategy fails in bear markets. Shows ML applied correctly to finance (not just "I threw a neural net at stock prices").

---

### Phase 19: Pairs Trading & Statistical Arbitrage

**Goal:** Add market-neutral strategies based on cointegration and mean-reversion of price spreads.

**New module:** `core/research/pairs.py`, `core/strategies/implementations/pairs_trading.py`

**What to build:**

- **Cointegration testing**: Implement Engle-Granger two-step procedure and Johansen trace test to identify cointegrated pairs within the approved universe. A cointegrated pair means their price spread is mean-reverting even if individual prices are random walks.
- **Spread construction**: For each cointegrated pair, estimate the hedge ratio via OLS regression (`price_A = β·price_B + ε`). The spread is `price_A - β·price_B`. Compute the z-score of the spread.
- **Ornstein-Uhlenbeck half-life**: Fit the O-U process `dX_t = θ(μ - X_t)dt + σdW_t` to the spread via OLS on `ΔX = a + bX_{t-1}`. Half-life = `-ln(2)/b`. Short half-lives (< 20 days) suggest profitable mean-reversion.
- **Pairs trading signals**: Enter when spread z-score exceeds ±2σ, exit when it reverts to ±0.5σ or after a time stop. This is a market-neutral strategy — long one leg, short the other — so it has low correlation with broad market moves.
- **Rolling cointegration check**: Re-test cointegration every N days. If a pair loses cointegration, close the position and remove the pair.

**Integration point:** Add `"pairs_mean_reversion"` as a new signal type. The strategy definition gains a `"pairs"` field listing ticker pairs and their parameters. The backtester and signal evaluator both need to handle paired positions (long + short simultaneously).

**Important caveat:** This requires expanding the broker interface to support short selling (at least in paper mode). The current `PaperBroker` only handles long positions. Add a `short_sell()` method alongside the existing `submit_order()`.

**Math involved:** Engle-Granger procedure, Johansen test, OLS regression, O-U process MLE, z-score signals.

**New files:**
```
core/research/
  pairs.py               # Cointegration tests, spread construction, O-U half-life
core/strategies/implementations/
  pairs_trading.py       # Pairs trading strategy
tests/
  test_pairs.py
```

**New dependencies:** `statsmodels` (already needed from Phase 14 for cointegration tests).

**Why it matters for interviews:** Pairs trading is the canonical statistical arbitrage strategy. Being able to explain cointegration vs. correlation, derive the hedge ratio, and compute the O-U half-life demonstrates deep understanding of the math behind stat-arb desks.

---

### Implementation Priority & Dependency Graph

```
Phase 13 (Alpha/IC)
  ↓
Phase 14 (Statistical Tests) ← depends on Phase 13 for factor metrics
  ↓
Phase 15 (Portfolio Optimization) ← depends on Phase 14 for validation
  ↓
Phase 16 (GARCH/Vol) ← depends on Phase 15 for vol-targeted sizing
  ↓
Phase 17 (VaR/CVaR) ← depends on Phase 16 for vol model inputs
  ↓
Phase 18 (Regime HMM) ← depends on Phase 16 for vol regime classification
  ↓
Phase 19 (Pairs Trading) ← independent, but benefits from Phases 14-16
```

### New Dependencies Summary

| Package | Phase | Purpose |
|---|---|---|
| `statsmodels` | 14, 19 | ADF test, OLS, cointegration, statistical tests |
| `cvxpy` | 15 | Convex optimization for portfolio construction |
| `arch` | 16 | GARCH models |
| `hmmlearn` | 18 | Hidden Markov Models |

### Suggested `pyproject.toml` Addition

```toml
[project.optional-dependencies]
quant = [
    "statsmodels>=0.14",
    "cvxpy>=1.4",
    "arch>=6.0",
    "hmmlearn>=0.3",
]
```

---

## 18. Deployment Roadmap: Local → Railway

The project follows a two-stage deployment strategy.

### Stage 1: Local Development & Testing (Current)

All development, testing, and paper trading validation happens on the local machine.

**Local environment specs:**
- CPU: AMD Ryzen 7 7700X (8 cores / 16 threads)
- RAM: 31 GB
- OS: Windows 11

**What runs locally:**

| Service | How It Runs | Resource Usage |
|---|---|---|
| Postgres 16 | Docker container | ~200 MB RAM |
| Redis 7 | Docker container | ~50 MB RAM |
| Qdrant | Docker container | ~200 MB RAM |
| Flower | Docker container | ~100 MB RAM |
| FastAPI server | Python process (venv) | ~100 MB RAM |
| Celery worker | Python process (venv) | ~100 MB RAM |
| FinBERT model | Loaded by Celery worker | ~1.5 GB RAM |
| **Total** | | **~2.3 GB RAM** |

With 31 GB of RAM, the local machine has more than enough headroom. The Ryzen 7 7700X handles all concurrent services without issue.

**Goals before moving to Stage 2:**
1. All 12 build phases complete
2. Full test suite passing (`pytest` exits 0 with all test files)
3. End-to-end paper trading validated over at least one full trading week
4. Pipeline runs reliably without manual intervention during market hours
5. Circuit breaker tested and confirmed working
6. PnL tracking verified against manual calculations

### Stage 2: Railway Cloud Deployment (Future)

Once the system is validated locally, it migrates to [Railway](https://railway.app) for always-on operation during market hours without requiring the local machine to stay powered on.

**Why Railway:**
- Managed Postgres, Redis built-in (no Docker needed)
- Simple deploy from GitHub repo
- Scales vertically if FinBERT or Qdrant needs more RAM
- Affordable for a single-user system (~$5-20/month depending on usage)
- Supports cron-like scheduling natively

**Railway service mapping:**

| Local Component | Railway Equivalent |
|---|---|
| Docker Postgres | Railway managed Postgres plugin |
| Docker Redis | Railway managed Redis plugin |
| Docker Qdrant | Railway service (custom Docker image) |
| `uvicorn apps.api.main:app` | Railway web service (auto-detected from Procfile) |
| `celery -A apps.scheduler.worker worker` | Railway worker service |
| Docker Flower | Railway service (optional, for monitoring) |

**What changes for Railway:**
- `DATABASE_URL`, `REDIS_URL` — injected by Railway automatically
- `QDRANT_URL` — points to the Qdrant Railway service's internal URL
- A `Procfile` or `railway.toml` is added to define services
- `docker-compose.yml` is no longer needed (Railway manages infrastructure)
- Environment variables are set in the Railway dashboard instead of `.env`

**What does NOT change:**
- All Python code stays exactly the same
- `core/config.py` already reads everything from env vars — no code changes needed
- Alembic migrations run the same way (`alembic upgrade head`)
- The test suite runs the same way

**Migration checklist (to be completed when ready):**
- [ ] Create Railway project linked to the GitHub repo
- [ ] Provision Postgres and Redis plugins
- [ ] Deploy Qdrant as a custom service
- [ ] Set all environment variables in Railway dashboard
- [ ] Add `Procfile` with web and worker processes
- [ ] Run `alembic upgrade head` on Railway Postgres
- [ ] Verify health endpoint responds
- [ ] Run one full news cycle end-to-end
- [ ] Confirm paper trading ticks during market hours
- [ ] Monitor for 1 full trading day before considering it stable

### Stage 3: Kubernetes Orchestration (Future)

Once the system is proven on Railway, the final stage scales it into a multi-instance architecture using Kubernetes. The key idea: **separate Docker containers focus on specific markets or stock types**, and **Kubernetes coordinates all of them for portfolio-level decisions**.

**Why Kubernetes:**
- Run specialized strategy pods per market sector (e.g., one pod for tech stocks, another for energy, another for ETFs)
- Each pod has its own ingestion pipeline, embeddings, and strategy — tuned to that market's characteristics
- A central portfolio coordinator aggregates positions, enforces cross-strategy risk limits, and prevents conflicting trades
- Horizontal scaling: add a new market by deploying a new pod with its own config
- Self-healing: K8s restarts crashed pods automatically, ensuring market hours are never missed
- Resource isolation: FinBERT sentiment scoring gets dedicated GPU nodes; lightweight RSS ingestion stays on small CPU nodes

**Architecture overview:**

```
┌─────────────────────────────────────────────────────────┐
│                   Kubernetes Cluster                     │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Tech Stocks  │  │   Energy     │  │   ETFs       │  │
│  │  Strategy Pod │  │  Strategy Pod│  │  Strategy Pod│  │
│  │              │  │              │  │              │  │
│  │ - RSS ingest │  │ - RSS ingest │  │ - RSS ingest │  │
│  │ - Embed/RAG  │  │ - Embed/RAG  │  │ - Embed/RAG  │  │
│  │ - Sentiment  │  │ - Sentiment  │  │ - Sentiment  │  │
│  │ - Backtest   │  │ - Backtest   │  │ - Backtest   │  │
│  │ - Paper trade│  │ - Paper trade│  │ - Paper trade│  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └────────┬────────┘────────┬────────┘           │
│                  ▼                 ▼                     │
│  ┌─────────────────────────────────────────────┐        │
│  │       Portfolio Coordinator Service          │        │
│  │                                             │        │
│  │ - Aggregates positions across all pods      │        │
│  │ - Enforces portfolio-wide risk limits       │        │
│  │ - Prevents conflicting trades (long AAPL    │        │
│  │   in tech pod + short AAPL in ETF pod)      │        │
│  │ - Global circuit breaker (total portfolio)  │        │
│  │ - Rebalances cross-strategy exposure        │        │
│  └──────────────────┬──────────────────────────┘        │
│                     │                                   │
│  ┌──────────────────┴──────────────────────────┐        │
│  │            Shared Infrastructure             │        │
│  │                                             │        │
│  │  Postgres (StatefulSet or managed)          │        │
│  │  Redis (for Celery + caching)               │        │
│  │  Qdrant (StatefulSet with persistent vol)   │        │
│  │  Prometheus + Grafana (observability)        │        │
│  └─────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

**Per-pod configuration:**

Each strategy pod gets its own environment overrides. The same codebase is deployed to every pod — only environment variables differ:

| Variable | Tech Pod | Energy Pod | ETFs Pod |
|---|---|---|---|
| `STRATEGY_APPROVED_UNIVERSE` | `AAPL,MSFT,NVDA,GOOGL,META` | `XOM,CVX,SLB,EOG,COP` | `SPY,QQQ,IWM,DIA,XLF` |
| `NEWS_SOURCES` | Tech-focused RSS feeds | Energy-focused RSS feeds | Broad market feeds |
| `VECTOR_COLLECTION` | `news_tech` | `news_energy` | `news_etf` |
| `STRATEGY_MIN_CONFIDENCE` | `0.7` (higher bar) | `0.6` | `0.5` (more liquid) |

**Portfolio Coordinator responsibilities:**
- Runs as a separate Deployment in the cluster
- Reads all strategy pods' positions from the shared Postgres `pnl_snapshots` table
- Computes aggregate gross exposure, net exposure, sector concentration
- If total portfolio daily loss exceeds a global threshold, sends a "halt" signal to all pods
- Detects conflicting positions (e.g., one pod is long AAPL, another is short via an ETF that holds AAPL) and flags for human review
- Exposes a dashboard API for cross-strategy portfolio visualization

**K8s resource types:**

| Component | K8s Resource | Replicas | Notes |
|---|---|---|---|
| Strategy pod | Deployment | 1 per market | Each gets its own ConfigMap for env |
| Portfolio coordinator | Deployment | 1 | Reads from shared DB |
| Postgres | StatefulSet or managed (e.g., CloudNativePG) | 1 primary + 1 replica | Persistent volume claims |
| Redis | Deployment | 1 | Or managed (ElastiCache, etc.) |
| Qdrant | StatefulSet | 1+ | Persistent volume for vectors |
| Celery workers | Deployment | 1 per pod | Separate queue per market |
| Flower | Deployment | 1 | Monitoring all queues |
| Prometheus | StatefulSet | 1 | Scrapes all pods |
| Grafana | Deployment | 1 | Dashboards for PnL, latency, errors |

**What changes for Kubernetes:**
- A `k8s/` directory is added with Helm charts or Kustomize manifests
- Each strategy pod gets a ConfigMap with its market-specific environment variables
- The portfolio coordinator is a new `core/portfolio/coordinator.py` module
- Celery queues are namespaced per market (e.g., `tech_queue`, `energy_queue`)
- Observability layer (`core/observability/`) is fully implemented with Prometheus metrics
- Health endpoints gain readiness and liveness probe paths (`/health/ready`, `/health/live`)

**What does NOT change:**
- All existing Python code, models, and MCP tools remain the same
- The per-pod pipeline is identical to the single-instance pipeline
- `core/config.py` already reads everything from env vars — no code changes needed
- The test suite runs the same way

**Migration checklist (to be completed when ready):**
- [ ] Choose a K8s provider (EKS, GKE, AKS, or self-hosted k3s)
- [ ] Create Helm chart / Kustomize base for the application
- [ ] Define ConfigMaps for each market sector
- [ ] Deploy shared infrastructure (Postgres, Redis, Qdrant) as StatefulSets
- [ ] Deploy first strategy pod and verify it runs a full news cycle
- [ ] Build the portfolio coordinator service
- [ ] Deploy additional strategy pods for other markets
- [ ] Set up Prometheus + Grafana for cross-pod monitoring
- [ ] Configure HorizontalPodAutoscaler for Celery workers
- [ ] Set up PodDisruptionBudgets for zero-downtime upgrades
- [ ] Run all strategy pods through 1 full trading week before adding more markets
- [ ] Document runbook for adding a new market sector (copy ConfigMap, deploy pod)

---

## 19. Monitoring with Claude Desktop (Dual MCP Servers)

This system can be monitored conversationally using Claude Desktop with two MCP servers running side by side:

1. **quant-news-rag** (our server) — exposes pipeline tools and 5 read-only monitoring tools
2. **alpaca-market-data** (Alpaca's official MCP server) — provides real-time market data and paper account info

### Setup

1. Install the Alpaca MCP server:
   ```bash
   pip install alpaca-mcp-server
   ```

2. Copy the MCP config template to your Claude Desktop config directory:
   ```bash
   cp mcp-config.example.json ~/.claude/mcp-config.json
   ```

3. Edit the config to fill in your Alpaca API credentials and correct `DATABASE_URL`.

4. Restart Claude Desktop to pick up the new MCP server configuration.

### Our Monitoring Tools

These 5 tools provide read-only visibility into system internals that Alpaca's server knows nothing about:

| Tool | Description | Example Question |
|---|---|---|
| `monitor_strategies` | List all strategies with status, version, backtest metrics | "What strategies are pending approval?" |
| `monitor_runs` | Recent pipeline runs (ingest, embed, sentiment, etc.) | "When did the last news cycle run?" |
| `monitor_pnl` | Daily PnL snapshots for a strategy | "Show me PnL for sentiment_momentum_v1 this week" |
| `monitor_health` | System health: trading mode, market status, connectivity | "Is the system healthy?" |
| `monitor_news` | Recent news articles with sentiment and tickers | "What news was ingested in the last hour?" |

### Alpaca MCP Server — Safe vs. Unsafe Tools

The Alpaca MCP server exposes tools for both reading and trading. Only use the read-only tools:

| Safe (Read-Only) | Unsafe (Do NOT Use) |
|---|---|
| Get account info | Place orders |
| Get positions | Cancel orders |
| Get portfolio history | Close positions |
| Get market data (bars, quotes) | |
| Get watchlist | |
| Get order history | |

The Alpaca server's trading tools bypass our safety rails (PAPER_GUARD, strategy approval, circuit breaker). All trading should go through our pipeline.

### Safety Notes

- Always set `ALPACA_PAPER_TRADE=True` in the Alpaca MCP server config. This ensures it connects to Alpaca's paper environment, not live.
- `PAPER_GUARD=true` in our server prevents any live broker from being instantiated.
- The two servers maintain **independent position ledgers**. Our `pnl_snapshots` table tracks positions from our paper broker. Alpaca's account shows positions placed through their API. They do not sync automatically.
- If you use Alpaca's MCP server to place a paper trade directly, our system will not know about it — it won't appear in `monitor_pnl` results.

### Example Operator Conversations

**Checking system status:**
> "Is the system healthy? When was the last news ingestion?"
>
> Claude calls `monitor_health` from our server and reports: trading mode is paper, market is open, last ingest was 3 minutes ago, 12 articles in the last 2 hours, Qdrant is connected.

**Reviewing a pending strategy:**
> "What strategies are pending approval? What are their backtest metrics?"
>
> Claude calls `monitor_strategies` with status filter `pending_approval` and displays the strategy name, version, Sharpe ratio, drawdown, and win rate.

**Checking real-time market data alongside PnL:**
> "What's the current price of SPY? And show me today's PnL for sentiment_momentum_v1."
>
> Claude calls Alpaca's market data tool for SPY's latest quote, then calls `monitor_pnl` from our server for today's snapshot. Both answers appear in the same conversation.

**Reviewing recent news sentiment:**
> "What news came in during the last 30 minutes? How's the sentiment?"
>
> Claude calls `monitor_news` with minutes=30 and displays titles, sources, sentiment labels, and extracted tickers.

---

## 20. Glossary

| Term | Definition |
|---|---|
| **Bar** | A single OHLCV (Open, High, Low, Close, Volume) data point for a ticker at a specific time |
| **Basis point (bps)** | 1/100th of 1%. 5 bps = 0.05%. Used for slippage and spread costs. |
| **Circuit breaker** | Automatic safety mechanism that halts all trading when daily losses exceed a threshold (2%) |
| **Cosine similarity** | Mathematical measure of similarity between two vectors. Used for semantic search in Qdrant. |
| **Drawdown** | Peak-to-trough decline in portfolio value. Max drawdown is the worst such decline. |
| **Embedding** | A numerical vector representation of text that captures semantic meaning. Used for similarity search. |
| **FinBERT** | A BERT language model fine-tuned on financial text for sentiment analysis |
| **Gross exposure** | Total absolute value of all positions divided by portfolio value. 1.0 = fully invested. |
| **Lookahead bias** | A backtesting bug where future data accidentally influences past decisions |
| **MCP** | Model Context Protocol — a standard for exposing tools to AI agents |
| **OHLCV** | Open, High, Low, Close, Volume — standard price bar format |
| **OOS** | Out-of-sample — a test window separate from the training/optimization window |
| **Paper trading** | Simulated trading with fake money to test strategies without financial risk |
| **PAPER_GUARD** | A runtime flag that prevents any real brokerage orders from being placed |
| **PnL** | Profit and Loss — the financial result of trading activity |
| **RAG** | Retrieval-Augmented Generation — an AI pattern where relevant documents are retrieved before generating a response |
| **Qdrant** | An open-source vector database for similarity search |
| **Sharpe ratio** | Risk-adjusted return metric. (Return - Risk-free rate) / Standard deviation. Higher is better. |
| **Slippage** | The difference between expected trade price and actual execution price |
| **Survivorship bias** | The error of only testing on tickers that currently exist, ignoring delisted ones |
| **Win rate** | Percentage of trades that were profitable |
| **pending_approval** | Strategy status meaning the AI proposed it but a human hasn't approved it yet |
| **active** | Strategy status meaning it's currently being paper-traded |
| **archived** | Strategy status meaning it was superseded by a newer version |
