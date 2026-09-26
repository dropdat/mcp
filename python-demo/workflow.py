"""Actual LangGraph branching: validate -> selected tool node -> result.

No model call: the MCP host chooses the tool. LangGraph orchestrates execution.
"""
import logging
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from uuid6 import uuid7

from backend import now
from transcript import parse_transcript


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    capturedAt: str | None = None


class Recall(BaseModel):
    query: str = Field(min_length=1)
    tag: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class Read(BaseModel):
    id: UUID
    includeLineage: bool = False


class ListInput(BaseModel):
    tag: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class Save(BaseModel):
    title: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)
    summary: str = ""
    source: Literal["chatgpt", "claude", "gemini"] = "claude"
    sourceUrl: str = ""
    tags: list[str] = Field(default_factory=list)


class Auto(BaseModel):
    title: str = Field(min_length=1)
    transcriptPath: str = Field(min_length=1)
    summary: str = ""
    sourceUrl: str = ""
    tags: list[str] = Field(default_factory=list)


MODELS = {"recall": Recall, "read": Read, "list": ListInput, "capsule": Save, "autocapsule": Auto}


class State(TypedDict, total=False):
    tool: str
    args: dict[str, Any]
    result: Any


def build_graph(backend):
    def validate(state):
        model = MODELS.get(state["tool"])
        if model is None:
            raise ValueError("Unknown tool")
        return {"args": model.model_validate(state["args"]).model_dump(mode="json")}

    def recall(state):
        return {"result": backend.search(**state["args"])}

    def read(state):
        a = state["args"]
        result = {"capsule": backend.get(a["id"])}
        if a["includeLineage"]:
            result["lineage"] = backend.lineage(a["id"])
        return {"result": result}

    def list_capsules(state):
        rows = backend.list(**state["args"])
        return {"result": [{k: c[k] for k in ("id", "title", "tags", "updatedAt")} for c in rows]}

    def save_body(args):
        body = {**args, "id": str(uuid7())}
        body["messages"] = [{**m, "capturedAt": m.get("capturedAt") or now()} for m in body["messages"]]
        return backend.create(body)

    def capsule(state):
        c = save_body(state["args"])
        return {"result": {k: c[k] for k in ("id", "title", "version")}}

    def autocapsule(state):
        a = dict(state["args"])
        parsed = parse_transcript(a.pop("transcriptPath"))
        a.update(source="claude", messages=parsed["messages"])
        a["sourceUrl"] = a["sourceUrl"] or parsed["transcriptPath"]
        c = save_body(a)
        return {"result": {**{k: c[k] for k in ("id", "title", "version")},
                           "messageCount": len(parsed["messages"]),
                           **{k: parsed[k] for k in ("transcriptPath", "startedAt", "endedAt")}}}

    graph = StateGraph(State)
    graph.add_node("validate", validate)
    graph.add_edge(START, "validate")
    nodes = {"recall": recall, "read": read, "list": list_capsules,
             "capsule": capsule, "autocapsule": autocapsule}
    for name, fn in nodes.items():
        graph.add_node(name, fn)
        graph.add_edge(name, END)
    graph.add_conditional_edges("validate", lambda s: s["tool"], {n: n for n in nodes})
    return graph.compile()


def run(graph, tool, args):
    result = None
    for event in graph.stream({"tool": tool, "args": args}, stream_mode="updates"):
        for node, update in event.items():
            logging.getLogger("dropdat.graph").info("node=%s", node)
            if "result" in update:
                result = update["result"]
    return result
