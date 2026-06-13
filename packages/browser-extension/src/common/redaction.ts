// Client-side redaction applied in the background worker before anything is
// queued or sent. Removes obvious secrets/PII: credit cards (Luhn-validated),
// SSNs, common token/secret formats, and `key=value` pairs whose key looks
// sensitive. Conservative by design — better to over-redact than leak.

import type { CandidateEvent, RawEvent } from "./types";

const MASK = "[redacted]";

function luhnValid(digits: string): boolean {
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = digits.charCodeAt(i) - 48;
    if (d < 0 || d > 9) return false;
    if (alt) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    alt = !alt;
  }
  return sum % 10 === 0;
}

const SENSITIVE_KEY = /(pass(word|wd)?|secret|token|api[_-]?key|auth|bearer|session|cookie|otp|cvv|pin)/i;

const PATTERNS: { name: string; re: RegExp; validate?: (m: string) => boolean }[] = [
  // Credit-card-like: 13-19 digits possibly separated by space/dash.
  {
    name: "cc",
    re: /\b(?:\d[ -]?){13,19}\b/g,
    validate: (m) => luhnValid(m.replace(/[^\d]/g, "")),
  },
  // US SSN.
  { name: "ssn", re: /\b\d{3}-\d{2}-\d{4}\b/g },
  // OpenAI / Anthropic / Stripe-style keys.
  { name: "sk", re: /\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}\b/g },
  { name: "stripe", re: /\b(sk|pk)_(live|test)_[A-Za-z0-9]{10,}\b/g },
  // AWS access key id.
  { name: "aws", re: /\bAKIA[0-9A-Z]{16}\b/g },
  // GitHub tokens.
  { name: "ghp", re: /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g },
  // Google API key.
  { name: "gapi", re: /\bAIza[0-9A-Za-z_-]{32,}\b/g },
  // JWT.
  { name: "jwt", re: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g },
  // Bearer tokens.
  { name: "bearer", re: /\bBearer\s+[A-Za-z0-9._-]{12,}\b/gi },
  // isitme keys themselves should never round-trip through content.
  { name: "isme", re: /\bisme_[A-Za-z0-9_-]{16,}\b/g },
];

/** Redact a free-text string. */
export function redactText(input: string): string {
  let out = input;
  for (const { re, validate } of PATTERNS) {
    out = out.replace(re, (match) => {
      if (validate && !validate(match)) return match;
      return MASK;
    });
  }
  // key=value / key: value where the key looks sensitive.
  out = out.replace(
    /(["']?[\w.-]*?(?:pass(?:word|wd)?|secret|token|api[_-]?key|auth|bearer|session|cookie|otp|cvv|pin)[\w.-]*?["']?\s*[:=]\s*)("?[^\s"'&,}]{3,}"?)/gi,
    (_full, key: string) => `${key}${MASK}`,
  );
  return out;
}

/** Redact secret-looking query params in a URL while keeping it parseable. */
export function redactUrl(url: string): string {
  try {
    const u = new URL(url);
    let changed = false;
    for (const [key, value] of [...u.searchParams.entries()]) {
      if (SENSITIVE_KEY.test(key) || redactText(value) !== value) {
        u.searchParams.set(key, MASK);
        changed = true;
      }
    }
    return changed ? u.toString() : url;
  } catch {
    return redactText(url);
  }
}

function redactValue(v: unknown): unknown {
  if (typeof v === "string") return redactText(v);
  if (Array.isArray(v)) return v.map(redactValue);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      out[k] = SENSITIVE_KEY.test(k) ? MASK : redactValue(val);
    }
    return out;
  }
  return v;
}

/** Apply redaction to an event in-place-safe manner, returning a new event. */
export function redactEvent(
  ev: CandidateEvent | RawEvent,
): CandidateEvent | RawEvent {
  const out: CandidateEvent | RawEvent = { ...ev };
  if (out.url) out.url = redactUrl(out.url);
  if (out.title) out.title = redactText(out.title);
  if (out.content) out.content = redactText(out.content);
  if (out.data) out.data = redactValue(out.data) as Record<string, unknown>;
  return out;
}
