"""Strategy proposal and validation MCP tools."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.mcp_server.schemas import (
    ProposeStrategyInput,
    ProposeStrategyOutput,
    SubmitStrategyInput,
    SubmitStrategyOutput,
    ValidateStrategyInput,
    ValidateStrategyOutput,
)
from core.agent.approval import submit_for_approval
from core.agent.rag_agent import AnthropicLLMClient, propose_strategy_update
from core.agent.validator import validate_strategy
from core.kb.embeddings import EmbeddingProvider, get_embedding_provider
from core.kb.vectorstore import VectorStoreBase, get_vectorstore
from core.storage.repos import strategy_repo


async def propose_strategy(
    session: AsyncSession,
    params: ProposeStrategyInput,
    store: VectorStoreBase | None = None,
    embedder: EmbeddingProvider | None = None,
) -> ProposeStrategyOutput:
    """Query KB and LLM to propose a strategy update."""
    # Get current active definition if it exists
    active = await strategy_repo.get_active_by_name(session, params.strategy_name)
    current_definition = active.definition if active else None

    llm_client = AnthropicLLMClient()
    if store is None:
        store = get_vectorstore()
    if embedder is None:
        embedder = get_embedding_provider()

    proposal = await propose_strategy_update(
        strategy_name=params.strategy_name,
        recent_minutes=params.recent_minutes,
        llm_client=llm_client,
        store=store,
        embedder=embedder,
        current_definition=current_definition,
    )

    return ProposeStrategyOutput(proposal=proposal.model_dump())


async def validate_strategy_tool(
    params: ValidateStrategyInput,
) -> ValidateStrategyOutput:
    """Validate a strategy definition against business rules."""
    result = validate_strategy(params.definition_json)
    return ValidateStrategyOutput(valid=result.valid, errors=result.errors)


async def submit_strategy(
    session: AsyncSession, params: SubmitStrategyInput
) -> SubmitStrategyOutput:
    """Submit a strategy for approval (status=pending_approval)."""
    version = await submit_for_approval(
        session=session,
        strategy_name=params.strategy_name,
        definition=params.definition_json,
        reason=params.reason,
        backtest_metrics=params.backtest_metrics,
    )
    await session.commit()

    return SubmitStrategyOutput(
        strategy_version_id=str(version.id),
        status=version.status,
    )
