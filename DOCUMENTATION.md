# Quant News-RAG Trading System — Technical Documentation

> A modular, paper-first quantitative trading system that ingests financial news, builds a vector knowledge base, uses a RAG agent to propose strategy updates, backtests them, and executes paper trades.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Prerequisites & Setup](#3-prerequisites--setup)
4. [Configuration Reference](#4-configuration-reference)
5. [Data Flow: Market Data](#5-data-flow-market-data)
6. [Data Flow: News Ingestion](#6-data-flow-news-ingestion)
7. [How Trading Decisions Are Made](#7-how-trading-decisions-are-made)
8. [Paper Trading & Signal Evaluation](#8-paper-trading--signal-evaluation)
9. [Backtesting](#9-backtesting)
10. [Safety Rails & Risk Controls](#10-safety-rails--risk-controls)
11. [API Reference](#11-api-reference)
12. [MCP Server](#12-mcp-server)
13. [Day-to-Day Usage](#13-day-to-day-usage)
14. [Database Schema](#14-database-schema)
15. [Project File Map](#15-project-file-map)
16. [Running Tests](#16-running-tests)
17. [Monitoring with Claude Desktop](#17-monitoring-with-claude-desktop)
18. [Future Phases: Quantitative Model Development](#18-future-phases-quantitative-model-development)
19. [Deployment Roadmap](#19-deployment-roadmap)
20. [Known Limitations](#20-known-limitations)
21. [Glossary](#21-glossary)

---

## 1. System Overview

This is an autonomous background system that:

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
                    +---------------+
                    |  RSS Feeds    |
                    |  (Yahoo,      |
                    |  NewsAPI)     |
                    +-------+-------+
                            |
                            v
               +------------------------+
               |   NEWS INGESTION       |
               |                        |
               |  fetch -> normalize    |
               |  -> deduplicate        |
               |  -> extract tickers    |
               |  -> store in Postgres  |
               +------------+-----------+
                            |
              +-------------+-------------+
              v             v             v
      +----------+   +----------+   +----------+
      |  Chunk   |   | Sentiment|   |  Market  |
      |  + Embed |   | Scoring  |   |  Data    |
      |  -> Qdrant|  | (FinBERT)|   | (Alpaca) |
      +-----+----+   +-----+----+  +-----+----+
            |               |             |
            v               v             v
      +-------------------------------------------+
      |           POSTGRES DATABASE               |
      |  news_documents | market_bars             |
      |  strategy_versions | pnl_snapshots        |
      +---------------------+---------------------+
                            |
                            v
              +-----------------------+
              |     RAG AGENT         |
              |                       |
              |  queries Qdrant       |
              |  reads recent news    |
              |  proposes strategy    |
              |  cites sources        |
              +-----------+-----------+
                          |
                          v
              +-----------------------+
              |    VALIDATOR          |
              |                       |
              |  checks tickers       |
              |  checks risk limits   |
              |  checks diff count    |
              +-----------+-----------+
                          |
                          v
              +-----------------------+
              |    BACKTESTER         |
              |                       |
              |  1-year in-sample     |
              |  90-day out-sample    |
              |  cost model           |
              +-----------+-----------+
                          |
                   passes thresholds?
                     |           |
                    YES          NO -> discard
                     |
                     v
              +-----------------------+
              |  PENDING APPROVAL     |
              |  (waits for human)    |
              +-----------+-----------+
                          |
                   human approves?
                     |           |
                    YES          NO -> archived
                     |
                     v
              +-----------------------+
              |   PAPER BROKER        |
              |                       |
              |  executes signals     |
              |  tracks positions     |
              |  records PnL          |
              |  circuit breaker      |
              +-----------------------+
```

### Service Boundaries

The codebase is split into four layers with strict dependency direction:

```
apps/api/          ->  FastAPI REST layer. Thin wrappers only — no business logic.
apps/mcp_server/   ->  MCP tool implementations. Calls core/ directly, never api/.
apps/scheduler/    ->  Celery task queue. Runs the automated pipeline on timers.
core/              ->  ALL business logic. Independently importable.

Dependency rule:
  apps/* -> core/*   (apps can import from core)
  core/* -> apps/*   (core NEVER imports from apps)
```

### Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Async throughout |
| C++ Extension | pybind11 (`_quant_core`) | Hot-path execution and backtesting logic compiled to native code |
| Build System | scikit-build-core + CMake | Compiles C++ extension; replaces setuptools |
| API | FastAPI | REST endpoints with Pydantic v2 validation |
| Task Queue | Celery + Redis | Scheduled jobs with retries and visibility (Flower UI) |
| Database | PostgreSQL 16 | All persistent state (6 tables) |
| Migrations | Alembic | Schema versioning (async mode) |
| Vector DB | Qdrant | Semantic search over news embeddings |
| Embeddings | Pluggable (mock / OpenAI) | Controlled by `EMBEDDINGS_PROVIDER` env var |
| Sentiment | FinBERT (local) | Finance-tuned sentiment scoring |
| Market Data | Alpaca API / yfinance | Historical + real-time OHLCV bars |
| Backtesting | vectorbt / backtrader | Strategy simulation (adapter pattern, swappable) |
| Broker | PaperBroker (internal) or AlpacaPaperBroker | Simulated order execution. Controlled by `BROKER_PROVIDER`. |

### C++ Extension (`_quant_core`)

Performance-critical execution and backtesting logic is implemented in C++ and exposed to Python via pybind11. The extension module `_quant_core` is compiled at install time by scikit-build-core + CMake.

**What moved to C++:**

| Component | C++ class | Python wrapper |
|---|---|---|
| Cost model | `CostModel` | `core/backtesting/cost_model.py` |
| Performance metrics | `compute_metrics()` | `core/backtesting/metrics.py` |
| Backtest engine | `BacktestEngine` | `core/backtesting/engine.py` |
| Paper broker | `PaperBroker` | `core/execution/paper_broker.py` |
| Risk checks | `check_exposure()`, `check_position_limit()`, `check_trade_rate()` | `core/execution/risk.py` |
| Position sizing | `compute_position_size()` | `core/execution/position_sizing.py` |
| Signal reconciliation | `SignalReconciler` | `core/execution/signal_evaluator.py` |

The Python modules remain the public API — they delegate to `_quant_core` internally. This preserves backward compatibility: all existing imports and function signatures are unchanged. If the C++ extension is unavailable (e.g., import error), the Python fallback code runs instead.

**Build:** `pip install -e ".[dev]"` triggers CMake, which compiles `cpp/src/*.cpp` and `cpp/bindings/*.cpp` into a shared library placed alongside the Python packages.

**Testing:** 24 parity tests in `tests/test_cpp_parity.py` verify that C++ and Python implementations produce identical results for every component.

---

## 3. Prerequisites & Setup

### What You Need Installed

1. **Python 3.11+**
2. **C++ build toolchain** — required to compile the `_quant_core` pybind11 extension:
   - **Windows:** MSVC 2022 Build Tools (`winget install Microsoft.VisualStudio.2022.BuildTools`), plus `cmake` and `ninja` (`pip install cmake ninja`)
   - **Linux/macOS:** `build-essential`, `cmake`, `ninja-build`, `python3-dev`
3. **Docker Desktop** — provides `docker` and `docker compose` for running Postgres, Redis, and Qdrant
4. **Git** — for version control

### API Keys

| Service | Required? | How to Get |
|---|---|---|
| Alpaca | Required for market data | Free account at [alpaca.markets](https://alpaca.markets). Get API key + secret from the dashboard. |
| Anthropic | Required for RAG agent | API key from [console.anthropic.com](https://console.anthropic.com). Powers the LLM calls in the RAG agent. |
| OpenAI | Optional (mock works for dev) | API key from [platform.openai.com](https://platform.openai.com). Only needed if `EMBEDDINGS_PROVIDER=openai`. |
| NewsAPI | Optional (RSS is default) | API key from [newsapi.org](https://newsapi.org). Only needed for the NewsAPI provider. |

For local development, you can run with **zero API keys** — the system defaults to `EMBEDDINGS_PROVIDER=mock` and `MARKET_DATA_PROVIDER=yfinance`.

### First-Time Setup

```bash
# 1. Clone the repo
git clone git@github.com:juancal28/quantAlgoV1.git
cd quantAlgoV1

# 2. Create and activate a virtual environment
python -m venv .venv
# On macOS/Linux:
source .venv/bin/activate
# On Windows (Git Bash):
source .venv/Scripts/activate

# 3. Install all dependencies (including dev tools)
# This also compiles the C++ extension via scikit-build-core + CMake
pip install -e ".[dev]"

# For sentiment analysis with FinBERT and backtesting with vectorbt:
pip install -e ".[sentiment,backtest]"

# 4. Copy the example env file and fill in your keys
cp .env.example .env
# Edit .env with your API keys

# 5. Start the backing services
docker compose up -d
# This starts:
#   Postgres  -> localhost:5432
#   Redis     -> localhost:6379
#   Qdrant    -> localhost:6333
#   Flower    -> localhost:5555 (Celery monitoring UI)

# 6. Run the database migration
alembic upgrade head
# Creates all 6 tables in Postgres

# 7. Verify everything works
pytest
# Should show all tests passing
```

---

## 4. Configuration Reference

All configuration is managed through environment variables loaded from a `.env` file via `core/config.py` (using `pydantic-settings`). Never hardcode values.

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

### LLM / RAG Agent

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty)* | Required for RAG agent LLM calls |

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
| `STRATEGY_MIN_CONFIDENCE` | `0.6` | Agent must have >=60% confidence to propose a change |
| `STRATEGY_MAX_DIFF_FIELDS` | `3` | Max fields the agent can change per proposal |
| `STRATEGY_MAX_ACTIVATIONS_PER_DAY` | `4` | Max strategy activations in a 24-hour window |
| `STRATEGY_MIN_BACKTEST_DAYS` | `252` | Minimum backtest window (252 trading days ~ 1 year) |
| `PENDING_APPROVAL_AUTO_APPROVE_MINUTES` | `0` | 0 = never auto-approve; N = auto-approve after N minutes |

### Multi-Agent

The system supports running N independent RAG agents in a single process, each focused on a different market segment. Configured via a single JSON environment variable. When `AGENT_CONFIGS` is empty (`[]`), the system falls back to single-agent behavior.

| Variable | Default | Description |
|---|---|---|
| `AGENT_CONFIGS` | `[]` | JSON array of agent configs. Each agent gets its own RSS feeds, Qdrant collection, and strategy name. |

Each agent config object has:

| Field | Description |
|---|---|
| `name` | Unique agent identifier (e.g., `"tech"`, `"energy"`) |
| `feed_urls` | List of RSS feed URLs specific to this agent's market segment |
| `collection_name` | Qdrant collection name for this agent's embeddings |
| `strategy_name` | Strategy name this agent proposes updates for |

Example:
```json
AGENT_CONFIGS='[
  {"name": "tech", "feed_urls": ["https://..."], "collection_name": "news_tech", "strategy_name": "tech_momentum_v1"},
  {"name": "energy", "feed_urls": ["https://..."], "collection_name": "news_energy", "strategy_name": "energy_sentiment_v1"}
]'
```

Shared across agents: Postgres `news_documents` table (deduplicated), Redis task queue, sentiment scoring. Each agent registers its own Celery beat schedule entry (`news-cycle-{agent.name}`).

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

## 5. Data Flow: Market Data

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
----------------------------------------------------------------------------------------------
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

## 6. Data Flow: News Ingestion

### The Ingestion Pipeline

Every `NEWS_POLL_INTERVAL_SECONDS` (default: 2 minutes), the system runs:

```
Step 1: FETCH
  - RSS fetcher hits configured feeds (Yahoo Finance by default)
  - Pulls up to MAX_DOCS_PER_POLL (50) articles

Step 2: NORMALIZE
  - Strips HTML tags
  - Standardizes encoding
  - Extracts title, content, published date, source URL

Step 3: DEDUPLICATE
  - Computes SHA-256 hash of normalized content
  - Checks content_hash against Postgres (unique index)
  - Checks source_url against Postgres (unique index)
  - Skips any article already seen

Step 4: EXTRACT TICKERS
  - Regex-based extraction of stock symbols from text
  - Matched against STRATEGY_APPROVED_UNIVERSE
  - Stored in the metadata JSON column: {"tickers": ["AAPL", "MSFT"]}

Step 5: STORE
  - Insert into news_documents table in Postgres
  - Returns list of new doc_ids

Step 6: CHUNK + EMBED
  - Each article split into ~1000-character chunks with 150-char overlap
  - Chunks are embedded (mock zeros in dev, OpenAI vectors in prod)
  - Vectors upserted into Qdrant with payload metadata:
    {doc_id, title, source, source_url, published_at, tickers,
     sentiment_score, sentiment_label, chunk_index, chunk_total}

Step 7: SCORE SENTIMENT
  - FinBERT scores each article: positive / negative / neutral + confidence
  - Scores saved to both Postgres (news_documents.sentiment_score) and
    Qdrant (payload.sentiment_score)
```

### Qdrant Vector DB Configuration

The vector collection uses:
- **Cosine distance** for similarity search
- **int8 scalar quantization** (keeps vectors in RAM for fast search)
- **1536 dimensions** (matching OpenAI text-embedding-3-small)

When the RAG agent needs to find relevant news, it embeds a query string and performs a cosine similarity search against all stored chunks.

---

## 7. How Trading Decisions Are Made

This system uses an **AI agent** to propose trading strategies, but with strict guardrails so no action is taken without validation and human approval.

### The Decision Pipeline

```
1. RAG AGENT runs
   - Receives: "What strategy updates are warranted by recent news?"
   - Queries Qdrant for relevant articles from the last N minutes
   - If fewer than 3 documents retrieved -> returns confidence=0.0, proposes nothing
   - Otherwise, drafts a strategy proposal:
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
   - Are all tickers in STRATEGY_APPROVED_UNIVERSE? -> reject if not
   - Is max_position_pct <= RISK_MAX_POSITION_PCT (10%)? -> reject if not
   - Are there unknown signal types? -> reject
   - Are changed fields <= STRATEGY_MAX_DIFF_FIELDS (3)? -> reject if too many
   - Is confidence >= STRATEGY_MIN_CONFIDENCE (0.6)? -> reject if not

3. BACKTESTER runs (if validation passes)
   - In-sample: last 252 trading days
   - Out-of-sample: 90 days before the in-sample window
   - Must pass ALL thresholds:
     * Sharpe ratio > 0.5
     * Max drawdown < 25%
     * Win rate > 40%

4. SUBMIT FOR APPROVAL (if backtest passes)
   - Creates a new strategy_versions row with status="pending_approval"
   - Logs the event in strategy_audit_log
   - DOES NOT ACTIVATE — waits for human

5. HUMAN REVIEWS
   - GET /strategies -> see all pending proposals
   - Review the rationale, cited sources, backtest metrics
   - POST /strategies/{name}/approve/{version_id} -> activate
   - The previously active version is archived
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

Valid signal types: `news_sentiment`, `volatility_filter`, `momentum`, `mean_reversion`.
Valid exit types: `time_stop`, `stop_loss`, `take_profit`.

---

## 8. Paper Trading & Signal Evaluation

### How Paper Trading Works

Once a strategy is approved and set to `status=active`, the paper trading loop kicks in.

Every 1 minute during NYSE market hours (9:30 AM - 4:00 PM ET):

```
1. CHECK MARKET HOURS
   - If market is closed -> log warning, skip (no-op)
   - Uses exchange_calendars (XNYS) for accurate NYSE schedule
     including holidays and early closes

2. LOAD ACTIVE STRATEGY
   - Read active strategy definition from Postgres

3. FETCH CURRENT PRICES
   - Via Alpaca Data API (BROKER_PROVIDER=alpaca) or from DB bars
     (BROKER_PROVIDER=internal)
   - Prices use bar open to prevent lookahead bias
   - Stale data (older than RISK_MAX_DATA_STALENESS_MINUTES) is skipped

4. EVALUATE SIGNALS (throttled by rebalance_minutes from strategy definition)
   a. Volatility filter (gate):
      - Reads VIXY ETF price as VIX proxy
      - If above max_vix, all signals go flat (risk-off)
      - Defaults to pass if no VIXY data available
   b. News sentiment:
      - Queries recent news from DB
      - Groups sentiment scores by ticker
      - Computes per-ticker average
      - Tickers above threshold get a "long" signal

5. RECONCILE POSITIONS
   - Compares target signals vs currently held positions
   - Determines which tickers to buy and which to sell

6. EXECUTE ORDERS through the broker
   - Checks circuit breaker, exposure limits, and trade rate limits
   - Sells first (to free up cash), then buys
   - Position sizing via equal-weight with RISK_MAX_POSITION_PCT cap
   - Whole shares only (fractional quantities are floored)

7. PERSIST PnL SNAPSHOT to Postgres and check circuit breaker
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

### No Real Money

The `PAPER_GUARD=true` flag is checked in **every broker method**. If somehow a non-paper broker is instantiated while this flag is set, the system raises a `RuntimeError` immediately. Additionally, `TRADING_MODE=paper` is checked at startup — any other value causes a hard exit.

---

## 9. Backtesting

### Purpose

Before any strategy can be activated, it must prove itself on historical data. The backtester simulates what would have happened if the strategy had been running over the past year.

### Two-Window Approach

Every strategy is tested on **two separate time periods**:

```
Timeline:
  <-- 90 days --><---------- 252 trading days (~1 year) ---------->  TODAY
  |  OUT-OF-SAMPLE  |              IN-SAMPLE                       |
  |  (sanity check)  |     (primary evaluation window)              |
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

## 10. Safety Rails & Risk Controls

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
----------------------------------------------------------------------------------------------------------
10:30 AM  | sent_mom_v1   | proposed  | agent     | {...}             | {...}            | "Based on..."
10:31 AM  | sent_mom_v1   | approved  | human     | null              | {...}            | null
10:31 AM  | sent_mom_v1   | activated | human     | null              | {...}            | null
```

---

## 11. API Reference

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
| `POST` | `/runs/news_cycle` | Manually trigger the full news->trade pipeline |

---

## 12. MCP Server

The system exposes an MCP (Model Context Protocol) tool server for programmatic access by AI agents.

### Pipeline Tools

| Tool | Description |
|------|-------------|
| `ingest_latest_news` | Fetch and store recent news articles |
| `embed_and_upsert_docs` | Embed documents and upsert to vector DB |
| `score_sentiment` | Run sentiment analysis on documents |
| `query_kb` | Search the knowledge base |
| `propose_strategy_update` | Have the RAG agent propose a strategy change |
| `validate_strategy` | Validate a strategy definition |
| `run_backtest` | Backtest a strategy definition |
| `submit_strategy_for_approval` | Submit a validated strategy for human approval |
| `paper_trade_tick` | Execute one paper trading tick |

### Monitoring Tools (Read-Only)

| Tool | Description |
|------|-------------|
| `get_system_health` | System health, trading mode, market status |
| `get_strategy_overview` | All strategies with status and metrics |
| `get_recent_runs` | Recent pipeline run history |
| `get_pnl_summary` | Daily PnL snapshots for a strategy |
| `get_recent_news_summary` | Recent news with sentiment scores |

---

## 13. Day-to-Day Usage

### Starting the System

```bash
# Terminal 1: Start backing services
docker compose up -d

# Terminal 2: Start the API server
source .venv/bin/activate
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
# On Windows, use the wrapper that sets the correct event loop policy:
#   python -m apps.api.run

# Terminal 3: Start the Celery worker
source .venv/bin/activate
celery -A apps.scheduler.worker worker --loglevel=info

# Terminal 4: Start the Celery beat scheduler
source .venv/bin/activate
celery -A apps.scheduler.worker beat --loglevel=info

# (Optional) Visit http://localhost:5555 for the Flower dashboard
```

### What Happens Automatically

Once running, the system operates on two loops:

1. **News cycle** (every 2 minutes):
   - Fetches new articles
   - Embeds and scores them
   - RAG agent may propose a strategy update
   - If valid + backtested -> submitted for your approval

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
| `content_hash` | TEXT | SHA-256 of normalized content. Unique index. |
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
Daily PnL records per strategy. Critical for circuit breaker — persisted in DB, not memory.

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
|
|-- CLAUDE.md                          # Build spec + constraints
|-- DOCUMENTATION.md                   # This file
|-- README.md                          # Project overview
|-- pyproject.toml                     # Dependencies and build config (scikit-build-core)
|-- .env.example                       # Template for environment variables
|-- docker-compose.yml                 # Postgres, Redis, Qdrant, Flower
|-- alembic.ini                        # Alembic config (DB URL injected at runtime)
|-- Dockerfile                         # Multi-stage build (builder + runtime)
|-- railway.toml                       # Railway deployment config
|-- entrypoint.sh                      # Container entrypoint (Alembic migration + exec)
|-- .dockerignore                      # Excludes .venv, tests, .git from Docker context
|
|-- alembic/
|   |-- env.py                         # Async migration runner
|   +-- versions/
|       +-- 001_initial.py             # Creates all 6 tables
|
|-- cpp/                               # C++ EXTENSION MODULE (_quant_core via pybind11)
|   |-- CMakeLists.txt                 # CMake build config
|   |-- include/quant_core/
|   |   |-- backtest_engine.hpp        # Backtest engine interface
|   |   |-- cost_model.hpp             # Trading cost model
|   |   |-- metrics.hpp                # Performance metrics (CAGR, Sharpe, etc.)
|   |   |-- order.hpp                  # Order type definition
|   |   |-- paper_broker.hpp           # Paper broker with slippage + commission
|   |   |-- position.hpp               # Position tracking
|   |   |-- position_sizer.hpp         # Equal-weight position sizing
|   |   |-- risk_checks.hpp            # Exposure, position, rate limit checks
|   |   |-- signal_reconciler.hpp      # Target vs held position reconciliation
|   |   +-- types.hpp                  # Shared type aliases
|   |-- src/
|   |   |-- backtest_engine.cpp        # Backtest simulation loop
|   |   |-- cost_model.cpp             # Commission + slippage + spread
|   |   |-- metrics.cpp                # CAGR, Sharpe, max drawdown, win rate, turnover
|   |   |-- paper_broker.cpp           # Order execution with fill simulation
|   |   |-- position_sizer.cpp         # Cash allocation per position
|   |   |-- risk_checks.cpp            # Pre-trade risk validation
|   |   +-- signal_reconciler.cpp      # Buy/sell signal generation from targets
|   |-- bindings/
|   |   |-- module.cpp                 # pybind11 module entry point
|   |   |-- bind_backtest.cpp          # Python bindings for backtest engine
|   |   |-- bind_cost_model.cpp        # Python bindings for cost model
|   |   |-- bind_metrics.cpp           # Python bindings for metrics
|   |   |-- bind_order_position.cpp    # Python bindings for Order/Position
|   |   |-- bind_paper_broker.cpp      # Python bindings for paper broker
|   |   |-- bind_position_sizer.cpp    # Python bindings for position sizer
|   |   |-- bind_risk.cpp              # Python bindings for risk checks
|   |   +-- bind_signal_reconciler.cpp # Python bindings for signal reconciler
|   +-- tests/                         # Catch2 C++ unit tests
|       |-- CMakeLists.txt
|       |-- test_backtest_engine.cpp
|       |-- test_cost_model.cpp
|       |-- test_metrics.cpp
|       +-- test_paper_broker.cpp
|
|-- core/                              # ALL BUSINESS LOGIC LIVES HERE
|   |-- config.py                      # Settings via pydantic-settings
|   |-- logging.py                     # Structured JSON logging
|   |-- timeutils.py                   # NYSE market hours (exchange_calendars)
|   |
|   |-- storage/
|   |   |-- db.py                      # Async SQLAlchemy engine + session
|   |   |-- models.py                  # 6 ORM models
|   |   +-- repos/
|   |       |-- news_repo.py           # News CRUD
|   |       |-- strategy_repo.py       # Strategy CRUD
|   |       |-- run_repo.py            # Run CRUD
|   |       |-- market_data_repo.py    # Market data upsert/query
|   |       +-- pnl_repo.py            # PnL snapshot upsert/query
|   |
|   |-- ingestion/
|   |   |-- fetchers/
|   |   |   |-- base.py               # Fetcher interface
|   |   |   |-- rss.py                # RSS feed fetcher
|   |   |   |-- market_data.py        # Alpaca / yfinance fetcher
|   |   |   +-- provider_newsapi.py   # NewsAPI fetcher (deferred to v2)
|   |   |-- normalize.py              # Text normalization
|   |   |-- dedupe.py                 # SHA-256 deduplication
|   |   +-- ticker_extract.py         # Regex ticker extraction
|   |
|   |-- kb/
|   |   |-- vectorstore.py            # Qdrant + FAISS mock
|   |   |-- chunking.py               # Deterministic text chunking
|   |   |-- embeddings.py             # Mock + OpenAI providers
|   |   |-- retrieval.py              # Query knowledge base
|   |   +-- sentiment.py              # FinBERT / LLM scoring
|   |
|   |-- agent/
|   |   |-- rag_agent.py              # RAG agent
|   |   |-- prompts.py                # Versioned prompt constants
|   |   |-- strategy_language.py      # Strategy JSON spec
|   |   |-- validator.py              # Strategy validator
|   |   +-- approval.py               # Approval gate
|   |
|   |-- strategies/
|   |   |-- base.py                   # Strategy interface
|   |   |-- registry.py               # Strategy registry
|   |   +-- implementations/
|   |       |-- sentiment_momentum.py # Sentiment momentum strategy
|   |       +-- event_risk_off.py     # Event risk-off strategy
|   |
|   |-- backtesting/
|   |   |-- engine.py                 # Backtesting engine (delegates to _quant_core)
|   |   |-- metrics.py                # Metrics (delegates to _quant_core)
|   |   +-- cost_model.py             # Cost model (delegates to _quant_core)
|   |
|   |-- execution/
|   |   |-- broker_base.py            # Broker interface
|   |   |-- paper_broker.py           # Paper broker (delegates to _quant_core)
|   |   |-- guard.py                  # PAPER_GUARD enforcement
|   |   |-- alpaca_paper.py           # Alpaca paper broker
|   |   |-- risk.py                   # Risk management (delegates to _quant_core)
|   |   |-- position_sizing.py        # Position sizing (delegates to _quant_core)
|   |   |-- price_feed.py             # Price abstraction (Alpaca, DB, Mock)
|   |   +-- signal_evaluator.py       # Signal evaluation engine for live execution
|   |
|   +-- observability/
|       |-- metrics.py                # App metrics (deferred to v2)
|       +-- tracing.py                # Distributed tracing (deferred to v2)
|
|-- apps/                             # THIN WRAPPERS — NO BUSINESS LOGIC
|   |-- api/
|   |   |-- main.py                   # FastAPI app
|   |   |-- run.py                    # Server entry point (Windows event loop fix)
|   |   |-- deps.py                   # Dependency injection
|   |   +-- routers/
|   |       |-- health.py             # GET /health
|   |       |-- news.py               # GET /news/recent
|   |       |-- strategies.py         # Strategy CRUD + approval
|   |       |-- backtests.py          # POST /strategies/{name}/backtest
|   |       |-- runs.py               # GET /runs/recent, POST /runs/news_cycle
|   |       +-- pnl.py                # GET /pnl/daily
|   |
|   |-- mcp_server/
|   |   |-- server.py                 # MCP stdio server
|   |   |-- schemas.py                # Tool schemas
|   |   +-- tools/
|   |       |-- ingest.py             # ingest_latest_news
|   |       |-- kb.py                 # embed_and_upsert_docs, query_kb
|   |       |-- sentiment.py          # score_sentiment
|   |       |-- strategy.py           # propose/validate/submit strategy
|   |       |-- backtest.py           # run_backtest
|   |       |-- execution.py          # paper_trade_tick
|   |       +-- monitoring.py         # 5 read-only monitoring tools
|   |
|   +-- scheduler/
|       |-- worker.py                 # Celery worker config + beat schedule
|       +-- jobs.py                   # Scheduled pipeline jobs
|
+-- tests/                            # 215 tests across 25 test files
    |-- conftest.py                   # Fixtures (SQLite, mock config)
    |-- test_smoke.py                 # Import + config smoke tests
    |-- test_dedupe.py                # Deduplication logic
    |-- test_ticker_extract.py        # Ticker regex extraction
    |-- test_market_data.py           # Market data fetcher + repo
    |-- test_mcp_tools.py             # MCP pipeline tools
    |-- test_monitoring_tools.py      # MCP monitoring tools
    |-- test_multi_agent.py           # Multi-agent architecture
    |-- test_strategy_validator.py    # Strategy validation rules
    |-- test_backtest_smoke.py        # Backtest engine + metrics
    |-- test_approval_gate.py         # Approval workflow
    |-- test_risk_circuit_breaker.py  # Circuit breaker + DB rehydration
    |-- test_paper_guard.py           # PAPER_GUARD enforcement
    |-- test_market_hours.py          # Market hours + no-op outside hours
    |-- test_price_feed.py            # Price feed implementations
    |-- test_signal_evaluator.py      # Signal evaluation engine
    |-- test_api_strategies.py        # Strategy API endpoints
    |-- test_api_news.py              # News API endpoints
    |-- test_api_pnl.py               # PnL API endpoints
    |-- test_api_runs.py              # Runs API endpoints
    |-- test_api_backtests.py         # Backtest API endpoints
    |-- test_scheduler_jobs.py        # Celery task wiring
    |-- test_alpaca_paper.py          # AlpacaPaperBroker + BROKER_PROVIDER
    +-- test_cpp_parity.py            # C++ extension parity (24 tests)
```

---

## 16. Running Tests

215 tests across 25 test files. All tests run with mocks — no external services required:

```bash
pytest
```

This includes 24 C++/Python parity tests (`test_cpp_parity.py`) that verify the `_quant_core` extension produces identical results to the original Python implementations for cost model, metrics, paper broker, risk checks, position sizing, signal reconciliation, and backtesting.

With coverage:

```bash
pytest --cov=core --cov=apps
```

---

## 17. Monitoring with Claude Desktop

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

| Tool | Description | Example Question |
|---|---|---|
| `monitor_strategies` | List all strategies with status, version, backtest metrics | "What strategies are pending approval?" |
| `monitor_runs` | Recent pipeline runs (ingest, embed, sentiment, etc.) | "When did the last news cycle run?" |
| `monitor_pnl` | Daily PnL snapshots for a strategy | "Show me PnL for sentiment_momentum_v1 this week" |
| `monitor_health` | System health: trading mode, market status, connectivity | "Is the system healthy?" |
| `monitor_news` | Recent news articles with sentiment and tickers | "What news was ingested in the last hour?" |

### Alpaca MCP Server — Safe vs. Unsafe Tools

| Safe (Read-Only) | Unsafe (Do NOT Use) |
|---|---|
| Get account info | Place orders |
| Get positions | Cancel orders |
| Get portfolio history | Close positions |
| Get market data (bars, quotes) | |
| Get watchlist | |
| Get order history | |

The Alpaca server's trading tools bypass our safety rails (PAPER_GUARD, strategy approval, circuit breaker). All trading should go through our pipeline.

---

## 18. Future Phases: Quantitative Model Development

The v1 system has solid engineering infrastructure but limited mathematical depth. The following phases add the quantitative rigor expected at professional quant firms. Each phase builds on the previous one — implement in order.

### Phase 13: Alpha Research Framework & Factor Models

**Goal:** Replace ad-hoc signal thresholds with a statistically rigorous factor evaluation pipeline.

**New module:** `core/research/alpha.py`

**What to build:**

- **Information Coefficient (IC) / Rank IC**: For each signal, compute the Spearman rank correlation between the signal value at time *t* and the forward return at *t+1*. Track IC mean, IC standard deviation, and the **Information Ratio** (IC_mean / IC_std).
- **Factor decay analysis**: Compute IC at horizons 1d, 2d, 5d, 10d, 20d to measure how quickly a signal's predictive power decays.
- **Cross-sectional momentum factor**: Replace the current rolling-return-on-open proxy with proper cross-sectional z-scores of returns across the universe.
- **Sentiment factor construction**: Z-score FinBERT sentiment across tickers at each point in time. Test IC against forward returns.

**Math involved:** Spearman's rho, z-score normalization, forward return calculation with proper lag alignment.

---

### Phase 14: Statistical Validation & Backtest Integrity

**Goal:** Move beyond "Sharpe > 0.5" to statistically defensible strategy validation.

**New module:** `core/backtesting/statistical_tests.py`

**What to build:**

- **Sharpe ratio significance test**: Compute `t = Sharpe * sqrt(N) / sqrt(1 + skew*Sharpe/2 + (kurt-3)*Sharpe^2/4)` (the Lo (2002) adjusted Sharpe test).
- **Multiple hypothesis correction**: Apply Bonferroni or Benjamini-Hochberg FDR correction when testing multiple strategy variants.
- **Walk-forward validation**: Rolling train/test splits instead of a single OOS window. Report the distribution of OOS Sharpe ratios.
- **Bootstrap confidence intervals**: Block bootstrap to preserve autocorrelation, recompute Sharpe/drawdown 10,000 times, report 95% CI.

**Enhanced metrics:** Sortino Ratio, Calmar Ratio, Profit Factor, Tail Ratio, Skewness/Kurtosis.

**Reference:** Andrew Lo, "The Statistics of Sharpe Ratios" (2002); Marcos Lopez de Prado, *Advances in Financial Machine Learning* (2018).

---

### Phase 15: Portfolio Optimization

**Goal:** Replace equal-weight position sizing with mathematically optimal portfolio construction.

**New module:** `core/execution/portfolio_optimizer.py`

**What to build:**

- **Mean-Variance Optimization (Markowitz)**: Maximize Sharpe ratio subject to constraints (long-only, max position size).
- **Minimum Variance Portfolio**: Minimize portfolio variance when return estimates are unreliable.
- **Risk Parity**: Equal risk contribution from each position.
- **Black-Litterman**: Combine market-cap-implied equilibrium returns with sentiment views from the RAG agent.
- **Ledoit-Wolf shrinkage**: Stabilize covariance estimation for small sample sizes.

**Integration:** New `position_sizing.type` values: `"mean_variance"`, `"min_variance"`, `"risk_parity"`, `"black_litterman"`.

---

### Phase 16: Time-Varying Volatility & Vol Targeting

**Goal:** Replace flat rolling-window volatility with proper time-series volatility models.

**New module:** `core/research/timeseries.py`

**What to build:**

- **GARCH(1,1) volatility model**: Time-varying volatility estimates via maximum likelihood.
- **EWMA volatility**: Exponentially Weighted Moving Average (lambda ~ 0.94, RiskMetrics standard).
- **Volatility regime classification**: Threshold-based low/medium/high vol regimes from GARCH output.
- **Stationarity testing**: ADF test on every signal before use; auto-difference if needed.

**Integration:** `"volatility_target"` position sizing type that scales weights by `target_vol / predicted_vol`.

---

### Phase 17: Risk Analytics & VaR/CVaR

**Goal:** Replace simple threshold-based risk checks with distributional risk modeling.

**New module:** `core/backtesting/risk_analytics.py`

**What to build:**

- **Value at Risk (VaR)** — parametric, historical, and Monte Carlo methods.
- **Conditional VaR (CVaR / Expected Shortfall)**: Mean of returns below VaR threshold.
- **Drawdown distribution**: Monte Carlo simulated max drawdown confidence intervals.
- **Stress testing**: Scenario shocks (e.g., "SPY drops 10%", "correlation spike to 0.9").

**Integration:** VaR/CVaR in backtest output; VaR-based position limits; circuit breaker early warning.

---

### Phase 18: Regime Detection (Hidden Markov Models)

**Goal:** Detect bull/bear market regimes and condition strategy behavior on the current regime.

**New module:** `core/research/regime.py`

**What to build:**

- **2-state Gaussian HMM**: Baum-Welch for parameter estimation, Viterbi for state decoding.
- **Regime-conditioned execution**: Only trade momentum in bull regime; risk-off in bear regime.
- **Online regime detection**: Forward algorithm updates regime probabilities in real-time.
- **Transition probability exposure**: Estimated transition matrix for reasoning about regime persistence.

**Integration:** `"regime_filter"` signal type in the strategy language.

---

### Phase 19: Pairs Trading & Statistical Arbitrage

**Goal:** Add market-neutral strategies based on cointegration and mean-reversion of price spreads.

**New module:** `core/research/pairs.py`, `core/strategies/implementations/pairs_trading.py`

**What to build:**

- **Cointegration testing**: Engle-Granger and Johansen trace test.
- **Spread construction**: OLS hedge ratio, z-score of spread.
- **Ornstein-Uhlenbeck half-life**: Fit O-U process to estimate mean-reversion speed.
- **Pairs trading signals**: Enter at +/-2 sigma, exit at +/-0.5 sigma.
- **Rolling cointegration check**: Re-test periodically; close positions if cointegration breaks.

**Integration:** `"pairs_mean_reversion"` signal type; broker extension for short selling in paper mode.

---

### Implementation Priority

```
Phase 13 (Alpha/IC)
  |
Phase 14 (Statistical Tests) <- depends on Phase 13
  |
Phase 15 (Portfolio Optimization) <- depends on Phase 14
  |
Phase 16 (GARCH/Vol) <- depends on Phase 15
  |
Phase 17 (VaR/CVaR) <- depends on Phase 16
  |
Phase 18 (Regime HMM) <- depends on Phase 16
  |
Phase 19 (Pairs Trading) <- independent, benefits from Phases 14-16
```

### New Dependencies

| Package | Phase | Purpose |
|---|---|---|
| `statsmodels` | 14, 19 | ADF test, OLS, cointegration, statistical tests |
| `cvxpy` | 15 | Convex optimization for portfolio construction |
| `arch` | 16 | GARCH models |
| `hmmlearn` | 18 | Hidden Markov Models |

---

## 19. Deployment Roadmap

### Stage 1: Local Development & Testing (Current)

All development, testing, and paper trading validation happens on the local machine.

**What runs locally:**

| Service | How It Runs | Resource Usage |
|---|---|---|
| Postgres 16 | Docker container | ~200 MB RAM |
| Redis 7 | Docker container | ~50 MB RAM |
| Qdrant | Docker container | ~200 MB RAM |
| Flower | Docker container | ~100 MB RAM |
| FastAPI server | Python process (venv) | ~100 MB RAM |
| Celery worker | Python process (venv) | ~100 MB RAM (+ `_quant_core` C++ extension, negligible overhead) |
| FinBERT model | Loaded by Celery worker | ~1.5 GB RAM |
| **Total** | | **~2.3 GB RAM** |

### Stage 2: Railway Cloud Deployment (In Progress)

Migrate to [Railway](https://railway.app) for always-on operation during market hours. The Dockerfile, `railway.toml`, and `entrypoint.sh` are already committed.

**Docker build:** Multi-stage (`builder` + `runtime`). The builder stage compiles the C++ extension, installs CPU-only PyTorch (no CUDA — Railway has no GPU), and pre-downloads the FinBERT model so it's cached in the image layer. The runtime stage copies only the installed packages and the HuggingFace model cache, keeping the final image lean.

**Railway service mapping:**

| Railway Service | Start Command | Role |
|---|---|---|
| **API** (web) | `entrypoint.sh uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT` | FastAPI server. Runs Alembic migrations on boot (via `entrypoint.sh` with retry). Health check on `/health` (300s timeout). |
| **Worker** | `entrypoint.sh celery -A apps.scheduler.worker worker --loglevel=info` | Celery worker. Picks tasks off Redis and executes them (news cycles, paper trade ticks). |
| **Beat** | `entrypoint.sh celery -A apps.scheduler.worker beat --loglevel=info` | Celery scheduler. Publishes tasks to Redis on a timer (news cycle every 120s, paper trade tick every 60s). Does not execute tasks. |
| **Postgres** | Railway managed plugin | Persistent state (6 tables). `DATABASE_URL` injected automatically. |
| **Redis** | Railway managed plugin | Celery message broker + result backend. `REDIS_URL` injected automatically. |
| **Qdrant** | Railway service (custom Docker image) | Vector DB for news embeddings. |
| **Flower** | Railway service (optional) | Celery task dashboard on port 5555. |

All three application services (API, Worker, Beat) share the same Docker image and codebase — they differ only in their start command. Set `RUN_MIGRATIONS=true` only on the API service to avoid migration races.

**`entrypoint.sh`:** Runs Alembic migrations with retry (5 attempts, 5s backoff) when `RUN_MIGRATIONS=true`, then `exec`s the start command. Beat and Worker services set `RUN_MIGRATIONS=false` (or leave it unset) to skip migrations.

**`railway.toml`:** Configures the API service with Dockerfile builder, health check path, 300s health check timeout (accounts for C++ extension compilation on first deploy), and restart-on-failure policy (max 5 retries).

### Stage 3: Kubernetes Orchestration (Future)

Separate Docker containers per market sector, coordinated by Kubernetes for portfolio-level decisions. The **multi-agent architecture** (`AGENT_CONFIGS`) already supports this at the code level — set one agent per pod with the same codebase, differentiated only by environment variables. What remains is the K8s infrastructure (Helm charts, manifests, portfolio coordinator service).

```
+-----------------------------------------------------------+
|                   Kubernetes Cluster                       |
|                                                           |
|  +--------------+  +--------------+  +--------------+    |
|  |  Tech Stocks  |  |   Energy     |  |   ETFs       |   |
|  |  Strategy Pod |  |  Strategy Pod|  |  Strategy Pod|   |
|  +---------+----+  +-------+------+  +-------+------+   |
|            |               |                 |            |
|            +-------+-------+--------+--------+            |
|                    v                v                      |
|  +-----------------------------------------------+       |
|  |       Portfolio Coordinator Service            |       |
|  |  - Aggregates positions across all pods        |       |
|  |  - Enforces portfolio-wide risk limits         |       |
|  |  - Global circuit breaker                      |       |
|  +-----------------------------------------------+       |
|                                                           |
|  +-----------------------------------------------+       |
|  |            Shared Infrastructure               |       |
|  |  Postgres | Redis | Qdrant | Prometheus        |       |
|  +-----------------------------------------------+       |
+-----------------------------------------------------------+
```

Each strategy pod runs the same codebase with different environment variables (different ticker universes, news sources, and confidence thresholds).

---

## 20. Known Limitations

- Survivorship bias is not corrected in the backtester (ETF-only universe is a partial mitigation).
- Near-duplicate detection (SimHash) is not implemented; only exact content hash dedup is used.
- Market data uses daily bars by default; intraday signals may not be fully representable.
- The RAG agent's confidence scores are self-reported and not calibrated.
- No portfolio-level risk management across multiple simultaneous strategies.
- VIX proxy uses VIXY ETF price (real VIX index not available via Alpaca data API). Degrades gracefully (defaults to pass) if no data.
- No fractional share support; order quantities are floored to whole shares.

---

## 21. Glossary

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
