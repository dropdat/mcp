// Thin HTTP client for the dropdat Go API. Auth = bearer token (Clerk JWT or
// dk_* API key). Routes mirror api/cmd/dropdat/main.go under /api/v1.

export type Source = "chatgpt" | "claude" | "gemini";

export type Role = "user" | "assistant" | "system";

export interface Message {
  role: Role;
  content: string;
  capturedAt: string; // RFC3339
}

export interface Capsule {
  id: string;
  userId: string;
  title: string;
  summary: string;
  source: Source;
  sourceUrl: string;
  messages: Message[];
  tags: string[];
  version: number;
  rootId: string;
  parentId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateCapsuleBody {
  id: string;
  title: string;
  summary: string;
  source: Source;
  sourceUrl: string;
  messages: Message[];
  tags: string[];
}

export interface ListFilters {
  q?: string;
  tag?: string;
  limit?: number;
}

export interface SearchHit {
  id: string;
  title: string;
  summary: string;
  source: Source;
  sourceUrl: string;
  tags: string[];
  updatedAt: string;
  score: number;
  vectorRank?: number;
  textRank?: number;
}

export class DropdatClient {
  private base: string;
  private token: string;

  constructor(base: string, token: string) {
    this.base = base.replace(/\/$/, "");
    this.token = token;
  }

  private async req<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const res = await fetch(`${this.base}/api/v1${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`dropdat ${method} ${path} → ${res.status}: ${text}`);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  list(filters: ListFilters = {}): Promise<Capsule[]> {
    const q = new URLSearchParams();
    if (filters.q) q.set("q", filters.q);
    if (filters.tag) q.set("tag", filters.tag);
    if (filters.limit) q.set("limit", String(filters.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return this.req("GET", `/capsules${suffix}`);
  }

  get(id: string): Promise<Capsule> {
    return this.req("GET", `/capsules/${id}`);
  }

  create(body: CreateCapsuleBody): Promise<Capsule> {
    return this.req("POST", "/capsules", body);
  }

  lineage(id: string): Promise<Capsule[]> {
    return this.req("GET", `/capsules/${id}/lineage`);
  }

  search(body: { query: string; tag?: string; limit?: number }): Promise<SearchHit[]> {
    return this.req("POST", "/capsules/search", body);
  }
}
