// Builds the link-trail (which page led to which) from webNavigation events.
// Content scripts capture explicit link *clicks*; this captures the resulting
// navigation *edges* (including back/forward and address-bar), keeping the two
// concerns separate and avoiding duplicates.
import type { CandidateEvent } from "../common/types";

interface TabInfo {
  url: string;
}

export class TabTracker {
  private tabs = new Map<number, TabInfo>();

  /**
   * Record a committed navigation. Returns a `link` candidate event describing
   * the edge (from -> to) when there is a meaningful previous URL.
   */
  onNavigation(
    tabId: number,
    toUrl: string,
    transition: string,
    qualifiers: string[],
  ): CandidateEvent | null {
    const prev = this.tabs.get(tabId);
    this.tabs.set(tabId, { url: toUrl });
    if (!prev || prev.url === toUrl) return null;
    return {
      type: "link",
      url: toUrl,
      data: {
        from: prev.url,
        transition,
        qualifiers,
        tab_id: tabId,
      },
    };
  }

  forget(tabId: number): void {
    this.tabs.delete(tabId);
  }

  current(tabId: number): string | undefined {
    return this.tabs.get(tabId)?.url;
  }
}
