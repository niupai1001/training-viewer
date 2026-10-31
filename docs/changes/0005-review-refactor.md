# 变更记录 0005：按审阅重构零配置体验、横轴、活动状态与增量扫描

- 变更编号：0005
- 日期：2026-10-31
- 关联需求/问题：`Training_Viewer_Review_2026-10-31.md` 的 P0/P1 与四阶段清单
- 代码提交：工作区变更
- 变更类别：行为修改 / 功能增加 / 索引 schema 迁移

## 1. 原来是什么

- 首页先显示运行数量、目录管理、运行列表、诊断，首次打开看不到训练曲线。
- 默认横轴固定 `global_step`；只有 Epoch 的合法日志打开后可能空图。
- 图表容器仅在有点时渲染，空数据变为有数据时可能不再初始化。
- TensorBoard/CSV 活跃训练固定显示“已导入”，没有独立的活动信息。
- 每次轮询都完整递归扫描根目录；目录大时 I/O 成本高。
- 只能识别 `run.json`、TensorBoard 事件文件、固定 `metrics.csv`，不能读任意命名的 CSV/TSV/JSONL/普通文本。
- 对比保存视图只恢复部分字段；运行页没有“加入对比”入口；导航把预测结果/诊断放在一级。
- 指标唯一键缺 `phase`，同一行的 `train_loss` 与 `val_loss` 只能入库一个。

## 2. 现在改变什么

**体验**

- 首页改为“当前/最近训练”优先：状态/活动、Epoch 进度、最佳/最新验证指标、学习率、Train/Val Loss 曲线、验证指标曲线、最新预测样本，其后才是最近实验。
- 一级导航压缩为“监控 / 实验库 / 对比”；目录、诊断、保存视图进入“高级设置 / 设置与诊断”。
- 实验库默认只显示名称、状态、关键指标、最近更新；高级筛选折叠；运行行提供“+ 对比”。
- 运行页自动推荐 Train Loss、Val Loss、验证主指标、学习率（最多 6 个），并内嵌最新产物预览。
- 运行页“加入对比”自动带同项目、同数据集的最近运行。
- 保存的对比视图新增 `GET /saved-views/{id}`，前端按 ID 恢复 runs/series/axis/smoothing/window/scale。

**正确性**

- `axis=auto` 成为默认：按每个指标真实存在的 `global_step` → `epoch` → `timestamp` 回退；响应中每个系列带自己的 `axis`，不伪造 Step。
- `MetricChart` 始终渲染容器，空状态用覆盖层；新增 Vitest 生命周期测试。
- 状态与活动分离：`status` 只由生命周期/心跳决定；`activity` 独立显示“最近仍在更新 / 已停止更新 / 已结束 / 活动未知”。没有 heartbeat 时不再因指标更新显示“运行中”。
- 指标表唯一键改为 `(run_id, source_file, source_offset, phase, metric_name)`；数据库 v1 自动迁移到 v2，保留旧数据。

**数据接入**

- 新增通用日志文件来源：任意文件名 CSV/TSV/JSONL、`*.log`/`*.txt`/`*.out`，内容嗅探后每文件一个 Run；纯业务 CSV 不导入。
- 新增通用 JSONL、纯文本规则读取器；普通文本识别 Step/Epoch + 明确指标键值。
- 新增本机系统目录选择接口 `POST /roots/select`（无桌面环境返回 501，并提示输入框/CLI/VS Code）。
- `training-viewer open` 无参数时明确提示恢复上次工作区（根目录本就持久化）。
- 扫描改为“每 2 秒只重读已知 Run；每 300 秒全量兜底；watchdog 目录事件立即全量”。
- 写入器把省略/`None` 的 `direction` 规范为 `none`，拒绝非法方向。

## 3. 为什么这样改

审阅的核心判断是：后端骨架可保留，问题在默认使用路径和信息架构。因此不重写系统，而是：

1. 把“看到曲线”放到首屏，把管理/诊断降级；
2. 用真实数据选择横轴，修掉可由代码推导的空图路径；
3. 把“日志活动”和“训练进程状态”分开，避免把文件写入冒充进程存在；
4. 用增量扫描和内容嗅探扩大可用输入，而不是要求用户先改训练代码；
5. 所有行为变化都保留原始日志只读、SQLite 可重建、TVLP 1.0 字段不变。

未采用的替代方案：

- 为首页另写一套图表库：复用现有 ECharts `MetricChart`。
- 用指标更新时间推断 `running`：会误导用户，改为独立 `activity`。
- 每次轮询都全量扫描：目录大时成本高，改为已知 Run 重读 + 长周期全量。
- 把任意文件都强行导入：会制造假指标；只接受能嗅探出 Step/Epoch + 数值指标的文件。

## 4. 影响范围

- 后端：`index_queries.py`（auto axis/activity/saved view）、`training_metric_indexer.py`（状态/唯一键/共享目录）、`database.py`（schema v2 迁移）、`service.py`（增量同步）、`watch/log_update_watcher.py`（目录事件）、`source_adapters/generic_log_file_adapter.py`、`log_readers/generic_jsonl_reader.py`、`log_readers/plain_text_log_reader.py`、`csv_metric_reader.py`、`system_directory_picker.py`、`routes_catalog.py`、`routes_metrics.py`、`writer.py`、`cli.py`。
- 前端：`OverviewPage`、`RunDetailPage`、`ExperimentsPage`、`ComparisonPage`、`RunMetricsTab`、`MetricChart`、`ChartControls`、`AppShell`、`DiagnosticsPage`、新增 `RootDirectoriesPanel` / `LatestArtifactPreview`、样式与类型。
- 测试：新增 `tests/test_axis_and_generic.py`、前端 `MetricChart.test.tsx`、`e2e/smoke.mjs`。
- 协议：TVLP 1.0 字段不变；`axis` 是查询参数，不是日志字段。
- 数据库：schema v2；启动时自动迁移旧 `metric_points`。

## 5. 验证结果

- `pytest -q`：**76 passed，2 skipped**（Windows 不允许创建符号链接）。
- `ruff check src tests tools --select F,E9`：通过。
- `npm run typecheck`：通过。
- `npm run test`：2 个 MetricChart 生命周期测试通过。
- `npm run build`：通过，构建资源写入 `src/training_viewer/web/`。
- `npm run e2e`：真实 Chrome 打开监控、实验库、运行详情、对比页；无 console error；截图见 `.devtools/e2e`。
- 真实数据：`TrainingRunWriter` 生成 live Run；查看器自动发现，首页显示 running/updating 与曲线；完成后显示 completed/finished。
- 性能：10k / 100k / 1M 点基准与 TensorBoard 20k 基准见 [`docs/performance.md`](../performance.md)。1M 查询约 9.4 秒，已明确列为瓶颈，不宣称秒开。

## 6. 回退方式

- 回退前端：恢复 `frontend/src/` 到 0004 提交并重新 `npm run build`；旧静态资源会覆盖新页面。
- 回退后端：恢复 `service.py` / `watch` 到 0004；保留 schema v2 也可运行（只是唯一键更宽），但旧代码不会生成 `activity` 字段。
- 回退 schema：需要先备份数据库；v2 → v1 不支持自动降级，删除 `index.sqlite3` 可重建。
- 通用来源：从 `builtin_adapters.py` 移除 `GenericLogFileSourceAdapter` 注册即可停止导入任意文件。
- 风险：回退首页会恢复“先配置后看曲线”；回退增量扫描会恢复每 2 秒全目录遍历。

## 7. 文档同步情况

- [x] README：两种接入模式、零配置打开、新导航、默认列、自动横轴
- [x] `AGENT_INTEGRATION.md`：已有日志 vs 新实验、心跳与 activity 语义、direction 约束
- [x] 架构：通用来源、增量/全量扫描、schema 唯一键、状态与活动
- [x] 日志来源：任意文件嗅探、自动横轴、活动标签
- [x] API：`axis=auto`、`/roots/select`、`GET /saved-views/{id}`、activity 字段
- [x] 术语表：Activity、Generic Log File Source、Auto Axis
- [x] 开发文档：前端测试、E2E、性能脚本
- [x] 性能：`docs/performance.md`
- [x] 变更记录：本文件

## 8. 未完成与风险（必须如实告知）

- **字段映射持久化未做**：歧义 CSV 需要先改成明确列名；没有“保存映射模板”的 UI/DB。审阅中的这一项没有完成。
- **TensorBoard 仍非真正 seek 增量**：使用事件序号游标，但从文件开头遍历跳过；20k 规模可接受，十万级以上未验证。
- **跨平台未实机复验**：只在 Windows 运行了安装、测试、构建、E2E；macOS/Linux 的目录选择框、watchdog、路径大小写差异未验证。
- **百万点查询仍慢**：9.4 秒，瓶颈为全量扫描后 Python 分桶；未做数据库端预聚合。
- **普通文本仅规则模板**：复杂格式可能不识别；当前没有“需要确认”的三态 UI。
- 审阅的“一键对比”压缩为运行行 `+ 对比` / 运行页“加入对比”后仍需在对比页确认指标；没有做到完全零点击。
