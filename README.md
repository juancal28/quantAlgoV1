# Quant News-RAG Trading System

A modular, **paper-only** quantitative trading system that ingests financial news, builds a vector knowledge base (RAG), uses an LLM agent to propose strategy updates, backtests them with dual-window validation, and executes paper trades — all with a mandatory human approval gate.

## How It Works

```
Fetch news (RSS) → Dedupe & store → Embed into Qdrant → Score sentiment
  → RAG agent proposes strategy update → Validator checks rules
  → Backtest (in-sample + out-of-sample) → Submit for human approval
  → Human approves via API → Signal engine evaluates → Paper broker executes
  → PnL tracked in DB → Circuit breaker monitors losses
```

The full pipeline runs on a Celery schedule every 2 minutes (configurable). Paper trading ticks run every 60 seconds during market hours.

### Signal Evaluation (paper_trade_tick)

Once a strategy is approved and active, each paper trading tick follows this flow:

1. **Check market hours** — no-op if NYSE is closed
2. **Load active strategy** definition from Postgres
3. **Fetch current prices** — via Alpaca Data API (`BROKER_PROVIDER=alpaca`) or from DB bars (`BROKER_PROVIDER=internal`). Prices use bar `open` to prevent lookahead bias. Stale data (older than `RISK_MAX_DATA_STALENESS_MINUTES`) is skipped.
4. **Evaluate signals** (throttled by `rebalance_minutes` from strategy definition):
   - **Volatility filter** (gate) — reads VIXY ETF price as VIX proxy. If above `max_vix`, all signals go flat (risk-off). Defaults to pass if no VIXY data.
   - **News sentiment** — queries recent news from DB, groups sentiment scores by ticker, computes per-ticker average. Tickers above `threshold` get a "long" signal.
5. **Reconcile positions** — compares target signals vs currently held positions to determine buys and sells
6. **Execute orders** through the broker:
   - Checks circuit breaker, exposure limits, and trade rate limits
   - Sells first (to free up cash), then buys
   - Position sizing via equal-weight with `RISK_MAX_POSITION_PCT` cap
   - Whole shares only (fractional quantities are floored)
7. **Persist PnL snapshot** to Postgres and check circuit breaker

## Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for Postgres, Qdrant, Redis, Flower)
- **Alpaca API keys** (free paper trading account at [alpaca.markets](https://alpaca.markets)) — required for market data
- **OpenAI API key** (optional) — only if using `EMBEDDINGS_PROVIDER=openai`; the default `mock` provider requires no key

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/juancal28/quantAlgoV1.git
cd quantAlgoV1
cp .env.example .env
```

Edit `.env` to fill in your API keys:

```
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
```

### 2. Start infrastructure services

```bash
docker-compose up -d
```

This starts:
| Service | Port | Purpose |
|---------|------|---------|
| Postgres | 5432 | Primary database |
| Qdrant | 6333 | Vector database for news embeddings |
| Redis | 6379 | Celery task broker |
| Flower | 5555 | Celery task monitoring dashboard |

### 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

For sentiment analysis with FinBERT and backtesting with vectorbt:

```bash
pip install -e ".[sentiment,backtest]"
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the application

**API server:**

```bash
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Celery worker** (in a separate terminal):

```bash
celery -A apps.scheduler.worker worker --loglevel=info
```

**Celery beat scheduler** (in a separate terminal):

```bash
celery -A apps.scheduler.worker beat --loglevel=info
```

## Usage

### Run a news cycle manually

Trigger a full pipeline run (ingest → embed → sentiment → agent → validate → backtest → submit):

```bash
curl -X POST http://localhost:8000/runs/news_cycle
```

### View recent news

```bash
curl http://localhost:8000/news/recent?minutes=120
```

### View strategies

```bash
# List all strategies
curl http://localhost:8000/strategies

# Get the active version of a strategy
curl http://localhost:8000/strategies/sentiment_momentum_v1/active

# Get all versions of a strategy
curl http://localhost:8000/strategies/sentiment_momentum_v1/versions
```

### Approve a pending strategy

Strategy proposals from the RAG agent **never auto-activate**. They land in `pending_approval` status and require explicit human approval:

```bash
curl -X POST http://localhost:8000/strategies/{name}/approve/{version_id}
```

### Run a backtest

```bash
curl -X POST http://localhost:8000/strategies/{name}/backtest
```

### View PnL

```bash
curl http://localhost:8000/pnl/daily?strategy=sentiment_momentum_v1
```

### View pipeline run history

```bash
curl http://localhost:8000/runs/recent
```

### Monitor Celery tasks

Open [http://localhost:5555](http://localhost:5555) in your browser for the Flower dashboard.

## Architecture

```
apps/            → Thin application layers (no business logic)
  api/           → FastAPI REST endpoints
  mcp_server/    → MCP tool server
  scheduler/     → Celery worker and periodic jobs
core/            → All business logic (independently importable)
  ingestion/     → News fetching, dedup, normalization, ticker extraction
  storage/       → SQLAlchemy models, DB session, repository layer
  kb/            → Embeddings, chunking, vector store, sentiment scoring
  agent/         → RAG agent, strategy language, validator, approval gate
  backtesting/   → Backtest engine, cost model, metrics
  execution/     → Paper broker, signal evaluator, price feed, risk, position sizing
  strategies/    → Strategy base class, registry, built-in implementations
```

**Dependency rule:** `apps/*` calls `core/*`, never the reverse.

## Safety Rails

This system enforces multiple layers of safety:

- **Paper-only mode**: `TRADING_MODE=paper` is the only valid value. The process hard-exits on startup if any other value is detected. No live trading codepath exists.
- **Paper guard**: Every broker method checks `PAPER_GUARD=true` before placing orders. Non-paper brokers raise `RuntimeError` immediately.
- **Human approval gate**: RAG agent proposals always land in `pending_approval` status. Activation requires an explicit API call.
- **Daily loss circuit breaker**: Persisted in Postgres (not memory). Halts all trading if daily loss exceeds the configured threshold (default 2%). Rehydrates on restart.
- **Risk checks on every tick**: Exposure limits, per-position caps, trade rate limits, and data staleness checks are all enforced before any order is placed.
- **Strategy validator**: Rejects proposals with unapproved tickers, risk limit violations, unknown signal types, or too many changed fields.
- **Dual-window backtesting**: Both in-sample (252 days) and out-of-sample (90 days) must pass Sharpe, drawdown, and win rate thresholds before a proposal can be submitted.

## Configuration

All configuration is managed via environment variables loaded through `pydantic-settings`. See [`.env.example`](.env.example) for the full list with defaults.

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | **Must be `paper`**. Hard exit otherwise. |
| `PAPER_GUARD` | `true` | Blocks any non-paper order execution |
| `PAPER_INITIAL_CASH` | `100000` | Starting paper portfolio value |
| `RISK_MAX_DAILY_LOSS_PCT` | `0.02` | Circuit breaker threshold (2%) |
| `RISK_MAX_POSITION_PCT` | `0.10` | Max single position size (10%) |
| `BROKER_PROVIDER` | `internal` | `internal` or `alpaca` (paper broker + price feed backend) |
| `RISK_MAX_DATA_STALENESS_MINUTES` | `30` | Skip price data older than this (minutes) |
| `ANTHROPIC_API_KEY` | *(empty)* | Required for RAG agent LLM calls |
| `EMBEDDINGS_PROVIDER` | `mock` | `mock` or `openai` |
| `SENTIMENT_PROVIDER` | `finbert` | `finbert`, `llm`, or `mock` |
| `STRATEGY_APPROVED_UNIVERSE` | `SPY,QQQ,...` | Allowed tickers for strategies |
| `NEWS_POLL_INTERVAL_SECONDS` | `120` | Pipeline run frequency |

## Running Tests

174 tests across 22 test files. All tests run with mocks — no external services required:

```bash
pytest
```

With coverage:

```bash
pytest --cov=core --cov=apps
```

## MCP Server

The system exposes an MCP (Model Context Protocol) tool server for programmatic access:

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
| `get_system_health` | Read-only: system health, trading mode, market status |
| `get_strategy_overview` | Read-only: all strategies with status and metrics |
| `get_recent_runs` | Read-only: recent pipeline run history |
| `get_pnl_summary` | Read-only: daily PnL snapshots for a strategy |
| `get_recent_news_summary` | Read-only: recent news with sentiment scores |

## Known Limitations (v1)

- Survivorship bias is not corrected in the backtester (ETF-only universe is a partial mitigation).
- Near-duplicate detection (SimHash) is not implemented; only exact content hash dedup is used.
- Market data uses daily bars by default; intraday signals may not be fully representable.
- The RAG agent's confidence scores are self-reported and not calibrated.
- No portfolio-level risk management across multiple simultaneous strategies.
- VIX proxy uses VIXY ETF price (real VIX index not available via Alpaca data API). Degrades gracefully (defaults to pass) if no data.
- No fractional share support; order quantities are floored to whole shares.

## Disclaimer

**This system is for paper trading and educational purposes only. No live trading is implemented or supported.**

- News-based signals have no guaranteed alpha. Past backtest performance does not predict future results.
- The RAG agent can make incorrect inferences. All strategy proposals require human review before activation.
- This software is provided as-is with no warranty. Use at your own risk.
