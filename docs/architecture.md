# Training Viewer 系统架构与真实数据流

本文描述 **V1.0.0 实际实现**，不是未来规划。图中的每个组件都能在 [`src/training_viewer/`](../src/training_viewer/) 与 [`frontend/src/`](../frontend/src/) 找到对应代码，组件细节见 [`docs/components/`](components/index.md)。

## 1. 定位与不可妥协的边界

Training Viewer 是本机日志消费者，不是训练调度器：

- 训练程序按 Training Viewer Log Protocol（TVLP，训练日志协议）1.0 输出文件即可；不需要安装 SDK、不需要联网，也不需要启动查看器。
- 查看器对用户添加的目录**只读**。索引数据库、备注、保存的对比视图位于应用数据目录。
- 删除索引数据库不会删除或损坏原始实验；重新扫描可以从日志重建全部指标、事件与产物引用。
- 远程接入、鉴权、多用户、训练调度、在线改超参数不在 V1 范围。

## 2. 进程边界与数据流

```text
训练进程（任意框架，独立进程；可选用 TrainingRunWriter）
  │ 追加 metrics.jsonl / events.jsonl / metrics.csv，写 artifacts/（只写）
  ▼
本机目录（用户显式添加的根目录）
  │
  ├─ 运行目录扫描器（RunDirectoryScanner）
  │     └─ 日志来源注册表（SourceAdapterRegistry）
  │          ├─ 标准训练日志来源（StandardTvlpSourceAdapter）
  │          ├─ TensorBoard 来源（TensorBoardSourceAdapter）
  │          └─ CSV 指标来源（CsvSourceAdapter）
  │
  ├─ 标准训练日志读取器（StandardTrainingLogReader）
  │  CSV 指标日志读取器（CsvMetricLogReader）
  │  TensorBoard 事件读取器（TensorBoardEventReader）
  │      输入：文件 + 文件游标；输出：规范化指标 / 事件 / 产物记录 + 解析问题
  │
  ├─ 训练指标索引器（TrainingMetricIndexer）
  │      输入：发现结果；输出：SQLite 指标点、产物、事件、游标、问题
  │      由 日志更新监听器（LogUpdateWatcher）轮询/文件事件触发
  │
  ├─ 索引查询（IndexQueries）
  │      输出：运行列表、曲线、对比、产物分组、时间线、诊断
  │
  ├─ FastAPI 应用（create_application）
  │      REST /api/v1/* + SSE /api/v1/stream + 静态前端
  │
  ▼  127.0.0.1:端口
浏览器前端（React + TypeScript + ECharts）
  │  SSE 收到“版本变化”通知 → 按需重新查询 REST
  ▼
用户界面：总览 / 实验管理 / 运行详情 / 实验对比 / 预测结果 / 诊断
```

训练 Agent 的接入路径独立于浏览器：它在训练代码中调用 `TrainingRunWriter` 写文件，然后执行 `training-viewer attach <日志根目录> --json`。`attach` 复用或后台启动本机服务、注册根目录并返回 URL；用户直接打开 URL，不需要手动启动服务。

**数据方向**：训练程序写文件 → 读取器 → 索引器 → SQLite → 查询层 → REST/SSE → 前端。没有反向写入训练目录的路径。

**进程边界**：训练进程与查看器进程彼此独立；查看器进程内的后台同步线程与 HTTP 请求共享 SQLite（WAL 模式，写操作串行）。

## 3. 组件清单

| 中文功能名 | 代码名 | 源文件 | 输入 → 输出 |
|---|---|---|---|
| 运行目录扫描器 | `RunDirectoryScanner` | `discovery/run_directory_scanner.py` | 根目录 → 发现的 Run + 目录级问题 |
| 日志来源注册表 | `SourceAdapterRegistry` | `source_adapters/base.py` | 目录 → 第一个匹配来源的一批 Run |
| 标准训练日志来源 | `StandardTvlpSourceAdapter` | `source_adapters/builtin_adapters.py` | 含 run.json 的目录 → Run + 日志文件读取器 |
| TensorBoard 来源 | `TensorBoardSourceAdapter` | 同上 | 事件文件目录 → 合成元数据的 Run |
| CSV 指标来源 | `CsvSourceAdapter` | 同上 | `metrics.csv` 目录 → 合成元数据的 Run |
| 通用日志文件来源 | `GenericLogFileSourceAdapter` | `source_adapters/generic_log_file_adapter.py` | 任意文件名 CSV/TSV/JSONL/文本 → 每文件一个 Run |
| 逻辑实验解析器 | `LogicalRunOverrideStore` | `identity/logical_runs.py` | 用户确认的文件组 → 一个逻辑 Run；sidecar 可撤销 |
| 用户状态存储 | `UserStateStore` | `user_state.py` | 根目录/备注/收藏/保存视图，与索引分库 |
| 结果文件发现器 | `discover_result_files` | `results/discovery.py` | 事件之外的图片候选，明确未确认 |
| 标准训练日志增量读取器 | `StandardTrainingLogReader` | `log_readers/standard_training_log_reader.py` | JSONL + 游标 → 指标/事件/产物记录 |
| CSV 指标日志读取器 | `CsvMetricLogReader` | `log_readers/csv_metric_reader.py` | CSV + 列映射/分隔符 → 指标记录 |
| 通用 JSONL 读取器 | `GenericJsonlMetricReader` | `log_readers/generic_jsonl_reader.py` | 扁平/类 TVLP JSONL → 指标记录 |
| 纯文本日志读取器 | `PlainTextLogReader` | `log_readers/plain_text_log_reader.py` | 规则模板文本 → 指标记录 |
| TensorBoard 事件读取器 | `TensorBoardEventReader` | `log_readers/tensorboard_event_reader.py` | 事件文件 + 游标 → 标量记录 |
| 运行元数据读取器 | `RunMetadataReader` | `run_metadata.py` | `run.json` → 校验后的元数据字典 |
| 训练指标索引器 | `TrainingMetricIndexer` | `indexing/training_metric_indexer.py` | 发现结果 → SQLite 索引与状态 |
| 索引查询 | `IndexQueries` | `indexing/index_queries.py` | SQLite → 页面/导出的数据结构 |
| 日志更新监听器 | `LogUpdateWatcher` | `watch/log_update_watcher.py` | 定时器/文件事件 → 同步调用 |
| 查看器应用服务 | `TrainingViewerService` | `service.py` | 根目录/同步/订阅 → 应用状态与 SSE 消息 |
| HTTP API 应用 | `create_application` | `api/app.py` | 服务 → REST + SSE + 静态资源 |
| 路径安全守卫 | `path_guard` | `security/path_guard.py` | 相对路径 + Run 目录 → 安全的磁盘路径 |
| 指标导出器 | `MetricCsvExporter` / `MetricJsonExporter` | `export/metric_exporters.py` | 对比结果 → CSV/JSON 文本 |
| 训练日志写入器 | `TrainingRunWriter` | `writer.py` | 训练参数与指标 → 合法 TVLP 文件 |
| 训练 Agent 接入命令 | `attach` / `status` / `stop` | `cli.py` | 日志根目录 → 后台查看器 URL |
| 指标曲线组件 | `MetricChart` | `frontend/src/components/MetricChart.tsx` | 曲线数据 + 显示参数 → ECharts 图表 |
| 实验对比页面 | `ComparisonPage` | `frontend/src/pages/ComparisonPage.tsx` | 多运行查询 → 曲线、Best/Last、差异表 |
| 预测结果对照器 | `PredictionComparisonViewer` | `frontend/src/components/PredictionComparisonViewer.tsx` | 产物分组 → 并排/叠加对照 |
| 实验产物视图注册表 | `artifactViews` | `frontend/src/view_plugins/artifactViews.tsx` | 产物类型 → 对应预览组件 |

## 4. SQLite 索引模型

指标索引：`<应用数据目录>/index.sqlite3`，开启 WAL，可删除重建。
用户状态：`<应用数据目录>/user_state.sqlite3`，保存根目录、备注、收藏、保存视图，**不可从日志重建**。

| 表 | 内容 | 所在库 | 是否可重建 |
|---|---|---|---|
| `watched_roots` | 用户显式添加的根目录 | user_state | 否 |
| `run_annotations` | 用户备注与收藏 | user_state | 否 |
| `saved_views` | 保存的对比视图 | user_state | 否 |
| `runs` | 运行身份、项目/实验组、状态、元数据 JSON、目录、最后更新时间 | index | 是 |
| `metric_points` | `run_id、phase、metric_name、step、epoch、timestamp、session_id、value、来源文件/偏移` | index | 是 |
| `artifacts` | 产物引用、角色、样本/分组、文件存在性与大小 | index | 是 |
| `training_events` | 生命周期与心跳 | index | 是 |
| `ingestion_cursors` | 每个文件已消费位置、文件身份、大小、mtime | index | 是 |
| `ingestion_issues` | 行级/目录级解析问题 | index | 是 |
| `run_conflicts` | 重复 `run_id` 的冲突记录 | index | 是（扫描重建） |

逻辑实验归并规则保存在 `<数据目录>/logical_runs.json`，不写训练目录；删除索引不会删除规则。

关键索引：`(run_id, phase, metric_name, global_step)`、`(run_id, phase, metric_name, epoch)`、`(run_id, timestamp)`，并为曲线列增加覆盖索引；`(project, experiment)`、`(run_id, tag)`、`(run_id, group_id)`。`IndexDatabase` 通过 `ATTACH DATABASE ... AS user_state` 让查询层访问用户状态。

**幂等键**：指标 `(run_id, source_file, source_offset, phase, metric_name)`（同一行的 train_loss 与 val_loss 可共存）；产物/事件 `(run_id, source_file, source_offset)`。因此重复扫描、查看器重启、文件重读都不会产生重复采样。v1 数据库启动时自动迁移到该键。

**曲线查询**：先 `COUNT`，超过 `max_points` 时在 SQLite 内按桶取 min/max/首/尾，最多返回 `max_points`；`Best`/`Last` 仍对原始点精确计算。结果按 `(run_id, phase, metric, axis, max_points)` 进程内缓存，写同步时失效。

## 5. 增量读取与一致性

### 5.1 游标语义

| 来源 | `offset` 含义 | 文件被截断/替换时的处理 |
|---|---|---|
| `metrics.jsonl` / `events.jsonl` | 已消费的字节偏移 | 文件身份变化或新大小小于游标 → 重置并删除该文件索引后重读 |
| `metrics.csv` | 已消费的数据行数 | 同上；重新读取整表并按行号幂等写入 |
| TensorBoard 事件文件 | 已处理的事件序号 | 同上；重新读取事件文件，只写入序号大于游标的事件 |

`run.json` 修改后重新读取元数据。若运行目录或来源类型变化，删除该 Run 的派生索引并按新位置重建；备注按 `run_id` 保留。若同一目录的 `run_id` 变化，删除旧 Run 的派生索引并记录诊断。

### 5.2 半行与坏行

- JSONL 只处理以换行结尾的完整行；末尾半行不导入、不判为永久损坏，并在游标中保留其起始偏移。
- 非 UTF-8、非法 JSON、未知字段、缺少 Step/Epoch、非有限数字、缺时区、危险产物路径等坏行会记录文件名与行号，并跳过该行；后续有效行继续导入。
- 一次读取最多报告 50 条错误，避免损坏文件刷爆诊断。
- 半行补齐后，之前的“等待补齐”提示会被删除，不会永久残留。

### 5.3 重复、截断与冲突

- 重复导入由唯一键阻止；同一步骤的 train 与 val 属于不同 `phase`，不会互相覆盖。
- 文件截断/轮转时，删除该文件的旧索引再重读，避免旧点残留。
- 两个目录出现相同 `run_id` 时，保留一个目录的索引，另一个写入 `run_conflicts` 并在运行详情和诊断页报警；不会静默合并。
- 目录被移动且不在任何已添加根目录下时，运行标记为“目录不可访问”，索引保留，状态为未知；恢复后重新扫描会重新可用。

## 6. 运行状态推导

状态值：`running`、`completed`、`failed`、`cancelled`、`unknown`、`imported`。另有独立的 `activity`：`updating`、`idle`、`finished`、`unknown`。

- 非 TVLP 来源（TensorBoard/CSV/通用文件）没有生命周期事件，显示 `imported`（已导入）；活动可能仍是“最近仍在更新”。
- TVLP：取最新 lifecycle 事件。`completed`/`failed`/`cancelled` 直接采用。
- 否则，只有最近 120 秒内收到 **heartbeat** 才显示 `running`。
- 有近期指标但没有近期心跳：状态 `unknown`，活动 `updating`；不把“日志在写”冒充“进程仍在运行”。
- 否则 → `unknown`，原因明确写出“日志停止不能证明训练失败”。
- 会话（`session_id`）用于区分断点续训；同一会话内的 Step 回退记录警告，不同会话之间 Step 重置是正常现象。

## 7. 查询与比较规则

- **按阶段取指标**：指标身份是 `phase/metric_name`（例如 `val/miou`），与 run.json 的 `metric_definitions` 键对应。
- **最优值**：只有 `direction` 为 `min`/`max` 才计算；使用全部原始采样，不使用平滑或降采样后的点。
- **最终值**：该指标最新时间戳的有效记录（无时间戳时按写入顺序）。
- **降采样**：返回点超过上限时使用最小-最大分桶，保留每桶的首尾、最小值、最大值；`total_points` 仍为原始数量。
- **不插值**：某个运行缺少指标时，对比图中该运行就是缺失，不补点、不截断其它运行。
- **可比性**：单位、数据集（名称/版本/划分）、指标定义/聚合、任务类型任一不同 → 明确警告；只有全部一致且方向明确时才允许自动排名与标记最优。
- **运行列表主要指标**：选择第一个声明了 min/max 方向的验证阶段指标；没有方向时退化为最近写入的指标，只显示最终值。

## 8. 实时推送（SSE）

- `LogUpdateWatcher` 每 2 秒调用 `TrainingViewerService.synchronize()`；默认只重读已知 Run。完整目录树发现每 300 秒兜底一次，watchdog 的目录创建/移动/删除事件会立即触发全量发现；watchdog 文件事件只提前唤醒，不替代轮询。
- 同步发现新 Run、新指标、状态变化或诊断变化时，`version` 增长，并向所有订阅者推送轻量消息 `{version, changed_runs, diagnostics_changed}`。
- 浏览器通过 `EventSource` 订阅 `/api/v1/stream`；收到消息后合并 600ms 内的多次通知，再按需重新查询 REST。
- SSE 不广播历史指标数据；断线后浏览器自动重连并重新查询。

## 9. 安全边界

- 默认监听 `127.0.0.1`；HTTP 中间件只接受 `Host` 为本机名称，并拒绝带外部 `Origin` 的请求。
- 产物内容接口必须满足：Run 目录位于当前注册的根目录内；产物相对路径通过白名单校验；解析后的真实路径仍在 Run 目录内。数据库被篡改也不能绕过。
- HTML/SVG 不作为可执行页面返回；图片仅允许常见位图格式内联。HTML 以 `text/plain` 附件返回。
- 表格预览限制 5 MiB、200 行、40 列；不执行单元格内容。

## 10. 插件边界

| 扩展点 | 机制 | 是否需要重新构建前端 |
|---|---|---|
| 日志来源适配器 | 实现 `SourceAdapter`，注册到 `SourceAdapterRegistry`；或安装 Python entry point（组名 `training_viewer.source_adapters`） | 否 |
| 指标导出器 | 实现 `MetricExporter`，注册到 `MetricExporterRegistry`；或 entry point（组名 `training_viewer.metric_exporters`） | 否 |
| 实验产物视图 | 实现 `ArtifactViewPlugin`，调用 `registerArtifactViewPlugin` | 是 |
| VS Code 入口 | 命令调用同一命令行/本机 REST | 否 |

V1 不实现第三方代码热加载。插件异常被记录并跳过，不阻止内置来源工作。Python 来源插件应提供 `plugin_manifest`（`name`、`version`、`adapter_id`、`capabilities`，可选 `description`/`requires`/`settings`）；缺失 manifest 仍以兼容模式加载但状态为 `missing-manifest`，加载失败记录在 `GET /plugins` 的 `status/error`。前端产物插件仍是编译期内建注册表，不宣称“安装任意前端插件即可生效”。

## 11. 配置与默认值

| 项 | 默认值 | 来源 |
|---|---|---|
| 应用数据目录 | `%LOCALAPPDATA%\TrainingViewer` / `~/.training_viewer` | `ApplicationPaths`，可被 `TRAINING_VIEWER_DATA_DIR` 或 `--data-dir` 覆盖 |
| 首选端口 | 8765 | `training-viewer open/serve/attach` |
| 轮询间隔 | 2 秒 | `--interval` |
| 全量目录发现间隔 | 300 秒 | `TrainingViewerService(full_scan_interval_seconds=...)` |
| 后台服务健康检查超时 | 25 秒 | `attach` |
| 运行中判定时限 | 120 秒 | `TrainingMetricIndexer.STALE_AFTER_SECONDS` |
| 扫描深度上限 | 12 层 | `RunDirectoryScanner(max_depth)` |
| 单根目录扫描目录数上限 | 50000 | `RunDirectoryScanner(max_directories)` |
| 保留解析问题数 | 2000 条 | `MAX_STORED_ISSUES` |
| 曲线最大返回点 | 详情 3000、对比 1500（上限 20000） | API 参数 |
| 前端产物预览 | 5 MiB / 200 行 / 40 列 | `routes_artifacts.py` |

## 12. 已知权衡

- TensorBoard 事件文件每次变化都会从头重读，没有按字节 seek；对超大事件文件需要后续优化。
- CSV 同样按文件变化整体重读；行游标保证不重复入库。
- 每 2 秒只重读已知 Run；每 300 秒完整发现一次目录树，watchdog 目录事件提前触发。复杂目录树可调整根目录或轮询间隔；匹配到的 Run 目录不会继续向下扫描产物。
- `attach` 启动的后台服务不会随 Agent 会话退出而停止；需要 `training-viewer stop` 管理。若在受限环境中无法写默认应用数据目录，使用 `--data-dir`。
- 训练侧写入器只面向单写者；DDP 多进程并发写同一文件不在 V1 保证范围。
- 前端打包为单个约 942 KiB（gzip 311 KiB）的 JavaScript 文件，包含 ECharts；本地使用无需 CDN，但首次加载体积较大。
- 数百万点的交互性能尚未基准测试；当前分桶策略保证极值不丢失，但未做视窗范围查询与缓存。
- 数据库写操作串行化；本地单用户场景可接受，不适合高并发多用户。

## 13. 仓库结构

```text
training_viewer_v1/
  README.md
  AGENT_INTEGRATION.md          # 交给训练 Agent 的接入契约
  pyproject.toml
  schemas/                       # TVLP 1.0 官方 JSON Schema（仓库源）
  examples/                      # 4 个示例运行
  tools/validate_log.py          # 原有独立校验工具
  src/training_viewer/
    application_paths.py
    run_metadata.py
    writer.py                    # 训练侧写入器（仅标准库）
    log_validation.py
    service.py
    cli.py                       # open / serve / attach / status / stop / validate
    api/                         # FastAPI 应用与路由
    discovery/                   # 目录扫描
    log_readers/                 # 三种读取器 + 公共类型
    source_adapters/             # 来源适配器与注册表
    indexing/                    # SQLite schema、索引器、查询
    watch/                       # 轮询 + watchdog
    export/                      # CSV/JSON 导出
    security/                    # 路径白名单
    schemas/                     # 安装包内的 Schema 副本
    web/                         # 构建后的前端静态资源
  frontend/                      # React + TypeScript + ECharts 源码
  tests/                         # pytest 测试
  docs/                          # 架构、组件、术语、变更、API
  vscode-extension/              # VS Code 扩展源码与 VSIX
```
