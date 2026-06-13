// Host allow/deny matching. Patterns match against the URL host and support a
// leading/trailing `*` wildcard plus bare-domain subdomain matching.
//   "example.com"     -> example.com and any *.example.com
//   "*.example.com"   -> only subdomains of example.com
//   "login.*"         -> hosts starting with "login."
//   "*bank*"          -> host contains "bank"

export function hostFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).host.toLowerCase();
  } catch {
    return null;
  }
}

function patternToRegex(pattern: string): RegExp {
  const p = pattern.trim().toLowerCase();
  // Escape regex specials except '*', which becomes '.*'.
  const escaped = p.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`);
}

export function hostMatches(host: string, pattern: string): boolean {
  const h = host.toLowerCase();
  const p = pattern.trim().toLowerCase();
  if (!p) return false;
  // Bare domain: match the domain itself and any subdomain.
  if (!p.includes("*")) {
    return h === p || h.endsWith(`.${p}`);
  }
  return patternToRegex(p).test(h);
}

function anyMatch(host: string, patterns: string[]): boolean {
  return patterns.some((p) => hostMatches(host, p));
}

/**
 * Decide whether a URL is capturable. Deny wins; if an allow-list is present,
 * the host must be on it. Non-http(s) schemes (chrome://, file://, etc.) are
 * never captured.
 */
export function isCapturable(
  url: string | null | undefined,
  allowList: string[],
  denyList: string[],
): boolean {
  if (!url) return false;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
  const host = parsed.host.toLowerCase();
  if (anyMatch(host, denyList)) return false;
  if (allowList.length > 0 && !anyMatch(host, allowList)) return false;
  return true;
}
