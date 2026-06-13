# isitme — browser capture extension

A Manifest V3 (TypeScript) Chrome extension that captures your online behavior
and feeds it to your local **isitme** brain via the Web API (BFF on `:5050`).
It is the browsing-data collector for your personal central brain.

> **This extension captures browsing data.** Everything stays local: events are
> sent only to the API base URL you configure (default `http://127.0.0.1:5050`),
> never to any third party. Capture is gated by per-category toggles, per-site
> allow/deny lists, and client-side redaction.

## What it captures

| Category        | What & how                                                                                                  | Event `type`     | Default |
| --------------- | ----------------------------------------------------------------------------------------------------------- | ---------------- | ------- |
| Page visits     | URL, title, referrer (and SPA route changes)                                                                | `visit`          | on      |
| Dwell time      | **Active** time on a page (visible **and** interacting within 30s), not just open-time                      | `dwell`          | on      |
| Clicks          | Clicks on links/buttons (tag, text, href)                                                                   | `click`          | on      |
| Link-trail      | Navigation edges — which page led to which (`from` → `to`, transition), incl. back/forward & address-bar    | `link`           | on      |
| Searches        | Search-engine queries (Google, Bing, DDG, Yahoo, Brave, Kagi, …) **and** on-page search boxes               | `search`         | on      |
| LLM chat        | Prompts typed into ChatGPT, Claude, Gemini, Copilot, Perplexity, etc. (on Enter-to-send / Send click)       | `llm_chat`       | **off** |
| Page content    | Main text of visited pages, attached to the `visit` event (clamped to ~4k chars)                            | `visit.content`  | **off** |

The event shape mirrors the brain's `RawEvent`
(`packages/brain-core/src/brain_core/models/events.py`): `type`, `timestamp`,
`source` (`"browser-extension"`), `session_id`, `url`, `title`, `content`, `data`.

## Privacy controls

- **Per-category toggles** — turn any capture category on/off in Options.
- **Allow / deny lists** — host patterns. Deny wins; if an allow-list is set,
  *only* those hosts are captured. `example.com` matches subdomains too; `*` is
  a wildcard (`login.*`, `*bank*`). Sensible deny defaults ship out of the box
  (`*.bank`, `accounts.google.com`, `login.*`, `*.onion`).
- **Client-side redaction** (on by default) — before anything leaves the
  browser, the background worker scrubs: credit cards (Luhn-validated), US SSNs,
  OpenAI/Anthropic/Stripe/AWS/GitHub/Google API keys, JWTs, bearer tokens,
  isitme keys, and any `key=value` pair whose key looks sensitive
  (`password`, `secret`, `token`, `api_key`, `auth`, `cvv`, …). Password input
  values are never read.
- **Pause** — one click in the popup halts all capture.

## Architecture

```
content script (per page)            background service worker (the policy gate)
  visits / clicks / dwell      ──▶     applyPolicy: paused? toggle? allow/deny? redact
  searches / LLM prompts                 │
                                         ▼
webNavigation (link-trail) ────────▶  persistent offline queue (chrome.storage)
                                         │  flush on: size ≥ batch, alarm (30s), idle
                                         ▼
                                  POST /api/ingest  (X-API-Key)
```

The **background worker is the single chokepoint**: content scripts only emit
"candidate" events; all redaction, allow/deny and toggle policy is enforced in
one place before anything is queued or sent. The queue is persisted so events
survive service-worker suspension and offline periods, and is drained in
batches with retry (failed sends stay queued).

## Permissions & justification

| Permission                | Why it's needed                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------ |
| `storage`                 | Persist config, the offline event queue, the OAuth profile, and daily counters.                  |
| `tabs`                    | Read active-tab URL/title to attribute events and re-inject after install.                        |
| `webNavigation`           | Detect navigations + SPA history changes to build the link-trail.                                 |
| `identity`                | Google sign-in via `launchWebAuthFlow` so the extension knows who the user is.                    |
| `scripting`               | Re-inject the content script into tabs already open when the extension is installed/updated.       |
| `idle`                    | Flush the batch when the machine goes idle; pause active-dwell accounting while idle.              |
| `alarms`                  | Reliable periodic flush in an MV3 service worker that may be suspended.                            |
| `host_permissions: <all_urls>` | Capture on the sites you visit (subject to allow/deny) and POST to the local API + Google userinfo. |

`<all_urls>` is inherent to a general browsing-capture tool; it is constrained
at runtime by the allow/deny lists and category toggles.

## Build & load (local dev)

```bash
cd packages/browser-extension
npm install            # uses the public registry via .npmrc
npm run build          # typecheck (tsc --noEmit) + bundle (esbuild) -> dist/
# npm run dev          # rebuild-on-change (watch)
# npm run zip          # build + produce isitme-extension.zip for the Web Store
```

Then in Chrome:

1. Open `chrome://extensions`, enable **Developer mode** (top-right).
2. Click **Load unpacked** and select the `packages/browser-extension/dist/` folder.
3. Copy the extension's **ID** (shown on the card) — you need it for OAuth.
4. Open the extension **Options** and set the **API base URL** and **API key**
   (or sign in with Google in the popup — see below).

The build is dependency-free at runtime (no framework); `dist/` contains
`manifest.json`, four bundled scripts, two HTML/CSS pairs, and generated icons.

## Sign-in & getting an API key

**Authentication (who you are)** — click **Sign in** in the popup. The
extension runs Google OAuth via `chrome.identity.launchWebAuthFlow`, verifies
the token against Google's userinfo endpoint, and stores your profile
(name/email/avatar). See [OAUTH below](#oauth-in-the-extension).

**Ingestion key (how it authenticates to the API)** — the supported path is to
mint an API key in the dashboard (Settings → API keys) and paste it into the
extension Options. The key is sent as the `X-API-Key` header on every
`POST /api/ingest`. Use **Validate** in Options to verify it against
`GET /api/keys/validate`.

> Optional auto-provisioning: if the Web API later exposes an endpoint that
> trades a Google token for an isitme key, enable **Auto-provision** in Options
> and set the endpoint path; the extension will request a key on sign-in and
> fall back to paste if the endpoint is absent.

## OAuth in the extension

`chrome.identity.launchWebAuthFlow` opens Google's consent screen and returns to
the extension redirect URI `https://<EXTENSION_ID>.chromiumapp.org/`. Because
the extension ID determines that URI, you must register it in Google Cloud:

1. **Google Cloud Console → APIs & Services → Credentials** → open the OAuth
   **web** client referenced by the project (`OAUTH_CLIENT_JSON` in root `.env`).
2. Under **Authorized redirect URIs**, add:
   `https://<EXTENSION_ID>.chromiumapp.org/`
   (replace `<EXTENSION_ID>` with the ID from `chrome://extensions`). The Options
   page prints the exact URI for you.
3. The OAuth consent screen is in **Testing**, so add your Google account under
   **OAuth consent screen → Test users**. Without this, sign-in returns
   `access_denied`.
4. Click **Save** in Options, then **Sign in** from the popup.

The Options page shows your live redirect URI and these instructions.

> The extension never holds the OAuth **client secret** — it uses the public
> client ID with the implicit (`response_type=token`) flow and validates the
> token via Google's userinfo endpoint.
>
> **Alternative — `chrome.identity.getAuthToken`:** instead of `launchWebAuthFlow`
> you can create a *Chrome Extension* OAuth client (type "Chrome App") in Google
> Cloud tied to your extension ID, add an `"oauth2"` block to the manifest, and
> call `getAuthToken`. It avoids the chromiumapp redirect but requires a stable
> extension ID (a `"key"` in the manifest or a published item) and a separate
> client. `launchWebAuthFlow` is used here because it works with the existing
> web client during local dev.

## Configuration reference

All settings live in **Options** (and in `chrome.storage.local`):

- **API base URL** / **API key** — connection + `X-API-Key`.
- **Capture toggles** — per category (above).
- **Redaction** — on/off.
- **Allow / deny lists** — host patterns.
- **Batching** — batch size (default 25), flush interval (default 30s), max
  offline queue (default 1000, oldest dropped past the cap).
- **Google sign-in** — client ID, auto-provision toggle + endpoint path.

See [`PUBLISHING.md`](./PUBLISHING.md) for Chrome Web Store deployment.
