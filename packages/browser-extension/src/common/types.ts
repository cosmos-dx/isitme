// Shared types. The event shape mirrors the brain's RawEvent contract
// (packages/brain-core/src/brain_core/models/events.py) — keep them in sync.

export type EventType =
  | "visit"
  | "click"
  | "dwell"
  | "link"
  | "search"
  | "llm_chat"
  | "content_create"
  | "opinion";

/** One captured signal. Mirrors brain_core RawEvent (shared fields + `data`). */
export interface RawEvent {
  id: string;
  type: EventType;
  /** ISO-8601 UTC timestamp. */
  timestamp: string;
  source: string;
  session_id?: string | null;
  url?: string | null;
  title?: string | null;
  content?: string | null;
  data: Record<string, unknown>;
}

/** POST /api/ingest body. */
export interface EventBatch {
  client: string;
  client_version: string;
  events: RawEvent[];
}

export type CaptureCategory =
  | "visits"
  | "clicks"
  | "dwell"
  | "links"
  | "searches"
  | "llmChat"
  | "pageContent";

export interface CaptureToggles {
  visits: boolean;
  clicks: boolean;
  dwell: boolean;
  links: boolean;
  searches: boolean;
  /** Capture prompts typed into ChatGPT / Claude / Gemini etc. (off by default). */
  llmChat: boolean;
  /** Capture page text/content with visits (off by default — privacy heavy). */
  pageContent: boolean;
}

export interface BatchConfig {
  /** Flush when the queue reaches this many events. */
  maxBatchSize: number;
  /** Periodic flush cadence (ms). */
  flushIntervalMs: number;
  /** Drop the oldest events if the offline queue exceeds this. */
  maxQueueSize: number;
}

export interface OAuthProfile {
  sub: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  signedInAt: string;
}

/** A Google OAuth token used as the ingestion Bearer credential. */
export interface AuthToken {
  /** OIDC id_token (preferred Bearer — verifiable offline by the Web API). */
  idToken: string | null;
  /** OAuth access_token (Bearer fallback; verified via Google by the Web API). */
  accessToken: string | null;
  /** Epoch milliseconds at which the token expires. */
  expiresAt: number;
}

export interface AuthConfig {
  /** Public Google OAuth client_id (NOT the secret). */
  googleClientId: string;
  /** Stored profile after a successful sign-in. */
  profile: OAuthProfile | null;
  /**
   * Cached Google OAuth token. Sent as `Authorization: Bearer <token>` on
   * every `/api/ingest`. Refreshed by re-running the (silent) auth flow when it
   * nears expiry. Null until the user signs in.
   */
  token: AuthToken | null;
  /**
   * Legacy/optional: if the Web API exposes an endpoint that exchanges a Google
   * id_token for an isitme API key, set this path to auto-provision a key on
   * sign-in. Disabled by default — Google OAuth (above) is the primary path.
   */
  autoProvisionKey: boolean;
  provisionPath: string;
}

export interface ExtensionConfig {
  apiBaseUrl: string;
  /** Legacy/optional manual `X-API-Key` fallback. OAuth is the default. */
  apiKey: string;
  /** Master pause switch (popup toggle). */
  paused: boolean;
  capture: CaptureToggles;
  /** If non-empty, ONLY hosts matching these patterns are captured. */
  allowList: string[];
  /** Hosts matching these patterns are never captured (wins over allow). */
  denyList: string[];
  redactionEnabled: boolean;
  batch: BatchConfig;
  auth: AuthConfig;
}

export interface DailyStats {
  date: string; // YYYY-MM-DD (local)
  total: number;
  byCategory: Partial<Record<EventType, number>>;
}

export interface RuntimeState {
  lastSyncAt: string | null;
  lastSyncOk: boolean;
  lastError: string | null;
  queueLength: number;
  /** Whether the last credential check (Bearer token or legacy key) succeeded. */
  apiKeyValid: boolean | null;
}

/** Resolved ingestion credential: a Google Bearer token or a legacy API key. */
export interface IngestAuth {
  bearer?: string | null;
  apiKey?: string | null;
}

// ---- message protocol (content <-> background, ui <-> background) -----------

export type Message =
  | { kind: "events"; events: CandidateEvent[] }
  | { kind: "getConfig" }
  | { kind: "getStatus" }
  | { kind: "setPaused"; paused: boolean }
  | { kind: "flushNow" }
  | { kind: "signIn" }
  | { kind: "signOut" }
  | { kind: "validateKey" }
  | { kind: "configChanged" };

/**
 * Events as emitted by content scripts before policy is applied. The background
 * worker is the single chokepoint that applies redaction, allow/deny lists and
 * capture toggles before anything is queued.
 */
export interface CandidateEvent {
  type: EventType;
  url?: string | null;
  title?: string | null;
  content?: string | null;
  data?: Record<string, unknown>;
}

export interface AuthStatus {
  /** Signed in with Google and holding a (currently valid) token. */
  signedIn: boolean;
  /** A cached token exists but has expired (needs a silent/interactive refresh). */
  tokenExpired: boolean;
  /** Falling back to a manually-pasted legacy API key. */
  usingLegacyKey: boolean;
}

export interface StatusResponse {
  config: Pick<ExtensionConfig, "paused" | "apiBaseUrl"> & {
    hasApiKey: boolean;
  };
  profile: OAuthProfile | null;
  auth: AuthStatus;
  stats: DailyStats;
  runtime: RuntimeState;
}

export interface ConfigResponse {
  paused: boolean;
  capture: CaptureToggles;
  llmChat: boolean;
  pageContent: boolean;
}
