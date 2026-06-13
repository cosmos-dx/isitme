import { useEffect, useMemo, useState } from "react";
import { Globe, ShieldCheck, TrendingUp } from "lucide-react";
import { api } from "../lib/api";
import type { GraphData, GraphNode, Profile, Stats } from "../lib/types";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-5">
      <div className="text-3xl font-semibold tracking-tight text-neutral-50 tnum">
        {value}
      </div>
      <div className="mt-1 text-xs uppercase tracking-wide text-neutral-500">
        {label}
      </div>
    </div>
  );
}

export function OverviewCards() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    Promise.all([api.stats(), api.profile(), api.graph()])
      .then(([s, p, g]) => {
        setStats(s);
        setProfile(p);
        setGraph(g);
      })
      .catch(() => setOffline(true));
  }, []);

  const topSites = useMemo((): GraphNode[] => {
    if (!graph) return [];
    return graph.nodes
      .filter((n) => n.type === "domain")
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 8);
  }, [graph]);

  const topQueries = useMemo((): GraphNode[] => {
    if (!graph) return [];
    return graph.nodes
      .filter((n) => n.type === "query" || n.type === "topic")
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 10);
  }, [graph]);

  return (
    <div className="space-y-5">
      {/* ---- stat counters ---- */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat
          label="Events"
          value={stats?.events ?? (offline ? "—" : "·")}
        />
        <Stat label="Nodes" value={stats?.nodes ?? (offline ? "—" : "·")} />
        <Stat label="Edges" value={stats?.edges ?? (offline ? "—" : "·")} />
        <Stat
          label="Memories"
          value={stats?.memories ?? (offline ? "—" : "·")}
        />
      </div>

      {/* ---- mindset ---- */}
      <div className="card p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-neutral-100">Mindset</h3>
          {stats && (
            <div className="flex gap-2 text-[11px]">
              <span className="rounded-full border border-white/10 px-2 py-0.5 text-neutral-400">
                mode: {stats.mode}
              </span>
              <span className="rounded-full border border-white/10 px-2 py-0.5 text-neutral-400">
                embed: {stats.embedding_provider}
              </span>
            </div>
          )}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-neutral-400">
          {profile?.summary?.trim()
            ? profile.summary
            : offline
              ? "Core Brain offline — start it on :8077 to derive your mindset."
              : "No profile yet. As you browse and chat, your interests and patterns appear here."}
        </p>

        {profile && profile.interests.length > 0 && (
          <div className="mt-5">
            <div className="eyebrow mb-2">Top interests</div>
            <div className="flex flex-wrap gap-2">
              {profile.interests.slice(0, 12).map((i) => (
                <span
                  key={i.topic}
                  className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1 text-xs text-neutral-300"
                >
                  {i.topic}
                  <span className="ml-1.5 font-mono text-[10px] text-neutral-500 tnum">
                    {i.weight.toFixed(1)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {profile && profile.top_domains.length > 0 && (
          <div className="mt-5">
            <div className="eyebrow mb-2">Top domains</div>
            <div className="flex flex-wrap gap-2">
              {profile.top_domains.slice(0, 10).map((d) => (
                <span
                  key={d.topic}
                  className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1 text-xs text-neutral-300"
                >
                  {d.topic}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ---- top sites ---- */}
      <div className="card p-6">
        <div className="flex items-center gap-2">
          <Globe size={16} className="text-accent-soft" />
          <h3 className="text-sm font-medium text-neutral-100">Top Sites</h3>
        </div>
        {topSites.length === 0 && !offline && (
          <p className="mt-3 text-xs text-neutral-500">
            Browse the web to populate your top sites.
          </p>
        )}
        {topSites.length > 0 && (
          <div className="mt-4 space-y-2.5">
            {topSites.map((site, idx) => (
              <div key={site.id} className="flex items-center gap-3">
                <span className="w-5 text-right font-mono text-[11px] text-neutral-600 tnum">
                  {idx + 1}
                </span>
                <div className="flex flex-1 items-center gap-2 min-w-0">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: site.color }}
                  />
                  <span className="truncate text-sm text-neutral-300">
                    {site.label}
                  </span>
                </div>
                <span className="shrink-0 font-mono text-[11px] text-neutral-500 tnum">
                  {site.weight.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ---- top queries & topics ---- */}
      <div className="card p-6">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-cyan-glow" />
          <h3 className="text-sm font-medium text-neutral-100">
            Top Queries & Topics
          </h3>
        </div>
        {topQueries.length === 0 && !offline && (
          <p className="mt-3 text-xs text-neutral-500">
            Search the web and your topics will appear here.
          </p>
        )}
        {topQueries.length > 0 && (
          <div className="mt-4 space-y-2.5">
            {topQueries.map((item, idx) => (
              <div key={item.id} className="flex items-center gap-3">
                <span className="w-5 text-right font-mono text-[11px] text-neutral-600 tnum">
                  {idx + 1}
                </span>
                <span className="flex-1 truncate text-sm text-neutral-300">
                  {item.label}
                </span>
                <span
                  className="inline-block rounded-full px-1.5 py-0.5 text-[9px] uppercase tracking-wide"
                  style={{
                    background: `${item.color}22`,
                    color: item.color,
                  }}
                >
                  {item.type}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-neutral-500 tnum">
                  {item.weight.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ---- security & redaction ---- */}
      <div className="card p-6">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-emerald-400" />
          <h3 className="text-sm font-medium text-neutral-100">
            Security & Redaction
          </h3>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-neutral-400">
          No leaks detected — redaction is active. Sensitive content (passwords,
          banking, health, PII) is scrubbed before storage.
        </p>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-xs text-emerald-300/80">
            Redaction active · Local-first · No cloud sync
          </span>
        </div>
        {profile && profile.recurring_opinions.length > 0 && (
          <div className="mt-4">
            <div className="eyebrow mb-2">Recurring opinions tracked</div>
            <div className="space-y-1.5">
              {profile.recurring_opinions.slice(0, 4).map((op) => (
                <div
                  key={op.text}
                  className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-3 py-2"
                >
                  <span className="truncate text-xs text-neutral-300">
                    {op.text}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-neutral-500 tnum">
                    {op.weight.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
