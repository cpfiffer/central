"""
MCP Server for ATProtocol Cognition

Exposes comind cognition as MCP resources and tools.
This is a prototype for issue #36.

Usage:
    # Run the server (stdio transport)
    uv run python -m tools.mcp_server
    
    # In an MCP client, connect to this server

Resources exposed:
    - cognition://thoughts - Recent thoughts
    - cognition://concepts - Semantic concepts
    
Tools exposed:
    - write_thought(content) - Record a thought
    - search_cognition(query) - Search cognition records
"""

import asyncio
import os
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent

load_dotenv()

# Import our cognition tools
from tools.cognition import (
    list_thoughts,
    list_concepts,
    write_thought,
    write_concept,
)

# Create the MCP server
app = Server("comind-cognition")


@app.list_resources()
async def list_resources():
    """List available cognition resources."""
    return [
        Resource(
            uri="cognition://thoughts",
            name="Recent Thoughts",
            description="Stream of working memory thoughts from central.comind.network",
            mimeType="text/plain"
        ),
        Resource(
            uri="cognition://concepts",
            name="Semantic Concepts",
            description="Key-value semantic knowledge store",
            mimeType="text/plain"
        ),
    ]


@app.read_resource()
async def read_resource(uri: str):
    """Read a cognition resource."""
    if uri == "cognition://thoughts":
        thoughts = await list_thoughts(limit=10)
        content = "\n\n---\n\n".join([
            f"[{t.get('createdAt', 'unknown')}]\n{t.get('content', '')}"
            for t in thoughts
        ])
        return content
    
    elif uri == "cognition://concepts":
        concepts = await list_concepts(limit=20)
        content = "\n\n".join([
            f"## {c.get('slug', 'unknown')}\n{c.get('understanding', '')}"
            for c in concepts
        ])
        return content
    
    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools():
    """List available cognition tools."""
    return [
        Tool(
            name="write_thought",
            description="Record a thought to ATProtocol cognition",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The thought content to record"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="write_concept",
            description="Store a semantic concept",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Concept identifier (kebab-case)"
                    },
                    "understanding": {
                        "type": "string",
                        "description": "What this concept means"
                    }
                },
                "required": ["slug", "understanding"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """Execute a cognition tool."""
    if name == "write_thought":
        uri = await write_thought(arguments["content"])
        return [TextContent(type="text", text=f"Recorded thought: {uri}")]
    
    elif name == "write_concept":
        uri = await write_concept(
            arguments["slug"],
            arguments["understanding"]
        )
        return [TextContent(type="text", text=f"Stored concept: {uri}")]
    
    raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
