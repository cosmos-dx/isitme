// Content script: observes the page and emits candidate events to the
// background worker, which is the single place that applies redaction,
// allow/deny and capture-toggle policy before anything is stored or sent.
import type { CandidateEvent, ConfigResponse, Message } from "../common/types";
import { clamp } from "../common/util";
import { DwellTracker } from "./dwell";
import { wireLlmCapture } from "./llm";
import { detectEngineQuery, wireOnPageSearch } from "./search";

const DEFAULT_CONFIG: ConfigResponse = {
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
  llmChat: false,
  pageContent: false,
};

let config: ConfigResponse = DEFAULT_CONFIG;

// ---- outbound buffer (debounced) -------------------------------------------

let buffer: CandidateEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function send(events: CandidateEvent[]): void {
  if (events.length === 0) return;
  buffer.push(...events);
  if (flushTimer) return;
  flushTimer = setTimeout(flushBuffer, 1500);
}

function flushBuffer(): void {
  flushTimer = null;
  if (buffer.length === 0) return;
  const events = buffer;
  buffer = [];
  chrome.runtime
    .sendMessage({ kind: "events", events } satisfies Message)
    .catch(() => {
      // Service worker asleep or extension reloading; drop silently — the
      // background queue + periodic flush is the durable path for accepted
      // events, and transient page signals aren't worth blocking on.
    });
}

window.addEventListener("pagehide", flushBuffer);

// ---- capture wiring ---------------------------------------------------------

function extractPageText(): string | null {
  const main =
    document.querySelector("main") ??
    document.querySelector("article") ??
    document.body;
  return clamp(main?.innerText ?? null, 4000);
}

function emitVisit(): void {
  if (!config.capture.visits) return;
  const event: CandidateEvent = {
    type: "visit",
    url: location.href,
    title: document.title || null,
    data: { referrer: document.referrer || null },
  };
  if (config.pageContent) event.content = extractPageText();
  send([event]);
}

function wireClicks(): void {
  document.addEventListener(
    "click",
    (e) => {
      if (!config.capture.clicks) return;
      const target = e.target as Element | null;
      const el = target?.closest?.("a,button,[role='button'],[role='link']");
      if (!el) return;
      const anchor = el.closest("a");
      const href = anchor instanceof HTMLAnchorElement ? anchor.href : undefined;
      const text = clamp(el.textContent, 120);
      const data: Record<string, unknown> = {
        tag: el.tagName.toLowerCase(),
        text,
      };
      if (href) data.href = href;
      send([{ type: "click", url: location.href, title: document.title || null, data }]);
    },
    { capture: true },
  );
}

// SPA route changes: content scripts can't observe the page's own
// history.pushState from the isolated world, so poll the URL cheaply and
// re-emit a visit + search detection when it changes.
function wireSpaNavigation(): void {
  let last = location.href;
  setInterval(() => {
    if (location.href === last) return;
    last = location.href;
    emitVisit();
    const q = detectEngineQuery();
    if (q && config.capture.searches) send([q]);
  }, 1000);
}

const dwell = new DwellTracker(send, () => config.capture.dwell && !config.paused);

async function loadConfig(): Promise<void> {
  try {
    const res = (await chrome.runtime.sendMessage({
      kind: "getConfig",
    } satisfies Message)) as ConfigResponse | undefined;
    if (res) config = res;
  } catch {
    // keep defaults
  }
}

chrome.runtime.onMessage.addListener((msg: Message) => {
  if (msg.kind === "configChanged") void loadConfig();
});

function onReady(): void {
  emitVisit();
  const q = detectEngineQuery();
  if (q && config.capture.searches) send([q]);
}

async function main(): Promise<void> {
  await loadConfig();
  wireClicks();
  wireOnPageSearch((events) => {
    if (config.capture.searches) send(events);
  });
  wireLlmCapture(send, () => config.capture.llmChat && !config.paused);
  wireSpaNavigation();
  dwell.start();

  if (document.readyState === "complete" || document.readyState === "interactive") {
    onReady();
  } else {
    window.addEventListener("DOMContentLoaded", onReady, { once: true });
  }
}

void main();
