import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import { api } from "../lib/api";
import type { GraphData, GraphNode } from "../lib/types";

interface Neighbor {
  id: string;
  label: string;
  type: string;
  relation: string;
  weight: number;
  direction: "out" | "in";
}

function useContainerSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 600, height: 520 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setSize({ width: Math.max(280, r.width), height: Math.max(360, r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

export function BrainGraph() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const { ref, size } = useContainerSize();

  useEffect(() => {
    let active = true;
    api
      .graph()
      .then((g) => {
        if (active) setData(g);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Build adjacency from string ids BEFORE react-force-graph mutates link refs.
  const { nodeById, adjacency } = useMemo(() => {
    const byId = new Map<string, GraphNode>();
    const adj = new Map<string, Neighbor[]>();
    if (!data) return { nodeById: byId, adjacency: adj };
    for (const n of data.nodes) byId.set(n.id, n);
    const push = (from: string, n: Neighbor) => {
      const list = adj.get(from) ?? [];
      list.push(n);
      adj.set(from, list);
    };
    for (const l of data.links) {
      const s = typeof l.source === "string" ? l.source : (l.source as { id: string }).id;
      const t = typeof l.target === "string" ? l.target : (l.target as { id: string }).id;
      const sn = byId.get(s);
      const tn = byId.get(t);
      if (sn && tn) {
        push(s, { id: t, label: tn.label, type: tn.type, relation: l.relation, weight: l.weight, direction: "out" });
        push(t, { id: s, label: sn.label, type: sn.type, relation: l.relation, weight: l.weight, direction: "in" });
      }
    }
    return { nodeById: byId, adjacency: adj };
  }, [data]);

  const selectedNeighbors = useMemo(() => {
    if (!selected) return [];
    return [...(adjacency.get(selected.id) ?? [])]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 12);
  }, [selected, adjacency]);

  const isEmpty = !loading && !error && (!data || data.nodes.length === 0);

  return (
    <div className="card relative overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
        <div>
          <h3 className="text-sm font-medium text-neutral-100">Your brain in 3D</h3>
          <p className="text-xs text-neutral-500">
            The space, the relations, the queries — colored by type, sized by weight.
          </p>
        </div>
        {data && (
          <span className="font-mono text-xs text-neutral-500 tnum">
            {data.nodes.length} nodes · {data.links.length} links
          </span>
        )}
      </div>

      <div ref={ref} className="relative h-[520px] w-full bg-ink-950">
        {loading && (
          <div className="absolute inset-0 grid place-items-center text-sm text-neutral-500">
            <span className="animate-pulse">rendering graph…</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-neutral-400">
            <div>
              <p className="text-neutral-300">Couldn’t reach the Core Brain.</p>
              <p className="mt-1 text-xs text-neutral-500">{error}</p>
              <p className="mt-3 text-xs text-neutral-600">
                Start it with <span className="font-mono text-neutral-400">brain serve</span> on
                :8077, then refresh.
              </p>
            </div>
          </div>
        )}
        {isEmpty && (
          <div className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-neutral-400">
            <div>
              <p className="text-neutral-300">Your brain is empty — for now.</p>
              <p className="mt-1 text-xs text-neutral-500">
                Install the extension or seed a few events to watch the graph grow.
              </p>
            </div>
          </div>
        )}
        {!loading && !error && data && data.nodes.length > 0 && (
          <ForceGraph3D
            graphData={data}
            width={size.width}
            height={size.height}
            backgroundColor="#08080a"
            nodeLabel={(n) => {
              const node = n as GraphNode;
              return `${node.label} · ${node.type} (${node.weight})`;
            }}
            nodeColor={(n) => (n as GraphNode).color}
            nodeVal={(n) => Math.max(1, Math.cbrt((n as GraphNode).val) * 2)}
            nodeOpacity={0.95}
            linkColor={() => "rgba(255,255,255,0.16)"}
            linkWidth={(l) => Math.min(2, 0.3 + (l as { weight: number }).weight * 0.4)}
            linkDirectionalParticles={0}
            onNodeClick={(n) => setSelected(nodeById.get((n as GraphNode).id) ?? null)}
            warmupTicks={40}
            cooldownTime={4000}
          />
        )}

        {selected && (
          <div className="absolute right-3 top-3 w-72 rounded-xl border border-white/[0.08] bg-ink-900/90 p-4 backdrop-blur-md">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span
                  className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
                  style={{ background: `${selected.color}22`, color: selected.color }}
                >
                  {selected.type}
                </span>
                <h4 className="mt-2 break-words text-sm font-medium text-neutral-100">
                  {selected.label}
                </h4>
                <p className="mt-1 font-mono text-xs text-neutral-500 tnum">
                  weight {selected.weight}
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-neutral-500 transition-colors hover:text-neutral-200"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="mt-3 max-h-56 space-y-1.5 overflow-auto pr-1">
              {selectedNeighbors.length === 0 && (
                <p className="text-xs text-neutral-500">No connections.</p>
              )}
              {selectedNeighbors.map((nb, i) => (
                <div
                  key={`${nb.id}-${i}`}
                  className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-2.5 py-1.5"
                >
                  <span className="truncate text-xs text-neutral-300">{nb.label}</span>
                  <span className="shrink-0 font-mono text-[10px] text-neutral-500">
                    {nb.relation}
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
