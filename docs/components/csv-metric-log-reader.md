# 组件说明：CSV 指标日志读取器（CsvMetricLogReader）

## 一句话说明

按显式列映射（或可验证的数值列推断）把 `metrics.csv` 转换成指标记录；不猜测缺失的 Step/Epoch，不修改 CSV，也不判断指标方向。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | CSV 指标日志读取器 |
| 代码类名 | `CsvMetricLogReader` |
| 源文件 | `src/training_viewer/log_readers/csv_metric_reader.py` |
| 所属模块 | 日志读取 |
| 上游 | `StandardTvlpSourceAdapter`（有 run.json）或 `CsvSourceAdapter`（无 run.json） |
| 下游 | `TrainingMetricIndexer` |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

已有实验常把指标导出为 CSV。直接按列位置猜测会把时间、标签或注释列当成指标，产生错误曲线。本组件要求明确列映射，或在没有映射时只接受“所有非空值都能解析为有限数字”的列；不能建立训练横轴的行会被报告而不是伪造。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 | 错误时 |
|---|---|---|---|---|
| 输入 | `file_path` | `Path` | `metrics.csv` | 不存在 → warning |
| 输入 | `run_directory` | `Path` | 计算相对来源路径 | — |
| 输入 | `cursor` | `FileCursor \| None` | `offset` 为数据行号，`size` 为文件大小 | 文件变小/身份变化 → 重置 |
| 输入 | 列映射 | `dict \| None` | 来自 `run.json` 的 `extensions.csv_metric_mapping` | 未知键或列不存在 → 问题并暂不导入 |
| 输出 | 指标记录 | `MetricPoint` 列表 | 每个数值单元格一条 | 空单元格跳过 |
| 输出 | 问题 | `ParseIssue` 列表 | 行号、原因 | 最多 50 条 |

### 支持的映射键

`step_column`、`epoch_column`、`timestamp_column`、`phase_column`、`session_column`、`metric_columns`（数组）。

没有显式映射时的列名别名：

- Step：`global_step`、`step`、`iteration`、`iter`、`iters`
- Epoch：`epoch`、`epochs`
- 时间：`timestamp`、`time`、`wall_time`、`date`、`datetime`
- 阶段：`phase`、`mode`、`split`
- 会话：`session_id`、`session`、`run_id`、`run`

## 主要处理流程

1. 读取表头（UTF-8 BOM 兼容）。
2. 若提供显式映射，逐列检查是否存在；不存在则报告并停止导入本文件。
3. 否则按别名识别 Step/Epoch/时间/阶段/会话列；其余列只有在全部非空值都为有限数字时才作为指标列。
4. 若既无 Step 也无 Epoch，报告“无法建立训练横轴”，不导入。
5. 从游标行号开始逐行读取；空行跳过。
6. `phase` 缺失时写 `unlabeled`；时间缺失时写 `NULL`，不伪造时间。
7. 每行数值生成指标记录；`source_offset` 为数据行索引，保证重复同步不重复入库。
8. 返回新游标（数据行总数）与问题列表。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 默认阶段 | `unlabeled` | 无 `phase` 列时的显示名称 |
| 分隔符 | 逗号 | 不支持分号/Excel 区域设置分隔符；请先转换 |
| 单次错误上限 | 50 | 防止损坏文件刷爆诊断 |

依赖 Python 标准库 `csv`。无第三方依赖。

## 和旧实现相比改变了什么

初始实现。V1 没有旧版本；2026-10-31 验证确认：映射列缺失、缺少 Step/Epoch、数值列识别均在测试覆盖范围内。CSV 来源与标准 TVLP 共用同一索引器，因此截断/重复规则一致。

## 如何验证

- `tests/test_indexing.py::test_csv_metrics_with_explicit_column_mapping`
- `test_csv_without_run_json_uses_synthetic_metadata`
- `test_csv_without_step_or_epoch_is_reported_not_invented`
- 手工：`examples/csv_training_log` 应显示 `train/loss`、`val/accuracy` 与 `learning_rate`。

## 已知限制与回退

- 只支持逗号分隔；不支持 `;` 或 Excel 多表。
- 日志按追加方式处理；就地修改已有行不会改写已索引的指标点。需要修正历史值时，应重建索引并保留原始文件版本说明。
- 没有显式映射时，阶段/时间靠英文别名识别，其他语言列名需要在 `run.json` 中显式映射。
- 文件变化时整体重读（行号幂等）；超大 CSV 需要后续优化。
- 回退：删除索引后重新扫描；CSV 文件不被修改。

## 名称解释

- CSV：Comma-Separated Values，逗号分隔值。
- 列映射：把 CSV 列名对应到协议字段的显式配置。
- `unlabeled`：未标注阶段，界面显示“未标注阶段”。
