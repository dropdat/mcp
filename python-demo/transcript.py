"""Explicit-path JSONL parsing, with the same text filtering as transcript.ts."""
import json
from pathlib import Path
from backend import now


def extract_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_result":
            text = extract_text(block.get("content"))
            if text.strip():
                parts.append(text)
    return "\n".join(parts)


def parse_transcript(path):
    source = Path(path).resolve(strict=True)
    if source.suffix != ".jsonl":
        raise ValueError("Expected a .jsonl transcript")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Demo transcript limit is 20 MiB")
    messages = []
    with source.open(encoding="utf-8-sig") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("type") not in ("user", "assistant"):
                continue
            if row.get("isMeta") or row.get("isSidechain"):
                continue
            message = row.get("message")
            if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                continue
            text = extract_text(message.get("content"))
            if text.strip():
                messages.append({"role": message["role"], "content": text,
                                 "capturedAt": row.get("timestamp") or now()})
    if not messages:
        raise ValueError("Transcript produced no messages")
    return {"messages": messages, "transcriptPath": str(source),
            "startedAt": messages[0]["capturedAt"], "endedAt": messages[-1]["capturedAt"]}
