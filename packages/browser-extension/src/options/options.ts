// Options page: edit and persist the full ExtensionConfig.
import { DEFAULT_CONFIG, getConfig, setConfig } from "../common/config";
import type { CaptureCategory, ExtensionConfig, Message } from "../common/types";

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el;
}
function input(id: string): HTMLInputElement {
  return $(id) as HTMLInputElement;
}
function textarea(id: string): HTMLTextAreaElement {
  return $(id) as HTMLTextAreaElement;
}

const CAPTURE_KEYS: CaptureCategory[] = [
  "visits",
  "dwell",
  "clicks",
  "links",
  "searches",
  "llmChat",
  "pageContent",
];

function captureCheckbox(key: CaptureCategory): HTMLInputElement {
  const el = document.querySelector<HTMLInputElement>(`input[data-capture="${key}"]`);
  if (!el) throw new Error(`missing capture toggle ${key}`);
  return el;
}

function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function fill(config: ExtensionConfig): void {
  input("apiBaseUrl").value = config.apiBaseUrl;
  input("apiKey").value = config.apiKey;
  for (const key of CAPTURE_KEYS) captureCheckbox(key).checked = config.capture[key];
  input("redactionEnabled").checked = config.redactionEnabled;
  textarea("allowList").value = config.allowList.join("\n");
  textarea("denyList").value = config.denyList.join("\n");
  input("maxBatchSize").value = String(config.batch.maxBatchSize);
  input("flushIntervalSec").value = String(Math.round(config.batch.flushIntervalMs / 1000));
  input("maxQueueSize").value = String(config.batch.maxQueueSize);
  input("googleClientId").value = config.auth.googleClientId;
  input("autoProvisionKey").checked = config.auth.autoProvisionKey;
  input("provisionPath").value = config.auth.provisionPath;
}

function collect(prev: ExtensionConfig): ExtensionConfig {
  return {
    ...prev,
    apiBaseUrl: input("apiBaseUrl").value.trim() || DEFAULT_CONFIG.apiBaseUrl,
    apiKey: input("apiKey").value.trim(),
    redactionEnabled: input("redactionEnabled").checked,
    capture: {
      visits: captureCheckbox("visits").checked,
      dwell: captureCheckbox("dwell").checked,
      clicks: captureCheckbox("clicks").checked,
      links: captureCheckbox("links").checked,
      searches: captureCheckbox("searches").checked,
      llmChat: captureCheckbox("llmChat").checked,
      pageContent: captureCheckbox("pageContent").checked,
    },
    allowList: linesToList(textarea("allowList").value),
    denyList: linesToList(textarea("denyList").value),
    batch: {
      maxBatchSize: clampInt(input("maxBatchSize").value, 1, 500, DEFAULT_CONFIG.batch.maxBatchSize),
      flushIntervalMs:
        clampInt(input("flushIntervalSec").value, 5, 3600, 30) * 1000,
      maxQueueSize: clampInt(
        input("maxQueueSize").value,
        50,
        100000,
        DEFAULT_CONFIG.batch.maxQueueSize,
      ),
    },
    auth: {
      ...prev.auth,
      googleClientId: input("googleClientId").value.trim() || DEFAULT_CONFIG.auth.googleClientId,
      autoProvisionKey: input("autoProvisionKey").checked,
      provisionPath: input("provisionPath").value.trim() || DEFAULT_CONFIG.auth.provisionPath,
    },
  };
}

function clampInt(value: string, min: number, max: number, fallback: number): number {
  const n = Number.parseInt(value, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function flashSaved(): void {
  const note = $("savedNote");
  note.hidden = false;
  setTimeout(() => (note.hidden = true), 1500);
}

async function save(): Promise<void> {
  const current = await getConfig();
  await setConfig(collect(current));
  flashSaved();
}

async function validateKey(): Promise<void> {
  const result = $("keyResult");
  result.textContent = "Validating…";
  result.className = "hint";
  await save(); // ensure background reads the latest base URL + key
  const res = (await chrome.runtime.sendMessage({ kind: "validateKey" } satisfies Message)) as {
    valid: boolean;
    status: number;
    error?: string;
  };
  if (res.valid) {
    result.textContent = "Key is valid.";
    result.className = "hint ok";
  } else {
    result.textContent = `Key is not valid (${res.error ?? `HTTP ${res.status}`}).`;
    result.className = "hint err";
  }
}

function wire(): void {
  $("saveBtn").addEventListener("click", () => void save());
  $("validateKey").addEventListener("click", () => void validateKey());
  $("resetBtn").addEventListener("click", async () => {
    await setConfig(structuredClone(DEFAULT_CONFIG));
    fill(await getConfig());
    flashSaved();
  });
  $("toggleKey").addEventListener("click", () => {
    const el = input("apiKey");
    const showing = el.type === "text";
    el.type = showing ? "password" : "text";
    $("toggleKey").textContent = showing ? "show" : "hide";
  });

  const redirect = chrome.identity.getRedirectURL();
  $("redirectHint").innerHTML =
    `In Google Cloud, add this extension redirect URI as an authorized redirect for the OAuth client: <code>${redirect}</code>. ` +
    `If the OAuth consent screen is in "Testing", add your Google account as a Test user.`;
}

async function init(): Promise<void> {
  wire();
  fill(await getConfig());
}

void init();
