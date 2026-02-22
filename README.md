# Quant News-RAG Trading System

**A personal project to learn quantitative trading by building a complete, working system from scratch.**

I built this project to develop a deep understanding of the systems, mathematics, and engineering behind quantitative trading — with the goal of pursuing an internship in the field. Rather than just reading about how quant systems work, I wanted to build one end-to-end: from data ingestion to strategy evaluation to simulated execution.

The system is paper-only (no real money) and is designed as a learning tool that demonstrates practical knowledge of the full quant trading stack.

---

## What It Does

This is an autonomous trading system that reads financial news, decides whether to adjust its trading strategy, validates that decision through backtesting, and then paper-trades with simulated money. The key ideas:

1. **News as a signal source** — The system continuously ingests financial news from RSS feeds, stores it in a searchable vector database, and scores each article's sentiment using a finance-tuned language model (FinBERT). This creates a structured, queryable representation of market-moving information.

2. **AI-assisted strategy proposals** — A RAG (Retrieval-Augmented Generation) agent reads recent news and proposes minimal adjustments to the current trading strategy. Every proposal must cite specific articles — no unsupported claims. This demonstrates how LLMs can be used as analytical tools with proper guardrails, not as autonomous decision-makers.

3. **Rigorous validation before execution** — No strategy goes live without passing through a validator (checking risk limits, approved tickers, and change scope) and a dual-window backtester (1-year in-sample + 90-day out-of-sample). The backtester applies realistic trading costs and prevents lookahead bias.

4. **Human-in-the-loop** — The AI never auto-activates a strategy. Every proposal lands in a "pending approval" state and requires explicit human sign-off. This is a deliberate design choice that reflects how real trading desks operate.

5. **Paper trading with full risk management** — Approved strategies trade with $100,000 of simulated money. The system enforces position limits, exposure caps, trade rate limits, and a daily loss circuit breaker that halts everything if losses exceed 2%.

---

## What I Learned Building This

### Quantitative Concepts
- **Backtesting integrity** — why lookahead bias is the most common and dangerous mistake in strategy development, and how to prevent it with explicit data shifting
- **Dual-window validation** — why in-sample performance alone is meaningless, and how out-of-sample testing helps detect overfitting
- **Risk management** — position sizing, gross exposure limits, circuit breakers, and why these matter more than the strategy itself
- **Trading cost modeling** — how commissions, slippage, and bid-ask spreads erode returns, and why a backtest without cost modeling is fiction
- **Signal construction** — turning raw data (news sentiment, price momentum) into tradeable signals with defined thresholds and lookback windows

### Software Engineering
- **Event-driven architecture** — Celery task queues with Redis for reliable, retryable pipeline execution
- **Async Python** — FastAPI with SQLAlchemy 2.x async for non-blocking I/O throughout
- **Vector databases** — Qdrant for semantic search over document embeddings, enabling the RAG agent to find relevant news
- **Database design** — 6-table Postgres schema with audit trails, versioned strategies, and persistent circuit breaker state
- **Clean architecture** — strict separation between business logic (`core/`) and application layers (`apps/`), with one-directional dependencies

### AI/ML Integration
- **RAG pipelines** — document chunking, embedding, vector search, and context-augmented generation
- **Sentiment analysis** — using FinBERT (a finance-tuned transformer) for domain-specific NLP
- **LLM guardrails** — constraining AI output through structured schemas, citation requirements, and mandatory validation gates

---

## System at a Glance

```
News (RSS) -> Store & Deduplicate -> Embed into Vector DB -> Score Sentiment
  -> RAG Agent proposes strategy update -> Validator checks rules
  -> Backtest (in-sample + out-of-sample) -> Submit for human approval
  -> Human approves -> Signal engine evaluates -> Paper broker executes
  -> PnL tracked -> Circuit breaker monitors losses
```

The full pipeline runs automatically every 2 minutes. Paper trading ticks run every 60 seconds during NYSE market hours.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ (async throughout) |
| API | FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Vector DB | Qdrant |
| Sentiment | FinBERT |
| Market Data | Alpaca API / yfinance |
| LLM | Anthropic Claude (via RAG agent) |
| Broker | Paper-only (internal or Alpaca paper) |

---

## Safety by Design

This system is **paper-only** — there is no live trading code. Multiple safety layers ensure this:

- The process hard-exits on startup if `TRADING_MODE` is set to anything other than `paper`
- Every broker method checks a `PAPER_GUARD` flag before placing any order
- The AI agent can never auto-activate a strategy — human approval is always required
- A daily loss circuit breaker (persisted in the database, not memory) halts all trading if losses exceed 2%

---

## Project Structure

```
core/           All business logic (independently importable)
  ingestion/    News fetching, dedup, normalization, ticker extraction
  kb/           Embeddings, chunking, vector store, sentiment scoring
  agent/        RAG agent, strategy language, validator, approval gate
  backtesting/  Backtest engine, cost model, metrics
  execution/    Paper broker, signal evaluator, risk management
  strategies/   Strategy definitions and registry
  storage/      Database models and repository layer

apps/           Thin application wrappers (no business logic)
  api/          FastAPI REST endpoints
  mcp_server/   MCP tool server for AI agent access
  scheduler/    Celery worker and periodic jobs

tests/          191 tests across 23 files (all run with mocks)
```

---

## Future Work

The v1 system has solid engineering infrastructure. Planned future phases add quantitative depth:

- **Alpha research framework** — Information Coefficient (IC) computation, factor decay analysis
- **Statistical validation** — Sharpe ratio significance testing, walk-forward validation, bootstrap confidence intervals
- **Portfolio optimization** — Mean-variance, risk parity, Black-Litterman
- **Volatility modeling** — GARCH, EWMA, vol-targeted position sizing
- **Risk analytics** — VaR/CVaR, Monte Carlo drawdown distributions, stress testing
- **Regime detection** — Hidden Markov Models for bull/bear market classification
- **Pairs trading** — Cointegration-based statistical arbitrage

See [DOCUMENTATION.md](DOCUMENTATION.md) for full technical details, setup instructions, and configuration reference.

---

## Disclaimer

This system is for paper trading and educational purposes only. No live trading is implemented or supported. News-based signals have no guaranteed alpha. Past backtest performance does not predict future results.
