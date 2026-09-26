"""Local SQLite demo or the existing Go API. No LLM is needed here."""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx


def now():
    return datetime.now(timezone.utc).isoformat()


class LocalBackend:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS capsules (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def create(self, body):
        c = {**body, "userId": "local-demo", "version": 1,
             "rootId": body["id"], "parentId": None, "createdAt": now(), "updatedAt": now()}
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO capsules VALUES (?, ?)", (c["id"], json.dumps(c)))
        return c

    def get(self, id):
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT body FROM capsules WHERE id = ?", (id,)).fetchone()
        if not row:
            raise ValueError("Capsule not found")
        return json.loads(row[0])

    def list(self, tag=None, limit=20):
        with sqlite3.connect(self.path) as db:
            rows = [json.loads(row[0]) for row in db.execute("SELECT body FROM capsules")]
        return sorted((c for c in rows if not tag or tag in c["tags"]),
                      key=lambda c: c["updatedAt"], reverse=True)[:limit]

    def lineage(self, id):
        return [self.get(id)]  # Local demo stores only initial versions.

    def search(self, query, tag=None, limit=10):
        terms = set(re.findall(r"\w+", query.lower()))
        hits = []
        for c in self.list(tag, 1000000):
            tokens = set(re.findall(r"\w+", " ".join([
                c["title"], c["summary"], *c["tags"],
                *(m["content"] for m in c["messages"])]).lower()))
            score = len(terms & tokens) / max(len(terms), 1)
            if score:
                hits.append({**{k: c[k] for k in
                    ("id", "title", "summary", "source", "sourceUrl", "tags", "updatedAt")},
                    "score": score, "searchMode": "local-keyword-demo"})
        return sorted(hits, key=lambda h: h["score"], reverse=True)[:limit]


class LiveBackend:
    def __init__(self, base, token):
        if not token:
            raise ValueError("Live mode requires DROPDAT_API_KEY")
        self.base, self.token = base.rstrip("/"), token

    def request(self, method, path, **kwargs):
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(method, self.base + "/api/v1" + path,
                    headers={"Authorization": "Bearer " + self.token,
                             "X-Dropdat-Client": "mcp"}, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            # Don't echo server bodies, request headers, or secrets into tool results.
            raise ValueError(f"Dropdat API returned HTTP {exc.response.status_code}") from None
        except httpx.RequestError:
            raise ValueError("Dropdat API network request failed") from None

    def create(self, body):
        return self.request("POST", "/capsules", json=body)

    def get(self, id):
        return self.request("GET", f"/capsules/{id}")

    def list(self, tag=None, limit=20):
        return self.request("GET", "/capsules", params={"limit": limit, **({"tag": tag} if tag else {})})

    def lineage(self, id):
        return self.request("GET", f"/capsules/{id}/lineage")

    def search(self, query, tag=None, limit=10):
        return self.request("POST", "/capsules/search", json={"query": query, "limit": limit,
                            **({"tag": tag} if tag else {})})


def configured_backend():
    mode = os.getenv("DROPDAT_MODE", "local")
    if mode == "live":
        return LiveBackend(os.getenv("DROPDAT_API_BASE", "https://dropdat.app"),
                           os.getenv("DROPDAT_API_KEY", ""))
    if mode != "local":
        raise ValueError("DROPDAT_MODE must be local or live")
    return LocalBackend(os.getenv("DROPDAT_DEMO_DB", str(Path(__file__).with_name("demo.sqlite3"))))
