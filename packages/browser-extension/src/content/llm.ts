// LLM chat capture (config-gated). On known LLM sites, capture the prompt the
// user submits. DOM structures change often, so we use a resilient heuristic:
// capture the focused composer's text on Enter-to-send or on a Send-button
// click, rather than depending on brittle per-site selectors.
import { clamp } from "../common/util";
import type { CandidateEvent } from "../common/types";

type Emit = (events: CandidateEvent[]) => void;

const LLM_SITES: { match: string; name: string }[] = [
  { match: "chatgpt.com", name: "chatgpt" },
  { match: "chat.openai.com", name: "chatgpt" },
  { match: "claude.ai", name: "claude" },
  { match: "gemini.google.com", name: "gemini" },
  { match: "bard.google.com", name: "gemini" },
  { match: "copilot.microsoft.com", name: "copilot" },
  { match: "perplexity.ai", name: "perplexity" },
  { match: "poe.com", name: "poe" },
  { match: "x.ai", name: "grok" },
  { match: "chat.deepseek.com", name: "deepseek" },
  { match: "chat.mistral.ai", name: "mistral" },
];

export function detectLlmSite(): string | null {
  const host = location.host.toLowerCase();
  return LLM_SITES.find((s) => host.includes(s.match))?.name ?? null;
}

function composerText(el: Element | null): string | null {
  if (!el) return null;
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
    return el.value;
  }
  if (el instanceof HTMLElement && el.isContentEditable) {
    return el.innerText;
  }
  return null;
}

function findComposer(): Element | null {
  const active = document.activeElement;
  if (active && composerText(active) != null) return active;
  // Fallbacks: the main editable area on the page.
  return (
    document.querySelector("textarea:not([readonly])") ??
    document.querySelector('[contenteditable="true"]') ??
    document.querySelector('[role="textbox"]')
  );
}

const SEND_HINT = /(send|submit)/i;

export function wireLlmCapture(emit: Emit, enabled: () => boolean): void {
  const site = detectLlmSite();
  if (!site) return;

  let lastEmitted = "";
  const emitPrompt = (text: string | null) => {
    if (!enabled()) return;
    const prompt = clamp(text, 8000);
    if (!prompt || prompt.length < 2 || prompt === lastEmitted) return;
    lastEmitted = prompt;
    emit([
      {
        type: "llm_chat",
        url: location.href,
        title: document.title || null,
        content: prompt,
        data: { site, role: "user" },
      },
    ]);
  };

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const text = composerText(e.target as Element);
      if (text != null) emitPrompt(text);
    },
    { capture: true },
  );

  document.addEventListener(
    "click",
    (e) => {
      const el = (e.target as Element | null)?.closest?.(
        'button,[role="button"]',
      );
      if (!el) return;
      const label = `${el.getAttribute("aria-label") ?? ""} ${el.getAttribute("data-testid") ?? ""} ${el.textContent ?? ""}`;
      if (SEND_HINT.test(label)) emitPrompt(composerText(findComposer()));
    },
    { capture: true },
  );
}
