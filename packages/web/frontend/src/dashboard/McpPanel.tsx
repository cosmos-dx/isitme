import { useEffect, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { api } from "../lib/api";
import type { McpConfig } from "../lib/types";

export function McpPanel() {
  const [config, setConfig] = useState<McpConfig | null>(null);
  const [minted, setMinted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = (mint = false) => {
    setBusy(true);
    setError(null);
    api
      .mcpConfig(mint ? { mint: true, name: "mcp" } : undefined)
      .then((c) => {
        setConfig(c);
        if (mint) setMinted(true);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  useEffect(() => {
    load(false);
  }, []);

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-neutral-100">MCP configuration</h3>
          <p className="mt-1 text-xs text-neutral-500">
            Paste into Cursor or Claude Desktop to let any LLM reach your brain.
          </p>
        </div>
        <button onClick={() => load(true)} disabled={busy} className="btn-ghost !px-3 !py-1.5 text-xs">
          {busy ? "…" : "Generate with new key"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-rose-400/80">{error}</p>}

      {config && (
        <>
          <div className="mt-4 flex items-center gap-2 text-xs text-neutral-500">
            <span className="rounded-full border border-white/10 px-2 py-0.5">
              brain: <span className="font-mono text-neutral-300">{config.brain_url}</span>
            </span>
            {config.api_key_prefix ? (
              <span className="rounded-full border border-white/10 px-2 py-0.5">
                key: <span className="font-mono text-neutral-300">{config.api_key_prefix}…</span>
              </span>
            ) : (
              <span className="rounded-full border border-amber-500/30 px-2 py-0.5 text-amber-300/90">
                placeholder key — generate one
              </span>
            )}
          </div>

          {minted && (
            <p className="mt-3 rounded-lg border border-accent/30 bg-accent/[0.06] px-3 py-2 text-xs text-accent-soft">
              A fresh key is embedded below and shown only once. Copy the whole config now.
            </p>
          )}

          <div className="relative mt-3">
            <pre className="max-h-72 overflow-auto rounded-xl border border-white/[0.07] bg-ink-950 p-4 font-mono text-[11px] leading-relaxed text-neutral-300">
              {config.snippet}
            </pre>
            <div className="absolute right-2 top-2">
              <CopyButton value={config.snippet} label="Copy config" />
            </div>
          </div>

          <p className="mt-3 whitespace-pre-wrap text-xs leading-relaxed text-neutral-500">
            {config.instructions}
          </p>
        </>
      )}
    </div>
  );
}
