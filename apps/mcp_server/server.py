"""MCP stdio server entry point.

Exposes the news ingestion, embedding, sentiment, and query tools
as MCP tools via stdio transport.
"""

from __future__ import annotations

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from apps.mcp_server.schemas import (
    EmbedInput,
    IngestInput,
    QueryInput,
    SentimentInput,
)
from core.logging import get_logger, setup_logging
from core.storage.db import get_session

logger = get_logger(__name__)

app = Server("quant-news-rag")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ingest_latest_news",
            description="Fetch and ingest latest news articles from RSS feeds",
            inputSchema=IngestInput.model_json_schema(),
        ),
        Tool(
            name="embed_and_upsert_docs",
            description="Chunk, embed, and upsert documents into the vector store",
            inputSchema=EmbedInput.model_json_schema(),
        ),
        Tool(
            name="score_sentiment",
            description="Score sentiment for documents using FinBERT",
            inputSchema=SentimentInput.model_json_schema(),
        ),
        Tool(
            name="query_kb",
            description="Query the knowledge base for relevant documents",
            inputSchema=QueryInput.model_json_schema(),
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import json

    from apps.mcp_server.tools.ingest import ingest_latest_news
    from apps.mcp_server.tools.kb import embed_and_upsert_docs, query_kb
    from apps.mcp_server.tools.sentiment import score_sentiment

    async for session in get_session():
        if name == "ingest_latest_news":
            result = await ingest_latest_news(session, IngestInput(**arguments))
        elif name == "embed_and_upsert_docs":
            result = await embed_and_upsert_docs(session, EmbedInput(**arguments))
        elif name == "score_sentiment":
            result = await score_sentiment(session, SentimentInput(**arguments))
        elif name == "query_kb":
            result = await query_kb(QueryInput(**arguments))
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result.model_dump()))]

    return [TextContent(type="text", text="Failed to get database session")]


async def main():
    setup_logging()
    logger.info("Starting MCP server...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
