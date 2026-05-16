// Read a Claude Code session transcript (jsonl) and project it into the
// dropdat capsule message format. Skips meta/hook entries, sub-agent
// (sidechain) activity, and thinking/tool-use blocks — keeps only the
// real user-and-assistant text.

import { readFile, readdir, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

import type { Message } from "./client.js";

interface Line {
  type?: string;
  isMeta?: boolean;
  isSidechain?: boolean;
  timestamp?: string;
  message?: {
    role?: "user" | "assistant" | "system";
    content?: unknown;
  };
}

export interface ParsedTranscript {
  path: string;
  messages: Message[];
  cwd?: string;
  startedAt?: string;
  endedAt?: string;
}

// projectKey mirrors Claude Code's encoding: leading slash + slashes → dashes.
//   /home/yusii/dropdat/backend/mcp  →  -home-yusii-dropdat-backend-mcp
export function projectKey(cwd: string): string {
  return cwd.replace(/\//g, "-");
}

// resolveLatest finds the newest .jsonl under ~/.claude/projects/<key>/.
export async function resolveLatest(cwd: string): Promise<string> {
  const dir = join(homedir(), ".claude", "projects", projectKey(cwd));
  const entries = await readdir(dir);
  const jsonl = entries.filter((e) => e.endsWith(".jsonl"));
  if (jsonl.length === 0) {
    throw new Error(`no .jsonl transcripts found in ${dir}`);
  }
  const stats = await Promise.all(
    jsonl.map(async (name) => {
      const path = join(dir, name);
      const s = await stat(path);
      return { path, mtimeMs: s.mtimeMs };
    }),
  );
  stats.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return stats[0].path;
}

export async function parseTranscript(path: string): Promise<ParsedTranscript> {
  const raw = await readFile(path, "utf8");
  const messages: Message[] = [];
  let cwd: string | undefined;
  let startedAt: string | undefined;
  let endedAt: string | undefined;

  for (const lineStr of raw.split("\n")) {
    if (!lineStr.trim()) continue;
    let line: Line & { cwd?: string };
    try {
      line = JSON.parse(lineStr) as Line & { cwd?: string };
    } catch {
      continue;
    }
    if (line.cwd && !cwd) cwd = line.cwd;

    if (line.type !== "user" && line.type !== "assistant") continue;
    if (line.isMeta) continue;
    if (line.isSidechain) continue;

    const role = line.message?.role;
    if (role !== "user" && role !== "assistant") continue;

    const text = extractText(line.message?.content);
    if (!text.trim()) continue;

    const ts = line.timestamp ?? new Date().toISOString();
    if (!startedAt) startedAt = ts;
    endedAt = ts;

    messages.push({ role, content: text, capturedAt: ts });
  }

  return { path, messages, cwd, startedAt, endedAt };
}

function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const block of content) {
    if (!block || typeof block !== "object") continue;
    const b = block as { type?: string; text?: string; content?: unknown };
    // Skip thinking + tool_use; keep text + tool_result (often holds output the
    // user can see). For tool_result, content may itself be a string or blocks.
    if (b.type === "text" && typeof b.text === "string") {
      parts.push(b.text);
    } else if (b.type === "tool_result") {
      const inner = extractText(b.content);
      if (inner.trim()) parts.push(inner);
    }
  }
  return parts.join("\n");
}
