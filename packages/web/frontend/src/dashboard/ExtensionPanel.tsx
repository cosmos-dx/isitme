import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ExtensionUsage } from "../lib/types";

export function ExtensionPanel() {
  const [usage, setUsage] = useState<ExtensionUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .extensionUsage()
      .then(setUsage)
      .catch((e: Error) => setError(e.message));
  }, []);

  const categories = usage ? Object.entries(usage.by_category).sort((a, b) => b[1] - a[1]) : [];
  const maxCat = categories.reduce((m, [, v]) => Math.max(m, v), 0) || 1;

  return (
    <div className="card p-6">
      <h3 className="text-sm font-medium text-neutral-100">Extension usage</h3>
      <p className="mt-1 text-xs text-neutral-500">
        What the browser extension has fed into your brain.
      </p>

      {error && <p className="mt-3 text-sm text-rose-400/80">{error}</p>}

      <div className="mt-4 grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="text-2xl font-semibold text-neutral-50 tnum">
            {usage?.events_captured ?? "·"}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">Events</div>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="text-2xl font-semibold text-neutral-50 tnum">{usage?.nodes ?? "·"}</div>
          <div className="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">Nodes</div>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="text-2xl font-semibold text-neutral-50 tnum">
            {usage?.memories ?? "·"}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">Memories</div>
        </div>
      </div>

      {categories.length > 0 && (
        <div className="mt-5">
          <div className="eyebrow mb-2">Graph composition by type</div>
          <div className="space-y-2">
            {categories.map(([cat, count]) => (
              <div key={cat} className="flex items-center gap-3">
                <span className="w-20 shrink-0 text-xs text-neutral-400">{cat}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
                  <div
                    className="h-full rounded-full bg-accent/70"
                    style={{ width: `${(count / maxCat) * 100}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right font-mono text-[11px] text-neutral-500 tnum">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
        <div className="eyebrow mb-2">Install the extension</div>
        <ol className="list-inside list-decimal space-y-1 text-xs leading-relaxed text-neutral-400">
          <li>
            Build it: <span className="font-mono text-neutral-300">packages/browser-extension</span>
          </li>
          <li>
            Open <span className="font-mono text-neutral-300">chrome://extensions</span>, enable
            Developer mode.
          </li>
          <li>
            Click <span className="text-neutral-300">Load unpacked</span> and select the built{" "}
            <span className="font-mono text-neutral-300">dist/</span> folder.
          </li>
          <li>Paste an API key (from the panel above) into the extension settings.</li>
        </ol>
      </div>
    </div>
  );
}
