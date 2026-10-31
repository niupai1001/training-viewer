import type { RunDetail } from "../types";
import { directionLabel, formatDateTime, unitLabel } from "../utils/format";
import { Field, EmptyState, Panel, Tag } from "./Common";
import { JsonView, RawJsonDetails } from "./JsonView";

const SOURCE_KIND_LABELS: Record<string, string> = {
  tvlp: "标准训练日志（TVLP 1.0）",
  tensorboard: "TensorBoard 事件文件",
  csv: "CSV 指标表",
  "generic-csv": "通用 CSV 文件",
  "generic-tsv": "通用 TSV 文件",
  "generic-jsonl": "通用 JSONL 文件",
  "plain-text": "普通文本训练日志",
};

export function RunConfigTab({ run }: { run: RunDetail }) {
  const definitions = Object.entries(run.metric_definitions ?? {});
  return (
    <div className="config-tab">
      {run.metadata_synthetic ? (
        <p className="notice notice-warning">
          该运行没有 run.json，项目与名称由目录推导。指标数据本身来自原始日志，没有被改写。
        </p>
      ) : null}

      <div className="config-grid">
        <Panel title="运行标识">
          <dl className="detail-list">
            <dt>运行 ID</dt>
            <dd className="mono">{run.run_id}</dd>
            <dt>展示名称</dt>
            <dd>{run.name}</dd>
            <dt>项目 / 实验组</dt>
            <dd>
              {run.project}
              {run.experiment ? ` / ${run.experiment}` : " / 未分组"}
            </dd>
            <dt>任务类型</dt>
            <dd>{run.task ?? "未声明"}</dd>
            <dt>创建时间</dt>
            <dd>{formatDateTime(run.created_at)}</dd>
            <dt>协议版本</dt>
            <dd>TVLP {run.schema_version ?? "1.0"}</dd>
            <dt>日志来源</dt>
            <dd>
              {SOURCE_KIND_LABELS[run.source_kind] ?? run.source_kind}
              <div className="muted small mono">{run.adapter_id}</div>
            </dd>
            <dt>运行目录</dt>
            <dd className="mono wrap-anywhere">{run.run_directory}</dd>
            <dt>扫描根目录</dt>
            <dd className="mono wrap-anywhere">{run.root_path}</dd>
          </dl>
          <p className="muted small">
            原始日志只读。删除索引数据库只会丢失查看器数据，不会影响上述目录中的训练记录。
          </p>
        </Panel>

        <Panel title="模型与数据集">
          <Field label="模型">
            {run.model?.name ? (
              <span>
                {run.model.name}
                {run.model.architecture ? ` · ${run.model.architecture}` : ""}
                {run.model.version ? ` · ${run.model.version}` : ""}
              </span>
            ) : (
              <span className="muted">未声明</span>
            )}
          </Field>
          <Field label="数据集">
            {run.dataset?.name ? (
              <span>
                {run.dataset.name}
                {run.dataset.version ? ` · 版本 ${run.dataset.version}` : ""}
                {run.dataset.split_definition ? ` · 划分 ${run.dataset.split_definition}` : ""}
                {run.dataset.fingerprint ? ` · 指纹 ${run.dataset.fingerprint}` : ""}
              </span>
            ) : (
              <span className="muted">未声明</span>
            )}
          </Field>
          <Field label="标签">
            {run.tags.length > 0 ? (
              <span className="tag-row">
                {run.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </span>
            ) : (
              <span className="muted">无</span>
            )}
          </Field>
          <Field label="随机种子">
            {typeof run.source.seed === "number" ? String(run.source.seed) : <span className="muted">未声明</span>}
          </Field>
          <Field label="代码来源">
            {Object.keys(run.source).length > 0 ? (
              <JsonView value={run.source} />
            ) : (
              <span className="muted">未声明</span>
            )}
          </Field>
        </Panel>
      </div>

      <Panel title="训练配置（run.json 的 config 字段）">
        {Object.keys(run.config).length > 0 ? (
          <JsonView value={run.config} />
        ) : (
          <EmptyState title="没有记录训练配置" description="训练程序可以在 run.json 的 config 字段中记录超参数。" />
        )}
      </Panel>

      <Panel title="指标定义">
        {definitions.length === 0 ? (
          <p className="muted">
            该运行没有声明 metric_definitions。指标仍可绘制，但无法判断优化方向、单位或可比性，因此不会自动评优。
          </p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">指标键</th>
                  <th scope="col">界面名称</th>
                  <th scope="col">方向</th>
                  <th scope="col">单位</th>
                  <th scope="col">聚合 / 定义</th>
                  <th scope="col">比较键</th>
                </tr>
              </thead>
              <tbody>
                {definitions.map(([key, definition]) => (
                  <tr key={key}>
                    <th scope="row">{key}</th>
                    <td>{definition.display_name ?? key}</td>
                    <td>{directionLabel(definition.direction)}</td>
                    <td>{unitLabel(definition.unit) || "—"}</td>
                    <td>
                      {definition.aggregation ?? "—"}
                      {definition.definition ? (
                        <div className="muted small">{definition.definition}</div>
                      ) : null}
                    </td>
                    <td>{definition.comparison_key ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          单位是数据单位而不是显示样式；不同单位、数据集或计算定义的指标不能直接比较。ratio 表示 0–1 的比例，
          不会自动换算成百分数。
        </p>
      </Panel>

      {Object.keys(run.extensions ?? {}).length > 0 ? (
        <Panel title="来源扩展信息（extensions）">
          <JsonView value={run.extensions} />
        </Panel>
      ) : null}

      <Panel title="原始运行元数据">
        <RawJsonDetails value={run.metadata} label="查看完整 run.json 内容" />
      </Panel>
    </div>
  );
}
