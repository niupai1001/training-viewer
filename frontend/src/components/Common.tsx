import type { ReactNode } from "react";
import { statusTone } from "../utils/format";
import type { Severity, WarningItem } from "../types";

export function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      {(title || actions) && (
        <header className="panel-header">
          {title ? <h2 className="panel-title">{title}</h2> : <span />}
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      )}
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function StatusBadge({
  status,
  label,
  reason,
}: {
  status: string;
  label?: string;
  reason?: string;
}) {
  const tone = statusTone(status);
  return (
    <span className={`status-badge status-${tone}`} title={reason ?? label ?? status}>
      <span className="status-dot" aria-hidden="true" />
      {label ?? status}
    </span>
  );
}

export function LoadingBlock({ label = "正在加载…" }: { label?: string }) {
  return (
    <div className="loading-block" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="error-block" role="alert">
      <strong>加载失败：</strong>
      <span>{error.message}</span>
      {onRetry ? (
        <button type="button" className="button button-small" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}

const SEVERITY_LABELS: Record<Severity, string> = {
  info: "提示",
  warning: "警告",
  error: "错误",
};

export function WarningList({ warnings }: { warnings: WarningItem[] }) {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <ul className="warning-list">
      {warnings.map((warning, index) => (
        <li key={`${warning.code}-${index}`} className={`warning warning-${warning.severity}`}>
          <span className="warning-level">{SEVERITY_LABELS[warning.severity] ?? warning.severity}</span>
          <span>{warning.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function Tag({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="tag" title={title}>
      {children}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function InfoHint({ text }: { text: string }) {
  return (
    <abbr className="info-hint" title={text} aria-label={text}>
      ?
    </abbr>
  );
}

export function WarnBadge({ label, title }: { label: string; title?: string }) {
  return (
    <span className="badge badge-warning" title={title}>
      {label}
    </span>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (tabId: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`tab ${active === tab.id ? "tab-active" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {typeof tab.count === "number" ? <span className="tab-count">{tab.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{children}</span>
    </div>
  );
}
