# @dropdat/mcp

MCP server for [dropdat](../README.md). Lets any MCP-capable AI client
(Claude Code, Cursor, Cline, Claude Desktop) recall, read, and save
capsules in the user's dropdat library.

## Tools

| Tool | Purpose |
|------|---------|
| `dropdat_recall`  | Keyword-search capsules (titles, summaries, message bodies). |
| `dropdat_read`    | Fetch one capsule's full contents by id (optional lineage). |
| `dropdat_list`    | Browse recent capsules, optional tag filter. |
| `dropdat_capsule` | Save the current conversation slice as a new capsule (model picks the messages). |
| `dropdat_autocapsule` | Save the **full verbatim** Claude Code session by reading the on-disk `.jsonl` transcript. |

`dropdat_recall` calls the hybrid `/capsules/search` endpoint
(vector + BM25 fused via RRF). Set `OPENAI_API_KEY` on the API for
full semantic recall; without it the endpoint degrades to BM25.

## Install

```bash
cd mcp
npm install
npm run build
```

## Configure

Issue an API key in the dashboard → **API Keys** (token shown once,
shape `dk_live_…`). Export it:

```bash
export DROPDAT_API_KEY=dk_live_xxx
# Optional — defaults to https://dropdat.app, the hosted API.
# Set this only if you're running the API locally or self-hosted.
# export DROPDAT_API_BASE=http://localhost:8080
```

If you're self-hosting the API and have `DEV_AUTH_BYPASS=1` enabled,
the API ignores tokens entirely and assumes `DEV_USER_ID`. Use a real
key against any normal deployment.

## Wire into a client

### Claude Code

Add to `~/.claude/mcp.json` (or project `.mcp.json`):

```json
{
  "mcpServers": {
    "dropdat": {
      "command": "node",
      "args": ["/absolute/path/to/backend/mcp/dist/index.js"],
      "env": {
        "DROPDAT_API_KEY": "dk_live_xxx"
      }
    }
  }
}
```

### Cursor / Cline / Claude Desktop

Same shape — point `command`/`args` at `dist/index.js` and pass the
two env vars. Transport is stdio.

## Develop

```bash
npm run dev   # tsx, no rebuild
npm run build # emit dist/
```

The compiled `dist/index.js` starts with a `#!/usr/bin/env node`
shebang and is `chmod +x`'d on build — once published, clients can
`npx -y @dropdat/mcp` instead of pinning a path.

## Endpoint surface used

All against the Go API under `/api/v1`:

- `GET    /capsules?q=&tag=&limit=`
- `POST   /capsules/search`
- `GET    /capsules/{id}`
- `GET    /capsules/{id}/lineage`
- `POST   /capsules`

Bearer auth — accepts either a Clerk session JWT or a `dk_*` API key.
The MCP server uses the API-key path so it survives long-running
agent sessions without a refresh dance.
