// Search detection: search-engine result queries (from the URL) and on-page
// search-box submissions.
import type { CandidateEvent } from "../common/types";

type Emit = (events: CandidateEvent[]) => void;

/** host substring -> query param used by that engine. */
const ENGINE_PARAMS: { match: string; param: string; name: string }[] = [
  { match: "google.", param: "q", name: "google" },
  { match: "bing.com", param: "q", name: "bing" },
  { match: "duckduckgo.com", param: "q", name: "duckduckgo" },
  { match: "search.yahoo.", param: "p", name: "yahoo" },
  { match: "yandex.", param: "text", name: "yandex" },
  { match: "baidu.com", param: "wd", name: "baidu" },
  { match: "ecosia.org", param: "q", name: "ecosia" },
  { match: "search.brave.com", param: "q", name: "brave" },
  { match: "startpage.com", param: "query", name: "startpage" },
  { match: "kagi.com", param: "q", name: "kagi" },
  { match: "perplexity.ai", param: "q", name: "perplexity" },
];

/** Detect a search-engine query from the current URL, if any. */
export function detectEngineQuery(): CandidateEvent | null {
  let url: URL;
  try {
    url = new URL(location.href);
  } catch {
    return null;
  }
  const host = url.host.toLowerCase();
  const engine = ENGINE_PARAMS.find((e) => host.includes(e.match));
  if (!engine) return null;
  const query = url.searchParams.get(engine.param);
  if (!query || !query.trim()) return null;
  return {
    type: "search",
    url: location.href,
    title: document.title || null,
    data: { query: query.trim(), engine: engine.name, source: "engine" },
  };
}

const SEARCH_NAME = /(search|query|q|keyword|term)/i;

function looksLikeSearchInput(el: Element): boolean {
  if (!(el instanceof HTMLInputElement)) return false;
  if (el.type === "search") return true;
  const hints = `${el.name} ${el.id} ${el.getAttribute("aria-label") ?? ""} ${el.placeholder}`;
  return el.type === "text" && SEARCH_NAME.test(hints);
}

/** Wire on-page search-box capture (form submit + Enter on search inputs). */
export function wireOnPageSearch(emit: Emit): void {
  const emitQuery = (value: string, field: string) => {
    const q = value.trim();
    if (q.length < 2) return;
    emit([
      {
        type: "search",
        url: location.href,
        title: document.title || null,
        data: { query: q, source: "on_page", field },
      },
    ]);
  };

  document.addEventListener(
    "submit",
    (e) => {
      const form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      const input = [...form.elements].find((el) => looksLikeSearchInput(el));
      if (input instanceof HTMLInputElement) emitQuery(input.value, input.name || "search");
    },
    { capture: true },
  );

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Enter") return;
      const el = e.target;
      if (el instanceof HTMLInputElement && looksLikeSearchInput(el)) {
        emitQuery(el.value, el.name || "search");
      }
    },
    { capture: true },
  );
}
