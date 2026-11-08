import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { useRoles } from "./auth";
import FleetPage from "./pages/FleetPage";
import EnginePage from "./pages/EnginePage";
import AlertsPage from "./pages/AlertsPage";
import PipelinePage from "./pages/PipelinePage";

function SignIn() {
  const auth = useAuth();
  return (
    <main className="signin">
      <div className="signin-card">
        <img src="/favicon.svg" alt="" width={48} height={48} />
        <h1>Fleet Health Console</h1>
        <p>Live remaining-useful-life predictions for a turbofan fleet, streamed through Kafka.</p>
        {auth.error && <p className="error">Sign-in failed: {auth.error.message}</p>}
        <button className="primary" onClick={() => auth.signinRedirect()}>
          Sign in with Keycloak
        </button>
      </div>
    </main>
  );
}

export default function App() {
  const auth = useAuth();
  const { roles } = useRoles();

  if (auth.isLoading) return <main className="signin">Loading…</main>;
  if (!auth.isAuthenticated) return <SignIn />;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>Fleet Health</span>
        </div>
        <nav>
          <NavLink to="/fleet">Fleet</NavLink>
          <NavLink to="/alerts">Alerts</NavLink>
          <NavLink to="/pipeline">Pipeline</NavLink>
        </nav>
        <div className="user">
          <span className="who">{auth.user?.profile.preferred_username}</span>
          {roles
            .filter((r) => r === "viewer" || r === "engineer")
            .map((r) => (
              <span key={r} className={`role role-${r}`}>
                {r}
              </span>
            ))}
          <button className="ghost" onClick={() => auth.signoutRedirect()}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/fleet" replace />} />
          <Route path="/fleet" element={<FleetPage />} />
          <Route path="/engines/:id" element={<EnginePage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="*" element={<Navigate to="/fleet" replace />} />
        </Routes>
      </main>
    </div>
  );
}
