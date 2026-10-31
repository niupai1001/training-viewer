# 组件说明：训练日志写入器（TrainingRunWriter）

## 一句话说明

训练程序侧的轻量日志写入辅助：创建 Run 目录、原子写 `run.json`、追加 `metrics.jsonl` / `events.jsonl`、生成会话、心跳和最终状态；不启动查看器、不连接 HTTP、不修改已有日志。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 训练日志写入器 |
| 代码类名 | `TrainingRunWriter` |
| 源文件 | `src/training_viewer/writer.py` |
| 所属模块 | 训练侧接入（可选） |
| 上游 | 训练/评估脚本；下游 | TVLP 日志文件（由查看器读取） |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

训练 Agent 或研究者直接手写 JSONL 容易遗漏 UTC 时区、Step/Epoch 约束、半行写入、状态事件和产物分组。写入器把这些规则封装成少量方法，并保证：

- `run.json` 用临时文件 + 原子替换，不产生半写入 JSON；
- 每个指标/事件立即 flush，查看器能实时读取；
- 会话 ID 自动生成，断点续训可复用同一个 `run_id`；
- 上下文管理器自动写 `started` / `completed`，异常时写 `failed`；
- 产物路径被限制在 Run 目录内。

它不负责：训练框架适配、自动发现指标、自动判断验证指标、上传文件、启动查看器。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | `log_root` / `run_directory` | 路径 | 二选一；默认 `<log_root>/<run_id>` |
| 输入 | `project`、`name` | 字符串 | 必填的人类可读身份 |
| 输入 | `run_id` | UUID 字符串 | 可选；断点续训必须复用 |
| 输入 | `metric_definitions` | 字典 | 键为 `phase/metric_name`，含 `direction`/`unit`/`definition` |
| 输入 | `config`、`model`、`dataset`、`source`、`tags` | JSON 兼容值 | 写入 `run.json` |
| 输入 | `session_id` | 字符串 | 可选；默认每次启动自动生成 |
| 输入 | `heartbeat_interval_seconds` | 浮点或 `None` | 默认 30 秒；`0` 关闭 |
| 输入 | `resume` | 布尔 | `True` 时复用已存在的 Run 并写 `resumed` |
| 输出 | `run.json` | JSON | 原子写入的元数据 |
| 输出 | `metrics.jsonl` | JSONL | 每行一条指标记录 |
| 输出 | `events.jsonl` | JSONL | lifecycle、heartbeat、artifact |
| 输出 | `artifact_path()` | `Path` | Run 目录内产物路径，自动创建父目录 |

## 主要方法

| 方法 | 作用 |
|---|---|
| `start()` | 创建/恢复目录、写元数据、打开日志、写 started/resumed、启动心跳 |
| `log_metrics(phase, metrics, global_step=?, epoch=?, ...)` | 追加一条指标记录；Step/Epoch 至少一个 |
| `log_heartbeat(global_step=?)` | 追加心跳；不表示训练完成 |
| `log_lifecycle(status, message=?)` | `started`/`resumed`/`completed`/`failed`/`cancelled` |
| `artifact_path(relative)` | 返回 Run 目录内绝对路径并创建父目录 |
| `log_artifact(path, artifact_type, tag, ...)` | 记录图像/表格/HTML/模型等产物引用 |
| `finish(status="completed", message=?)` | 停止心跳、写结束事件、关闭文件 |
| `with TrainingRunWriter(...) as run` | 自动 start 与 finish；异常自动 failed |

## 主要处理流程

1. 校验 `project`/`name`、运行目录参数与已有元数据（`resume`）。
2. 新运行：`run.json` 写临时文件后 `os.replace`；恢复运行：保持原 `run_id` 与元数据不变。
3. 以追加模式打开两个 JSONL 文件；写入 `started` 或 `resumed`。
4. 可选心跳线程每 30 秒写一条 heartbeat，带最近一次 `global_step`。
5. `log_metrics` 校验阶段、有限数字、Step/Epoch、`epoch_progress`，写入带 UTC 时间、`event_id`、`session_id` 的记录并 flush。
6. `log_artifact` 校验相对路径和类型，写入带 `group_id`/`sample_id`/`role` 的事件。
7. `finish` 停止心跳、写结束事件、关闭文件；重复调用安全。
8. 训练代码抛异常时，上下文管理器写 `failed` 后重新抛出。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `heartbeat_interval_seconds` | `30` | `0` 或 `None` 关闭 |
| `session_id` | 自动生成 | 每次进程启动唯一 |
| `resume` | `False` | 已存在目录必须显式设 `True` |
| 运行目录 | `<log_root>/<run_id>` | 也可显式 `run_directory` |

依赖：Python 标准库（`json`、`math`、`os`、`threading`、`uuid`、`datetime`、`pathlib`）。**不依赖 FastAPI 或查看器进程**，可单文件复制到训练仓库。

## 和旧实现相比改变了什么

初始实现。第一版此前只提供协议与读取器，训练 Agent 需要手写 JSONL；本组件把协议约束和原子写入封装起来，并配合 `attach` 完成 Agent 自动接入。读取器、协议字段与数据库结构未改变。

## 如何验证

- `tests/test_writer.py`：完整 Run、原子元数据、产物、恢复会话、异常失败、非法输入、拒绝无 resume 覆盖。
- 手工：运行 `AGENT_INTEGRATION.md` 的示例训练片段，执行 `training-viewer validate <run目录>`，再 `training-viewer attach <log_root> --json`，确认运行状态为 completed 且曲线有点。
- 写入器生成的 `run.json` 应被 `schemas/run.schema.json` 接受。

## 已知限制与回退

- 同一 Run 目录不支持多个训练进程同时写入；推荐仅 rank 0 写入。
- 不自动判断哪个指标是“最佳指标”；`metric_definitions` 必须由训练 Agent 按真实定义填写。
- 心跳是活动证据，不代表训练质量；`finish` 必须执行，否则查看器会显示状态未知。
- 若训练环境不能安装本包，可复制 `writer.py`（仅标准库）。
- 回退：不调用写入器、直接按协议写文件；已生成日志不会被修改。

## 名称解释

- Writer：写入器。
- `run_id`：运行唯一标识，断点续训复用它。
- `session_id`：一次训练进程启动到退出的会话。
- flush：把缓冲区内容立即写入文件，供读取器看到。
- 原子替换：先写临时文件再替换目标，避免解析器读到半写入 JSON。
