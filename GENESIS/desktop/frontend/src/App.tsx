import { useEffect, useState, type ReactNode } from "react";
import { api, usePolling } from "./api";
import { readRoute, type Route } from "./router";
import type { Status } from "./types";
import { Agents } from "./views/Agents";
import { Approvals } from "./views/Approvals";
import { Dashboard } from "./views/Dashboard";
import { Diagnostics } from "./views/Diagnostics";
import { Projects } from "./views/Projects";
import { ResearchLab } from "./views/ResearchLab";
import { Tasks } from "./views/Tasks";

const NAV: { page: string; label: string; icon: ReactNode }[] = [
  { page: "dashboard", label: "Dashboard", icon: <path d="M4 13h6V4H4zm10 7h6V11h-6zM4 20h6v-5H4zm10-11h6V4h-6z" /> },
  { page: "progetti", label: "Progetti", icon: <path d="M3 7h7l2 2h9v10H3z" /> },
  { page: "compiti", label: "Compiti", icon: <path d="M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2" /> },
  { page: "agenti", label: "Agenti", icon: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 8c0-3.3 3.1-6 7-6s7 2.7 7 6" /> },
  { page: "laboratorio", label: "Laboratorio", icon: <path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7 15h10" /> },
  { page: "approvazioni", label: "Approvazioni", icon: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zm-3 9l2 2 4-4" /> },
  { page: "diagnostica", label: "Diagnostica", icon: <path d="M3 12h4l3-7 4 14 3-7h4" /> },
];

export function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const status = usePolling(() => api<Status>("/api/status"), 3000);

  useEffect(() => {
    const onHash = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const s = status.data;
  const online = status.error === null && s !== null;
  let content: ReactNode;
  switch (route.page) {
    case "progetti":
      content = <Projects />;
      break;
    case "compiti":
      content = <Tasks route={route} />;
      break;
    case "agenti":
      content = <Agents />;
      break;
    case "laboratorio":
      content = <ResearchLab />;
      break;
    case "approvazioni":
      content = <Approvals onChange={status.refresh} />;
      break;
    case "diagnostica":
      content = <Diagnostics />;
      break;
    default:
      content = <Dashboard status={s} error={status.error} refresh={status.refresh} />;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#/dashboard" aria-label="GÉNESIS, dashboard">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">GÉNESIS</span>
        </a>
        <nav aria-label="Sezioni">
          {NAV.map((item) => (
            <a
              key={item.page}
              href={`#/${item.page}`}
              aria-label={item.label}
              title={item.label}
              className={`nav-item ${route.page === item.page || (item.page === "dashboard" && !NAV.some((n) => n.page === route.page)) ? "active" : ""}`}
              aria-current={route.page === item.page ? "page" : undefined}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">{item.icon}</svg>
              <span>{item.label}</span>
              {item.page === "approvazioni" && s && s.pending_approvals > 0 && (
                <span className="nav-count" aria-label={`${s.pending_approvals} in attesa`}>{s.pending_approvals}</span>
              )}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`dot ${online && s?.worker_running ? "dot-ok" : "dot-bad"}`} aria-hidden="true" />
          <span>{online ? (s?.worker_running ? "Core attivo" : "Esecutore fermo") : "Non connesso"}</span>
          {s && <span className="version">v{s.version}</span>}
        </div>
      </aside>
      <main className="content">{content}</main>
    </div>
  );
}
