// Background service worker: the single policy + networking chokepoint.
// Responsibilities:
//   * Apply paused / capture-toggle / allow-deny / redaction policy to every
//     candidate event before it is queued.
//   * Batch + persist events; flush periodically (alarms), on idle, on size.
//   * Build the navigation link-trail from webNavigation.
//   * Handle UI messages: status, pause, flush, sign-in/out, key validation.
import {
  bumpStats,
  getConfig,
  getRuntime,
  getStats,
  patchConfig,
  patchRuntime,
} from "../common/config";
import { redactEvent } from "../common/redaction";
import { isCapturable } from "../common/sites";
import type {
  CandidateEvent,
  CaptureToggles,
  EventType,
  ExtensionConfig,
  Message,
  RawEvent,
  StatusResponse,
} from "../common/types";
import { nowIso, uuid } from "../common/util";
import { fetchUsage, ingest, validateKey } from "./api";
import { signInWithGoogle } from "./auth";
import { EventQueue } from "./queue";
import { TabTracker } from "./tracking";

const SOURCE = "browser-extension";
const CLIENT_VERSION = chrome.runtime.getManifest().version;
const FLUSH_ALARM = "isitme.flush";

const queue = new EventQueue(1000);
const tracker = new TabTracker();
const sessionId = uuid();
let flushing = false;

// ---- policy -----------------------------------------------------------------

const CATEGORY_OF: Record<EventType, keyof CaptureToggles | null> = {
  visit: "visits",
  click: "clicks",
  dwell: "dwell",
  link: "links",
  search: "searches",
  llm_chat: "llmChat",
  content_create: "pageContent",
  opinion: null,
};

function allowedByToggle(type: EventType, capture: CaptureToggles): boolean {
  const cat = CATEGORY_OF[type];
  if (cat === null) return true;
  return capture[cat];
}

/** Turn a content/nav candidate into a sendable RawEvent, or null if filtered. */
function applyPolicy(
  candidate: CandidateEvent,
  config: ExtensionConfig,
): RawEvent | null {
  if (config.paused) return null;
  if (!allowedByToggle(candidate.type, config.capture)) return null;
  // URL-bearing events must pass allow/deny. Events without a URL (rare) pass.
  if (candidate.url && !isCapturable(candidate.url, config.allowList, config.denyList)) {
    return null;
  }
  // Link edges: the originating page must also be capturable, else strip it.
  if (candidate.type === "link" && candidate.data && typeof candidate.data.from === "string") {
    if (!isCapturable(candidate.data.from, config.allowList, config.denyList)) {
      delete candidate.data.from;
    }
  }

  const base: RawEvent = {
    id: uuid(),
    type: candidate.type,
    timestamp: nowIso(),
    source: SOURCE,
    session_id: sessionId,
    url: candidate.url ?? null,
    title: candidate.title ?? null,
    content: candidate.content ?? null,
    data: candidate.data ?? {},
  };
  return config.redactionEnabled ? (redactEvent(base) as RawEvent) : base;
}

async function intake(candidates: CandidateEvent[]): Promise<void> {
  if (candidates.length === 0) return;
  const config = await getConfig();
  queue.setMaxSize(config.batch.maxQueueSize);
  const accepted: RawEvent[] = [];
  const byType: Record<string, number> = {};
  for (const c of candidates) {
    const ev = applyPolicy(c, config);
    if (!ev) continue;
    accepted.push(ev);
    byType[ev.type] = (byType[ev.type] ?? 0) + 1;
  }
  if (accepted.length === 0) return;
  const queueLen = await queue.enqueue(accepted);
  await bumpStats(byType);
  await patchRuntime({ queueLength: queueLen });
  if (queueLen >= config.batch.maxBatchSize) {
    void flush();
  }
}

// ---- flush ------------------------------------------------------------------

async function flush(): Promise<void> {
  if (flushing) return;
  flushing = true;
  try {
    const config = await getConfig();
    if (!config.apiKey) return;
    // Drain in batches so a big offline backlog ships in chunks.
    for (;;) {
      const batch = await queue.peek(config.batch.maxBatchSize);
      if (batch.length === 0) break;
      const result = await ingest(config.apiBaseUrl, config.apiKey, batch, CLIENT_VERSION);
      if (!result.ok) {
        await patchRuntime({
          lastSyncOk: false,
          lastError: result.error ?? `HTTP ${result.status}`,
        });
        return; // keep events queued; retry on next flush
      }
      const remaining = await queue.drop(batch.length);
      await patchRuntime({
        lastSyncAt: nowIso(),
        lastSyncOk: true,
        lastError: null,
        queueLength: remaining,
      });
    }
  } finally {
    flushing = false;
  }
}

// ---- lifecycle --------------------------------------------------------------

chrome.runtime.onInstalled.addListener(async () => {
  await getConfig(); // materialize defaults
  chrome.alarms.create(FLUSH_ALARM, { periodInMinutes: 0.5 });
  await reinjectOpenTabs();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(FLUSH_ALARM, { periodInMinutes: 0.5 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === FLUSH_ALARM) void flush();
});

chrome.idle.setDetectionInterval(60);
chrome.idle.onStateChanged.addListener((state) => {
  if (state === "idle" || state === "locked") void flush();
});

// Re-inject the content script into already-open tabs after install/update so
// capture starts without requiring a manual reload.
async function reinjectOpenTabs(): Promise<void> {
  try {
    const tabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
    await Promise.all(
      tabs
        .filter((t) => typeof t.id === "number")
        .map((t) =>
          chrome.scripting
            .executeScript({ target: { tabId: t.id as number }, files: ["content.js"] })
            .catch(() => undefined),
        ),
    );
  } catch {
    // best effort
  }
}

// ---- navigation link-trail --------------------------------------------------

function handleNavigation(
  details: chrome.webNavigation.WebNavigationTransitionCallbackDetails,
): void {
  if (details.frameId !== 0) return; // top frame only
  const candidate = tracker.onNavigation(
    details.tabId,
    details.url,
    details.transitionType ?? "link",
    details.transitionQualifiers ?? [],
  );
  if (candidate) void intake([candidate]);
}

chrome.webNavigation.onCommitted.addListener(handleNavigation);
chrome.webNavigation.onHistoryStateUpdated.addListener(handleNavigation);
chrome.tabs.onRemoved.addListener((tabId) => tracker.forget(tabId));

// ---- config change broadcast ------------------------------------------------

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes["isitme.config"]) return;
  void broadcastConfigChange();
});

async function broadcastConfigChange(): Promise<void> {
  const tabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
  for (const t of tabs) {
    if (typeof t.id !== "number") continue;
    chrome.tabs
      .sendMessage(t.id, { kind: "configChanged" } satisfies Message)
      .catch(() => undefined);
  }
}

// ---- messaging --------------------------------------------------------------

chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  void handleMessage(msg).then(sendResponse);
  return true; // async response
});

async function handleMessage(msg: Message): Promise<unknown> {
  switch (msg.kind) {
    case "events":
      await intake(msg.events);
      return { ok: true };

    case "getConfig": {
      const config = await getConfig();
      return {
        paused: config.paused,
        capture: config.capture,
        llmChat: config.capture.llmChat,
        pageContent: config.capture.pageContent,
      };
    }

    case "getStatus":
      return buildStatus();

    case "setPaused": {
      await patchConfig({ paused: msg.paused });
      return { ok: true };
    }

    case "flushNow":
      await flush();
      return buildStatus();

    case "signIn":
      return doSignIn();

    case "signOut": {
      await patchConfig({
        auth: { ...(await getConfig()).auth, profile: null },
      });
      return buildStatus();
    }

    case "validateKey": {
      const config = await getConfig();
      const res = await validateKey(config.apiBaseUrl, config.apiKey);
      await patchRuntime({ apiKeyValid: res.valid, lastError: res.error ?? null });
      return { valid: res.valid, status: res.status, error: res.error };
    }

    default:
      return { ok: false, error: "unknown message" };
  }
}

async function doSignIn(): Promise<unknown> {
  const config = await getConfig();
  try {
    const result = await signInWithGoogle(config);
    const patch: Partial<ExtensionConfig> = {
      auth: { ...config.auth, profile: result.profile },
    };
    if (result.apiKey) patch.apiKey = result.apiKey;
    await patchConfig(patch);
    if (result.apiKey) {
      const res = await validateKey(config.apiBaseUrl, result.apiKey);
      await patchRuntime({ apiKeyValid: res.valid });
    }
    return { ok: true, profile: result.profile, provisioned: Boolean(result.apiKey) };
  } catch (err) {
    return { ok: false, error: String(err instanceof Error ? err.message : err) };
  }
}

async function buildStatus(): Promise<StatusResponse> {
  const [config, stats, runtime] = await Promise.all([
    getConfig(),
    getStats(),
    getRuntime(),
  ]);
  // Opportunistically refresh server-side totals (non-blocking failure).
  void fetchUsage(config.apiBaseUrl, config.apiKey);
  return {
    config: {
      paused: config.paused,
      apiBaseUrl: config.apiBaseUrl,
      hasApiKey: Boolean(config.apiKey),
    },
    profile: config.auth.profile,
    stats,
    runtime,
  };
}
