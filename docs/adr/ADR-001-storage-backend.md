# ADR-001：存储与查询后端选择

- 状态：Accepted
- 日期：2026-10-31
- 关联：Deep Audit 2026-10-31 阶段 2
- 决策：继续使用本机 SQLite 索引，不把 MLflow 作为权威存储

> 范围限定：该决策针对**当前单用户、本机、只读导入、轻量启动**的训练查看器；它不声称 MLflow 在所有场景都劣于 SQLite，也不覆盖 MLflow 的全部存储后端。

## 1. 问题

现有 SQLite 已经能保存 Run、指标、产物引用和游标，但审计指出：

- 指标查询把全量点搬进 Python 再降采样，百万点慢；
- 指标、备注/收藏/保存视图混在一个可重建数据库；
- 需要判断是否用 MLflow Tracking 替换自研的 `runs/metric_points` 查询与存储。

约束：本机单用户、原始日志只读、TVLP 1.0、无训练 SDK 依赖、Windows/CUDA 环境。

## 2. 比较过的方案

| 方案 | 结论 |
|---|---|
| A. MLflow Tracking 作为权威存储，TVLP importer 写入，前端读 MLflow | 隔离原型已跑通，但导入慢、依赖重、session/epoch 语义不匹配；不作为生产后端 |
| B. 保留 SQLite，修复数据正确性、隔离用户状态、SQL 层降采样/索引优化 | **采用** |
| C. Aim 作为存储/可视化引擎 | 不采用；引入新 SDK 和存储耦合，无法直接满足“任意历史日志只读导入” |
| D. TensorBoard 核心 | 不采用；只能作来源，不能承担身份、比较和工作区 |

## 3. 实测

环境：Windows，Python 3.13，本机 SSD，合成 TVLP 指标。

### MLflow 隔离原型

`tools/mlflow_spike.py`，MLflow 3.17.2（`mlflow-skinny`），文件后端：

| 数据量 | 导入 | 单指标 history | 备注 |
|---:|---:|---:|---|
| 10,000 点 | 9.309 s | 0.047 s | 导入为逐批 `log_batch`；文件后端需 `MLFLOW_ALLOW_FILE_STORE=true` |

同规模现有 SQLite：首次索引约 0.4 s，查询约 0.1 s（见 `docs/performance.md`）。MLflow 导入没有减少工程量，反而增加：

- importer 必须维护 `source_run_id → mlflow_run_id` 与幂等高水位；
- `epoch`-only、`session_id`、`epoch_progress` 没有原生一一映射；
- 文件后端处于维护模式，SQLite 后端需要完整 `mlflow` 依赖；
- MLflow 默认 UI 不符合“曲线与结果为中心”的工作区目标；
- 仍需自研来源身份、逻辑实验归并和只读边界。

### SQLite 优化

- 增加覆盖索引和物化桶后，100 万点首次查询约 3.1 s（同机同数据，见 `docs/performance.md`）。
- SQL 层 min/max/首/尾分桶仍扫描全量或区间，但不再把全部点搬进 Python；返回点数受 `max_points` 限制。
- 100 万点索引约 44 s、SQLite 约 1.66 GB；这是当前明确代价，未宣称“百万点秒开”。

## 4. 决策

**采用 B：保留 SQLite 作为唯一权威后端。**

- 不新增 `mlflow` 运行时依赖；spike 只保留在 `tools/`，不进入主程序。
- 不保留两份同时写入的权威元数据。
- 指标索引库与用户状态库分离（`index.sqlite3` / `user_state.sqlite3`）。
- 查询继续在 SQLite 上做 SQL 分桶和覆盖索引；后续若需要百万点首屏更快，再评估物化桶，而不是迁到 MLflow。

## 5. 兼容与回退

- TVLP 1.0 字段不变；已有日志无需迁移。
- 旧 `index.sqlite3` 的备注/收藏/保存视图启动时复制到 `user_state.sqlite3`；旧库保留但不再作为用户状态权威。
- 删除 `index.sqlite3` 可重建指标索引，不会删除用户状态。
- 回退 MLflow 不需要：没有生产代码依赖它。若未来重新评估，保持 `tools/mlflow_spike.py` 作为可复现实验，不将探索性引擎写进生产路径。

## 6. 未验证 / 风险

- 没有用户的 62 个真实来源文件，无法在此环境复核 53→62 的身份差异；`tools/export_source_inventory.py` 已提供逐文件清单，需要在真实数据目录运行。
- 100,000 点 MLflow 对比未完成（原型在 10,000 点已显示导入明显更慢）；不据此宣称所有规模结论。
- 百万点查询 3.5 s 仍高于“首屏即时”；物化桶/窗口范围查询未实现。
- 前端 1440×900 / 1366×768 的真实浏览器验收仍需在重建工作区后执行。
