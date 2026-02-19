"""RAG agent for strategy proposals.

Uses an LLM to analyze retrieved documents and propose strategy updates.
The LLM is a tool, not the decision maker — all proposals go through
validation and approval gates before activation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, runtime_checkable

from core.agent.prompts import (
    DOCUMENT_TEMPLATE_V1,
    SYSTEM_PROMPT_V1,
    USER_PROMPT_V1,
)
from core.agent.strategy_language import StrategyProposal
from core.config import get_settings
from core.kb.embeddings import EmbeddingProvider
from core.kb.retrieval import query_knowledge_base
from core.kb.vectorstore import VectorStoreBase
from core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completion clients."""

    async def complete(self, system: str, user: str) -> str:
        """Send a system + user prompt and return the LLM's text response."""
        ...


class AnthropicLLMClient:
    """Wraps anthropic.AsyncAnthropic for LLM calls."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import anthropic

        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.ANTHROPIC_API_KEY,
        )
        self._model = model or settings.LLM_MODEL

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


class MockLLMClient:
    """Returns canned JSON for testing. No external calls."""

    def __init__(self, response: dict | None = None) -> None:
        self._response = response

    async def complete(self, system: str, user: str) -> str:
        if self._response is not None:
            return json.dumps(self._response)
        # Default canned response with no changes
        return json.dumps({
            "new_definition": {
                "name": "test_strategy",
                "universe": ["SPY", "QQQ"],
                "signals": [{"type": "news_sentiment", "threshold": 0.5}],
                "rules": {
                    "rebalance_minutes": 60,
                    "max_positions": 5,
                    "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
                    "exits": [{"type": "time_stop", "minutes": 360}],
                },
            },
            "rationale": "No significant changes warranted based on current evidence.",
            "risks": "Minimal risk as no changes proposed.",
            "expected_behavior": "Strategy continues unchanged.",
            "confidence": 0.0,
            "cited_doc_ids": [],
            "changed_fields": [],
        })


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]}...")


def _format_documents(results: list[dict[str, Any]]) -> str:
    """Format KB query results into the document template string."""
    parts = []
    for r in results:
        payload = r.get("payload", {})
        parts.append(DOCUMENT_TEMPLATE_V1.format(
            doc_id=r.get("id", "unknown"),
            title=payload.get("title", "untitled"),
            source=payload.get("source", "unknown"),
            published_at=payload.get("published_at", "unknown"),
            sentiment_score=payload.get("sentiment_score", "N/A"),
            sentiment_label=payload.get("sentiment_label", "N/A"),
            snippet=payload.get("snippet", payload.get("title", "")),
        ))
    return "\n".join(parts)


async def propose_strategy_update(
    strategy_name: str,
    recent_minutes: int,
    *,
    llm_client: LLMClient,
    store: VectorStoreBase,
    embedder: EmbeddingProvider,
    current_definition: dict | None = None,
) -> StrategyProposal:
    """Query KB for recent news, ask LLM to propose a strategy update.

    If fewer than 3 documents are retrieved, returns a proposal with
    confidence=0.0 and no changes.
    """
    settings = get_settings()

    # 1. Query KB
    query = f"Recent financial news for strategy {strategy_name}"
    results = await query_knowledge_base(
        store=store,
        embedder=embedder,
        query=query,
        top_k=20,
    )
    logger.info("KB query returned %d results for strategy %s", len(results), strategy_name)

    # 2. If <3 results, return low-confidence no-change proposal
    if len(results) < 3:
        logger.warning(
            "Fewer than 3 documents retrieved (%d). Returning confidence=0.0.",
            len(results),
        )
        default_def = current_definition or {
            "name": strategy_name,
            "universe": ["SPY"],
            "signals": [{"type": "news_sentiment", "threshold": 0.5}],
            "rules": {
                "rebalance_minutes": 60,
                "max_positions": 5,
                "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
                "exits": [{"type": "time_stop", "minutes": 360}],
            },
        }
        return StrategyProposal(
            new_definition=default_def,
            rationale="Insufficient evidence — fewer than 3 documents retrieved.",
            risks="No changes proposed.",
            expected_behavior="Strategy unchanged.",
            confidence=0.0,
            cited_doc_ids=[],
            changed_fields=[],
        )

    # 3. Format documents
    documents_text = _format_documents(results)
    result_doc_ids = {r.get("id", "") for r in results}

    # 4. Build prompts
    current_def_json = json.dumps(current_definition or {}, indent=2)
    system_prompt = SYSTEM_PROMPT_V1.format(
        approved_universe=settings.STRATEGY_APPROVED_UNIVERSE,
        strategy_name=strategy_name,
        max_diff_fields=settings.STRATEGY_MAX_DIFF_FIELDS,
    )
    user_prompt = USER_PROMPT_V1.format(
        current_definition=current_def_json,
        documents=documents_text,
        strategy_name=strategy_name,
    )

    # 5. Call LLM
    logger.info("Calling LLM for strategy proposal: %s", strategy_name)
    raw_response = await llm_client.complete(system_prompt, user_prompt)

    # 6. Parse JSON
    parsed = _extract_json(raw_response)

    # 7. Post-process: verify cited doc_ids exist in results
    cited = parsed.get("cited_doc_ids", [])
    verified_cited = [doc_id for doc_id in cited if doc_id in result_doc_ids]
    parsed["cited_doc_ids"] = verified_cited

    # 8. Return proposal
    return StrategyProposal.model_validate(parsed)
