# 变更记录 0006：深度审计硬门槛、逻辑身份、存储拆分与统一工作区

- 变更编号：0006
- 日期：2026-10-31
- 关联：`Training_Viewer_Deep_Audit_and_Refactor_2026-10-31.md`
- 代码提交：工作区变更（待提交）
- 变更类别：数据正确性修复 / 训练安全 / 架构调整 / UI 重建

## 1. 原来是什么

- 四类读取器在 50 条错误后跳过后续解析，但游标仍前进，坏行后的合法指标会永久漏导（P0-01）。
- 文本读取器用文本模式 + `len(encode())` 计算偏移，CRLF/非法 UTF-8/多字节可能偏离真实字节位置（P1-03）。
- `TrainingRunWriter` 默认创建后台心跳线程；用户报告 CUDA 下 `0xC0000005`，根因未定位（P0-02）。
- 通用日志一文件一 Run，目录移动改变 ID，同训练多文件被拆开；扫描器在父目录匹配后停止，漏子目录独立 Run（P1-04）。
- 指标、备注、收藏、保存视图、根目录混在一个可重建数据库；删索引会丢用户状态（P2-10）。
- 曲线查询先取全量点再 Python 降采样；百万点慢（P1-05）。
- TensorBoard 只解析 scalar；已有预测图没有事件引用就不出现（P1-06）。
- 插件只有加载函数，没有 manifest/状态/失败记录；前端仍不能动态加载（P1-07）。
- 三个主页面分开，比较需重新选 Run/Metric/轴；默认最新 Run 可能抢走用户上次选择（P1-08/09）。

## 2. 现在改变什么

**数据正确性与训练安全**

- `ReadResult` 分离 `total_issue_count` / `suppressed_issue_count`：错误详情最多 50 条，但**每条合法记录继续解析**；结束追加“还有 N 条问题（详情已截断；有效记录未跳过）”。
- 四类读取器（标准 JSONL、CSV、通用 JSONL、纯文本）全部覆盖；新增 60 坏 + 1000 好的测试。
- 纯文本读取改为二进制追加读取；游标是物理字节；逐行严格 UTF-8 解码，非法行报告而不静默替换；CRLF/中文/多字节/半行测试。
- `TrainingRunWriter` 默认 `heartbeat_interval_seconds=0`，不创建后台线程；默认由训练主线程调用 `log_heartbeat`，异步心跳为显式 opt-in。
- 新增 `tools/cuda_writer_smoke.py`：CPU/CUDA × Writer 默认/异步/纯文件/创建顺序的独立子进程矩阵，开启 `faulthandler`，不循环崩溃主进程。当前机器无 torch/CUDA，未执行。

**身份与用户状态**

- 新增 `LogicalRunOverrideStore`：sidecar `logical_runs.json` 存在 Viewer 数据目录；默认不按目录自动合并；用户确认后把同目录多文件归并为一个逻辑 Run，可撤销；原始日志不改。
- 扫描器在通用文件父目录匹配后继续下探子目录，避免漏掉独立子 Run。
- 新增 `GET /audit/sources` 与 `tools/export_source_inventory.py`：逐文件列出 parser、原始 ID、逻辑 Run、归并、置信度、点数。
- 新增 `user_state.sqlite3`：根目录、备注、收藏、保存视图独立保存；旧 `index.sqlite3` 启动时迁移；删除索引不会清空用户状态。
- `IndexDatabase` 通过 `ATTACH ... AS user_state` 查询；根目录查询迁移到独立库。

**性能**

- 曲线查询在 SQLite 内按桶取 min/max/首/尾，按 `max_points` 截断；增加覆盖索引；结果进程内缓存，同步时失效。
- 百万点查询从约 9.4 s 降至约 3.5 s；代价是索引约 43 s、数据库约 1.57 GB（见 `docs/performance.md`）。
- 未做物化桶/缩放区间查询，仍不能称为“百万点秒开”。

**结果与插件**

- 新增结果文件候选发现（事件之外的预测/标签/输入图片），全部标记 `requires_confirmation=true`，只读安全图片；未确认不进入结论。
- 新增 Python 来源插件 manifest 校验、加载状态、失败记录和 `GET /plugins`；前端动态插件仍不支持，文档明确说明。
- 新增 `tests/test_audit_features.py` 覆盖来源清单、插件清单、结果候选和安全内容。

**界面**

- 新增 `TrainingWorkspacePage`：左侧运行树/多选，右侧单 Run 或自动叠加共同指标；高级抽屉放配置、诊断、来源清单；旧 `/`、`/runs`、`/runs/:id`、`/compare` 全部路由转发。
- 首次打开优先恢复 `localStorage` 上次主动选择的 Run；示例（合成元数据）不优先抢占真实运行。
- 新增来源映射面板，用户可选文件、命名逻辑实验、撤销归并。
- 单 Run 主区最多 2 个核心曲线；比较自动选 Train Loss + 验证 max 指标；不插值、不默认排名。
- 保留 `MetricChart`、ECharts、API 与结果页；旧总览/实验库/对比/运行详情页文件已删除，旧路由转发到工作区。

## 3. 为什么这样改

审计判断：保留 SQLite 与现有读取/索引骨架，但必须先修数据丢失与训练安全，再修正身份和用户状态边界，最后重建交互。MLflow 隔离原型在 10,000 点导入 9.3 s，明显慢于现有索引 0.4 s，且 session/epoch 语义不匹配；ADR-001 因此选择 SQLite，不引入第二个权威后端。

未采用：

- 用 MLflow 替换生产存储（导入慢、依赖重、默认 UI 不符合目标）；
- 按目录自动合并通用文件（会静默混淆 seed/数据集/重启）；
- 错误详情截断时跳过合法行（直接数据丢失）；
- 在 CUDA 主进程里循环复现崩溃；
- 把备注/视图继续留在可重建索引库。

## 4. 影响范围

- 后端：读取器基类、四类读取器、writer、scanner、database、index_queries、indexer、service、user_state、identity、results、source_adapters、API 路由/请求模型。
- 前端：统一工作区、AppShell 路由/导航、RunMetricsTab chartLimit、来源映射/来源清单/结果候选组件、API 类型。
- 数据：v1 指标表迁移 v2；新增 `user_state.sqlite3`；sidecar `logical_runs.json`。
- 协议：TVLP 1.0 字段不变。
- 工具：来源清单、CUDA 矩阵、MLflow spike、基准。

## 5. 验证结果

- `pytest -q`：**89 passed，2 skipped**（Windows 符号链接限制）。
- `ruff check src tests tools --select F,E9`：通过。
- `npm run typecheck`：通过。
- `npm run test`：MetricChart 生命周期测试（2）通过。
- `npm run build`：通过。
- `npm run e2e`：真实 Chrome 1440×900、1366×768 工作区/多选/诊断，无 console error。
- 示例来源清单：7 个来源、4 个逻辑实验（`audit/run_inventory_examples.csv`）。
- 百万点与 MLflow 10k 数据：见 `docs/performance.md`。
- CUDA：本机无 torch/CUDA，**未验证**；只交付可复现矩阵脚本。

## 6. 回退方式

- UI：从 Git 恢复旧页面文件并把路由改回旧页面；当前 `TrainingWorkspacePage` 是唯一主入口。
- 读取器：回退错误/字节游标改动会重新引入数据丢失/偏移风险，不建议。
- 用户状态：旧库仍有表；新库可保留；删除 `user_state.sqlite3` 会丢用户数据，必须先备份。
- 逻辑归并：删除 `logical_runs.json` 并重新扫描；原始日志不动。
- 存储后端：没有生产 MLflow 依赖，无需迁移。

## 7. 文档同步

- [x] ADR-001 存储后端
- [x] 架构/API/性能/日志来源
- [x] 组件：工作区、逻辑解析、用户状态、结果发现、映射/清单/候选面板
- [x] README / AGENT / 开发文档
- [x] 审计来源清单说明

## 8. 未完成与风险

- **62 个真实来源**：没有用户数据，未生成真实 `audit/run_inventory.csv`，未解释 53→62；只提供工具与示例清单。
- **CUDA 根因**：未在用户环境复现，未验证修复；默认无后台线程是风险降低，不是已证明的根因修复。
- **百万点**：3.5 s 首屏仍慢；缩放局部仍全量扫描；未做物化桶。
- **字段映射**：歧义 CSV 仍无持久化人工映射 UI；只有逻辑实验归并。
- **结果图像**：未解析 TensorBoard image 事件，未做多光谱/GeoTIFF 波段/掩膜配置；“确认并转 artifact”未实现。
- **插件**：仅 Python source adapter manifest；前端仍不能动态安装。
- **跨平台**：只在 Windows 实机验证；macOS/Linux 未验证。
- **UI**：旧页面文件已删除；指标选择偏好已持久化；对比默认会优先使用上次选中的验证指标，但仍不是完整的指标偏好管理。
