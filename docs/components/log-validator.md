# 组件说明：协议校验器（log_validation）

## 一句话说明

按 TVLP 1.0 的 JSON Schema 校验一个 Run 目录，并额外检查产物路径安全与文件存在性；只读，不写索引，也不修改训练目录。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 协议校验器 |
| 代码函数 | `validate_run_directory` |
| 源文件 | `src/training_viewer/log_validation.py` |
| 所属模块 | 校验 / CLI |
| 上游 | `training-viewer validate`；下游 | 终端输出、JSON 报告 |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

训练程序输出日志后，需要一个不依赖服务、不需要启动 Web UI 的检查工具。它与 `tools/validate_log.py` 使用相同的 Schema，并复用路径规则，保证协议校验结论一致。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | `run_directory` | `Path` | 包含 run.json 的目录 |
| 输入 | `schema_directory` | `Path` | 安装包内 `schemas/` |
| 输出 | `ValidationReport` | 数据类 | 检查记录数、消息列表 |
| 输出 | 消息 | `ValidationMessage` | 级别（error/warning/info）、文件、行号、中文说明 |

## 主要处理流程

1. 检查目录存在。
2. 加载 `run.schema.json`、`metrics.schema.json`、`events.schema.json`（Draft 2020-12 + 格式检查）。
3. `run.json`：必需，整文件校验。
4. `metrics.jsonl` / `events.jsonl`：只校验以换行结尾的完整行；末尾半行给出 info，不判为错误。
5. 拒绝 `NaN`/`Infinity`；指标值再次检查有限性。
6. 产物事件：路径必须是安全相对路径；解析后不得越出 Run 目录；文件不存在给 warning。
7. 汇总错误与警告；有错误时 CLI 退出码为 1。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 可选文件缺失 | info | `metrics.jsonl`/`events.jsonl` 可以不存在 |
| `run.json` 缺失 | error | 协议必需 |
| `--json` | false | 输出机器可读报告 |

依赖：`jsonschema`（Draft 2020-12）。Schema 是发布包的一部分；测试检查安装包副本与仓库 `schemas/` 字节一致。

## 和旧实现相比改变了什么

初始实现。校验器与原有 `tools/validate_log.py` 保持同一 Schema 与路径规则；新增安装包内 Schema 副本，并加入一致性测试防止漂移。

## 如何验证

- `tests/test_validation.py`：示例通过、坏字段、半行、缺失产物、路径穿越。
- `tests/test_validation.py::test_packaged_schemas_match_repository_schemas`。
- `tests/test_cli.py`：退出码与 JSON 输出。
- 手工：`training-viewer validate examples/segformer_baseline`。

## 已知限制与回退

- JSON Schema 无法表达时间单调性、指标语义可比性等跨字段规则；这些由解析/查询逻辑处理。
- 只校验协议字段，不验证训练代码或模型质量。
- 回退：命令只读，无数据变更。

## 名称解释

- TVLP：Training Viewer Log Protocol，训练日志协议。
- JSON Schema：描述 JSON 结构约束的标准。
- 半行：文件末尾尚未写完的 JSON 行。
