import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Logo } from "../components/Logo";
import { ApiKeysPanel } from "../dashboard/ApiKeysPanel";
import { AskBox } from "../dashboard/AskBox";
import { BrainGraph } from "../dashboard/BrainGraph";
import { ExtensionPanel } from "../dashboard/ExtensionPanel";
import { McpPanel } from "../dashboard/McpPanel";
import { OverviewCards } from "../dashboard/OverviewCards";
import { SetupWizard } from "../dashboard/SetupWizard";
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
      <div className="container-content flex h-14 items-center justify-between sm:h-16">
        <Logo />
        <div className="flex items-center gap-2 sm:gap-3">
          {user?.picture ? (
            <img
              src={user.picture}
              alt={user.name ?? "you"}
              className="h-6 w-6 rounded-full border border-white/10 sm:h-7 sm:w-7"
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className="grid h-6 w-6 place-items-center rounded-full bg-accent/20 text-[10px] text-accent-soft sm:h-7 sm:w-7 sm:text-xs">
              {(user?.name ?? user?.email ?? "?").slice(0, 1).toUpperCase()}
            </span>
          )}
          <span className="hidden text-sm text-neutral-400 sm:inline">
            {user?.name ?? user?.email}
          </span>
          <button onClick={handleLogout} className="btn-ghost !px-2 !py-1 text-[11px] sm:!px-3 sm:!py-1.5 sm:text-xs">
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("overview");
  const [showSetup, setShowSetup] = useState(
    () => !localStorage.getItem("isitme.setup_dismissed"),
  );

  const dismissSetup = useCallback(() => {
    localStorage.setItem("isitme.setup_dismissed", "1");
    setShowSetup(false);
  }, []);

  if (showSetup) {
    return (
      <div className="min-h-screen">
        <TopBar />
        <main className="container-content py-12 sm:py-20">
          <SetupWizard onDismiss={dismissSetup} />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="container-content py-6 sm:py-8">
        <div className="mb-2">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-50 sm:text-2xl">
            How your brain looks
          </h1>
          <p className="mt-1 text-xs text-neutral-500 sm:text-sm">
            The space, the relations, the queries — and the keys that make it portable.
          </p>
        </div>

        <div className="mt-6">
          <BrainGraph />
        </div>

        <div className="mt-6 -mx-6 overflow-x-auto px-6 sm:mx-0 sm:px-0">
          <div className="flex gap-1 border-b border-white/[0.06] pb-px min-w-max sm:min-w-0 sm:flex-wrap sm:gap-1.5">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`whitespace-nowrap rounded-t-lg px-3 py-1.5 text-xs transition-colors sm:px-4 sm:py-2 sm:text-sm ${
                  tab === t.id
                    ? "bg-white/[0.04] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-300"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 pb-12 sm:mt-6 sm:pb-16">
          {tab === "overview" && (
            <div className="grid gap-4 sm:gap-6 lg:grid-cols-[1.3fr_1fr]">
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
