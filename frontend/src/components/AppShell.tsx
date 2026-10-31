import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { useRoute } from "../navigation/route";
import type { RouteInfo } from "../navigation/route";
import { TrainingWorkspacePage } from "../pages/TrainingWorkspacePage";
import { ResultsPage } from "../pages/ResultsPage";
import { DiagnosticsPage } from "../pages/DiagnosticsPage";
import { EmptyState } from "./Common";

type NavigationKey = "overview" | "diagnostics";

const NAV_ITEMS: { key: NavigationKey; label: string; href: string; icon: string }[] = [
  { key: "overview", label: "工作区", href: "#/", icon: "◉" },
  { key: "diagnostics", label: "设置与诊断", href: "#/diagnostics", icon: "⚙" },
];

export function AppShell({ connected }: { connected: boolean }) {
  const route = useRoute();
  const liveVersion = useLiveVersion();
  const projects = useApi(() => api.projects(), [liveVersion]);
  const meta = useApi(() => api.meta(), [liveVersion]);
  const [navOpen, setNavOpen] = useState(false);
  const activeKey = resolveActiveKey(route.path);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <a href="#/" className="brand-link" onClick={() => setNavOpen(false)}>
            <span className="brand-mark" aria-hidden="true">
              TV
            </span>
            <span>
              <strong>Training Viewer</strong>
              <small>训练实验查看器</small>
            </span>
          </a>
        </div>

        <nav className="main-nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.key}
              href={item.href}
              className={`nav-link ${activeKey === item.key ? "nav-active" : ""}`}
              onClick={() => setNavOpen(false)}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              {item.label}
              {item.key === "diagnostics" ? null : null}
            </a>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="root-summary">
            <span>{projects.data?.roots.length ?? 0} 个日志根目录</span>
            <a href="#/diagnostics">设置与诊断</a>
          </div>
          <p className="muted small">
            {meta.data ? `v${meta.data.version} · TVLP ${meta.data.tvlp_schema_version}` : "Training Viewer"}
          </p>
          <p className="muted small">原始日志只读 · 索引可重建</p>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <button
            type="button"
            className="nav-toggle"
            aria-label={navOpen ? "收起导航" : "展开导航"}
            aria-expanded={navOpen}
            onClick={() => setNavOpen((value) => !value)}
          >
            ☰
          </button>
          <span className="topbar-title">本机深度学习训练实验查看器</span>
          <span
            className={`live-indicator ${connected ? "live-on" : "live-off"}`}
            title={
              connected
                ? "服务器发送事件（SSE）已连接，日志更新会实时反映到页面"
                : "实时连接断开；页面仍会在刷新或重新连接后更新"
            }
          >
            <span className="live-dot" aria-hidden="true" />
            {connected ? "实时已连接" : "实时连接中…"}
          </span>
        </header>

        <main className="main-content">
          <RouteView route={route} />
        </main>
      </div>
      {navOpen ? <div className="sidebar-backdrop" onClick={() => setNavOpen(false)} /> : null}
    </div>
  );
}

function resolveActiveKey(path: string): NavigationKey {
  if (path === "/" || path === "") {
    return "overview";
  }
  if (path === "/runs" || path.startsWith("/runs/") || path === "/compare" || path === "/") {
    return "overview";
  }
  if (path === "/results") {
    return "overview";
  }
  if (path.startsWith("/diagnostics")) {
    return "diagnostics";
  }
  return "overview";
}

function RouteView({ route }: { route: RouteInfo }) {
  const path = route.path.replace(/\/+$/, "") || "/";
  if (
    path === "/" ||
    path === "/runs" ||
    path === "/compare" ||
    /^\/runs\/[^/]+$/.test(path)
  ) {
    return <TrainingWorkspacePage />;
  }
  if (path === "/results") {
    return <ResultsPage />;
  }
  if (path === "/diagnostics") {
    return <DiagnosticsPage />;
  }
  return (
    <div className="page">
      <EmptyState
        title="页面不存在"
        description={`没有找到路径 ${path}。`}
        action={<a className="button" href="#/">返回工作区</a>}
      />
    </div>
  );
}
