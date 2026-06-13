// Active-time (dwell) tracking. Counts time the page is BOTH visible AND the
// user is active (interacted within IDLE_MS), not just time the tab is open.
import type { CandidateEvent } from "../common/types";

const IDLE_MS = 30_000; // no interaction for this long => inactive
const TICK_MS = 5_000;
const PERIODIC_EMIT_MS = 60_000; // checkpoint long reading sessions

type Emit = (events: CandidateEvent[]) => void;

export class DwellTracker {
  private activeMs = 0;
  private lastActivity = Date.now();
  private lastTick = Date.now();
  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private sinceEmit = 0;
  private readonly emit: Emit;
  private readonly enabled: () => boolean;

  constructor(emit: Emit, enabled: () => boolean) {
    this.emit = emit;
    this.enabled = enabled;
  }

  start(): void {
    const activity = () => {
      this.lastActivity = Date.now();
    };
    for (const ev of ["mousemove", "mousedown", "keydown", "scroll", "wheel", "touchstart"]) {
      window.addEventListener(ev, activity, { passive: true, capture: true });
    }
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") this.flush();
    });
    window.addEventListener("pagehide", () => this.flush());
    window.addEventListener("beforeunload", () => this.flush());

    this.tickTimer = setInterval(() => this.tick(), TICK_MS);
  }

  private isActive(): boolean {
    return (
      document.visibilityState === "visible" &&
      Date.now() - this.lastActivity < IDLE_MS
    );
  }

  private tick(): void {
    if (typeof chrome === "undefined" || !chrome.runtime?.id) {
      this.stop();
      return;
    }
    const now = Date.now();
    const elapsed = now - this.lastTick;
    this.lastTick = now;
    if (this.isActive()) {
      this.activeMs += elapsed;
      this.sinceEmit += elapsed;
      if (this.sinceEmit >= PERIODIC_EMIT_MS) this.flush();
    }
  }

  /** Emit accumulated active-time as a dwell event and reset the accumulator. */
  flush(): void {
    this.tick();
    if (!this.enabled()) {
      this.activeMs = 0;
      this.sinceEmit = 0;
      return;
    }
    const ms = Math.round(this.activeMs);
    this.activeMs = 0;
    this.sinceEmit = 0;
    if (ms < 1000) return; // ignore sub-second blips
    this.emit([
      {
        type: "dwell",
        url: location.href,
        title: document.title || null,
        data: { dwell_ms: ms, active_ms: ms },
      },
    ]);
  }

  stop(): void {
    if (this.tickTimer) clearInterval(this.tickTimer);
  }
}
