import { Navigate, Route, Routes } from "react-router-dom";
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

export default function App() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/dashboard"
        element={
          loading ? (
            <FullPageLoader />
          ) : user ? (
            <Dashboard />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
