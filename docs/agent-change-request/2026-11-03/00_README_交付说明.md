# Training Viewer Agent 整改交付包

版本：1.1（2026-11-03，新增大量指标选择和单次评估分流）。该版本更新上一版交付包，不是第二个独立任务。

此包用于直接交给 Claude Code、Codex 或其他代码 Agent 对 `niupai1001/training-viewer` 开展整改。

## 文件与阅读顺序

1. **`03_Agent_Execution_Prompt.md`**：将文件全文作为 Agent 入口任务发送，要求 Agent 读取其余文件并直接执行。
2. **`01_Training_Viewer_Change_Contract.md`**：不可降低的工程、数据、协议、UI 与真实验收契约。
3. **`02_Training_Viewer_Implementation_Plan.md`**：阶段 0–5 的文件级实施路线、开源组件选型和交付清单。

契约的 A01–A24 是验收编号，阶段计划与验收标准一一对应。请将本包全部文件放入仓库工作区，例如 `docs/agent-change-request/2026-11-01/`，并与项目原有 AGENT_INTEGRATION、TVLP 协议文档一起供 Agent 阅读。

**审计基线**：`405e2a52712f8a826e53b28ae5f89050f2feb8ed`。当前工作树/最新 HEAD 与基线不同，Agent 应先审查差异，避免覆盖已修改部分。

**重要限制**：这是一套修改契约与实施方案，不代表代码已实施或真实 CUDA 故障已排除。

**本次新增：** 图片显示大量 `capacity/*`、`combo_SWIR_pair/*` 等字段，旧界面把一点评估数据当成训练曲线候选。契约 C10 强制实现可搜索指标目录、分组、分页、自定义图表、单点评估表及视图持久化。新增 A16–A24 验收。
