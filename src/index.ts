#!/usr/bin/env node
// Dropdat MCP server. Exposes capsule recall/save/read tools over stdio so
// MCP-capable clients (Claude Code, Cursor, Cline, Claude Desktop) can read
// from and write to a user's dropdat library.

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import { DropdatClient, type Source } from "./client.js";
import { parseTranscript, resolveLatest } from "./transcript.js";

const API_BASE = process.env.DROPDAT_API_BASE ?? "http://localhost:8080";
const API_KEY = process.env.DROPDAT_API_KEY ?? "";

if (!API_KEY) {
  console.error(
    "DROPDAT_API_KEY not set. Issue one in the dashboard → API Keys, then export it.",
  );
  process.exit(1);
}

const client = new DropdatClient(API_BASE, API_KEY);

const SOURCES = ["chatgpt", "claude", "gemini"] as const;

const RecallInput = z.object({
  query: z.string().min(1).describe("Keyword search across capsule titles, summaries, and message bodies."),
  tag: z.string().optional().describe("Optional tag filter."),
  limit: z.number().int().min(1).max(50).optional().default(10),
});

const ReadInput = z.object({
  id: z.string().uuid().describe("Capsule id (uuid v7)."),
  includeLineage: z.boolean().optional().default(false).describe("Also return prior versions in lineage order."),
});

const ListInput = z.object({
  tag: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional().default(20),
});

const AutocapsuleInput = z.object({
  title: z.string().min(1).describe("Short human title for the capsule."),
  summary: z.string().optional().default("").describe("Optional one-or-two-sentence gist."),
  tags: z.array(z.string()).optional().default([]),
  transcriptPath: z
    .string()
    .optional()
    .describe(
      "Absolute path to the Claude Code session .jsonl. If omitted, the server picks the newest transcript under ~/.claude/projects/<cwd-key>/, where <cwd-key> is the current working directory with slashes replaced by dashes.",
    ),
  cwd: z
    .string()
    .optional()
    .describe(
      "Working directory of the session. Used only when transcriptPath is omitted, to locate the right project folder.",
    ),
  sourceUrl: z.string().optional().default(""),
});

const SaveInput = z.object({
  title: z.string().min(1).describe("Short human title for the capsule."),
  summary: z.string().optional().default("").describe("One- or two-sentence gist; what this conversation was about."),
  source: z.enum(SOURCES).optional().default("claude").describe("Originating AI provider."),
  sourceUrl: z.string().optional().default("").describe("Permalink to the original chat, if any."),
  tags: z.array(z.string()).optional().default([]),
  messages: z
    .array(
      z.object({
        role: z.enum(["user", "assistant", "system"]),
        content: z.string(),
        capturedAt: z.string().optional().describe("RFC3339 timestamp; defaults to now."),
      }),
    )
    .min(1)
    .describe("Conversation turns to persist. Caller is the agent — pass the relevant slice of the current session."),
});

const server = new Server(
  { name: "dropdat-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "dropdat_recall",
      description:
        "Hybrid (vector + keyword) semantic search across the user's dropdat capsule library. Use this whenever the user asks about prior decisions, past sessions, or anything they may have discussed with another AI — even if their phrasing doesn't match exact words from earlier conversations. Returns ranked hits with id, title, summary, tags, and a fused score.",
      inputSchema: zodToJsonSchema(RecallInput),
    },
    {
      name: "dropdat_read",
      description:
        "Fetch one capsule's full contents (all messages) by id. Pair with dropdat_recall to drill into a hit.",
      inputSchema: zodToJsonSchema(ReadInput),
    },
    {
      name: "dropdat_list",
      description: "List recent capsules, optionally filtered by tag. Use to browse, not to search.",
      inputSchema: zodToJsonSchema(ListInput),
    },
    {
      name: "dropdat_capsule",
      description:
        "Save the current conversation (or a relevant slice of it) as a new capsule. Call when the user says 'remember this', 'save this conversation', or at the end of a meaningful session.",
      inputSchema: zodToJsonSchema(SaveInput),
    },
    {
      name: "dropdat_autocapsule",
      description:
        "Save the FULL verbatim Claude Code session as a capsule by reading its on-disk .jsonl transcript directly. Use this instead of dropdat_capsule when the user wants the entire conversation, not just a model-reconstructed slice. The server reads the file itself — no need to pass messages.",
      inputSchema: zodToJsonSchema(AutocapsuleInput),
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  try {
    switch (name) {
      case "dropdat_recall": {
        const p = RecallInput.parse(args);
        const hits = await client.search({ query: p.query, tag: p.tag, limit: p.limit });
        return text(JSON.stringify(hits, null, 2));
      }
      case "dropdat_read": {
        const p = ReadInput.parse(args);
        const capsule = await client.get(p.id);
        const out: Record<string, unknown> = { capsule };
        if (p.includeLineage) out.lineage = await client.lineage(p.id);
        return text(JSON.stringify(out, null, 2));
      }
      case "dropdat_list": {
        const p = ListInput.parse(args);
        const results = await client.list({ tag: p.tag, limit: p.limit });
        return text(
          JSON.stringify(
            results.map((c) => ({ id: c.id, title: c.title, tags: c.tags, updatedAt: c.updatedAt })),
            null,
            2,
          ),
        );
      }
      case "dropdat_autocapsule": {
        const p = AutocapsuleInput.parse(args);
        const path = p.transcriptPath ?? (await resolveLatest(p.cwd ?? process.cwd()));
        const parsed = await parseTranscript(path);
        if (parsed.messages.length === 0) {
          return errorText(`transcript at ${path} produced no messages`);
        }
        const created = await client.create({
          id: uuidv7(),
          title: p.title,
          summary: p.summary,
          source: "claude" as Source,
          sourceUrl: p.sourceUrl || path,
          tags: p.tags,
          messages: parsed.messages,
        });
        return text(
          JSON.stringify(
            {
              id: created.id,
              title: created.title,
              version: created.version,
              transcriptPath: path,
              messageCount: parsed.messages.length,
              startedAt: parsed.startedAt,
              endedAt: parsed.endedAt,
            },
            null,
            2,
          ),
        );
      }
      case "dropdat_capsule": {
        const p = SaveInput.parse(args);
        const now = new Date().toISOString();
        const created = await client.create({
          id: uuidv7(),
          title: p.title,
          summary: p.summary,
          source: p.source as Source,
          sourceUrl: p.sourceUrl,
          tags: p.tags,
          messages: p.messages.map((m) => ({
            role: m.role,
            content: m.content,
            capturedAt: m.capturedAt ?? now,
          })),
        });
        return text(
          JSON.stringify(
            { id: created.id, title: created.title, version: created.version },
            null,
            2,
          ),
        );
      }
      default:
        return errorText(`unknown tool: ${name}`);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return errorText(msg);
  }
});

function text(content: string) {
  return { content: [{ type: "text" as const, text: content }] };
}

function errorText(msg: string) {
  return { content: [{ type: "text" as const, text: msg }], isError: true };
}

// Minimal zod → JSON Schema. Covers the shapes used above; not general.
function zodToJsonSchema(schema: z.ZodTypeAny): Record<string, unknown> {
  const def = schema._def;
  if (schema instanceof z.ZodObject) {
    const shape = schema.shape as Record<string, z.ZodTypeAny>;
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    for (const [k, v] of Object.entries(shape)) {
      properties[k] = zodToJsonSchema(v);
      if (!(v instanceof z.ZodOptional) && !(v instanceof z.ZodDefault)) {
        required.push(k);
      }
    }
    return { type: "object", properties, ...(required.length ? { required } : {}) };
  }
  if (schema instanceof z.ZodOptional || schema instanceof z.ZodDefault) {
    return zodToJsonSchema(schema._def.innerType);
  }
  if (schema instanceof z.ZodArray) {
    return { type: "array", items: zodToJsonSchema(schema._def.type) };
  }
  if (schema instanceof z.ZodEnum) {
    return { type: "string", enum: schema._def.values };
  }
  if (schema instanceof z.ZodString) {
    const out: Record<string, unknown> = { type: "string" };
    if (def.description) out.description = def.description;
    return out;
  }
  if (schema instanceof z.ZodNumber) return { type: "number" };
  if (schema instanceof z.ZodBoolean) return { type: "boolean" };
  return {};
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`dropdat-mcp ready — base=${API_BASE}`);
}

main().catch((err) => {
  console.error("dropdat-mcp fatal:", err);
  process.exit(1);
});
