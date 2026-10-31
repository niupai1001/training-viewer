# 组件说明：标准训练日志增量读取器（StandardTrainingLogReader）

## 一句话说明

把 `metrics.jsonl` / `events.jsonl` 中新增的**完整行**转换为与来源无关的指标、产物、生命周期或心跳记录；不写数据库、不生成界面数据，也不修改训练日志。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 标准训练日志增量读取器 |
| 代码类名 | `StandardTrainingLogReader` |
| 源文件 | `src/training_viewer/log_readers/standard_training_log_reader.py` |
| 唯一组件标识 | `source.standard_training_log`（文件读取器层面复用同一标识） |
| 所属模块 | 日志读取 |
| 上游 | `StandardTvlpSourceAdapter`；下游 | `TrainingMetricIndexer` |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

训练进程会持续追加日志，而查看器可能随时启动、退出或重启。整文件重读会重复入库，直接读尾行会把写了一半的 JSON 当坏数据。本组件只消费完整新增行，并把无法解析的行报告为带行号的问题。它不负责数据库去重、状态推导或产物文件存在性检查。

## 输入与输出

| 方向 | 名称 | 类型 / 单位 | 说明 | 缺失或错误时 |
|---|---|---|---|---|
| 输入 | `file_path` | `Path` | 日志文件绝对路径 | 文件不存在 → warning 问题，返回空结果 |
| 输入 | `run_directory` | `Path` | 用于计算数据库中的相对来源路径 | — |
| 输入 | `cursor` | `FileCursor \| None` | 上次的文件身份、字节偏移、行号、大小、mtime | `None` 或身份/大小不匹配 → 从头读取并标记 `reset` |
| 输出 | `records` | `MetricPoint` / `ArtifactRecord` / `LifecycleRecord` / `HeartbeatRecord` 列表 | 每个指标/事件一条 | 坏行不产生记录 |
| 输出 | `issues` | `ParseIssue` 列表 | 文件名、从 1 开始的行号、中文消息、级别 | — |
| 输出 | `cursor` | `FileCursor` | 新的字节偏移、下一行号、大小、mtime | 无法 stat 文件时无游标 |
| 输出 | `reset` | `bool` | 是否检测到截断/替换 | 索引器据此删除该文件旧索引 |

`metrics.jsonl` 的一行可以包含多个指标，因此会生成多条 `MetricPoint`，它们的 `source_offset` 相同、`metric_name` 不同。

## 主要处理流程

1. `stat` 文件，取得设备号 + inode（Windows 上同样可用）作为文件身份。
2. 如果游标缺失、文件身份变化或当前大小小于游标偏移 → 从头读取并设置 `reset=True`。
3. 从游标偏移读取到文件末尾，查找最后一个换行符；只处理它之前的完整行。
4. 逐行解码 UTF-8 并解析 JSON，拒绝 `NaN`/`Infinity`。
5. 指标记录校验：`timestamp` 带时区、`phase` 非空、`metrics` 非空且值为有限数字、至少有一个 Step/Epoch、拒绝未知字段。
6. 事件记录校验：`lifecycle` 状态枚举；`heartbeat` 可选 Step；`artifact` 必须有类型/标签/安全相对路径，并校验 Epoch/Step。
7. 每个完整行按原始字节数推进偏移；坏行记录行号后跳过，继续处理后续行。
8. 返回新游标。文件末尾若仍有半行，本次不消费，并产生“等待补齐”提示；该提示在补齐后由索引器删除。

## 配置与依赖

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `MAX_REPORTED_ISSUES_PER_READ` | 50 | 单次读取最多保留的错误详情；超过后只追加“还有 N 条”摘要，**不跳过后续合法行** |

依赖：Python 标准库 `json`、`pathlib`、`datetime`；项目内 `security.path_guard` 用于产物路径白名单。没有第三方运行时依赖。

## 和旧实现相比改变了什么

初始实现，无旧版本。2026-10-31 首轮验证修正了“首次读取误报文件被截断”的问题：现在只在已有游标的情况下记录截断警告；补齐半行后会删除过期的“等待补齐”提示。参见[变更记录 0002](../changes/0002-first-verification-fixes.md)。

## 如何验证

- `tests/test_standard_reader.py::test_only_complete_lines_are_consumed_and_partial_line_is_completed`
- `test_invalid_lines_are_reported_with_line_numbers_and_skipped`
- `test_invalid_metric_values_and_missing_axis_are_rejected`
- `test_artifact_event_path_traversal_is_rejected`
- `test_truncated_file_resets_cursor`
- 真实文件验证：启动 `training-viewer open examples`，确认两个示例运行都导入且无首次截断误报。

## 已知限制与回退

- 只支持 UTF-8 JSONL；GBK 等编码会作为坏行报告。
- 同一个 JSONL 被多个进程并发追加不在保证范围内；推荐仅 rank 0 写入。
- 事件记录必须是单行 JSON；不支持跨行格式化 JSON。
- 回退：删除索引数据库并重启即可重建；读取器不修改原始文件，因此没有数据损失风险。

## 名称解释

- JSONL：JSON Lines，每行一个独立 JSON 对象。
- `source_offset`：该行在文件中的起始字节偏移，用于幂等导入。
- `reset`：检测到文件身份变化或截断，需要重建该文件索引。
