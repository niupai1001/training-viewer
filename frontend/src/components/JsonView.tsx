import { useState } from "react";

/** 只读 JSON 展示：用于超参数、元数据和配置。不执行任何字符串内容。 */
export function JsonView({ value, name }: { value: unknown; name?: string }) {
  return (
    <div className="json-view">
      {name ? <div className="json-key-line">{name}</div> : null}
      <JsonNode value={value} depth={0} />
    </div>
  );
}

function JsonNode({ value, depth }: { value: unknown; depth: number }) {
  const [expanded, setExpanded] = useState(depth < 2);
  if (value === null) {
    return <span className="json-null">null</span>;
  }
  if (typeof value === "boolean") {
    return <span className="json-boolean">{String(value)}</span>;
  }
  if (typeof value === "number") {
    return <span className="json-number">{value}</span>;
  }
  if (typeof value === "string") {
    return <span className="json-string">{value}</span>;
  }
  if (Array.isArray(value)) {
    return (
      <div className="json-array">
        <button type="button" className="json-toggle" onClick={() => setExpanded(!expanded)}>
          {expanded ? "▾" : "▸"} 数组（{value.length} 项）
        </button>
        {expanded ? (
          <ol>
            {value.map((item, index) => (
              <li key={index}>
                <JsonNode value={item} depth={depth + 1} />
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div className="json-object">
        <button type="button" className="json-toggle" onClick={() => setExpanded(!expanded)}>
          {expanded ? "▾" : "▸"} 对象（{entries.length} 项）
        </button>
        {expanded ? (
          <dl>
            {entries.map(([key, child]) => (
              <div className="json-entry" key={key}>
                <dt>{key}</dt>
                <dd>
                  <JsonNode value={child} depth={depth + 1} />
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    );
  }
  return <span>{String(value)}</span>;
}

export function RawJsonDetails({ value, label = "查看原始 JSON" }: { value: unknown; label?: string }) {
  return (
    <details className="raw-json">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
