import json
from unittest.mock import patch

import httpx
import pytest

from backend import LiveBackend, LocalBackend
from transcript import parse_transcript
from workflow import build_graph, run


def test_graph_roundtrip_and_isolation(tmp_path):
    graph = build_graph(LocalBackend(tmp_path / "a.sqlite3"))
    saved = run(graph, "capsule", {"title": "Kotlin", "tags": ["gsoc"],
        "messages": [{"role": "user", "content": "widget reviews"}]})
    assert run(graph, "recall", {"query": "widget"})[0]["id"] == saved["id"]
    assert run(graph, "recall", {"query": "widget", "tag": "other"}) == []
    assert run(graph, "recall", {"query": "unmatched"}) == []
    assert run(graph, "read", {"id": saved["id"], "includeLineage": True})["lineage"][0]["version"] == 1
    with pytest.raises(ValueError):
        run(graph, "capsule", {"title": "empty", "messages": []})
    with pytest.raises(ValueError):
        run(graph, "recall", {"query": "x", "limit": 51})
    assert len(run(graph, "list", {})) == 1
    assert LocalBackend(tmp_path / "other.sqlite3").list() == []


def test_transcript_filters(tmp_path):
    path = tmp_path / "sample.jsonl"
    rows = [
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "skip"}},
        {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": "skip"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "text": "private"}, {"type": "text", "text": "visible"}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": [{"type": "text", "text": "tool output"}]}]}}
    ]
    path.write_text("broken\nnull\n" + "\n".join(map(json.dumps, rows)), encoding="utf-8")
    assert [m["content"] for m in parse_transcript(path)["messages"]] == ["visible", "tool output"]
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no messages"):
        parse_transcript(path)


def test_live_http_contract_without_network():
    def handle(request):
        assert str(request.url) == "https://example.test/api/v1/capsules/search"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["X-Dropdat-Client"] == "mcp"
        assert json.loads(request.content) == {"query": "widget", "limit": 3, "tag": "gsoc"}
        return httpx.Response(200, json=[{"id": "example"}])
    client = httpx.Client(transport=httpx.MockTransport(handle))
    with patch("backend.httpx.Client", return_value=client):
        assert LiveBackend("https://example.test/", "test-key").search("widget", "gsoc", 3) == [{"id": "example"}]


def test_live_errors_do_not_echo_secret():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="secret-token")))
    with patch("backend.httpx.Client", return_value=client), pytest.raises(ValueError) as err:
        LiveBackend("https://example.test", "secret-token").get("x")
    assert str(err.value) == "Dropdat API returned HTTP 401"
