"""Run an offline end-to-end interview demo over a real MCP stdio connection."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    with tempfile.TemporaryDirectory(prefix="dropdat-demo-") as tmp:
        transcript = Path(tmp) / "sample.jsonl"
        transcript.write_text(json.dumps({"type": "user", "message": {
            "role": "user", "content": "Keep the Python demo separate from the TypeScript server."}}), encoding="utf-8")
        env = {**os.environ, "DROPDAT_MODE": "local", "DROPDAT_DEMO_DB": str(Path(tmp) / "demo.sqlite3")}
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name("server.py"))], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert len(tools) == 5
                print("1. Discovered:", ", ".join(t.name for t in tools))

                async def call(name, args):
                    result = await session.call_tool(name, args)
                    if result.isError:
                        raise RuntimeError(result.content)
                    data = result.structuredContent
                    if data is None:
                        blocks = [c.text for c in result.content if c.type == "text"]
                        data = json.loads("\n".join(blocks))
                    # FastMCP wraps non-object return annotations in {"result": ...}.
                    if isinstance(data, dict) and set(data) == {"result"}:
                        return data["result"]
                    return data

                saved = await call("dropdat_capsule", {"title": "Offline-first architecture",
                    "tags": ["interview"], "messages": [
                        {"role": "user", "content": "Why IndexedDB?"},
                        {"role": "assistant", "content": "IndexedDB preserves captured conversations when the network is down."}]})
                print("2. Saved capsule:", saved["id"])
                hits = await call("dropdat_recall", {"query": "IndexedDB", "tag": "interview"})
                assert hits and hits[0]["id"] == saved["id"]
                print("3. Recall found:", hits[0]["title"], "(local keyword demo)")
                full = await call("dropdat_read", {"id": hits[0]["id"], "includeLineage": True})
                assert len(full["capsule"]["messages"]) == 2 and len(full["lineage"]) == 1
                print("4. Read context:", full["capsule"]["messages"][1]["content"])
                auto = await call("dropdat_autocapsule", {"title": "Transcript demo", "transcriptPath": str(transcript)})
                assert auto["messageCount"] == 1
                print("5. Imported transcript:", auto["messageCount"], "message")
                listed = await call("dropdat_list", {})
                assert len(listed) == 2
                print("6. Listed", len(listed), "capsules")
                error = await session.call_tool("dropdat_read", {"id": "not-a-uuid"})
                assert error.isError
                print("7. Invalid input correctly returned MCP isError")
                print("PASS: all five tools exercised over stdio; no remote writes or model key required.")


if __name__ == "__main__":
    asyncio.run(main())
