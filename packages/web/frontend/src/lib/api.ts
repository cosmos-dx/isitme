import type {
  ApiKey,
  ApiKeyCreated,
  AskResponse,
  ExtensionUsage,
  GraphData,
  McpConfig,
  MeResponse,
  Profile,
  SearchResponse,
  Stats,
} from "./types";

// The Web API / BFF. Overridable for non-default setups; defaults to :5050.
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:5050";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  loginUrl: () => `${API_BASE}/auth/google/login`,

  me: () => request<MeResponse>("/auth/me"),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  listKeys: () => request<ApiKey[]>("/api/keys"),
  createKey: (name: string) =>
    request<ApiKeyCreated>("/api/keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeKey: (id: string) =>
    request<{ ok: boolean }>(`/api/keys/${id}`, { method: "DELETE" }),

  mcpConfig: (opts?: { mint?: boolean; name?: string; key?: string }) => {
    const params = new URLSearchParams();
    if (opts?.mint) params.set("mint", "true");
    if (opts?.name) params.set("name", opts.name);
    if (opts?.key) params.set("key", opts.key);
    const qs = params.toString();
    return request<McpConfig>(`/api/mcp-config${qs ? `?${qs}` : ""}`);
  },

  graph: () => request<GraphData>("/api/graph"),
  stats: () => request<Stats>("/api/stats"),
  profile: () => request<Profile>("/api/profile"),
  ask: (question: string, k = 6) =>
    request<AskResponse>("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question, k }),
    }),
  extensionUsage: () => request<ExtensionUsage>("/api/extension/usage"),
  search: (query: string, k = 10) =>
    request<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, k }),
    }),
};
