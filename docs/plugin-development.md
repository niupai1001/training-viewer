# 插件开发指南

V1 提供三个显式扩展点：日志来源适配器、指标导出器、前端实验产物视图。插件失败会被记录并跳过，不影响内置来源与页面。

## 1. 日志来源适配器（Source Adapter）

### 1.1 职责

发现一种目录结构中的运行，并为其中的日志文件提供读取器。适配器**不**写数据库、不生成图表、不修改原始文件。

### 1.2 接口

来自 [`source_adapters/base.py`](../src/training_viewer/source_adapters/base.py)：

```python
class SourceAdapter(Protocol):
    adapter_id: str
    display_name: str

    def discover(self, run_directory: Path) -> DiscoveredRun | None: ...
```

`DiscoveredRun` 字段：

| 字段 | 含义 |
|---|---|
| `source_kind` | 来源类型，写入运行记录 |
| `adapter_id` | 全局唯一插件标识，例如 `source.my_format` |
| `run_directory` | Run 根目录（绝对路径） |
| `run_id` | 运行唯一标识；没有 `run.json` 时由适配器合成并保持稳定 |
| `metadata` | 至少含 `schema_version`、`run_id`、`project`、`name`、`created_at` 的元数据字典 |
| `log_files` | `LogFileSpec(file_path, reader)` 列表 |
| `metadata_file` | `run.json` 路径或 `None` |
| `metadata_synthetic` | 元数据是否由目录推导 |

读取器接口：

```python
class LogFileReader(Protocol):
    file_kind: str

    def read_new_records(
        self,
        file_path: Path,
        run_directory: Path,
        cursor: FileCursor | None,
    ) -> ReadResult: ...
```

`ReadResult` 包含 `records`（指标/产物/生命周期/心跳）、`issues`（文件名、行号、中文消息、严重级别）、`cursor`（文件身份、偏移、大小、mtime）与 `reset`（是否检测到截断/替换）。

### 1.3 最小示例

```python
import json
from pathlib import Path
from training_viewer.source_adapters.base import DiscoveredRun, LogFileSpec


class JsonSummarySourceAdapter:
    """把目录中的 summary.json 当作一个只含最终指标的外部来源。"""

    adapter_id = "source.json_summary"
    display_name = "JSON 汇总文件"

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        summary_path = run_directory / "summary.json"
        if not summary_path.is_file() or summary_path.is_symlink():
            return None
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        metadata = {
            "schema_version": "1.0",
            "run_id": payload["run_id"],
            "project": payload.get("project", "外部来源"),
            "name": payload.get("name", run_directory.name),
            "created_at": "2026-10-31T08:00:00Z",
            "extensions": {"source_adapter": self.adapter_id},
        }
        return DiscoveredRun(
            source_kind="json-summary",
            adapter_id=self.adapter_id,
            run_directory=run_directory,
            run_id=payload["run_id"],
            metadata=metadata,
            log_files=[LogFileSpec(summary_path, MySummaryReader())],
            metadata_file=None,
            metadata_synthetic=True,
        )
```

读取器必须自己维护幂等（索引器按“来源文件 + offset + 指标名”去重）并返回中文问题。

### 1.4 注册方式

**方式 A：代码内显式注册**

```python
from training_viewer.service import TrainingViewerService
from training_viewer.source_adapters.base import SourceAdapterRegistry

registry = SourceAdapterRegistry()
registry.register(JsonSummarySourceAdapter())
service = TrainingViewerService(paths, source_adapter_registry=registry)
```

注意：传入自定义注册表会替换内置注册表。需要内置来源时，先调用 `build_builtin_source_adapter_registry()`，再 `register()`。

**方式 B：安装式 entry point（推荐给独立插件包）**

在自己的 `pyproject.toml` 中声明：

```toml
[project.entry-points."training_viewer.source_adapters"]
json_summary = "my_viewer_plugin:JsonSummarySourceAdapter"
```

目标可以是适配器类（无参构造）或适配器实例。安装后启动 Training Viewer 会自动加载。单个插件加载失败只写日志，不阻止启动。

### 1.5 约束

- `run_id` 必须稳定；不要用随机数。无元数据来源应使用目录路径哈希，并明确告诉用户移动目录会改变身份。
- 不要修改训练目录；不要删除日志。
- 不要从适配器直接写 SQLite；让索引器处理游标和幂等。
- 不认识的记录应跳过并报告，不要猜造数值。
- 读取大文件时要提供可控游标，不能每次扫描都无界重读（若必须重读，在文档中说明）。

## 2. 指标导出器（Exporter）

接口来自 [`export/metric_exporters.py`](../src/training_viewer/export/metric_exporters.py)：

```python
class MetricExporter(Protocol):
    format_id: str
    media_type: str
    file_extension: str

    def serialize(self, comparison: dict, metadata: dict) -> str: ...
```

`comparison` 是 `/compare/query` 的响应结构；`metadata` 包含导出时间、横轴、运行/指标集合、最大点数、平滑方法、坐标轴类型与协议版本。

注册：

```python
from training_viewer.export.metric_exporters import MetricExporterRegistry, MetricExporter

class HtmlMetricExporter:
    format_id = "html"
    media_type = "text/html; charset=utf-8"
    file_extension = "html"

    def serialize(self, comparison: dict, metadata: dict) -> str:
        # 必须转义所有用户数据，不能执行脚本
        return "<html>...</html>"
```

安装式 entry point 组名：`training_viewer.metric_exporters`。

安全要求：导出内容中的运行名、指标名、路径都视为不可信文本，必须转义；不要在导出器中读取任意文件或执行命令。

## 3. 前端实验产物视图（View Plugin）

接口来自 [`frontend/src/view_plugins/artifactViews.tsx`](../frontend/src/view_plugins/artifactViews.tsx)：

```tsx
export interface ArtifactViewProps {
  artifact: Artifact;
  onOpenImage: (artifact: Artifact) => void;
  onPreviewTable: (artifact: Artifact) => void;
}

export interface ArtifactViewPlugin {
  id: string;
  label: string;
  supports: (artifact: Artifact) => boolean;
  render: (props: ArtifactViewProps) => ReactNode;
}
```

注册：

```tsx
import { registerArtifactViewPlugin } from "./view_plugins/artifactViews";

registerArtifactViewPlugin({
  id: "artifact.audio",
  label: "音频产物",
  supports: (artifact) => artifact.artifact_type === "file" && artifact.path.endsWith(".wav"),
  render: ({ artifact }) => <audio controls src={artifact.content_url} />,
});
```

V1 的视图插件在构建时打包；新增视图后需要重新运行 `npm run build`。第三方视图不能用服务端返回的 HTML 直接 `dangerouslySetInnerHTML` 执行。

## 4. VS Code 入口

扩展通过命令行与本机 REST 工作，不复制前端。新增编辑器命令时：

- 使用 `trainingViewer.command` 配置启动命令；
- 通过 `/api/v1/health` 探测实例；
- 通过 `POST /api/v1/roots` 添加目录；
- 用 `vscode.env.openExternal` 打开 `http://127.0.0.1:<端口>/#/...`。

## 5. 测试插件

- 适配器：至少测试“发现正确目录”“不匹配时返回 None”“读取器幂等”“坏数据产生问题记录”。
- 导出器：测试 CSV/JSON/HTML 转义、下载头、元数据字段。
- 视图插件：测试 `supports()` 边界和缺失文件占位。
- 运行 `pytest -q`、`npm run typecheck`，并手工加载一次真实目录验证。

参考 [`tests/test_indexing.py`](../tests/test_indexing.py) 中的 `test_custom_source_adapter_can_register_without_core_changes`。
