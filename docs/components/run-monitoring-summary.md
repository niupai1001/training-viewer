# 运行监控摘要（RunMonitoringSummary）

## 职责

把分散在运行状态、指标点和生命周期事件里的首屏信息，统一成后端摘要，避免前端从任意字段拼 KPI。API：`GET /api/v1/runs/{run_id}/summary`。

## 输入 / 输出

- 输入：`runs`、`metric_points`、`training_events`、`run.json`。
- 输出：`timing`、`current_epoch/global_step`、`train_loss`、`val_loss`、`primary_validation_metric`、`learning_rate`、`last_log_at`。
- 不写数据库、不改变原始记录。

## 计时语义

- 有 started/resumed 与结束事件：按 session 累计，停机间隔不计入 `active_training_seconds`；`source=lifecycle_events`。
- 没有生命周期：只返回指标首末 `wall_span_seconds`，`source=metric_timestamps`，`quality=partial`。
- 开放会话：用最后指标作为活动证据估算，`open_session=true`、`quality=partial`；不把当前时间差无限累加。
- UI 在有累计时长时显示“累计运行时长”，否则显示“日志跨度”。

## 指标选择

复用指标目录的 `train_loss`、`val_loss`、`primary_validation`、`learning_rate` 角色；声明优先。没有指标返回 `null`，由前端显示“未记录”，不以 Test 代替 Val。

## 已知限制

- 没有 `RunMonitoringSummary` 的缓存；每次 API 查询执行固定次数的 SQL。
- 开放会话估算仍可能把训练后长时间停顿算入，因此标记 partial，不当作确认值。
- 计划 Epoch 只从 `config.epochs` 读取，未做任务级推断。
