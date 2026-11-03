# 组件说明：运行元数据读取器（RunMetadataReader）

## 一句话说明

读取并校验目录中的 `run.json`，输出统一为 UTC 的元数据字典；不创建、不修复、不写回元数据，也不负责扫描目录。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 运行元数据读取器 |
| 代码类名 | `RunMetadataReader` |
| 源文件 | `src/training_viewer/run_metadata.py` |
| 所属模块 | 日志协议 |
| 上游 | `StandardTvlpSourceAdapter`；下游 | `TrainingMetricIndexer`（通过 `DiscoveredRun.metadata`） |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

`run.json` 是运行身份、项目/实验组、配置和指标定义的权威来源。如果解析失败后继续猜测，会污染运行列表与对比结果。本组件把结构错误转成明确的中文异常，目录扫描器会把异常记录为诊断问题，并且不再向下扫描该目录的产物。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 | 错误时 |
|---|---|---|---|---|
| 输入 | `run_directory` | `Path` | 包含 `run.json` 的 Run 目录 | 文件不存在/是符号链接 → `InvalidRunDirectoryError` |
| 输出 | 元数据字典 | `dict` | 原始字段 + 规范化 `created_at`（UTC 固定宽度字符串） | — |
| 输出异常 | `InvalidRunDirectoryError` | 异常 | 中文原因，例如缺少 `run_id`、未知字段、方向非法 | 扫描器记录目录级问题 |

## 主要处理流程

1. 确认 `run.json` 是普通文件，不是符号链接。
2. 以 UTF-8 读取 JSON，拒绝 `NaN`/`Infinity`。
3. 拒绝未知顶层字段；第三方数据必须放在 `extensions`。
4. 校验必需字段：`schema_version="1.0" 或 "1.1"`、`run_id`、`project`、`name`、带时区的 `created_at`。
5. 校验可选结构：`model`/`dataset` 为对象、`tags` 为无重复字符串数组、`config`/`source`/`extensions` 为对象。
6. 逐项校验 `metric_definitions`：键为 `phase/metric_name`，`direction` 必须是 `min`/`max`/`none`，其它允许字段为字符串，未知字段拒绝。
7. 把 `created_at` 规范化为 UTC；其它字段保持原值，供界面和对比使用。

## 配置与依赖

无配置项。依赖 Python 标准库与 `jsonschema` 仅用于独立校验器；本组件使用手写中文校验，比 Schema 更严格（额外的时区要求）。

## 和旧实现相比改变了什么

初始实现。首轮验证发现：手写校验抛出的 `ValueError` 未被扫描器转换为目录诊断，导致一个坏 `run.json` 让整次同步失败；现在 `read()` 统一包装为 `InvalidRunDirectoryError`。参见[变更记录 0002](../changes/0002-first-verification-fixes.md)。

## 如何验证

- `tests/test_indexing.py::test_invalid_run_json_becomes_directory_diagnostic`
- `tests/test_indexing.py::test_run_metadata_reader_rejects_unknown_fields`
- `tests/test_validation.py::test_broken_run_json_reports_schema_error`
- 手工：`training-viewer validate examples/segformer_baseline` 应通过。

## 已知限制与回退

- 只接受协议 1.0；未来协议升级需要显式迁移策略。
- 非 UTF-8 文件无法读取，会产生诊断。
- 回退：删除索引后重新扫描；原始 `run.json` 不会被修改。

## 名称解释

- `metric_definitions`：指标定义表，键为 `phase/metric_name`，`direction` 决定最佳值方向。
- `schema_version`：日志协议版本，支持 `1.0`（历史）和 `1.1`（四要素）。
