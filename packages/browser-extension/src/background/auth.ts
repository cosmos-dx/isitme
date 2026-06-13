// Google sign-in inside the extension via chrome.identity.launchWebAuthFlow.
//
// Flow (OAuth 2.0 implicit, no client secret in the extension):
//   1. Build the Google authorize URL with response_type=token and the
//      redirect_uri chrome.identity.getRedirectURL() ->
//      https://<EXTENSION_ID>.chromiumapp.org/
//   2. launchWebAuthFlow opens Google's consent screen and returns the redirect
//      URL with #access_token=... in the fragment.
//   3. We validate `state`, then call Google's userinfo endpoint to learn who
//      the user is (sub/email/name/picture) and store it.
//
// Obtaining an ingestion API key: the supported path is pasting a key minted
// from the dashboard. If the Web API later exposes a provisioning endpoint that
// trades a Google access_token for an isitme key, enable auth.autoProvisionKey
// and set auth.provisionPath — we'll call it here and store the returned key.

import type { ExtensionConfig, OAuthProfile } from "../common/types";
import { nowIso, uuid } from "../common/util";

const AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo";
const SCOPE = "openid email profile";

export interface SignInResult {
  profile: OAuthProfile;
  /** A provisioned API key, if auto-provisioning succeeded. */
  apiKey?: string;
}

function parseFragment(redirectUrl: string): URLSearchParams {
  const hash = redirectUrl.includes("#") ? redirectUrl.split("#")[1] ?? "" : "";
  return new URLSearchParams(hash);
}

export async function signInWithGoogle(
  config: ExtensionConfig,
): Promise<SignInResult> {
  const clientId = config.auth.googleClientId.trim();
  if (!clientId) throw new Error("No Google client_id configured (set it in Options).");

  const redirectUri = chrome.identity.getRedirectURL();
  const state = uuid();
  const nonce = uuid();
  const authUrl =
    `${AUTH_ENDPOINT}?` +
    new URLSearchParams({
      client_id: clientId,
      response_type: "token",
      redirect_uri: redirectUri,
      scope: SCOPE,
      state,
      nonce,
      prompt: "select_account",
      include_granted_scopes: "true",
    }).toString();

  const redirectResponse = await chrome.identity.launchWebAuthFlow({
    url: authUrl,
    interactive: true,
  });
  if (!redirectResponse) throw new Error("Sign-in was cancelled.");

  const params = parseFragment(redirectResponse);
  const returnedState = params.get("state");
  if (returnedState !== state) throw new Error("OAuth state mismatch — aborting.");

  const error = params.get("error");
  if (error) throw new Error(`Google returned an error: ${error}`);

  const accessToken = params.get("access_token");
  if (!accessToken) throw new Error("No access_token returned by Google.");

  const userinfo = await fetchUserInfo(accessToken);
  const profile: OAuthProfile = {
    sub: userinfo.sub,
    email: userinfo.email ?? null,
    name: userinfo.name ?? null,
    picture: userinfo.picture ?? null,
    signedInAt: nowIso(),
  };

  const result: SignInResult = { profile };

  if (config.auth.autoProvisionKey && config.auth.provisionPath) {
    const key = await tryProvisionKey(config, accessToken);
    if (key) result.apiKey = key;
  }

  return result;
}

interface GoogleUserInfo {
  sub: string;
  email?: string;
  name?: string;
  picture?: string;
}

async function fetchUserInfo(accessToken: string): Promise<GoogleUserInfo> {
  const resp = await fetch(USERINFO_ENDPOINT, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!resp.ok) throw new Error(`userinfo failed (HTTP ${resp.status}).`);
  const data = (await resp.json()) as GoogleUserInfo;
  if (!data.sub) throw new Error("userinfo response missing 'sub'.");
  return data;
}

/**
 * Best-effort key provisioning. Trades the Google access_token for an isitme
 * API key against a Web-API endpoint. Returns null (and never throws) when the
 * endpoint is absent so sign-in still succeeds and the user can paste a key.
 */
async function tryProvisionKey(
  config: ExtensionConfig,
  accessToken: string,
): Promise<string | null> {
  try {
    const url = `${config.apiBaseUrl.replace(/\/+$/, "")}${config.auth.provisionPath}`;
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ client: "extension", access_token: accessToken }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { key?: string; api_key?: string };
    return data.key ?? data.api_key ?? null;
  } catch {
    return null;
  }
}
