// Thin client for the local Web API (BFF on :5050). Implements only the shared
// contract: POST /api/ingest, GET /api/keys/validate, GET /api/extension/usage.
import type { EventBatch, RawEvent } from "../common/types";

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

export async function ingest(
  baseUrl: string,
  apiKey: string,
  events: RawEvent[],
  clientVersion: string,
): Promise<IngestResult> {
  if (!apiKey) return { ok: false, status: 0, error: "no api key configured" };
  const body: EventBatch = { client: CLIENT, client_version: clientVersion, events };
  try {
    const resp = await fetch(joinUrl(baseUrl, "/api/ingest"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
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

export async function validateKey(
  baseUrl: string,
  apiKey: string,
): Promise<ValidateResult> {
  if (!apiKey) return { valid: false, status: 0, error: "no api key" };
  try {
    const resp = await fetch(joinUrl(baseUrl, "/api/keys/validate"), {
      method: "GET",
      headers: { "X-API-Key": apiKey },
    });
    return { valid: resp.ok, status: resp.status, error: resp.ok ? undefined : await safeText(resp) };
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
  apiKey: string,
): Promise<UsageResult> {
  try {
    const resp = await fetch(joinUrl(baseUrl, "/api/extension/usage"), {
      method: "GET",
      headers: apiKey ? { "X-API-Key": apiKey } : {},
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
