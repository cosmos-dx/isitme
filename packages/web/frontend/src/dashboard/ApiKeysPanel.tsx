import { useEffect, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { api } from "../lib/api";
import type { ApiKey, ApiKeyCreated } from "../lib/types";

export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const load = () =>
    api
      .listKeys()
      .then(setKeys)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    void load();
  }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createKey(name.trim() || "default");
      setJustCreated(created);
      setName("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    await api.revokeKey(id);
    await load();
  };

  return (
    <div className="card p-6">
      <h3 className="text-sm font-medium text-neutral-100">API keys</h3>
      <p className="mt-1 text-xs text-neutral-500">
        These authenticate the browser extension and MCP clients to your brain.
      </p>

      <div className="mt-4 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="key name (e.g. laptop-extension)"
          className="flex-1 rounded-xl border border-white/[0.08] bg-ink-950 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-accent/50 focus:outline-none"
        />
        <button onClick={create} disabled={busy} className="btn-primary !px-4">
          {busy ? "Creating…" : "Create"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-rose-400/80">{error}</p>}

      {justCreated && (
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/[0.06] p-4">
          <p className="text-xs font-medium text-accent-soft">
            Copy this key now — it’s shown only once.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 truncate rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-neutral-200">
              {justCreated.key}
            </code>
            <CopyButton value={justCreated.key} />
          </div>
        </div>
      )}

      <div className="mt-5 space-y-2">
        {keys.length === 0 && (
          <p className="text-sm text-neutral-500">No keys yet.</p>
        )}
        {keys.map((k) => (
          <div
            key={k.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm text-neutral-200">{k.name}</span>
                {k.revoked && (
                  <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] text-rose-300">
                    revoked
                  </span>
                )}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-neutral-500">
                {k.prefix}…· created {new Date(k.created_at).toLocaleDateString()}
                {k.last_used ? ` · used ${new Date(k.last_used).toLocaleDateString()}` : ""}
              </div>
            </div>
            {!k.revoked && (
              <button
                onClick={() => revoke(k.id)}
                className="shrink-0 text-xs text-neutral-500 transition-colors hover:text-rose-300"
              >
                Revoke
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
