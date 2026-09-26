# Dropdat Python + LangGraph demo

An additive interview demo next to the existing TypeScript MCP server. The existing server is unchanged.

## What each layer does

```text
MCP host (Claude Code / Cursor / Inspector)
  -> Python MCP SDK: stdio, tool discovery, argument schema, tool errors
  -> LangGraph: START -> validate -> selected tool node -> END
  -> Local SQLite demo OR existing Go API
  -> MCP tool result -> host
```

MCP is the protocol. LangGraph is the workflow engine; it does not replace MCP.
The host chooses a tool. This graph is deterministic and does not call an LLM.
LangGraph is useful here to demonstrate explicit state, routing, and observable steps;
the original thin adapter does not require an orchestration framework.

## Quick start (PowerShell, Python 3.11+)

```powershell
cd Y:\projects\dropdat\mcp\python-demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe demo.py
```

`demo.py` launches a real MCP subprocess, discovers all five tools, saves a capsule,
recalls it, reads its messages and lineage, imports a synthetic transcript, lists
the library, and verifies an invalid request returns `isError`. It forces local
mode, uses a temporary database and synthetic data, and makes no remote writes.
Graph node names are logged to stderr; protocol stdout remains clean.

For direct server use: `.\.venv\Scripts\python.exe server.py`. A stdio server waits
for an MCP client; it is not an interactive terminal chatbot.

## Connect an MCP host

Add an entry to the host's MCP configuration (update paths if moved):

```json
{
  "mcpServers": {
    "dropdat-python-demo": {
      "command": "Y:\\projects\\dropdat\\mcp\\python-demo\\.venv\\Scripts\\python.exe",
      "args": ["Y:\\projects\\dropdat\\mcp\\python-demo\\server.py"],
      "env": {"DROPDAT_MODE": "local"}
    }
  }
}
```

In this configuration capsules persist in `demo.sqlite3` beside the server.
`DROPDAT_DEMO_DB` overrides that path. Use synthetic conversation data for demos.

Example host requests:

1. "Save this decision using dropdat_capsule: we chose IndexedDB for offline capture."
2. "Use dropdat_recall to find our IndexedDB decision."
3. "Use dropdat_read to show the complete saved conversation."

## Live Go API mode

Set `DROPDAT_MODE=live`, `DROPDAT_API_KEY` to your existing key, and optionally
`DROPDAT_API_BASE` (defaults to `https://dropdat.app`) in the host environment.
Live mode actually reads/writes your Dropdat account. Do not put secrets in Git.
This demo sends `X-Dropdat-Client: mcp`, so the API's current MCP entitlement check applies.
No live account operations were used during implementation validation.

## Tools and files

| Tool | Behavior |
|---|---|
| `dropdat_recall` | Search; optional tag and limit |
| `dropdat_read` | Full capsule; optional lineage |
| `dropdat_list` | Recent metadata; optional tag |
| `dropdat_capsule` | Save caller-supplied messages with UUID v7 |
| `dropdat_autocapsule` | Parse an explicitly selected JSONL transcript and save text |

`server.py`: MCP tool declarations. `workflow.py`: LangGraph routing + validation.
`backend.py`: local/live adapters. `transcript.py`: filtering. `demo.py`: stdio walkthrough.

## Intentional demo limits

- Local search is simple token overlap, not embeddings, RRF, or BM25. Live search
  delegates to the existing Go API's hybrid retrieval.
- Local mode has one demo user, initial versions only, and no production authentication,
  team access, attachment handling, or billing.
- Autocapsule requires an explicit `.jsonl` path; it does not guess Claude's OS-specific
  project folder. It filters malformed, meta and sidechain records, keeps visible text
  and nested tool-result text, and excludes thinking/tool-use blocks. It is not a raw backup.
- In live mode, autocapsule uploads the parsed content of the selected file.
- No model-generated answer or autonomous tool-selection loop is included. An MCP host
  provides that layer. LangChain could be used on that client side later.
- MCP SDK is deliberately constrained to v1 for the established `FastMCP` / `ClientSession`
  API and compatibility with the existing stdio workflow. MCP v2 has different APIs.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe demo.py
```

Tests cover graph routing and validation, persistence/tag isolation, transcript filtering,
and HTTP headers/payloads/error redaction using a mock transport.

References: https://github.com/modelcontextprotocol/python-sdk and
https://docs.langchain.com/oss/python/langgraph/graph-api
