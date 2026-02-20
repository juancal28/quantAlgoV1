# Quant News-RAG Trading System — Claude Code Build Spec
_Complete implementation plan. Follow exactly, in order._

---

## 0) What We're Building

A modular, paper-first quantitative trading system:

- A **news ingestion loop** fetches, dedupes, and stores market news every N minutes.
- A **market data fetcher** pulls OHLCV bars from Alpaca (required for backtesting).
- A **sentiment scorer** tags each article with a directional score at embed time.
- An **embedding + vector store** layer indexes news into a searchable knowledge base.
- A **RAG agent** queries the KB and proposes **strategy updates** (signals, params, rules).
- A **human approval gate** sits between every agent proposal and activation.
- A **backtester** runs in-sample + out-of-sample validation before any proposal is submitted for approval.
- A **paper broker** simulates execution with a persistent daily PnL + circuit breaker.
- Everything is orchestrated via **Celery tasks** and exposed via an **MCP server** and **FastAPI**.

**Default mode: PAPER ONLY. `TRADING_MODE=paper` is the only valid value. Hard exit on startup if changed.**

---

## 1) Goals

- End-to-end pipeline: fetch news + market data → store → embed + sentiment → RAG → validate → dual-window backtest → submit for approval → human approves → paper execution.
- Clean separation: `apps/` is thin; all business logic lives in `core/`.
- Repeatable local dev with Docker Compose.
- Safety rails: PAPER_GUARD, circuit breaker persisted in DB, human approval gate, approved ticker universe.
- Observability: structured JSON logs, run history in Postgres, Celery Flower for task visibility.

---

## 2) Non-Goals (v1)

- Live trading of any kind.
- Ultra-low-latency or HFT execution.
- Survivorship-bias-corrected backtesting (document as known limitation).
- Guaranteed alpha.
- Near-duplicate dedup via SimHash (use content hash; SimHash is a TODO v2 comment).

---

## 3) Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI (async, Pydantic v2) |
| Task queue | **Celery + Redis** (not APScheduler — retries, visibility, Flower) |
| Database | Postgres, SQLAlchemy 2.x async, Alembic migrations |
| Vector DB | Qdrant (Docker); FAISS mock for unit tests |
| Embeddings | Pluggable: `mock` (default) or `openai` |
| Sentiment | `ProsusAI/finbert` local model or `mock` |
| Market data | Alpaca Data API (default), yfinance (fallback) |
| Backtesting | vectorbt (adapter pattern so it's swappable) |
| Broker | `PaperBroker` (internal sim), `AlpacaPaperBroker` (optional) |
| MCP | stdio MCP server |

---

## 4) Architecture

### Service Boundary Rule
```
apps/* → core/*   ✓  (apps call core)
core/* → apps/*   ✗  (never)
```

### Data Flow (every N minutes via Celery)
```
Fetch news (RSS/NewsAPI)
  → normalize + dedupe (content hash)
  → ticker extraction (regex vs approved universe)
  → store in news_documents (Postgres)
  → embed chunks → upsert to Qdrant
  → score sentiment → update news_documents + Qdrant payload
  → agent retrieves context from KB
  → agent proposes strategy delta (JSON, cites doc_ids)
  → validator checks: tickers, risk rules, diff field count, confidence
  → run in-sample backtest (last STRATEGY_MIN_BACKTEST_DAYS trading days)
  → run OOS backtest (90 days before in-sample)
  → if both pass thresholds → submit_for_approval (status=pending_approval)
  → human calls POST /strategies/{name}/approve/{version_id}
  → status=active → paper_trade_tick (every 1 min, market hours only)
  → pnl_snapshot persisted to Postgres
  → circuit breaker checks against DB snapshot (not memory)
```

---

## 5) Repo Layout (create exactly)

```
quant-news-rag/
  README.md
  CLAUDE.md
  PROJECT.md
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
        market_data.py
        provider_newsapi.py
      normalize.py
      dedupe.py
      ticker_extract.py
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
      sentiment.py
    agent/
      rag_agent.py
      prompts.py
      strategy_language.py
      validator.py
      approval.py
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
      guard.py
      alpaca_paper.py
      risk.py
      position_sizing.py
      price_feed.py
      signal_evaluator.py
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
```

---

## 6) Configuration

All config in `core/config.py` using `pydantic-settings`. Load from environment. Never hardcode.

### `.env.example`
```env
# App
APP_ENV=dev

# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/quant

# Redis / Celery
REDIS_URL=redis://localhost:6379/0

# Vector DB
QDRANT_URL=http://localhost:6333

# News ingestion
NEWS_POLL_INTERVAL_SECONDS=120
NEWS_SOURCES=rss:https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US
MAX_DOCS_PER_POLL=50

# Market data (REQUIRED for backtester)
MARKET_DATA_PROVIDER=alpaca
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
MARKET_DATA_LOOKBACK_DAYS=365
BAR_TIMEFRAME=1Day

# Embeddings
EMBEDDINGS_PROVIDER=mock
OPENAI_API_KEY=
VECTOR_COLLECTION=news
VECTOR_SIZE=1536
CHUNK_SIZE_CHARS=1000
CHUNK_OVERLAP_CHARS=150

# Sentiment
SENTIMENT_PROVIDER=mock

# Risk
RISK_MAX_GROSS_EXPOSURE=1.0
RISK_MAX_POSITION_PCT=0.10
RISK_MAX_DAILY_LOSS_PCT=0.02
RISK_MAX_TRADES_PER_HOUR=30
RISK_MAX_DATA_STALENESS_MINUTES=30

# Execution
PAPER_INITIAL_CASH=100000
PAPER_GUARD=true
TRADING_MODE=paper

# Strategy agent
STRATEGY_MIN_CONFIDENCE=0.6
STRATEGY_MAX_DIFF_FIELDS=3
STRATEGY_MAX_ACTIVATIONS_PER_DAY=4
STRATEGY_MIN_BACKTEST_DAYS=252
STRATEGY_APPROVED_UNIVERSE=SPY,QQQ,AAPL,MSFT,AMZN,GOOGL,META,NVDA,BRK.B,JPM
PENDING_APPROVAL_AUTO_APPROVE_MINUTES=0
```

### Startup validation (in `core/config.py`)
```python
if settings.TRADING_MODE != "paper":
    raise SystemExit("FATAL: TRADING_MODE must be 'paper' in v1. Live trading is not implemented.")
```

---

## 7) Data Models (Postgres, SQLAlchemy 2.x)

Implement in `core/storage/models.py`. Use `mapped_column` and `DeclarativeBase`.

### `news_documents`
- `id` uuid pk
- `source` text
- `source_url` text (unique index)
- `title` text
- `published_at` timestamptz
- `fetched_at` timestamptz
- `content` text
- `content_hash` text (unique index) — SHA-256 of normalized content
- `metadata` jsonb — `{tickers: [], author, tags}`
- `sentiment_score` float nullable
- `sentiment_label` text nullable — `positive | negative | neutral`

### `market_bars`
- `id` uuid pk
- `ticker` text
- `timeframe` text
- `bar_time` timestamptz
- `open, high, low, close` numeric
- `volume` bigint
- `fetched_at` timestamptz
- unique constraint: `(ticker, timeframe, bar_time)`

### `strategy_versions`
- `id` uuid pk
- `name` text
- `version` int
- `status` text — `pending_approval | active | archived`
- `definition` jsonb
- `created_at` timestamptz
- `activated_at` timestamptz nullable
- `approved_by` text nullable — `"human" | "auto" | null`
- `reason` text
- `backtest_metrics` jsonb

### `strategy_audit_log`
- `id` uuid pk
- `timestamp` timestamptz
- `strategy_name` text
- `version_id` uuid fk → `strategy_versions`
- `action` text — `proposed | approved | rejected | activated | archived`
- `trigger` text — `agent | human | scheduler`
- `before_definition` jsonb nullable
- `after_definition` jsonb nullable
- `backtest_metrics` jsonb nullable
- `llm_rationale` text nullable
- `diff_fields` jsonb

### `pnl_snapshots`
- `id` uuid pk
- `strategy_name` text
- `snapshot_date` date
- `realized_pnl` numeric
- `unrealized_pnl` numeric
- `gross_exposure` numeric
- `peak_pnl` numeric
- `positions` jsonb
- `created_at` timestamptz
- unique: `(strategy_name, snapshot_date)`

### `runs`
- `id` uuid pk
- `run_type` text — `ingest | embed | sentiment | agent_update | backtest | execution`
- `started_at` timestamptz
- `ended_at` timestamptz nullable
- `status` text — `running | ok | fail`
- `details` jsonb

---

## 8) Alembic Setup

**Run `alembic init alembic` before writing any code beyond models. Create `001_initial.py` that creates all tables above. All subsequent model changes must be expressed as numbered migrations, never raw `ALTER TABLE`.**

---

## 9) Vector DB (Qdrant)

Collection config:
```python
COLLECTION_CONFIG = {
    "vectors": {
        "size": settings.VECTOR_SIZE,
        "distance": "Cosine",
    },
    "optimizers_config": {"default_segment_number": 2},
    "quantization_config": {"scalar": {"type": "int8", "always_ram": True}},
}
```

Payload per point: `doc_id, title, source, source_url, published_at, tickers, tags, sentiment_score, sentiment_label, chunk_index, chunk_total`

Chunking: `CHUNK_SIZE_CHARS` chars, `CHUNK_OVERLAP_CHARS` overlap (both from config). Chunking must be deterministic — same input always produces same output.

---

## 10) News Ingestion

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

## 11) Sentiment Scoring (`core/kb/sentiment.py`)

Run after embedding, before Qdrant upsert.

- `SENTIMENT_PROVIDER=finbert`: load `ProsusAI/finbert` from HuggingFace. Score each document chunk. Aggregate to document-level by averaging chunk scores, weighted by chunk length.
- `SENTIMENT_PROVIDER=mock`: return `score=0.0, label="neutral"` for all docs.
- Store `sentiment_score` (float, -1 to 1) and `sentiment_label` in `news_documents` and in Qdrant payload.

---

## 12) Strategy Language

JSON spec. Implement parser + schema in `core/agent/strategy_language.py`.

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

## 13) RAG Agent (`core/agent/rag_agent.py`)

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

### Prompts (`core/agent/prompts.py`)
- All prompts are **named module-level string constants** (not inline f-strings).
- Every claim in the proposal must cite at least one `doc_id` or be labeled `[INFERENCE]`.
- System prompt must instruct: "Never invent tickers or sources. If you cannot cite a document, do not make the claim."

---

## 14) Validator (`core/agent/validator.py`)

Hard checks (all must pass):
- All tickers in `universe` are in `STRATEGY_APPROVED_UNIVERSE` (loaded from config).
- No unknown signal or exit types.
- `max_position_pct` ≤ `RISK_MAX_POSITION_PCT`.
- `len(changed_fields)` ≤ `STRATEGY_MAX_DIFF_FIELDS` when comparing to current active version.
- `confidence` ≥ `STRATEGY_MIN_CONFIDENCE`.
- No unknown top-level fields (strict schema).

Returns `{valid: bool, errors: list[str]}`.

---

## 15) Backtesting (`core/backtesting/`)

### Engine (`engine.py`)
- Accepts: `definition_json`, `start_date`, `end_date`, market bars from `market_data_repo`.
- Load bars from Postgres (not from fetcher at backtest time — data must already be ingested).
- Load sentiment signals from `news_documents` within the window.
- **Lookahead guard**: all signal arrays must be shifted by 1 bar before being used for position entry. Add comment: `# lookahead guard: shift(1)` at each shift site.
- Apply cost model before computing returns.

### Cost Model (`cost_model.py`)
Configurable via env:
- `BACKTEST_COMMISSION_PER_TRADE=1.00` (dollars)
- `BACKTEST_SLIPPAGE_BPS=5`
- `BACKTEST_SPREAD_BPS=2`

### Metrics (`metrics.py`)
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
In `README.md` and `engine.py` docstring: "Survivorship bias is not corrected in v1 (ETF-only universe is a partial mitigation)."

---

## 16) Human Approval Gate (`core/agent/approval.py`)

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

## 17) Risk & Execution

### PAPER_GUARD (`core/execution/guard.py`)
```python
def assert_paper_guard():
    if settings.PAPER_GUARD and settings.TRADING_MODE != "paper":
        raise RuntimeError("PAPER_GUARD: live trading blocked. Set PAPER_GUARD=false and TRADING_MODE=paper to proceed.")
```
Call `assert_paper_guard()` at the top of every broker method that places an order.

### Risk (`core/execution/risk.py`)
Checks per tick:
- Gross exposure ≤ `RISK_MAX_GROSS_EXPOSURE`
- Per-position ≤ `RISK_MAX_POSITION_PCT`
- Trades in last hour ≤ `RISK_MAX_TRADES_PER_HOUR`
- News data age ≤ `RISK_MAX_DATA_STALENESS_MINUTES` (check `max(published_at)` from recent news)

### Circuit Breaker (persistent)
- On every `paper_trade_tick`, load today's `pnl_snapshot` from Postgres.
- If `realized_pnl / PAPER_INITIAL_CASH < -RISK_MAX_DAILY_LOSS_PCT`: halt all trading, log `circuit_breaker_tripped`, set a `halted` flag in `pnl_snapshots` for the day.
- On startup, rehydrate: check today's `pnl_snapshot` for `halted=true` and refuse to trade if found.
- **Never hold circuit breaker state only in memory.**

### Price Feed (`core/execution/price_feed.py`)
Abstraction for fetching current prices with three implementations:
- **`AlpacaPriceFeed`** — calls Alpaca `StockHistoricalDataClient.get_stock_latest_bar()`. Uses `bar.open` (`# lookahead guard: shift(1)`). Skips tickers with data older than `RISK_MAX_DATA_STALENESS_MINUTES`.
- **`DbPriceFeed`** — reads the most recent bar from Postgres via `market_data_repo.get_bars_for_ticker()`. Used when `BROKER_PROVIDER=internal`.
- **`MockPriceFeed`** — returns preset prices dict. For tests.
- **`get_price_feed(session=None)`** — factory: returns `AlpacaPriceFeed` when `BROKER_PROVIDER=alpaca`, else `DbPriceFeed(session)`.

### Signal Evaluator (`core/execution/signal_evaluator.py`)
Core engine that evaluates strategy signals and places orders:
- **`evaluate_news_sentiment_signal(session, signal_config, universe)`** — queries `news_repo.get_recent()`, groups sentiment scores by ticker, returns `{ticker: avg_score}` for tickers above threshold.
- **`evaluate_volatility_filter(session, signal_config)`** — reads latest VIXY bar as VIX proxy. Returns `True` (pass) or `False` (risk-off). Defaults to `True` if no VIXY data.
- **`generate_signals_from_definition(session, definition, current_prices)`** — evaluates all signals: volatility filter as gate, then news sentiment. Returns `{ticker: "long"|"flat"}`.
- **`reconcile_positions(signals, current_positions)`** — compares target vs held. Returns `(tickers_to_buy, tickers_to_sell)`.
- **`execute_signals(broker, signals, current_prices, definition, circuit_breaker_tripped)`** — orchestrates orders: SELLs first, then BUYs with position sizing. Whole shares only. Checks exposure limits, trade rate, and circuit breaker.

### Market Hours
`core/timeutils.py` must export: `is_market_open() -> bool`, `minutes_until_close() -> int`, `next_market_open() -> datetime`, `is_pre_market() -> bool`.
`paper_trade_tick` must check `is_market_open()` first. If closed: log a debug message and return `{market_open: false, orders: [], positions: [], pnl_snapshot: null}`.

---

## 18) MCP Server

Implement in `apps/mcp_server/server.py` with handlers in `apps/mcp_server/tools/`. Tool names are a strict contract — do not rename.

| Tool | Inputs | Outputs |
|---|---|---|
| `ingest_latest_news` | `max_items: int` | `{ingested: int, doc_ids: list[str]}` |
| `embed_and_upsert_docs` | `doc_ids: list[str]` | `{upserted_chunks: int}` |
| `score_sentiment` | `doc_ids: list[str]` | `{scored: int}` |
| `query_kb` | `query: str, top_k: int, filters?: obj` | `{results: [{doc_id, title, score, snippet, published_at, source_url, sentiment_score}]}` |
| `propose_strategy_update` | `strategy_name: str, recent_minutes: int` | `{proposal: {new_definition, rationale, risks, expected_behavior, confidence, cited_doc_ids, changed_fields}}` |
| `validate_strategy` | `definition_json: obj` | `{valid: bool, errors: list[str]}` |
| `run_backtest` | `definition_json: obj, start: str, end: str` | `{metrics: {cagr, sharpe, max_drawdown, win_rate, turnover, avg_trade_return}, passed: bool}` |
| `submit_strategy_for_approval` | `strategy_name: str, definition_json: obj, reason: str, backtest_metrics: obj` | `{strategy_version_id: str, status: "pending_approval"}` |
| `paper_trade_tick` | `strategy_name: str` | `{orders: list, positions: list, pnl_snapshot: obj, market_open: bool}` |

---

## 19) Scheduler (Celery)

### `apps/scheduler/worker.py`
Celery app with Redis broker. Enable Flower for task monitoring (expose port 5555 in docker-compose).

### `apps/scheduler/jobs.py`

**`news_cycle`** — periodic, every `NEWS_POLL_INTERVAL_SECONDS`:
```
Step 1: ingest_latest_news
Step 2: embed_and_upsert_docs (for new doc_ids)
Step 3: score_sentiment (for new doc_ids)
Step 4: propose_strategy_update
Step 5: validate_strategy
Step 6: run_backtest (in-sample)
Step 7: run_backtest (OOS)
Step 8: if both pass thresholds → submit_strategy_for_approval
Step 9: write run record to DB with all step outcomes
```
Each step is a separate Celery task with `max_retries=3, retry_backoff=True`.

**`paper_trade_tick`** — periodic, every 60 seconds:
```
For each strategy with status=active:
  → paper_trade_tick (no-op if market closed)
  → persist pnl_snapshot
  → check circuit breaker
```

---

## 20) FastAPI Endpoints

```
GET  /health
GET  /news/recent?minutes=120
GET  /strategies
GET  /strategies/{name}/active
GET  /strategies/{name}/versions
POST /strategies/{name}/approve/{version_id}    ← human approval gate
POST /strategies/{name}/backtest
GET  /runs/recent
POST /runs/news_cycle                           ← manual trigger
GET  /pnl/daily?strategy={name}
```

No business logic in routers. All calls delegate to `core/`.

---

## 21) Docker Compose

Provide `docker-compose.yml` with:
- `postgres` — port 5432, health check
- `qdrant` — port 6333 + 6334
- `redis` — port 6379
- `flower` — port 5555 (Celery task dashboard)

All services on a shared `quant-net` network. Include volume mounts for Postgres and Qdrant data persistence.

---

## 22) Tests (must all pass with `pytest`)

Use mocks/fakes for all external services. No real API calls in tests.

| Test file | What it must verify |
|---|---|
| `test_dedupe` | Same URL → skipped; same content hash → skipped; different content → ingested |
| `test_chunking` | Same input always produces same chunks; overlap size is correct |
| `test_ticker_extract` | `AAPL` in content → extracted; `THE` not extracted; tickers not in universe → filtered |
| `test_vectorstore_mock` | Upsert 3 docs, query returns correct doc_ids sorted by score |
| `test_strategy_validator` | Rejects: unknown ticker, excess diff fields, risk violation, unknown signal type, low confidence |
| `test_backtest_smoke` | With mock market data, returns all required metric fields; `passed` is bool |
| `test_risk_circuit_breaker` | Simulate daily loss exceeding limit → trading halted; restart → still halted (rehydrated from DB) |
| `test_paper_guard` | `assert_paper_guard()` raises when `TRADING_MODE != "paper"` and `PAPER_GUARD=true` |
| `test_approval_gate` | Agent proposal creates `status=pending_approval`, not `active`; `approve()` sets `active` |
| `test_market_hours` | `paper_trade_tick` returns `market_open=false` and empty orders outside NYSE hours |
| `test_price_feed` | MockPriceFeed returns preset prices; DbPriceFeed uses `bar.open`, skips stale data, handles empty bars |
| `test_signal_evaluator` | Sentiment threshold filtering, per-ticker grouping, volatility gate, position reconciliation, sell-before-buy order, circuit breaker skip, whole shares, trade rate limit |

---

## 23) Acceptance Criteria (Definition of Done)

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

## 24) README Requirements

Include:
1. Prerequisites (Docker, Python 3.11+, API keys needed).
2. Setup: clone → copy `.env.example` → `docker-compose up` → `alembic upgrade head` → `uvicorn` / `celery worker`.
3. How to run one news cycle manually (via `POST /runs/news_cycle` or direct Celery call).
4. How to view strategies, news, and PnL via API.
5. How to approve a pending strategy version.
6. Caveats and risk disclaimers section including:
   - "This system is for paper trading only. No live trading is implemented."
   - "News-based signals have no guaranteed alpha. Past backtest performance does not predict future results."
   - "Survivorship bias is not corrected in v1."
   - "The RAG agent can make incorrect inferences. All strategy proposals require human review before activation."

---

## 25) Implementation Order (do this sequence exactly)

After each numbered phase, run `pytest` and fix failures before proceeding.

1. **Scaffold + config + logging** — `pyproject.toml`, `core/config.py` (with startup TRADING_MODE hard exit), `core/logging.py`, `.env.example`, `docker-compose.yml`.

2. **Postgres models + Alembic** — `core/storage/models.py` (all tables), `alembic init`, `001_initial.py` migration, all repos in `core/storage/repos/`. Run `alembic upgrade head`.

3. **Market data ingestion** — `core/ingestion/fetchers/market_data.py` (Alpaca + yfinance fallback), `market_data_repo.py`. This must exist before the backtester.

4. **News ingestion** — `rss.py` fetcher, `normalize.py`, `dedupe.py`, `ticker_extract.py` with static S&P 500 ticker list. Write `test_dedupe.py`, `test_ticker_extract.py`.

5. **Chunking + embeddings + vectorstore** — `chunking.py` (deterministic), `embeddings.py` (mock + openai pluggable), `vectorstore.py` (Qdrant client + collection init + FAISS mock), `retrieval.py`. Write `test_chunking.py`, `test_vectorstore_mock.py`.

6. **Sentiment scoring** — `core/kb/sentiment.py` (finbert + mock). MCP tool `score_sentiment`.

7. **MCP server tools 1–4** — `ingest_latest_news`, `embed_and_upsert_docs`, `score_sentiment`, `query_kb`. Wire to core functions.

8. **RAG agent + strategy language + validator** — `strategy_language.py`, `rag_agent.py`, `prompts.py` (named constants), `validator.py`. MCP tools `propose_strategy_update`, `validate_strategy`. Write `test_strategy_validator.py`.

9. **Backtest engine** — `engine.py` (lookahead guard), `cost_model.py`, `metrics.py`. Both in-sample + OOS windows. MCP tool `run_backtest`. Write `test_backtest_smoke.py`.

10. **Approval gate + strategy versioning** — `approval.py`, `strategy_audit_log` writes. MCP tool `submit_strategy_for_approval`. Write `test_approval_gate.py`.

11. **Paper broker + risk + guard + PnL persistence** — `paper_broker.py`, `guard.py`, `risk.py`, `position_sizing.py`, `pnl_repo.py`. Circuit breaker with DB rehydration. MCP tool `paper_trade_tick`. Write `test_risk_circuit_breaker.py`, `test_paper_guard.py`, `test_market_hours.py`.

12. **FastAPI endpoints + Celery scheduler** — all routers, `worker.py`, `jobs.py` with retry logic, Flower in docker-compose.

13. **Tests, README, docs polish** — all tests green, README complete with disclaimers, `conftest.py` with shared fixtures and service mocks.

---

## 26) Known Limitations to Document (not fix in v1)

- SimHash near-duplicate detection not implemented (content hash only).
- Survivorship bias not corrected in backtester.
- Market data for backtesting uses daily bars by default; intraday signals may not be fully representable.
- The RAG agent's strategy proposals depend on LLM quality and retrieved context; confidence scores are self-reported and not calibrated.
- No portfolio-level risk management across multiple simultaneous strategies in v1.

---

End of file.
