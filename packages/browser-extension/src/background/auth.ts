// Google sign-in inside the extension via chrome.identity.launchWebAuthFlow.
//
// The token obtained here is the ingestion credential: it is sent as
// `Authorization: Bearer <token>` to the Web API, which verifies it against
// Google (see packages/web/api/src/web_api/google_auth.py). No API key needed.
//
// Flow (brokered through the isitme Web API — NOT directly to Google):
//   1. Build the Web API URL `${apiBase}/auth/google/login?ext_redirect=<chromiumapp>`
//      where ext_redirect = chrome.identity.getRedirectURL() ->
//      https://<EXTENSION_ID>.chromiumapp.org/.
//   2. launchWebAuthFlow opens that URL. The Web API runs the standard Google
//      authorization-code flow using its OWN registered redirect_uri
//      (http://localhost:5050/auth/google/callback) + client secret, so the
//      extension never needs its chromiumapp.org URI registered with Google.
//   3. The Web API redirects back to the chromiumapp.org URI with
//      #id_token=...&state=...&expires_in=... in the fragment.
//   4. We validate `state`, derive the profile from the id_token claims (the
//      Web API already verified the token), and cache it.
//
// This avoids registering the extension redirect with Google and avoids the
// deprecated OAuth implicit grant.

import type { AuthToken, ExtensionConfig, OAuthProfile } from "../common/types";
import { nowIso, uuid } from "../common/util";

// Treat a token as expired this many ms early so we refresh before it lapses.
const EXPIRY_SKEW_MS = 60_000;

export interface SignInResult {
  profile: OAuthProfile;
  token: AuthToken;
}

export interface SignInOptions {
  /** false = silent refresh (no UI); only succeeds if Google can auth without prompting. */
  interactive?: boolean;
}

interface IdTokenClaims {
  sub?: string;
  email?: string;
  name?: string;
  picture?: string;
  nonce?: string;
  exp?: number;
}

function parseFragment(redirectUrl: string): URLSearchParams {
  const hash = redirectUrl.includes("#") ? (redirectUrl.split("#")[1] ?? "") : "";
  return new URLSearchParams(hash);
}

/** Decode a JWT payload (no signature check — the Web API verifies the token). */
function decodeJwtPayload(jwt: string): IdTokenClaims | null {
  const parts = jwt.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = (parts[1] ?? "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    return JSON.parse(atob(padded)) as IdTokenClaims;
  } catch {
    return null;
  }
}

/** True when the cached token is present and not within the expiry skew window. */
export function isTokenValid(token: AuthToken | null): boolean {
  if (!token) return false;
  if (!token.idToken && !token.accessToken) return false;
  return token.expiresAt - EXPIRY_SKEW_MS > Date.now();
}

/** The Bearer string to send for a token (prefers the verifiable id_token). */
export function bearerOf(token: AuthToken | null): string | null {
  if (!token) return null;
  return token.idToken ?? token.accessToken ?? null;
}

/** Base URL for the brokered OAuth flow. Use `localhost` (not 127.0.0.1) so the
 * Web API's session cookie set on `/auth/google/login` round-trips to the
 * `/auth/google/callback` redirect, which is pinned to `localhost` by the
 * registered Google redirect_uri. */
function authBase(config: ExtensionConfig): string {
  return config.apiBaseUrl.replace("127.0.0.1", "localhost").replace(/\/+$/, "");
}

export async function signInWithGoogle(
  config: ExtensionConfig,
  options: SignInOptions = {},
): Promise<SignInResult> {
  const interactive = options.interactive ?? true;

  const redirectUri = chrome.identity.getRedirectURL();
  const state = uuid();
  const authUrl =
    `${authBase(config)}/auth/google/login?` +
    new URLSearchParams({ ext_redirect: redirectUri, ext_state: state }).toString();

  const redirectResponse = await chrome.identity.launchWebAuthFlow({
    url: authUrl,
    interactive,
  });
  if (!redirectResponse) throw new Error("Sign-in was cancelled.");

  const params = parseFragment(redirectResponse);
  const error = params.get("error");
  if (error) throw new Error(`Sign-in failed: ${error}`);
  if (params.get("state") !== state) throw new Error("OAuth state mismatch — aborting.");

  const idToken = params.get("id_token");
  if (!idToken) throw new Error("No id_token returned by the isitme Web API.");

  const claims = decodeJwtPayload(idToken);
  if (!claims || !claims.sub) throw new Error("Could not decode the Google id_token.");

  const expiresIn = Number.parseInt(params.get("expires_in") ?? "3600", 10);
  const expiresAt = Date.now() + (Number.isFinite(expiresIn) ? expiresIn : 3600) * 1000;

  const profile: OAuthProfile = {
    sub: claims.sub,
    email: claims.email ?? null,
    name: claims.name ?? null,
    picture: claims.picture ?? null,
    signedInAt: nowIso(),
  };
  const token: AuthToken = { idToken, accessToken: null, expiresAt };
  return { profile, token };
}
