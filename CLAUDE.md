# CLAUDE.md — Quant News-RAG Trading System

## Project Overview

A modular, paper-first quantitative trading system that ingests financial news, builds a vector knowledge base, uses a RAG agent to propose strategy updates, backtests them, and optionally executes paper trades. This is a long-running background system, not a request/response app.

**Default mode: PAPER ONLY. `TRADING_MODE=paper` is the only valid value. Hard exit on startup if changed.**

**Deployment: Railway.** The production backend runs on Railway. All environment variable changes, service configuration, and infrastructure updates must target the Railway deployment. Use `railway variables --set` for env changes, not local `.env` edits (local `.env` is for local dev only). The Railway project has Postgres, Redis, and Qdrant services already provisioned.

---

## Goals

- End-to-end pipeline: fetch news + market data → store → embed + sentiment → RAG → validate → dual-window backtest → submit for approval → human approves → paper execution.
- Clean separation: `apps/` is thin; all business logic lives in `core/`.
- Repeatable local dev with Docker Compose.
- Safety rails: PAPER_GUARD, circuit breaker persisted in DB, human approval gate, approved ticker universe.
- Observability: structured JSON logs, run history in Postgres, Celery Flower for task visibility.

---

## Non-Goals (v1)

- Live trading of any kind.
- Ultra-low-latency or HFT execution.
- Survivorship-bias-corrected backtesting (document as known limitation).
- Guaranteed alpha.
- Near-duplicate dedup via SimHash (use content hash; SimHash is a TODO v2 comment).

---

## Critical Constraints (Non-Negotiable)

### Safety Rails
- `TRADING_MODE=paper` is the **only valid value in v1**. If anything other than `"paper"` is detected at startup, the process must **hard exit**. Do not implement a live trading codepath.
- `PAPER_GUARD=true` must be checked in every broker adapter method. If a non-paper broker is instantiated and this flag is set, raise `RuntimeError` immediately.
- Strategy proposals from the RAG agent must **never auto-activate**. They must land in `status=pending_approval` first. Activation requires an explicit call to `POST /strategies/{name}/approve/{version_id}`.
- The daily loss circuit breaker state must be **persisted in Postgres** (`pnl_snapshots` table), never held only in memory. Rehydrate on startup.

### No Lookahead Bias
- In the backtester, signals must only use data available at the bar's open. Any future-leaking data access is a bug. Be explicit in comments when indexing time series.

---

## Architecture Principles

### Service Boundaries
```
api/          → FastAPI REST layer. No business logic. Thin wrappers around core/.
mcp_server/   → MCP tool implementations. Calls core/ only, never api/.
scheduler/    → Celery. Calls MCP tools via internal client or direct import.
core/         → All business logic. Must be independently importable (no circular deps with apps/).
```

### Dependency Direction
```
apps/* → core/*   ✓
core/* → apps/*   ✗ (never)
```

### Async
- Use `async/await` throughout FastAPI and any I/O-bound code (DB, HTTP, Qdrant).
- Celery tasks are sync wrappers; keep the actual logic in async core functions called via `asyncio.run()` or a dedicated event loop.

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Use `pyproject.toml`, not `setup.py` |
| API | FastAPI | Async, Pydantic v2 models |
| Task Queue | Celery + Redis | Not APScheduler — we need retries, visibility, Flower |
| Database | Postgres (SQLAlchemy 2.x async) | All models in `core/storage/models.py` |
| Migrations | Alembic | Run `alembic init` before writing any other code after models |
| Vector DB | Qdrant | Docker; FAISS mock for unit tests |
| Embeddings | Pluggable (`mock` default, `openai` optional) | Controlled by `EMBEDDINGS_PROVIDER` env var |
| Sentiment | `ProsusAI/finbert` (local) or LLM call | Runs at embed time, stored in DB + Qdrant payload |
| Market Data | Alpaca Data API (default), yfinance (fallback) | Required for backtester |
| Backtesting | vectorbt OR backtrader (adapter pattern) | Engine must be swappable |
| Broker | `PaperBroker` (default), `AlpacaPaperBroker` (optional) | No live broker in v1 |
| MCP | MCP stdio server | HTTP optional |

---

## Environment Variables

All config is loaded via `core/config.py` using `pydantic-settings`. Never hardcode values.

### Required
```
APP_ENV=dev
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/quant
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
```

### News Ingestion
```
NEWS_POLL_INTERVAL_SECONDS=120
NEWS_SOURCES=rss:https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US
MAX_DOCS_PER_POLL=50
DEDUP_CONTENT_HASH=sha256        # exact dedup; SimHash is TODO v2
```

### Market Data
```
MARKET_DATA_PROVIDER=alpaca      # alpaca | yfinance
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
MARKET_DATA_LOOKBACK_DAYS=365
BAR_TIMEFRAME=1Day
```

### Embeddings & Vector DB
```
EMBEDDINGS_PROVIDER=mock         # mock | openai
OPENAI_API_KEY=                  # only if provider=openai
VECTOR_COLLECTION=news
VECTOR_SIZE=1536                 # override for local embedding models
CHUNK_SIZE_CHARS=1000
CHUNK_OVERLAP_CHARS=150
```

### Sentiment
```
SENTIMENT_PROVIDER=finbert       # finbert | llm | mock
```

### Risk & Execution
```
RISK_MAX_GROSS_EXPOSURE=1.0
RISK_MAX_POSITION_PCT=0.10
RISK_MAX_DAILY_LOSS_PCT=0.02
RISK_MAX_TRADES_PER_HOUR=30
RISK_MAX_DATA_STALENESS_MINUTES=30
PAPER_INITIAL_CASH=100000
PAPER_GUARD=true
TRADING_MODE=paper               # ONLY VALID VALUE IN V1 — hard exit if changed
```

### Strategy Agent
```
STRATEGY_MIN_CONFIDENCE=0.6
STRATEGY_MAX_DIFF_FIELDS=3
STRATEGY_MAX_ACTIVATIONS_PER_DAY=4
STRATEGY_MIN_BACKTEST_DAYS=252
STRATEGY_APPROVED_UNIVERSE=SPY,QQQ,AAPL,MSFT,AMZN,GOOGL,META,NVDA,BRK.B,JPM
PENDING_APPROVAL_AUTO_APPROVE_MINUTES=0   # 0 = never auto-approve; N = approve after N min in paper mode
```

### Quality Scoring (replaces backtest gate in pipeline)
```
QUALITY_MIN_COMPOSITE_SCORE=0.5          # composite threshold for proposal to pass
QUALITY_MIN_CITED_DOCS=3                 # target number of cited docs for full evidence score
QUALITY_RECENCY_LOOKBACK_MINUTES=480     # docs older than this get recency=0
QUALITY_WEIGHT_EVIDENCE=0.30             # weight for evidence strength dimension
QUALITY_WEIGHT_RECENCY=0.25             # weight for recency dimension
QUALITY_WEIGHT_CONSENSUS=0.25           # weight for sentiment consensus dimension
QUALITY_WEIGHT_COVERAGE=0.20            # weight for universe ticker coverage dimension
```

Note: `run_backtest` MCP tool and API endpoint remain available for manual use. Only the automated pipeline gate uses quality scoring.

### Startup Validation
```python
if settings.TRADING_MODE != "paper":
    raise SystemExit("FATAL: TRADING_MODE must be 'paper' in v1. Live trading is not implemented.")
```

---

## Data Models (Postgres)

Define all in `core/storage/models.py` using SQLAlchemy 2.x declarative style with `mapped_column`.

### `news_documents`
```
id                uuid pk
source            text
source_url        text (unique index)
title             text
published_at      timestamptz
fetched_at        timestamptz
content           text
content_hash      text (unique index)    -- SHA-256 of normalized content
metadata          jsonb                  -- {tickers: [], author, tags}
sentiment_score   float nullable         -- set after sentiment scoring
sentiment_label   text nullable          -- positive | negative | neutral
```

### `market_bars`
```
id                uuid pk
ticker            text
timeframe         text                   -- 1Day, 1Hour, etc.
bar_time          timestamptz
open              numeric
high              numeric
low               numeric
close             numeric
volume            bigint
fetched_at        timestamptz
unique(ticker, timeframe, bar_time)
```

### `strategy_versions`
```
id                uuid pk
name              text
version           int
status            text                   -- pending_approval | active | archived
definition        jsonb
created_at        timestamptz
activated_at      timestamptz nullable
approved_by       text nullable          -- "human" | "auto" | null
reason            text
backtest_metrics  jsonb                  -- metrics that passed validation
```

### `strategy_audit_log`
```
id                uuid pk
timestamp         timestamptz
strategy_name     text
version_id        uuid fk strategy_versions
action            text                   -- proposed | approved | rejected | activated | archived
trigger           text                   -- agent | human | scheduler
before_definition jsonb nullable
after_definition  jsonb nullable
backtest_metrics  jsonb nullable
llm_rationale     text nullable
diff_fields       jsonb                  -- list of changed fields
```

### `pnl_snapshots`
```
id                uuid pk
strategy_name     text
snapshot_date     date
realized_pnl      numeric
unrealized_pnl    numeric
gross_exposure    numeric
peak_pnl          numeric                -- for drawdown tracking
positions         jsonb
created_at        timestamptz
unique(strategy_name, snapshot_date)
```

### `runs`
```
id                uuid pk
run_type          text                   -- ingest | embed | sentiment | agent_update | backtest | execution
started_at        timestamptz
ended_at          timestamptz nullable
status            text                   -- running | ok | fail
details           jsonb
```

---

## Alembic Setup

Run `alembic init alembic` before writing any code beyond models. Create `001_initial.py` that creates all tables above. All subsequent model changes must be expressed as numbered migrations, never raw `ALTER TABLE`.

---

## Vector DB (Qdrant)

Collection config in `core/kb/vectorstore.py`:
```python
COLLECTION_CONFIG = {
    "vectors": {
        "size": settings.VECTOR_SIZE,       # from env, default 1536
        "distance": "Cosine",
    },
    "optimizers_config": {"default_segment_number": 2},
    "quantization_config": {"scalar": {"type": "int8", "always_ram": True}},
}
```

Payload per point:
```
doc_id, title, source, source_url, published_at, tickers, tags,
sentiment_score, sentiment_label, chunk_index, chunk_total
```

Chunking: `CHUNK_SIZE_CHARS` chars, `CHUNK_OVERLAP_CHARS` overlap (both from config). Chunking must be deterministic — same input always produces same output.

---

## News Ingestion

### Fetchers (`core/ingestion/fetchers/`)
- `base.py` — abstract `BaseFetcher` with `fetch() -> list[RawDocument]`
- `rss.py` — parses `rss:` prefixed URLs from `NEWS_SOURCES`
- `market_data.py` — fetches OHLCV bars from Alpaca API; fallback to yfinance if `MARKET_DATA_PROVIDER=yfinance`
- `provider_newsapi.py` — stub (optional, requires `NEWSAPI_KEY`)

### Normalize (`core/ingestion/normalize.py`)
- Strip HTML, normalize whitespace, lowercase title for hashing.
- Extract and normalize ISO publication date.

### Dedupe (`core/ingestion/dedupe.py`)
- SHA-256 of normalized content → `content_hash`.
- Check `content_hash` AND `source_url` against DB before inserting.
- If duplicate: skip silently, increment a dedup counter in run details.
- **Do not implement SimHash in v1. Add `# TODO v2: near-duplicate detection via SimHash` comment.**

### Ticker Extraction (`core/ingestion/ticker_extract.py`)
- At ingest time, run regex over title + content to find uppercase 1–5 char tokens.
- Filter against a pre-loaded set of valid tickers (load from `STRATEGY_APPROVED_UNIVERSE` plus a broader static list of S&P 500 tickers bundled as a static asset).
- Store extracted tickers in `news_documents.metadata["tickers"]`.

---

## Sentiment Scoring

Implemented in `core/kb/sentiment.py`. Run after embedding, before Qdrant upsert.

- `SENTIMENT_PROVIDER=finbert`: load `ProsusAI/finbert` from HuggingFace. Score each document chunk. Aggregate to document-level by averaging chunk scores, weighted by chunk length.
- `SENTIMENT_PROVIDER=mock`: return `score=0.0, label="neutral"` for all docs.
- Store `sentiment_score` (float, -1 to 1) and `sentiment_label` in `news_documents` and in Qdrant payload.

---

## Strategy Language

JSON spec; validated by `core/agent/validator.py`. All fields are exhaustively checked — unknown fields are rejected.

```json
{
  "name": "sentiment_momentum_v1",
  "universe": ["SPY", "QQQ"],
  "signals": [
    {"type": "news_sentiment", "lookback_minutes": 240, "threshold": 0.65, "direction": "long"},
    {"type": "volatility_filter", "max_vix": 25}
  ],
  "rules": {
    "rebalance_minutes": 60,
    "max_positions": 5,
    "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
    "exits": [{"type": "time_stop", "minutes": 360}]
  }
}
```

Valid signal types: `news_sentiment, volatility_filter, momentum, mean_reversion`. Reject unknown types.
Valid exit types: `time_stop, stop_loss, take_profit`. Reject unknown types.

---

## RAG Agent

Implemented in `core/agent/rag_agent.py`. The LLM is a tool, not the decision maker.

### Inputs
- Recent news window (last `recent_minutes` from KB)
- Current active strategy definition
- Risk constraints from config

### Process
1. Retrieve top-K docs from Qdrant using queries derived from current universe tickers + macro keywords (`rates, inflation, earnings, guidance, layoffs, regulation, fed, cpi, gdp`).
2. If fewer than 3 docs retrieved: return `{confidence: 0.0, proposal: null, reason: "insufficient_context"}`. Do not propose.
3. Summarize retrieved docs into structured events: `{event_type, impacted_assets, directionality, confidence, time_horizon}`.
4. Propose minimal strategy delta. Constraints:
   - Only change fields necessary given the events.
   - New tickers must be in `STRATEGY_APPROVED_UNIVERSE`.
   - Count changed fields; if > `STRATEGY_MAX_DIFF_FIELDS`, reduce scope or note limitation.
5. Output: `{new_definition, rationale, risks, expected_behavior, confidence, cited_doc_ids, changed_fields}`.

### Rules
1. Every factual claim in a proposal must cite at least one `doc_id`. Claims without citation must be labeled `[INFERENCE]`.
2. Agent must never invent tickers not in the retrieved documents or approved universe.
3. Proposals must include: `{new_definition, rationale, risks, expected_behavior, confidence, cited_doc_ids, changed_fields}`.
4. If fewer than 3 documents are retrieved, the agent must return `confidence=0.0` and not propose a change.
5. Prompts live in `core/agent/prompts.py` as versioned string constants (not f-strings at call time — this makes prompts auditable).

---

## Strategy Validator

Implemented in `core/agent/validator.py`. Hard checks (all must pass):

- All tickers in `universe` are in `STRATEGY_APPROVED_UNIVERSE` (loaded from config).
- No unknown signal or exit types.
- `max_position_pct` ≤ `RISK_MAX_POSITION_PCT`.
- `len(changed_fields)` ≤ `STRATEGY_MAX_DIFF_FIELDS` when comparing to current active version.
- `confidence` ≥ `STRATEGY_MIN_CONFIDENCE`.
- No unknown top-level fields (strict schema).

Returns `{valid: bool, errors: list[str]}`.

---

## Backtesting

### Engine (`core/backtesting/engine.py`)
- Accepts: `definition_json`, `start_date`, `end_date`, market bars from `market_data_repo`.
- Load bars from Postgres (not from fetcher at backtest time — data must already be ingested).
- Load sentiment signals from `news_documents` within the window.
- **Lookahead guard**: all signal arrays must be shifted by 1 bar before being used for position entry. Add comment: `# lookahead guard: shift(1)` at each shift site.
- Apply cost model before computing returns.

### Cost Model (`core/backtesting/cost_model.py`)
Configurable via env:
- `BACKTEST_COMMISSION_PER_TRADE=1.00` (dollars)
- `BACKTEST_SLIPPAGE_BPS=5`
- `BACKTEST_SPREAD_BPS=2`

### Metrics (`core/backtesting/metrics.py`)
Must return: `{cagr, sharpe, max_drawdown, win_rate, turnover, avg_trade_return}`.

### Activation Thresholds (configurable)
- Sharpe > 0.5
- Max drawdown < 25%
- Win rate > 40%

### Dual-Window Validation
- In-sample: last `STRATEGY_MIN_BACKTEST_DAYS` trading days (default 252).
- OOS: 90 trading days immediately before in-sample window.
- Both windows must independently pass thresholds for proposal to be submitted for approval.

### Document Limitations
Survivorship bias is not corrected in v1 (ETF-only universe is a partial mitigation).

---

## Human Approval Gate

Implemented in `core/agent/approval.py`.

- `submit_for_approval(strategy_name, definition, reason, backtest_metrics)`:
  - Creates `strategy_versions` record with `status=pending_approval`.
  - Writes to `strategy_audit_log` with `action=proposed`.
  - If `PENDING_APPROVAL_AUTO_APPROVE_MINUTES > 0`, schedule a Celery task to auto-approve after N minutes (paper mode convenience only).
  - Never automatically approves if `PENDING_APPROVAL_AUTO_APPROVE_MINUTES=0`.

- `approve(version_id, approved_by="human")`:
  - Sets `status=active` on requested version.
  - Archives all previously active versions for this strategy name.
  - Writes to `strategy_audit_log` with `action=approved, trigger=human`.
  - Enforces `STRATEGY_MAX_ACTIVATIONS_PER_DAY`.

---

## Risk & Execution

### PAPER_GUARD (`core/execution/guard.py`)
```python
def assert_paper_guard():
    if settings.PAPER_GUARD and settings.TRADING_MODE != "paper":
        raise RuntimeError("PAPER_GUARD: live trading blocked.")
```
Call `assert_paper_guard()` at the top of every broker method that places an order.

### Risk (`core/execution/risk.py`)
Checks per tick:
- Gross exposure ≤ `RISK_MAX_GROSS_EXPOSURE`
- Per-position ≤ `RISK_MAX_POSITION_PCT`
- Trades in last hour ≤ `RISK_MAX_TRADES_PER_HOUR`
- News data age ≤ `RISK_MAX_DATA_STALENESS_MINUTES`

### Circuit Breaker (persistent)
- On every `paper_trade_tick`, load today's `pnl_snapshot` from Postgres.
- If `realized_pnl / PAPER_INITIAL_CASH < -RISK_MAX_DAILY_LOSS_PCT`: halt all trading, log `circuit_breaker_tripped`.
- On startup, rehydrate: check today's `pnl_snapshot` and refuse to trade if tripped.
- **Never hold circuit breaker state only in memory.**

### Price Feed (`core/execution/price_feed.py`)
Three implementations:
- **`AlpacaPriceFeed`** — calls Alpaca `StockHistoricalDataClient.get_stock_latest_bar()`. Uses `bar.open` (`# lookahead guard: shift(1)`). Skips stale data.
- **`DbPriceFeed`** — reads the most recent bar from Postgres via `market_data_repo`. Used when `BROKER_PROVIDER=internal`.
- **`MockPriceFeed`** — returns preset prices dict. For tests.
- **`get_price_feed(session=None)`** — factory: returns `AlpacaPriceFeed` when `BROKER_PROVIDER=alpaca`, else `DbPriceFeed(session)`.

### Signal Evaluator (`core/execution/signal_evaluator.py`)
- **`evaluate_news_sentiment_signal(session, signal_config, universe)`** — queries `news_repo.get_recent()`, groups sentiment scores by ticker, returns `{ticker: avg_score}` for tickers above threshold.
- **`evaluate_volatility_filter(session, signal_config)`** — reads latest VIXY bar as VIX proxy. Returns `True` (pass) or `False` (risk-off). Defaults to `True` if no VIXY data.
- **`generate_signals_from_definition(session, definition, current_prices)`** — evaluates all signals: volatility filter as gate, then news sentiment. Returns `{ticker: "long"|"flat"}`.
- **`reconcile_positions(signals, current_positions)`** — compares target vs held. Returns `(tickers_to_buy, tickers_to_sell)`.
- **`execute_signals(broker, signals, current_prices, definition, circuit_breaker_tripped)`** — orchestrates orders: SELLs first, then BUYs with position sizing. Whole shares only.

### Market Hours
`core/timeutils.py` must export: `is_market_open() -> bool`, `minutes_until_close() -> int`, `next_market_open() -> datetime`, `is_pre_market() -> bool`.
`paper_trade_tick` must check `is_market_open()` first. If closed: log a debug message and return `{market_open: false, orders: [], positions: [], pnl_snapshot: null}`.

---

## MCP Tool Contract (strict names)

| Tool | Inputs | Outputs |
|---|---|---|
| `ingest_latest_news` | `max_items: int` | `{ingested: int, doc_ids: list[str]}` |
| `embed_and_upsert_docs` | `doc_ids: list[str]` | `{upserted_chunks: int}` |
| `score_sentiment` | `doc_ids: list[str]` | `{scored: int}` |
| `query_kb` | `query: str, top_k: int, filters?: obj` | `{results: [{doc_id, title, score, snippet, published_at, source_url, sentiment_score}]}` |
| `propose_strategy_update` | `strategy_name: str, recent_minutes: int` | `{proposal: {new_definition, rationale, risks, expected_behavior, confidence, cited_doc_ids, changed_fields}}` |
| `validate_strategy` | `definition_json: obj` | `{valid: bool, errors: list[str]}` |
| `run_backtest` | `definition_json: obj, start: str, end: str` | `{metrics: {cagr, sharpe, max_drawdown, win_rate, turnover, avg_trade_return}, passed: bool, equity_curve_path?: str}` |
| `submit_strategy_for_approval` | `strategy_name: str, definition_json: obj, reason: str, backtest_metrics: obj` | `{strategy_version_id: str, status: "pending_approval"}` |
| `paper_trade_tick` | `strategy_name: str` | `{orders: list, positions: list, pnl_snapshot: obj, market_open: bool}` |

---

## Scheduler Pipeline (Celery)

Tasks in `apps/scheduler/jobs.py`. Each step is a separate Celery task with retry on failure (max 3 retries, exponential backoff).

```
news_cycle (every NEWS_POLL_INTERVAL_SECONDS):
  1. ingest_latest_news
  2. embed_and_upsert_docs
  3. score_sentiment
  4. propose_strategy_update
  5. validate_strategy
  6. score_proposal_quality (evidence, recency, consensus, coverage)
  7. if quality passes threshold → submit_strategy_for_approval (status=pending_approval)
  8. write run record to DB

paper_trade_tick (every 1 minute, market hours only):
  1. paper_trade_tick for each active strategy
  2. persist pnl_snapshot
  3. check daily loss circuit breaker (rehydrate from DB, not memory)
```

---

## API Endpoints

```
GET  /health
GET  /news/recent?minutes=120
GET  /strategies
GET  /strategies/{name}/active
GET  /strategies/{name}/versions
POST /strategies/{name}/approve/{version_id}     ← human approval gate
POST /strategies/{name}/backtest
GET  /runs/recent
POST /runs/news_cycle                            ← manual trigger
GET  /pnl/daily?strategy={name}
```

No business logic in routers. All calls delegate to `core/`.

---

## Docker Compose

Provide `docker-compose.yml` with:
- `postgres` — port 5432, health check
- `qdrant` — port 6333 + 6334
- `redis` — port 6379
- `flower` — port 5555 (Celery task dashboard)

All services on a shared `quant-net` network. Include volume mounts for Postgres and Qdrant data persistence.

---

## Repo Layout

```
quant-news-rag/
  README.md
  CLAUDE.md                        ← this file (build spec + constraints)
  DOCUMENTATION.md                 ← user-facing docs, setup, future phases
  pyproject.toml
  alembic.ini
  .env.example
  docker-compose.yml
  alembic/
    env.py
    versions/
      001_initial.py
  apps/
    api/
      main.py
      routers/
        health.py
        news.py
        strategies.py
        backtests.py
        runs.py
        pnl.py
      deps.py
    mcp_server/
      server.py
      tools/
        ingest.py
        kb.py
        sentiment.py
        strategy.py
        backtest.py
        execution.py
      schemas.py
    scheduler/
      worker.py
      jobs.py
  core/
    config.py
    logging.py
    timeutils.py
    ingestion/
      fetchers/
        base.py
        rss.py
        market_data.py             ← REQUIRED for backtester
        provider_newsapi.py
      normalize.py
      dedupe.py
      ticker_extract.py            ← regex ticker extraction at ingest time
    storage/
      db.py
      models.py
      repos/
        news_repo.py
        strategy_repo.py
        run_repo.py
        market_data_repo.py
        pnl_repo.py
    kb/
      embeddings.py
      vectorstore.py
      chunking.py
      retrieval.py
      sentiment.py                 ← finbert or LLM scoring
    agent/
      rag_agent.py
      prompts.py                   ← versioned string constants, not inline f-strings
      strategy_language.py
      validator.py
      approval.py                  ← approval gate logic
      quality_scorer.py            ← proposal quality scoring (replaces backtest gate)
    strategies/
      base.py
      registry.py
      implementations/
        sentiment_momentum.py
        event_risk_off.py
    backtesting/
      engine.py
      metrics.py
      cost_model.py
    execution/
      broker_base.py
      paper_broker.py
      guard.py                     ← PAPER_GUARD enforcement
      alpaca_paper.py
      risk.py
      position_sizing.py
      price_feed.py                ← real-time price abstraction (Alpaca, DB, Mock)
      signal_evaluator.py          ← signal evaluation engine for live execution
    observability/
      metrics.py
      tracing.py
  tests/
    conftest.py
    test_dedupe.py
    test_chunking.py
    test_ticker_extract.py
    test_vectorstore_mock.py
    test_strategy_validator.py
    test_backtest_smoke.py
    test_risk_circuit_breaker.py
    test_paper_guard.py
    test_approval_gate.py
    test_market_hours.py
    test_price_feed.py
    test_signal_evaluator.py
    test_quality_scorer.py
```

---

## Testing Requirements

All tests must pass with `pytest`. No external services — use mocks/fakes for Qdrant, Postgres, and LLM.

| Test | What it verifies |
|---|---|
| `test_dedupe` | Same URL/content not ingested twice; different content ingested |
| `test_chunking` | Chunking is deterministic; overlap is correct |
| `test_ticker_extract` | Known tickers extracted; false positives handled |
| `test_vectorstore_mock` | Upsert + query returns correct results in mock |
| `test_strategy_validator` | Rejects: invalid tickers, risk violations, unknown fields, excess diff |
| `test_backtest_smoke` | Runs with mock market data; returns all required metric fields |
| `test_risk_circuit_breaker` | Breaker trips at daily loss limit; state rehydrates from DB after restart |
| `test_paper_guard` | Non-paper broker raises with PAPER_GUARD=true |
| `test_approval_gate` | Agent proposals land in pending_approval, not active |
| `test_market_hours` | paper_trade_tick no-ops outside market hours |
| `test_price_feed` | MockPriceFeed returns preset prices; DbPriceFeed uses open price, skips stale data |
| `test_signal_evaluator` | Sentiment threshold filtering, volatility gate, position reconciliation, order execution flow |
| `test_quality_scorer` | Evidence strength, recency, consensus, coverage scoring; composite threshold; graceful handling of missing docs |

---

## Build Phases (All Complete)

All 12 build phases have been completed. Follow this sequence for reference. Run `pytest` after each phase.

1. **Scaffold + config + logging** — `core/config.py`, `core/logging.py`, `pyproject.toml`, `.env.example`, `docker-compose.yml`
2. **Postgres models + Alembic** — `core/storage/models.py`, `alembic/`, `001_initial.py` migration, repos
3. **Market data ingestion** — `core/ingestion/fetchers/market_data.py`, `market_data_repo.py` (needed early for backtester)
4. **News ingestion** — RSS fetcher, `normalize.py`, `dedupe.py`, `ticker_extract.py`
5. **Chunking + embeddings + vectorstore** — Qdrant client, mock, `sentiment.py`
6. **MCP server tools 1–4** — `ingest_latest_news`, `embed_and_upsert_docs`, `score_sentiment`, `query_kb`
7. **RAG agent + strategy language + validator** — MCP tools 4–5, approval gate
8. **Backtest engine + cost model + metrics** — MCP tool 6, both windows (in-sample + OOS)
9. **Strategy versioning + approval API** — MCP tool 7 (`submit_strategy_for_approval`), `POST /approve/`
10. **Paper broker + risk + guard + PnL persistence** — MCP tool 8, circuit breaker with DB rehydration
11. **FastAPI endpoints + Celery scheduler wiring**
12. **Tests, README, docs polish**

**Deferred to v2:** `observability/metrics.py`, `observability/tracing.py` (Prometheus/OpenTelemetry), `provider_newsapi.py` (NewsAPI fetcher).

---

## Acceptance Criteria

- `docker-compose up` starts all services cleanly.
- `pytest` passes with no external service calls.
- `alembic upgrade head` creates all tables with correct schema.
- One manual `news_cycle` run:
  - Ingests ≥ 1 news item from configured RSS source.
  - Embeds and upserts into Qdrant (or mock).
  - Scores sentiment.
  - Agent produces a strategy proposal with at least one cited `doc_id`.
  - Proposal validates.
  - Both backtest windows run (may use mock data) and produce metric objects.
  - Strategy version created in Postgres with `status=pending_approval`.
- `POST /strategies/{name}/approve/{version_id}` transitions status to `active`.
- All API endpoints return sensible JSON (tested manually or via `httpx` in tests).
- `TRADING_MODE=live` in `.env` causes process to exit with a clear error on startup.
- `PAPER_GUARD=true` with any non-paper broker raises `RuntimeError` before any order is placed.

---

## Common Mistakes to Avoid

- **Do not store circuit breaker state in memory only.** Always write to `pnl_snapshots` and read from it on startup.
- **Do not auto-activate strategies.** `submit_strategy_for_approval` sets `status=pending_approval`. Only `POST /approve/` sets `status=active`.
- **Do not allow tickers outside `STRATEGY_APPROVED_UNIVERSE`.** The validator must check this list against env config, not a hardcoded value.
- **Do not let the agent propose a strategy with >STRATEGY_MAX_DIFF_FIELDS changed fields.** Count the diff in `validator.py` before returning `valid=true`.
- **Do not index market data at bar close for signal generation.** Shift by 1 bar. Comment every shift.
- **Do not write business logic in `apps/`.** If you find yourself writing a DB query or embedding call inside a FastAPI router, move it to `core/`.
- **Do not use APScheduler.** Use Celery with Redis. Tasks must have retry logic.
- **Do not put prompts inline in `rag_agent.py`.** All prompts are named constants in `core/agent/prompts.py`.

---

## Known Limitations (v1)

- SimHash near-duplicate detection not implemented (content hash only).
- Survivorship bias not corrected in backtester.
- Market data for backtesting uses daily bars by default; intraday signals may not be fully representable.
- The RAG agent's strategy proposals depend on LLM quality and retrieved context; confidence scores are self-reported and not calibrated.
- No portfolio-level risk management across multiple simultaneous strategies in v1.

---

## Glossary

| Term | Meaning |
|---|---|
| pending_approval | Strategy proposed by agent, not yet human-approved |
| active | Currently executing strategy version |
| archived | Superseded strategy version, kept for audit |
| news_cycle | Full pipeline run: ingest → embed → sentiment → agent → validate → backtest → submit |
| paper_trade_tick | Single execution tick for paper positions |
| OOS | Out-of-sample backtest window |
| PAPER_GUARD | Runtime flag that prevents any live order from being placed |
| circuit breaker | Daily loss limit that halts all trading if breached |
