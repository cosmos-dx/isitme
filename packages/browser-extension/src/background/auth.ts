// Google sign-in inside the extension via chrome.identity.launchWebAuthFlow.
//
// The token obtained here is the ingestion credential: it is sent as
// `Authorization: Bearer <token>` to the Web API, which verifies it against
// Google (see packages/web/api/src/web_api/google_auth.py). No API key needed.
//
// Flow (OAuth 2.0 implicit — no client secret in the extension):
//   1. Build the Google authorize URL with response_type="id_token token" and
//      the redirect_uri chrome.identity.getRedirectURL() ->
//      https://<EXTENSION_ID>.chromiumapp.org/
//   2. launchWebAuthFlow opens Google's consent screen (interactive) — or
//      reuses an existing session (silent, interactive:false for refresh) — and
//      returns the redirect URL with #id_token=...&access_token=... in the
//      fragment.
//   3. We validate `state` + `nonce`, derive the profile from the id_token
//      claims, and return both tokens + an expiry for caching.

import type { AuthToken, ExtensionConfig, OAuthProfile } from "../common/types";
import { nowIso, uuid } from "../common/util";

const AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo";
const SCOPE = "openid email profile";
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

export async function signInWithGoogle(
  config: ExtensionConfig,
  options: SignInOptions = {},
): Promise<SignInResult> {
  const interactive = options.interactive ?? true;
  const clientId = config.auth.googleClientId.trim();
  if (!clientId) throw new Error("No Google client_id configured (set it in Options).");

  const redirectUri = chrome.identity.getRedirectURL();
  const state = uuid();
  const nonce = uuid();
  const authUrl =
    `${AUTH_ENDPOINT}?` +
    new URLSearchParams({
      client_id: clientId,
      response_type: "id_token token",
      redirect_uri: redirectUri,
      scope: SCOPE,
      state,
      nonce,
      prompt: interactive ? "select_account" : "none",
      include_granted_scopes: "true",
    }).toString();

  const redirectResponse = await chrome.identity.launchWebAuthFlow({
    url: authUrl,
    interactive,
  });
  if (!redirectResponse) throw new Error("Sign-in was cancelled.");

  const params = parseFragment(redirectResponse);
  if (params.get("state") !== state) throw new Error("OAuth state mismatch — aborting.");

  const error = params.get("error");
  if (error) throw new Error(`Google returned an error: ${error}`);

  const idToken = params.get("id_token");
  const accessToken = params.get("access_token");
  if (!idToken && !accessToken) {
    throw new Error("No token returned by Google.");
  }
  const expiresIn = Number.parseInt(params.get("expires_in") ?? "3600", 10);
  const expiresAt = Date.now() + (Number.isFinite(expiresIn) ? expiresIn : 3600) * 1000;

  let profile: OAuthProfile | null = null;
  if (idToken) {
    const claims = decodeJwtPayload(idToken);
    if (!claims) throw new Error("Could not decode the Google id_token.");
    if (claims.nonce && claims.nonce !== nonce) {
      throw new Error("OAuth nonce mismatch — aborting.");
    }
    if (claims.sub) {
      profile = {
        sub: claims.sub,
        email: claims.email ?? null,
        name: claims.name ?? null,
        picture: claims.picture ?? null,
        signedInAt: nowIso(),
      };
    }
  }
  if (!profile) {
    if (!accessToken) throw new Error("Google id_token missing 'sub'.");
    profile = await fetchUserInfoProfile(accessToken);
  }

  const token: AuthToken = {
    idToken: idToken ?? null,
    accessToken: accessToken ?? null,
    expiresAt,
  };
  return { profile, token };
}

interface GoogleUserInfo {
  sub: string;
  email?: string;
  name?: string;
  picture?: string;
}

async function fetchUserInfoProfile(accessToken: string): Promise<OAuthProfile> {
  const resp = await fetch(USERINFO_ENDPOINT, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!resp.ok) throw new Error(`userinfo failed (HTTP ${resp.status}).`);
  const data = (await resp.json()) as GoogleUserInfo;
  if (!data.sub) throw new Error("userinfo response missing 'sub'.");
  return {
    sub: data.sub,
    email: data.email ?? null,
    name: data.name ?? null,
    picture: data.picture ?? null,
    signedInAt: nowIso(),
  };
}
