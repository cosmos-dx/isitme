import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Logo } from "../components/Logo";
import { ApiKeysPanel } from "../dashboard/ApiKeysPanel";
import { AskBox } from "../dashboard/AskBox";
import { BrainGraph } from "../dashboard/BrainGraph";
import { ExtensionPanel } from "../dashboard/ExtensionPanel";
import { McpPanel } from "../dashboard/McpPanel";
import { OverviewCards } from "../dashboard/OverviewCards";
import { useAuth } from "../hooks/useAuth";

type Tab = "overview" | "keys" | "mcp" | "extension";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "keys", label: "API keys" },
  { id: "mcp", label: "MCP config" },
  { id: "extension", label: "Extension" },
];

function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="container-content flex h-16 items-center justify-between">
        <Logo />
        <div className="flex items-center gap-3">
          {user?.picture ? (
            <img
              src={user.picture}
              alt={user.name ?? "you"}
              className="h-7 w-7 rounded-full border border-white/10"
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className="grid h-7 w-7 place-items-center rounded-full bg-accent/20 text-xs text-accent-soft">
              {(user?.name ?? user?.email ?? "?").slice(0, 1).toUpperCase()}
            </span>
          )}
          <span className="hidden text-sm text-neutral-400 sm:inline">
            {user?.name ?? user?.email}
          </span>
          <button onClick={handleLogout} className="btn-ghost !px-3 !py-1.5 text-xs">
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="container-content py-8">
        <div className="mb-2">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-50">
            How your brain looks
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            The space, the relations, the queries — and the keys that make it portable.
          </p>
        </div>

        <div className="mt-6">
          <BrainGraph />
        </div>

        <div className="mt-8 flex flex-wrap gap-1.5 border-b border-white/[0.06] pb-px">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-t-lg px-4 py-2 text-sm transition-colors ${
                tab === t.id
                  ? "bg-white/[0.04] text-neutral-100"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="mt-6 pb-16">
          {tab === "overview" && (
            <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
              <OverviewCards />
              <AskBox />
            </div>
          )}
          {tab === "keys" && (
            <div className="max-w-2xl">
              <ApiKeysPanel />
            </div>
          )}
          {tab === "mcp" && (
            <div className="max-w-3xl">
              <McpPanel />
            </div>
          )}
          {tab === "extension" && (
            <div className="max-w-2xl">
              <ExtensionPanel />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
