import { useEffect } from "react";
import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";

function FullPageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950">
      <div className="flex items-center gap-3 text-neutral-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
        <span className="text-sm tracking-wide">loading your brain…</span>
      </div>
    </div>
  );
}

/** After landing on /dashboard from OAuth, try to tell the isitme extension
 * that login succeeded so it can authenticate using the same user. The
 * extension listens for external messages and can silently re-auth via
 * launchWebAuthFlow (same Google session). This is best-effort; if no
 * extension is installed it silently fails. */
function useNotifyExtension(user: { email?: string | null } | null) {
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    if (!user) return;
    if (params.get("ext_auth") !== "1") return;
    params.delete("ext_auth");
    setParams(params, { replace: true });
    try {
      if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
        chrome.runtime.sendMessage({ kind: "signIn" }).catch(() => {});
      }
    } catch {
      // no extension
    }
  }, [user, params, setParams]);
}

function DashboardRoute() {
  const { user, loading } = useAuth();
  useNotifyExtension(user);

  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/" replace />;
  return <Dashboard />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/dashboard" element={<DashboardRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
