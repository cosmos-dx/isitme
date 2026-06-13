// Thin client for the local Web API (BFF on :5050). Implements only the shared
// contract: POST /api/ingest, GET /auth/me, GET /api/extension/usage.
//
// Auth uses the shared Bearer contract: `Authorization: Bearer <google token>`.
// A legacy `X-API-Key` is supported as a fallback when no Google token is set.
import type { EventBatch, IngestAuth, RawEvent } from "../common/types";

const CLIENT = "extension";

export interface IngestResult {
  ok: boolean;
  status: number;
  error?: string;
}

export interface ValidateResult {
  valid: boolean;
  status: number;
  error?: string;
}

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}${path}`;
}

/** Build auth headers, preferring the Google Bearer token over the legacy key. */
function authHeaders(auth: IngestAuth): Record<string, string> | null {
  if (auth.bearer) return { Authorization: `Bearer ${auth.bearer}` };
  if (auth.apiKey) return { "X-API-Key": auth.apiKey };
  return null;
}

export async function ingest(
  baseUrl: string,
  auth: IngestAuth,
  events: RawEvent[],
  clientVersion: string,
): Promise<IngestResult> {
  const headers = authHeaders(auth);
  if (!headers) return { ok: false, status: 0, error: "not signed in" };
  const body: EventBatch = { client: CLIENT, client_version: clientVersion, events };
  try {
    const resp = await fetch(joinUrl(baseUrl, "/api/ingest"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      return { ok: false, status: resp.status, error: await safeText(resp) };
    }
    return { ok: true, status: resp.status };
  } catch (err) {
    return { ok: false, status: 0, error: String(err) };
  }
}

/** Verify a credential by resolving the caller via GET /auth/me (Bearer or key). */
export async function validateAuth(
  baseUrl: string,
  auth: IngestAuth,
): Promise<ValidateResult> {
  const headers = authHeaders(auth);
  if (!headers) return { valid: false, status: 0, error: "not signed in" };
  try {
    const resp = await fetch(joinUrl(baseUrl, "/auth/me"), { method: "GET", headers });
    if (!resp.ok) {
      return { valid: false, status: resp.status, error: await safeText(resp) };
    }
    const data = (await resp.json()) as { authenticated?: boolean };
    return {
      valid: Boolean(data.authenticated),
      status: resp.status,
      error: data.authenticated ? undefined : "token not accepted",
    };
  } catch (err) {
    return { valid: false, status: 0, error: String(err) };
  }
}

export interface UsageResult {
  ok: boolean;
  data?: Record<string, unknown>;
}

export async function fetchUsage(
  baseUrl: string,
  auth: IngestAuth,
): Promise<UsageResult> {
  const headers = authHeaders(auth);
  try {
    const resp = await fetch(joinUrl(baseUrl, "/api/extension/usage"), {
      method: "GET",
      headers: headers ?? {},
    });
    if (!resp.ok) return { ok: false };
    return { ok: true, data: (await resp.json()) as Record<string, unknown> };
  } catch {
    return { ok: false };
  }
}

async function safeText(resp: Response): Promise<string> {
  try {
    return (await resp.text()).slice(0, 300);
  } catch {
    return `HTTP ${resp.status}`;
  }
}
