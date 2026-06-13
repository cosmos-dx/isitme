// Small shared helpers.

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  // Fallback (older runtimes).
  return Array.from({ length: 32 }, () =>
    Math.floor(Math.random() * 16).toString(16),
  ).join("");
}

export function nowIso(): string {
  return new Date().toISOString();
}

/** Truncate long strings so we never ship megabytes of page text per event. */
export function clamp(text: string | null | undefined, max: number): string | null {
  if (!text) return null;
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return null;
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
