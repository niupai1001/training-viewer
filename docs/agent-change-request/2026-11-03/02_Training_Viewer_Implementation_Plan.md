# Training Viewer 详细整改实施方案

> 对应强制契约：`01_Training_Viewer_Change_Contract.md`  
> 项目版本基线：`405e2a52712f8a826e53b28ae5f89050f2feb8ed`（开始执行先检查远端 HEAD）  
> 实施方式：分阶段提交、每阶段可运行、保留历史日志兼容；不要求修改用户本地历史数据。

## 1. 项目现状与重构取舍

### 已确认有价值、应尽可能保留

- `src/training_viewer/log_readers/`：标准 JSONL、普通 JSONL、CSV、文本、TensorBoard 的日志读取能力；继续维护游标、错误恢复和只读约束。
- `src/training_viewer/indexing/`：SQLite 数据索引与时间序列查询；保留并扩展统一语义摘要，不重建一整套指标数据库。
- `src/training_viewer/service.py`、`api/routes_*`：扫描、SSE 增量通知、API 端点；扩展，不随 UI 迁移重写。
- `frontend/src/charts/echarts.ts` 和 `MetricChart.tsx` 内已有 ECharts 接入：保留图表内核，重构选项与展示。
- 标准 TVLP 1.0 与用户状态独立存储：继续兼容，明确迁移/回滚路径。

### 必须重做/整合

- `RunMetricsTab.tsx` 的“选指标 → 展开大图 → 下方表格”默认主流程；将其变为高级分析，建立新的 `TrainingOverview` 默认视图。
- `AppShell.tsx` 与 `RunSelector.tsx` 的层级与空间组织；唯一左栏，右侧监控视图。
- 图表尺度处理、指标语义层、运行时间汇总和默认 KPI。
- 手写基础 UI 的统一风格；逐步迁移到一种成熟设计系统，清理旧 CSS。

### 暂不迁移

- 不立刻迁移到 MLflow/Aim 后端，也不把 MLflow SQLite 和自研索引同时作为长期权威数据源。原有仓库已有 MLflow 对照实验，但不足以证明所有场景都适合迁移。本轮重点是日志接入正确性与终端查看体验。
- 不开发远程日志读取、插件商店、账号系统、训练调度/推理服务。

## 2. 阶段 0：建立可复现基线与失败用例（必须先完成）

**任务**

1. `git status`、确认 `HEAD`、审查现有分支状态；创建单独工作分支。
2. 执行现有 `pytest`、前端 `typecheck`、`vitest`、`build`、Playwright E2E；记录通过/失败/跳过，区分未安装依赖与真实失败。
3. 在仓库 `tests/fixtures/` 或 `frontend/e2e/fixtures/` 加：大初始 Loss、Train/Val Loss、只有 Train Loss、未知进度键、断点续训时间跨度、老版本 run.json、v1.1 新样本（先按预期失败）。
4. 记录 UI 旧截图（1440×900、1366×768）与真实目录输入来源清单；不要用静态 mock 冒充运行结果。
5. 将本次问题与 A01–A15 用例映射到测试文件，先实现最危险路径的失败测试（Red）。

**阶段验收**：提交一份基线表、真实旧截图、失败用例及执行命令；无功能变化时也不能宣称重构完成。

## 3. 阶段 1：后端监控摘要与指标解释（最高优先级）

**主要文件**

- 新建 `src/training_viewer/metrics/metric_semantics.py`（指标语义解析）和 `src/training_viewer/monitoring/run_monitoring_summary.py`（统一监控摘要）；根据项目简化路径，避免仅为分层过度拆文件。
- 修改 `src/training_viewer/indexing/index_queries.py`，添加 `get_monitoring_summary(run_id)`。
- 修改 `src/training_viewer/api/routes_metrics.py` 或 `routes_catalog.py`，提供 `GET /api/runs/{run_id}/summary`（具体路径遵循现有 API 风格）。
- 修改 `frontend/src/types.ts`、`frontend/src/api/client.ts`。
- 增加 `tests/test_metric_semantics.py`、`tests/test_run_monitoring_summary.py`。

**实现要点**

- `MetricSemanticResolver` 四级来源优先级，允许读旧元数据，不在导入时自动写回。
- 识别 Loss/Val Loss/学习率/验证指标，强制保留 `raw_key`、`phase`、`source` 和未知定义提示。
- 计算累计运行时长、日志跨度、生命周期状态和活跃状态时标注证据类型，不以数据正在追加推断进程状态。
- `primary_validation_metric` 优先使用明确声明；别名识别仅做安全默认，不对未知分数自动排名。
- SSE 更新应让相应 Run 的摘要和指标重新查询，不以 `status==='running'` 为条件。

**阶段验收**：A03–A07、A11 的 API 级测试通过；对同一输入重建缓存后查询结果一致；后端返回摘要示例附真实字段出处。

## 4. 阶段 2：曲线尺度与科学显示（P0）

**主要文件**

- `frontend/src/components/MetricChart.tsx`
- `frontend/src/components/ChartControls.tsx`
- `frontend/src/utils/format.ts` / `frontend/src/utils/smoothing.ts`
- 新建图表尺度纯函数 `frontend/src/charts/lossAxisPolicy.ts`（计算可见范围、后期范围、正值判定、刻度格式）
- `frontend/src/components/MetricChart.test.tsx` + E2E 对应测试

**实现任务**

1. 将图表设置从整排控件移到图表内轻量操作菜单；按钮清晰显示“全程 / 聚焦后期 / 对数 / 更多”。
2. 后期聚焦使用**最后 20% 横轴范围**与实际可见数值重算 Y 轴；后端窗口查询时解决 `datazoom` 更新循环与视图跳转。
3. 同一 Loss 图支持 Train 和 Val 两条序列，实际 Val 点稀疏时只连原始记录点，不补齐不存在的数据。
4. 确保 tooltip 显示真实值、Step/Epoch、原始来源；图例优先使用语义化显示名。
5. 导出 PNG/SVG 保留当前缩放；原始 CSV 不与显示缩放/平滑混为一谈。
6. 支持无数据、单点、全零、负数、常数、大离群值、Session 切换与两个实验对照。

**阶段验收**：A01、A02、A03；提供全程/后期/对数三张真实浏览器截图，后期坐标范围实际变化可被 E2E 断言，不能只检查按钮存在。

## 5. 阶段 3：新默认监控工作区与视觉体系（P0/P1）

**主要文件**

- `frontend/src/pages/TrainingWorkspacePage.tsx`
- `frontend/src/components/AppShell.tsx`
- `frontend/src/components/RunSelector.tsx`
- `frontend/src/components/RunMetricsTab.tsx`
- `frontend/src/styles.css`
- 新建 `TrainingOverview.tsx`, `TrainingSummaryCards.tsx`, `TrainingLossPanel.tsx`, `ValidationScorePanel.tsx`, `ExperimentListItem.tsx` 等必要组件，名称应反映功能，不为每个卡片额外做一层抽象。

**推荐设计技术**

- `shadcn/ui + Radix + Tailwind` 为单一选型；先制作一个可交互的真实数据页面，再整体迁移。不使用 UI 框架默认视觉作为最终设计。
- `react-resizable-panels` 处理唯一实验栏宽度、折叠与持久化。
- 保留 ECharts 图表，不因引入 shadcn 改写为 Recharts。
- `TanStack Table` 仅用于高级实验列表/参数对比，不引入默认首页。
- 所有使用的第三方包应锁定版本并更新 `docs/third-party-licenses.md`。

**屏幕与交互规格**

- 1440×900：一个实验栏（340–420px），六项 KPI、Loss 图主要部分可见，默认不出现指标表格/横轴长工具栏。
- 1366×768：核心 KPI 可一至两行排列，Loss 图的标题与曲线起始部分在首屏；不能被大段介绍文字挤到折叠下方。
- 实验栏标题显示 2–3 行组合名，鼠标悬停/详情能看到四要素完整说明；不要用省略号丢掉模型架构与改动。
- 点击实验行＝切换当前实验；单独“比较”控件＝添加到对比。避免现在复选框造成含糊的交互。
- 图像结果区域按需展开，仍可关联原图、标签、预测；不应转为只有文件路径的列表。
- 提供亮/暗主题，适当展示状态，但不为每条普通信息使用彩色徽章。

**阶段验收**：A10、A11，移动端适配与键盘导航通过；对照旧版截图附“消失了哪些重复入口与配置项”的差异说明。

## 5A. 阶段 3B：海量指标浏览器与自定义图表（新增 P0）

此阶段与阶段 3 的新设计系统整合，不要只在旧 `RunMetricsTab` 上增加更多折叠块。必须先使用截图中实际的 `capacity/*`、`combo_SWIR_pair/*` 形态建立固定回归夹具，覆盖 1 点、两点、多点和重复横轴。

**后端：** 扩展 `src/training_viewer/indexing/index_queries.py` 的指标目录查询、分页、分组、独立 X 值计数与分类；在 `src/training_viewer/metrics/metric_semantics.py` 或职责明确的邻近模块输出 `MetricCatalogItem`，并在 API routes 增加独立搜索端点。分类属于显示建议，不能改写指标原始内容。

**前端：** 新建一个 `MetricBrowserDrawer` / `MetricCatalog` 组件，替换目前主页面 `metric-picker` 的全量按钮云。支持搜索（中文名、原始字段、说明）、按阶段与语义类别筛选、路径树分组、按页加载、选中预览、添加新图/加入现有图、移除和重新排列。`RunMetricsTab.tsx` 中默认按选中数目输出图表的旧逻辑应迁移到高级区；不得保留选 6 项仅展示 2 项的不一致行为。

**单次指标：** 新增表格型 `MetricEvaluationTable`，用于一个点的组合指标；对于明确声明结构维度的组合，提供可选热力图。单点不得被删除或强行画出有连续趋势的折线。

**视图存储：** 在 Viewer 独立用户状态中保存选中原始键、图表位置、类型、横纵轴配置；提供恢复、删除和字段失效提示。跨实验对比仅在同语义和量纲下叠加。

**性能：** 千级指标不能一次绘制成按钮群；在 1,000 与 10,000 指标夹具下记录 API 响应体、搜索耗时、首屏 DOM 节点数。避免 UI 把全部候选先加载到内存再隐藏。

**阶段验收：** 契约 A16–A24。交付新的 1440×900 首屏、指标浏览器展开、搜索结果、单次评估表格和自定义多曲线截图。

## 6. 阶段 4：TVLP v1.1 契约与 Writer 端到端升级

**主要文件**

- `schemas/` 与 `src/training_viewer/schemas/`：新增 v1.1 Schema，不覆盖 v1.0。
- `src/training_viewer/run_metadata.py`：版本分流校验，新增 `experiment_description` 与指标元数据。
- `src/training_viewer/writer.py`：新输出可选 v1.1/逐步设为默认，要求四段描述；保持默认无后台心跳线程。
- `src/training_viewer/log_validation.py`：按版本校验、明确缺项及修复建议。
- `src/training_viewer/source_adapters/`：历史文件名推断信息与标准字段分离，禁止虚构模型架构。
- `AGENT_INTEGRATION.md`、`docs/documentation_and_naming_standard.md`、`docs/glossary.md`、`docs/log-sources.md`：同步，并包括 C10 规定的指标分组与建议视图字段。

**落地流程**

1. 明确语义字段、版本规则、迁移策略，写 Schema 正反例及 Writer 行为测试。
2. 添加新 Writer 参数和名称生成器，禁止空字符串/`obs`/纯版本号成为 1.1 新 Run 的说明字段。
3. Viewer 只读导入旧日志；无说明者保留原始标签但将完整身份标为缺失，可存 Viewer 侧补充元数据。
4. 保留 `run_id` 与断点续训一致性，增强状态/生命周期信息记录而不干扰训练进程。
5. 训练 Agent 接入指令必须给出 1.1 示例和“没有数据就写未记录而非编造”的原则。

**阶段验收**：A08、A09、A15。校验器能够同时接受合法 v1.0 和 v1.1 文件；错误字段有中文诊断且不影响旧实验读取。

## 7. 阶段 5：高级分析、性能、真实环境集成

**关键范围**

- 对比运行下共同指标选择、相同量纲与定义提示、共享可见范围；保留自定义指标与参数差异。
- 不再以 `<RunMetricsTab chartLimit={2}/>` 截掉选中的第三个指标，默认图表应有明确的指标槽位。
- 百万级指标的数据查询仍通过后端窗口和降采样，无全量点传给浏览器；验证性能、缓存失效和图表内存。
- Windows/CUDA 训练器单独验证 Writer；严格对照后台心跳开关与直接文件写入，未实机复现不能关闭缺陷。
- 对真实 62 个来源记录输出 `原始文件 → 逻辑 Run → 数值点数 → 映射方式 → 可信程度`，说明重复/缺失项。
- 旧收藏、备注、保存的对比视图、现有日志与产物路径继续可用；必要迁移提供回滚策略。

**阶段验收**：A12–A15，真实端到端测试通过；不得因 E2E 通过就宣称 Windows/CUDA 问题也验证完成。

## 8. Agent 实施与提交规则

1. 各阶段尽量形成独立、可回滚提交（建议：测试基线、语义与摘要、尺度、UI、协议、集成），避免一次覆盖所有文件。
2. 每阶段先给出简短实现列表，随后直接编码、运行测试、启动真实页面并截图；不要反复停留在方案讨论。
3. 对已有公共 API 的变更应更新调用方和合同测试；不允许只修改组件渲染或只添加新页面而未接上真实日志。
4. 需要拉取第三方项目源代码时检查 LICENSE/NOTICE，记录使用方式、依赖版本及替代原因；不要复制未经核验的商业图标或图片。
5. 不要修改或删除历史训练文件；写入实验演示数据必须位于明确的测试/临时目录。
6. 修改后列出实际提交 SHA、文件清单、命令、测试结果、关键截图路径与不可验证项目；不能使用“全部修复”概括未实测内容。
7. 严格保持新组件职责和名称可理解：每个重要组件中文一句话说明“输入、处理、输出、边界”；日志版本、产品版本与组件变更版本不得混为一谈。

## 9. 交付物与最终验收表

**仓库应交付**

- 可运行的新版单工作区，而非静态效果图。
- v1.0/v1.1 兼容实现和协议范例、准确的验证器输出。
- 自动化测试结果（后端、前端、E2E）；浏览器实机截图：`1440x900-overview.png`、`1366x768-overview.png`、`loss-full.png`、`loss-late-focus.png`、`loss-log.png`、`compare.png`。
- 真实实验来源清单及关键曲线与日志原始数据的一致性验证。
- Windows/CUDA Writer 实测记录，若无环境则标为“阻断项未关闭”。
- 更新 README、用户操作文档、工程架构、术语表、组件文档、变更日志、第三方许可证。

**完成定义**：项目通过 `01_Training_Viewer_Change_Contract.md` 的 A01–A24 逐项验证，或将不可验证的环境项明确列为尚未完成。不得用页面数量、组件数量、代码行数或静态截图替代实际功能验收。
