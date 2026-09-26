"""MCP v1-compatible stdio transport. All logging goes to stderr."""
import logging
import sys

from mcp.server.fastmcp import FastMCP

from backend import configured_backend
from workflow import Message, build_graph, run

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s: %(message)s")
mcp = FastMCP("dropdat-python-langgraph-demo")
graph = build_graph(configured_backend())


@mcp.tool()
def dropdat_recall(query: str, tag: str | None = None, limit: int = 10) -> list[dict]:
    """Find saved context. Local mode uses keyword matching; live mode uses Go hybrid search."""
    return run(graph, "recall", locals())


@mcp.tool()
def dropdat_read(id: str, includeLineage: bool = False) -> dict:
    """Read full capsule messages and optionally its lineage."""
    return run(graph, "read", locals())


@mcp.tool()
def dropdat_list(tag: str | None = None, limit: int = 20) -> list[dict]:
    """Browse recent capsule metadata, optionally filtered by tag."""
    return run(graph, "list", locals())


@mcp.tool()
def dropdat_capsule(title: str, messages: list[Message], summary: str = "",
                    source: str = "claude", sourceUrl: str = "", tags: list[str] | None = None) -> dict:
    """Save the supplied conversation slice. This tool writes data."""
    args = {**locals(), "messages": [m.model_dump() for m in messages], "tags": tags or []}
    return run(graph, "capsule", args)


@mcp.tool()
def dropdat_autocapsule(title: str, transcriptPath: str, summary: str = "",
                        sourceUrl: str = "", tags: list[str] | None = None) -> dict:
    """Read an explicitly selected local JSONL transcript and save its filtered text.

    Reads a local file and writes a capsule. In live mode this uploads the parsed text.
    """
    return run(graph, "autocapsule", {**locals(), "tags": tags or []})


if __name__ == "__main__":
    mcp.run(transport="stdio")
