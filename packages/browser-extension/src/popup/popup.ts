// Popup: live status (signed-in user, events today, queue, last sync) plus
// pause/resume, sync-now and sign-in/out controls.
import type { Message, StatusResponse } from "../common/types";

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing element #${id}`);
  return el;
}

async function ask<T>(msg: Message): Promise<T> {
  return (await chrome.runtime.sendMessage(msg)) as T;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.round(diff / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function render(status: StatusResponse): void {
  const { config, profile, stats, runtime } = status;

  // pause pill + toggle button
  const pill = $("pausePill");
  pill.textContent = config.paused ? "paused" : "active";
  pill.classList.toggle("paused", config.paused);
  ($("toggleBtn") as HTMLButtonElement).textContent = config.paused
    ? "Resume capture"
    : "Pause capture";

  // account
  const avatar = $("avatar") as HTMLImageElement;
  if (profile) {
    $("accountName").textContent = profile.name ?? "Signed in";
    $("accountEmail").textContent = profile.email ?? "";
    ($("authBtn") as HTMLButtonElement).textContent = "Sign out";
    if (profile.picture) {
      avatar.src = profile.picture;
      avatar.hidden = false;
    } else {
      avatar.hidden = true;
    }
  } else {
    $("accountName").textContent = "Not signed in";
    $("accountEmail").textContent = "";
    ($("authBtn") as HTMLButtonElement).textContent = "Sign in";
    avatar.hidden = true;
  }

  // stats
  $("eventsToday").textContent = String(stats.total);
  $("queueLen").textContent = String(runtime.queueLength);

  const breakdown = $("breakdown");
  breakdown.innerHTML = "";
  for (const [type, count] of Object.entries(stats.byCategory).sort(
    (a, b) => (b[1] ?? 0) - (a[1] ?? 0),
  )) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${type} <b>${count}</b>`;
    breakdown.appendChild(chip);
  }

  // meta
  $("lastSync").textContent = runtime.lastSyncAt
    ? `${relativeTime(runtime.lastSyncAt)}${runtime.lastSyncOk ? "" : " (failed)"}`
    : "never";
  const keyState = $("keyState");
  if (!config.hasApiKey) {
    keyState.textContent = "not set";
  } else if (runtime.apiKeyValid === true) {
    keyState.textContent = "valid";
  } else if (runtime.apiKeyValid === false) {
    keyState.textContent = "invalid";
  } else {
    keyState.textContent = "set";
  }

  const errorRow = $("errorRow");
  if (runtime.lastError) {
    errorRow.hidden = false;
    $("errorText").textContent = runtime.lastError;
  } else {
    errorRow.hidden = true;
  }

  $("baseUrl").textContent = config.apiBaseUrl.replace(/^https?:\/\//, "");
}

async function refresh(): Promise<void> {
  render(await ask<StatusResponse>({ kind: "getStatus" }));
}

function wire(): void {
  $("toggleBtn").addEventListener("click", async () => {
    const status = await ask<StatusResponse>({ kind: "getStatus" });
    await ask({ kind: "setPaused", paused: !status.config.paused });
    await refresh();
  });

  $("flushBtn").addEventListener("click", async () => {
    ($("flushBtn") as HTMLButtonElement).disabled = true;
    render(await ask<StatusResponse>({ kind: "flushNow" }));
    ($("flushBtn") as HTMLButtonElement).disabled = false;
  });

  $("authBtn").addEventListener("click", async () => {
    const status = await ask<StatusResponse>({ kind: "getStatus" });
    const btn = $("authBtn") as HTMLButtonElement;
    btn.disabled = true;
    if (status.profile) {
      await ask({ kind: "signOut" });
    } else {
      btn.textContent = "Signing in…";
      const res = await ask<{ ok: boolean; error?: string }>({ kind: "signIn" });
      if (!res.ok && res.error) {
        $("errorRow").hidden = false;
        $("errorText").textContent = res.error;
      }
    }
    btn.disabled = false;
    await refresh();
  });

  $("optionsLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
}

wire();
void refresh();
setInterval(() => void refresh(), 3000);
