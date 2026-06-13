import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import {
  Box,
  LayoutList,
  Loader2,
  Maximize2,
  Minimize2,
  Search,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type { GraphData, GraphLink, GraphNode, SearchResult } from "../lib/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RELATION_COLORS: Record<string, string> = {
  visited: "#4f8cff",
  searched: "#34d399",
  about: "#22d3ee",
  interested_in: "#eab308",
  holds: "#f472b6",
  led_to: "#f97316",
  chatted_with: "#f59e0b",
  related_to: "#a78bfa",
  used: "#6366f1",
  mentioned: "#94a3b8",
  knows: "#fb7185",
  references: "#818cf8",
};

function getRelationColor(relation: string): string {
  return RELATION_COLORS[relation] ?? "#555";
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Neighbor {
  id: string;
  label: string;
  type: string;
  relation: string;
  weight: number;
  direction: "out" | "in";
  color: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GraphLegend({ relations }: { relations: string[] }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1.5 border-t border-white/[0.06] px-5 py-2.5">
      <span className="mr-1 text-[10px] font-medium uppercase tracking-wide text-neutral-600">
        Relations
      </span>
      {relations.map((r) => (
        <div key={r} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: getRelationColor(r) }}
          />
          <span className="text-[10px] text-neutral-500">
            {r.replace(/_/g, " ")}
          </span>
        </div>
      ))}
    </div>
  );
}

function KnowledgeListView({
  data,
  adjacency,
  onSelect,
}: {
  data: GraphData;
  adjacency: Map<string, Neighbor[]>;
  onSelect: (node: GraphNode) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const grouped = useMemo(() => {
    const groups = new Map<string, GraphNode[]>();
    for (const node of data.nodes) {
      const list = groups.get(node.type) ?? [];
      list.push(node);
      groups.set(node.type, list);
    }
    for (const [, nodes] of groups) {
      nodes.sort((a, b) => b.weight - a.weight);
    }
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [data]);

  const toggle = (type: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  return (
    <div className="h-full space-y-3 overflow-auto p-4">
      {grouped.map(([type, nodes]) => {
        const isOpen = expanded.has(type);
        const shown = isOpen ? nodes.slice(0, 50) : nodes.slice(0, 5);
        return (
          <div
            key={type}
            className="rounded-xl border border-white/[0.06] bg-white/[0.02]"
          >
            <button
              onClick={() => toggle(type)}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left"
            >
              <span className="text-[10px] text-neutral-600">
                {isOpen ? "▾" : "▸"}
              </span>
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: nodes[0]?.color }}
              />
              <span className="text-sm font-medium capitalize text-neutral-200">
                {type}
              </span>
              <span className="text-xs text-neutral-500">
                ({nodes.length})
              </span>
            </button>
            <div className="border-t border-white/[0.04] px-2 pb-2">
              {shown.map((node) => (
                <button
                  key={node.id}
                  onClick={() => onSelect(node)}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-white/[0.04]"
                >
                  <span className="flex-1 truncate text-xs text-neutral-300">
                    {node.label}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-neutral-500 tnum">
                    w{node.weight.toFixed(1)}
                  </span>
                  <span className="shrink-0 text-[10px] text-neutral-600">
                    {adjacency.get(node.id)?.length ?? 0} links
                  </span>
                </button>
              ))}
              {nodes.length > shown.length && (
                <button
                  onClick={() => toggle(type)}
                  className="px-3 py-1 text-[10px] text-accent-soft hover:underline"
                >
                  {isOpen
                    ? "Show less"
                    : `+ ${nodes.length - shown.length} more`}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

function useContainerSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 600, height: 520 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r)
        setSize({
          width: Math.max(280, r.width),
          height: Math.max(360, r.height),
        });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function BrainGraph() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [viewMode, setViewMode] = useState<"3d" | "list">("3d");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- ForceGraph methods ref
  const fgRef = useRef<any>(undefined);
  const { ref, size } = useContainerSize();

  // --- data fetch ----------------------------------------------------------
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

  // --- fullscreen side-effects ---------------------------------------------
  useEffect(() => {
    if (!fullscreen) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  // --- adjacency map -------------------------------------------------------
  const { nodeById, adjacency } = useMemo(() => {
    const byId = new Map<string, GraphNode>();
    const adj = new Map<string, Neighbor[]>();
    if (!data) return { nodeById: byId, adjacency: adj };
    for (const n of data.nodes) byId.set(n.id, n);
    const push = (from: string, nb: Neighbor) => {
      const list = adj.get(from) ?? [];
      list.push(nb);
      adj.set(from, list);
    };
    for (const l of data.links) {
      const s =
        typeof l.source === "string"
          ? l.source
          : (l.source as { id: string }).id;
      const t =
        typeof l.target === "string"
          ? l.target
          : (l.target as { id: string }).id;
      const sn = byId.get(s);
      const tn = byId.get(t);
      if (sn && tn) {
        push(s, {
          id: t,
          label: tn.label,
          type: tn.type,
          relation: l.relation,
          weight: l.weight,
          direction: "out",
          color: tn.color,
        });
        push(t, {
          id: s,
          label: sn.label,
          type: sn.type,
          relation: l.relation,
          weight: l.weight,
          direction: "in",
          color: sn.color,
        });
      }
    }
    return { nodeById: byId, adjacency: adj };
  }, [data]);

  // --- unique relation types for legend ------------------------------------
  const uniqueRelations = useMemo(() => {
    if (!data) return [];
    const set = new Set<string>();
    for (const l of data.links) set.add(l.relation);
    return [...set].sort();
  }, [data]);

  // --- selected node's neighbours grouped by relation ----------------------
  const groupedNeighbors = useMemo(() => {
    if (!selected) return new Map<string, Neighbor[]>();
    const all = adjacency.get(selected.id) ?? [];
    const groups = new Map<string, Neighbor[]>();
    for (const nb of all) {
      const list = groups.get(nb.relation) ?? [];
      list.push(nb);
      groups.set(nb.relation, list);
    }
    for (const [, nbs] of groups) {
      nbs.sort((a, b) => b.weight - a.weight);
    }
    return groups;
  }, [selected, adjacency]);

  // --- search highlight ----------------------------------------------------
  const highlightNodeIds = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q || !data) return null;
    const ids = new Set<string>();
    for (const n of data.nodes) {
      if (
        n.label.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q) ||
        n.id.toLowerCase().includes(q)
      ) {
        ids.add(n.id);
      }
    }
    return ids.size > 0 ? ids : null;
  }, [searchQuery, data]);

  // --- camera focus --------------------------------------------------------
  const focusOnNode = useCallback(
    (nodeId: string) => {
      if (!fgRef.current || !data) return;
      type SimNode = GraphNode & { x?: number; y?: number; z?: number };
      const node = data.nodes.find((n) => n.id === nodeId) as
        | SimNode
        | undefined;
      if (!node || node.x === undefined) return;
      const nx = node.x;
      const ny = node.y ?? 0;
      const nz = node.z ?? 0;
      const dist = 80;
      const hyp = Math.hypot(nx, ny, nz) || 1;
      const ratio = 1 + dist / hyp;
      type FG = { cameraPosition: (p: Record<string, number>, l: Record<string, number>, ms: number) => void };
      (fgRef.current as FG).cameraPosition(
        { x: nx * ratio, y: ny * ratio, z: nz * ratio },
        { x: nx, y: ny, z: nz },
        1500,
      );
    },
    [data],
  );

  // --- semantic search via API ---------------------------------------------
  const handleSemanticSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    try {
      const res = await api.search(q);
      setSearchResults(res.results ?? []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleSemanticSearch();
      if (highlightNodeIds && highlightNodeIds.size === 1) {
        focusOnNode([...highlightNodeIds][0]);
      }
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setSearchResults([]);
  };

  const isEmpty = !loading && !error && (!data || data.nodes.length === 0);

  // -----------------------------------------------------------------------
  return (
    <div
      className={
        fullscreen
          ? "fixed inset-0 z-50 flex flex-col bg-ink-950"
          : "card relative overflow-hidden"
      }
    >
      {/* ---- header ---- */}
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-neutral-100">
            Your brain in 3D
          </h3>
          <p className="text-xs text-neutral-500">
            Colored by type, sized by weight, edges by relation.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {data && (
            <span className="hidden font-mono text-xs text-neutral-500 tnum sm:inline">
              {data.nodes.length} nodes · {data.links.length} links
            </span>
          )}

          {/* view mode toggle */}
          <div className="flex rounded-lg border border-white/[0.08] bg-white/[0.02]">
            <button
              onClick={() => setViewMode("3d")}
              className={`flex items-center gap-1 rounded-l-lg px-2.5 py-1.5 text-[11px] transition-colors ${
                viewMode === "3d"
                  ? "bg-white/[0.08] text-neutral-100"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
              title="3D View"
            >
              <Box size={13} /> 3D
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`flex items-center gap-1 rounded-r-lg px-2.5 py-1.5 text-[11px] transition-colors ${
                viewMode === "list"
                  ? "bg-white/[0.08] text-neutral-100"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
              title="Knowledge Graph"
            >
              <LayoutList size={13} /> Knowledge Graph
            </button>
          </div>

          {/* fullscreen toggle */}
          <button
            onClick={() => setFullscreen((f) => !f)}
            className="rounded-lg border border-white/[0.08] p-1.5 text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-200"
            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>
      </div>

      {/* ---- search bar (3D mode only) ---- */}
      {viewMode === "3d" && (
        <div className="border-b border-white/[0.06] px-5 py-2">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500"
              />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search nodes… (Enter for brain search)"
                className="w-full rounded-lg border border-white/[0.08] bg-ink-950 py-2 pl-9 pr-8 text-xs text-neutral-200 placeholder:text-neutral-600 focus:border-accent/50 focus:outline-none"
              />
              {searchQuery && (
                <button
                  onClick={clearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <button
              onClick={() => void handleSemanticSearch()}
              disabled={searching || !searchQuery.trim()}
              className="btn-ghost !px-3 !py-1.5 text-xs"
            >
              {searching ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                "Search Brain"
              )}
            </button>
          </div>

          {searchQuery.trim() && (
            <p className="mt-1.5 text-[10px] text-neutral-500">
              {highlightNodeIds?.size ?? 0} node
              {(highlightNodeIds?.size ?? 0) !== 1 ? "s" : ""} matching &quot;
              {searchQuery}&quot;
            </p>
          )}

          {searchResults.length > 0 && (
            <div className="mt-2 max-h-36 space-y-1.5 overflow-auto">
              <span className="text-[10px] font-medium uppercase tracking-wide text-neutral-600">
                Brain memories
              </span>
              {searchResults.slice(0, 5).map((r) => (
                <div
                  key={r.id}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-1.5 text-[11px] text-neutral-400"
                >
                  <span className="mr-2 font-mono text-[10px] text-neutral-600 tnum">
                    {r.score.toFixed(2)}
                  </span>
                  {r.text.slice(0, 140)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---- graph / list canvas ---- */}
      <div
        ref={ref}
        className={`relative w-full bg-ink-950 ${
          fullscreen ? "flex-1" : "h-[520px]"
        }`}
      >
        {loading && (
          <div className="absolute inset-0 grid place-items-center text-sm text-neutral-500">
            <span className="animate-pulse">rendering graph…</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-neutral-400">
            <div>
              <p className="text-neutral-300">
                Couldn&apos;t reach the Core Brain.
              </p>
              <p className="mt-1 text-xs text-neutral-500">{error}</p>
              <p className="mt-3 text-xs text-neutral-600">
                Start it with{" "}
                <span className="font-mono text-neutral-400">brain serve</span>{" "}
                on :8077, then refresh.
              </p>
            </div>
          </div>
        )}
        {isEmpty && (
          <div className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-neutral-400">
            <div>
              <p className="text-neutral-300">
                Your brain is empty — for now.
              </p>
              <p className="mt-1 text-xs text-neutral-500">
                Install the extension or seed a few events to watch the graph
                grow.
              </p>
            </div>
          </div>
        )}

        {/* 3D force graph */}
        {!loading && !error && data && data.nodes.length > 0 && viewMode === "3d" && (
          <ForceGraph3D
            ref={fgRef}
            graphData={data}
            width={size.width}
            height={size.height}
            backgroundColor="#08080a"
            nodeLabel={(n) => {
              const node = n as GraphNode;
              return `${node.label} · ${node.type} (w: ${node.weight})`;
            }}
            nodeColor={(n) => {
              const node = n as GraphNode;
              if (highlightNodeIds && !highlightNodeIds.has(node.id))
                return "rgba(100,100,100,0.15)";
              return node.color;
            }}
            nodeVal={(n) => {
              const node = n as GraphNode;
              const base = Math.max(1, Math.cbrt(node.val) * 2);
              if (highlightNodeIds?.has(node.id)) return base * 1.8;
              return base;
            }}
            nodeOpacity={0.95}
            linkLabel={(l) => {
              const link = l as GraphLink;
              return `${link.relation} (w: ${link.weight})`;
            }}
            linkColor={(l) => {
              const link = l as GraphLink;
              if (highlightNodeIds) {
                const src =
                  typeof link.source === "string"
                    ? link.source
                    : (link.source as { id: string }).id;
                const tgt =
                  typeof link.target === "string"
                    ? link.target
                    : (link.target as { id: string }).id;
                if (!highlightNodeIds.has(src) && !highlightNodeIds.has(tgt))
                  return "rgba(255,255,255,0.03)";
              }
              return getRelationColor(link.relation);
            }}
            linkWidth={(l) =>
              Math.min(2.5, 0.3 + (l as { weight: number }).weight * 0.5)
            }
            linkDirectionalParticles={0}
            onNodeClick={(n) => {
              type SimNode = GraphNode & {
                x?: number;
                y?: number;
                z?: number;
              };
              const node = n as SimNode;
              setSelected(nodeById.get(node.id) ?? null);
              if (fgRef.current && node.x !== undefined) {
                const nx = node.x;
                const ny = node.y ?? 0;
                const nz = node.z ?? 0;
                const dist = 80;
                const hyp = Math.hypot(nx, ny, nz) || 1;
                const ratio = 1 + dist / hyp;
                type FG = {
                  cameraPosition: (
                    p: Record<string, number>,
                    l: Record<string, number>,
                    ms: number,
                  ) => void;
                };
                (fgRef.current as FG).cameraPosition(
                  { x: nx * ratio, y: ny * ratio, z: nz * ratio },
                  { x: nx, y: ny, z: nz },
                  1500,
                );
              }
            }}
            warmupTicks={40}
            cooldownTime={4000}
          />
        )}

        {/* Knowledge-graph list view */}
        {!loading &&
          !error &&
          data &&
          data.nodes.length > 0 &&
          viewMode === "list" && (
            <KnowledgeListView
              data={data}
              adjacency={adjacency}
              onSelect={(node) => setSelected(node)}
            />
          )}

        {/* ---- node detail panel ---- */}
        {selected && (
          <div
            className={`absolute right-3 top-3 ${
              fullscreen ? "bottom-3" : "max-h-[500px]"
            } flex w-80 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900/95 backdrop-blur-md`}
          >
            {/* header */}
            <div className="border-b border-white/[0.06] p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <span
                    className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
                    style={{
                      background: `${selected.color}22`,
                      color: selected.color,
                    }}
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
                  <X size={16} />
                </button>
              </div>

              {/* attributes */}
              {Object.keys(selected.attributes).length > 0 && (
                <div className="mt-3 space-y-1">
                  {Object.entries(selected.attributes)
                    .slice(0, 6)
                    .map(([k, v]) => (
                      <div
                        key={k}
                        className="flex justify-between gap-2 text-[11px]"
                      >
                        <span className="shrink-0 text-neutral-500">{k}</span>
                        <span className="truncate text-neutral-400">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>

            {/* connections grouped by relation type */}
            <div className="flex-1 space-y-3 overflow-auto p-4">
              {groupedNeighbors.size === 0 && (
                <p className="text-xs text-neutral-500">No connections.</p>
              )}
              {[...groupedNeighbors.entries()].map(([relation, nbs]) => (
                <div key={relation}>
                  <div className="mb-1.5 flex items-center gap-1.5">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: getRelationColor(relation) }}
                    />
                    <span className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">
                      {relation.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] text-neutral-600">
                      ({nbs.length})
                    </span>
                  </div>
                  <div className="space-y-1">
                    {nbs.map((nb, i) => (
                      <button
                        key={`${nb.id}-${i}`}
                        onClick={() => {
                          setSelected(nodeById.get(nb.id) ?? null);
                          focusOnNode(nb.id);
                        }}
                        className="flex w-full items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-2.5 py-1.5 text-left transition-colors hover:bg-white/[0.06]"
                      >
                        <div className="flex min-w-0 items-center gap-1.5">
                          <span
                            className="h-1.5 w-1.5 shrink-0 rounded-full"
                            style={{ background: nb.color }}
                          />
                          <span className="truncate text-xs text-neutral-300">
                            {nb.label}
                          </span>
                        </div>
                        <span className="shrink-0 font-mono text-[10px] text-neutral-500 tnum">
                          {nb.weight.toFixed(1)}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ---- legend ---- */}
      {data && uniqueRelations.length > 0 && viewMode === "3d" && (
        <GraphLegend relations={uniqueRelations} />
      )}
    </div>
  );
}
