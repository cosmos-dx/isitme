# Publishing the isitme extension to the Chrome Web Store

This guide covers everything from a developer account to a published listing,
with special attention to the privacy disclosures required for an extension
that **captures browsing data**. It also covers loading the build unpacked for
local development.

> Chrome Web Store policies and the dashboard change over time. Where exact
> wording matters (data policy, screenshot sizes), confirm against the current
> [Chrome Web Store developer docs](https://developer.chrome.com/docs/webstore/)
> before submitting.

---

## 0. Load unpacked for local development (no account needed)

```bash
cd packages/browser-extension
npm install
npm run build      # -> dist/
```

1. Open `chrome://extensions` and enable **Developer mode**.
2. **Load unpacked** → select `packages/browser-extension/dist/`.
3. Note the extension **ID** on the card (needed for OAuth — see README).
4. Reload from the card after each `npm run build`. (`npm run dev` rebuilds JS
   on change; re-run `npm run build` to refresh static assets/icons.)

---

## 1. Create a Chrome Web Store developer account

1. Go to the [Developer Dashboard](https://chrome.google.com/webstore/devconsole).
2. Sign in with the Google account that will own the listing.
3. Accept the developer agreement and pay the **one-time US$5 registration fee**.
4. (Recommended) Complete account verification and set a **publisher display
   name**. Items that request sensitive permissions get more scrutiny from a
   verified publisher.

---

## 2. Prepare the build (MV3) and zip it

The store accepts a ZIP of the **built** extension — the contents of `dist/`,
**not** the `dist` folder itself (`manifest.json` must be at the ZIP root).

```bash
cd packages/browser-extension
npm run build          # typecheck + bundle to dist/
npm run zip            # builds, then zips dist/ -> isitme-extension.zip
```

Before zipping, bump `version` in `package.json` (the build injects it into
`manifest.json`). Each upload must have a **higher** version than the last.

Verify the ZIP root contains: `manifest.json`, `background.js`, `content.js`,
`popup.html/js/css`, `options.html/js/css`, and `icons/`.

---

## 3. Listing assets

Prepare these before creating the item (you can't publish without them):

- **Icon**: 128×128 PNG (already generated at `dist/icons/icon-128.png`; you may
  replace it with a polished version).
- **Screenshots**: at least one, **1280×800** or **640×400** PNG/JPEG. Show the
  popup (status) and the Options page. 3–5 screenshots is ideal.
- **Small promo tile** (optional but recommended): 440×280 PNG.
- **Listing text**: a clear name, a short summary, and a detailed description
  that states plainly that the extension captures browsing activity and sends it
  to a server the user controls.
- **Category**: Productivity (or Developer Tools).
- **Language**: primary listing language.

---

## 4. Privacy: disclosures, justifications, and Limited Use

This extension collects **Web browsing activity** and **personally identifiable
information** (the signed-in Google profile). You **must** disclose this
accurately or the item will be rejected.

In the dashboard's **Privacy practices** tab:

1. **Single purpose** — state it in one sentence, e.g.:
   > "Captures the user's browsing activity (visits, dwell, clicks, searches and
   > optional LLM prompts) and sends it to the user's own isitme brain server."

2. **Permission justifications** — provide a one-line reason for each (see the
   table in `README.md`). Be ready to justify `host_permissions: <all_urls>`:
   capture is inherent to the product and is constrained at runtime by the
   user's allow/deny lists and per-category toggles.

3. **Data usage disclosures** — declare the data types collected:
   - *Web browsing activity* (URLs, page titles, page content if enabled).
   - *Personally identifiable information* (Google account name/email from
     sign-in).
   - *User activity* (clicks, dwell, searches; LLM prompts if enabled).
   Then check the required certifications:
   - You **do not** sell or transfer data to third parties (data goes only to
     the user's configured API).
   - You **do not** use the data for purposes unrelated to the single purpose.
   - You **do not** use the data for creditworthiness / lending.

4. **Limited Use compliance** — confirm adherence to the
   [Chrome Web Store Limited Use policy](https://developer.chrome.com/docs/webstore/program-policies/limited-use):
   data is used only to provide the user-facing feature, not sold, and not
   transferred except as required to operate the feature (here: to the user's
   own server).

5. **Privacy policy URL** — **required** for items handling sensitive/personal
   data. Host a policy that covers: what is collected, that it is sent only to
   the user-configured endpoint (no third parties), local client-side redaction
   of secrets/PII, that LLM-chat and page-content capture are off by default and
   opt-in, retention (local to the user's brain), and how to disable/uninstall.
   A starter policy:
   > "isitme captures your browsing activity (page visits, dwell time, clicks,
   > link navigation, search queries, and — only if you enable them — LLM chat
   > prompts and page content). This data is sent **only** to the API endpoint
   > you configure (by default a server running on your own machine) using an
   > API key you provide. We do not sell or share your data with third parties.
   > Secrets and obvious PII are redacted in your browser before sending. You can
   > pause capture, scope it with allow/deny lists, or uninstall at any time."

---

## 5. OAuth verification implications

The extension signs the user in with Google (scopes `openid email profile`).

- These are **non-sensitive** scopes, so a full Google OAuth security
  assessment is generally **not** required. If you later add sensitive/restricted
  scopes, Google may require app verification (and possibly a third-party
  security assessment) before non-test users can sign in.
- The OAuth consent screen will be in **Testing** by default — only listed
  **Test users** can sign in. To allow any Google user, move the consent screen
  to **In production** (Google Cloud Console → OAuth consent screen → Publish).
- A **published** extension has a **stable extension ID**, so its redirect URI
  `https://<EXTENSION_ID>.chromiumapp.org/` is fixed. Register that exact URI in
  the OAuth web client's **Authorized redirect URIs** before release (see
  `README.md`). For local unpacked dev the ID differs — register that one too,
  or use a manifest `"key"` to pin the ID across machines.

---

## 6. Upload via the Developer Dashboard

1. Dashboard → **Items** → **Add new item**.
2. Upload `isitme-extension.zip`.
3. Fill in the **Store listing** (assets + text from step 3).
4. Complete the **Privacy practices** tab (step 4) — this is where most
   browsing-data extensions get held up; be thorough.
5. Set **Distribution**: visibility (Public / Unlisted / Private) and regions.
   *Unlisted* is a good first release for a personal tool — installable by link
   without public discovery.
6. **Save draft**, then **Submit for review**.

---

## 7. Review, publishing, and rollout

- **Review time**: typically hours to a few days; longer for items with broad
  host permissions and sensitive data. Expect possible follow-up questions about
  `<all_urls>` and the data disclosures.
- **Outcome**: you'll be emailed on approval or rejection. Rejections cite the
  specific policy — fix and resubmit.
- **Rollout**: on approval, you can publish immediately or use **partial /
  percentage rollout** (in the publish settings) to release gradually.
- **Updates**: bump `version`, `npm run zip`, upload the new ZIP, and resubmit.
  Permission **increases** (new permissions / broader host access) re-trigger
  review and may re-prompt users for consent.

---

## Pre-submission checklist

- [ ] `npm run build` passes (strict typecheck + bundle).
- [ ] `version` bumped in `package.json`.
- [ ] ZIP root contains `manifest.json` (not nested under `dist/`).
- [ ] 128×128 icon + ≥1 screenshot (1280×800) prepared.
- [ ] Privacy policy URL is live and accurate.
- [ ] Data-usage disclosures + Limited Use certifications completed.
- [ ] Each permission has a justification; `<all_urls>` rationale ready.
- [ ] Published extension's `chromiumapp.org` redirect URI registered in Google
      Cloud; consent screen Test users (or In production) configured.
- [ ] Default capture is privacy-safe (LLM chat + page content **off**;
      redaction **on**; banking/auth hosts denied).
