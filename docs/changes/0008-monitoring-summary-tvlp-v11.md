# 0008：RunMonitoringSummary 与 TVLP 1.1

- 日期：2026-11-03
- 依据：V1.1 契约 C2、C5、A06–A09
- 状态：**后端摘要与 TVLP 1.1 首版完成；历史 1.0 保持兼容**

## RunMonitoringSummary

新增 `GET /api/v1/runs/{id}/summary`，避免前端从零散字段拼 KPI：

- `timing.active_training_seconds`：按生命周期 started/resumed 与 completed/failed/cancelled 分会话累计；开放会话到最后一个指标，标记 `open_session`。
- `timing.wall_span_seconds`：有 started+结束事件用生命周期跨度；否则用指标首末，标记 `metric_timestamps`。
- `timing.source` / `quality` / `open_session` 明确证据，不把指标首末叫“有效训练时长”。
- `current_epoch` / `current_global_step` / `planned_epochs`。
- `train_loss`、`val_loss`、`primary_validation_metric`、`learning_rate`，包含最新值、Best、单位、方向、定义来源；缺失为 `null`。
- UI 的六项摘要改为读该摘要；有生命周期时显示“累计运行时长”，否则显示“日志跨度”。

测试：`tests/test_run_monitoring_summary.py` 覆盖双会话停机不计入、无事件只用日志跨度、开放会话估算。

## TVLP 1.1

新增：

- `schemas/run-1.1.schema.json` 与包内副本。
- `experiment_description` 四段必填：`data_description`、`model_architecture`、`modification_plan`、`research_objective`；`change_details` 可选。
- `metric_definitions` 1.1 可选 `category`、`semantic_group`、`suggested_view`、`default_visibility`、`is_primary`、`display_name_en`；`direction` 可省略。
- 可选 `metric_groups`（路径/标签，不改变原始指标）。
- `RunMetadataReader` 按版本校验，1.0 拒绝 1.1 专属字段。
- `TrainingRunWriter` 增加 `schema_version` 与 `experiment_description`；默认仍为 1.0，显式 1.1 时四段必填。
- `log_validation.py` 与 `tools/validate_log.py` 按版本选择 Schema。
- 前端 `RunMetadata.experiment_description` 与可展开四段说明。

测试：`tests/test_tvlp_v11.py` 覆盖 1.1 写读校验、缺段拒绝、1.0 兼容且拒绝 1.1 字段。

## 验证

```powershell
pytest tests/test_run_monitoring_summary.py tests/test_tvlp_v11.py -q
npm run typecheck
npm run build
npm run e2e
```

本机：后端 104 passed, 2 skipped；前端 3 Vitest；E2E 通过。

## 未完成

- `TrainingRunWriter` 默认仍输出 1.0；新训练 Agent 需要显式 `schema_version="1.1"`。
- 尚未提供“从四要素自动生成 name”的强制生成器；当前要求调用方传入摘要名。
- 指标 `metric_groups` 只进入校验/元数据，尚未驱动热力图或复杂维度 UI。
- 无真实 62 来源、无 CUDA 实测，保持未关闭。
