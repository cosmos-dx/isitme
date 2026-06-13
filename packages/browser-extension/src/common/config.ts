// Config + lightweight persisted state, stored in chrome.storage.local.
import type {
  DailyStats,
  ExtensionConfig,
  RuntimeState,
} from "./types";

const CONFIG_KEY = "isitme.config";
const STATS_KEY = "isitme.stats";
const RUNTIME_KEY = "isitme.runtime";

/** Default Google OAuth client_id (public, web client from the project .env). */
const DEFAULT_GOOGLE_CLIENT_ID =
  "1047363130881-nim9lmjh7ub7eavadh87bjnh7r5q5ali.apps.googleusercontent.com";

export const DEFAULT_CONFIG: ExtensionConfig = {
  apiBaseUrl: "http://127.0.0.1:5050",
  apiKey: "",
  paused: false,
  capture: {
    visits: true,
    clicks: true,
    dwell: true,
    links: true,
    searches: true,
    llmChat: false,
    pageContent: false,
  },
  allowList: [],
  denyList: [
    // Sensible privacy defaults: never capture banking / auth flows.
    "*.bank",
    "accounts.google.com",
    "login.*",
    "*.onion",
  ],
  redactionEnabled: true,
  batch: {
    maxBatchSize: 25,
    flushIntervalMs: 30_000,
    maxQueueSize: 1000,
  },
  auth: {
    googleClientId: DEFAULT_GOOGLE_CLIENT_ID,
    profile: null,
    token: null,
    autoProvisionKey: false,
    provisionPath: "/api/extension/provision",
  },
};

function mergeConfig(stored: Partial<ExtensionConfig> | undefined): ExtensionConfig {
  if (!stored) return structuredClone(DEFAULT_CONFIG);
  return {
    ...DEFAULT_CONFIG,
    ...stored,
    capture: { ...DEFAULT_CONFIG.capture, ...(stored.capture ?? {}) },
    batch: { ...DEFAULT_CONFIG.batch, ...(stored.batch ?? {}) },
    auth: { ...DEFAULT_CONFIG.auth, ...(stored.auth ?? {}) },
    allowList: stored.allowList ?? DEFAULT_CONFIG.allowList,
    denyList: stored.denyList ?? DEFAULT_CONFIG.denyList,
  };
}

export async function getConfig(): Promise<ExtensionConfig> {
  const raw = await chrome.storage.local.get(CONFIG_KEY);
  return mergeConfig(raw[CONFIG_KEY] as Partial<ExtensionConfig> | undefined);
}

export async function setConfig(config: ExtensionConfig): Promise<void> {
  await chrome.storage.local.set({ [CONFIG_KEY]: config });
}

export async function patchConfig(
  patch: Partial<ExtensionConfig>,
): Promise<ExtensionConfig> {
  const current = await getConfig();
  const next = mergeConfig({ ...current, ...patch });
  await setConfig(next);
  return next;
}

// ---- daily stats ------------------------------------------------------------

function todayKey(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function emptyStats(): DailyStats {
  return { date: todayKey(), total: 0, byCategory: {} };
}

export async function getStats(): Promise<DailyStats> {
  const raw = await chrome.storage.local.get(STATS_KEY);
  const stats = raw[STATS_KEY] as DailyStats | undefined;
  if (!stats || stats.date !== todayKey()) return emptyStats();
  return stats;
}

export async function bumpStats(
  byType: Record<string, number>,
): Promise<DailyStats> {
  const stats = await getStats();
  for (const [type, n] of Object.entries(byType)) {
    const key = type as keyof DailyStats["byCategory"];
    stats.byCategory[key] = (stats.byCategory[key] ?? 0) + n;
    stats.total += n;
  }
  await chrome.storage.local.set({ [STATS_KEY]: stats });
  return stats;
}

// ---- runtime state ----------------------------------------------------------

export function emptyRuntime(): RuntimeState {
  return {
    lastSyncAt: null,
    lastSyncOk: false,
    lastError: null,
    queueLength: 0,
    apiKeyValid: null,
  };
}

export async function getRuntime(): Promise<RuntimeState> {
  const raw = await chrome.storage.local.get(RUNTIME_KEY);
  return (raw[RUNTIME_KEY] as RuntimeState | undefined) ?? emptyRuntime();
}

export async function patchRuntime(
  patch: Partial<RuntimeState>,
): Promise<RuntimeState> {
  const current = await getRuntime();
  const next = { ...current, ...patch };
  await chrome.storage.local.set({ [RUNTIME_KEY]: next });
  return next;
}
