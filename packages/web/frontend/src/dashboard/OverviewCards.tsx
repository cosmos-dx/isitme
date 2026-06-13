import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Profile, Stats } from "../lib/types";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-5">
      <div className="text-3xl font-semibold tracking-tight text-neutral-50 tnum">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-neutral-500">{label}</div>
    </div>
  );
}

export function OverviewCards() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    Promise.all([api.stats(), api.profile()])
      .then(([s, p]) => {
        setStats(s);
        setProfile(p);
      })
      .catch(() => setOffline(true));
  }, []);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Events" value={stats?.events ?? (offline ? "—" : "·")} />
        <Stat label="Nodes" value={stats?.nodes ?? (offline ? "—" : "·")} />
        <Stat label="Edges" value={stats?.edges ?? (offline ? "—" : "·")} />
        <Stat label="Memories" value={stats?.memories ?? (offline ? "—" : "·")} />
      </div>

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
    </div>
  );
}
