# Training Viewer — 本地训练实验查看器设计规范（文档 V1.1）

**状态：设计提案（文档版本 1.1），非已发布的软件。** 当前日志数据协议仍为 **1.0**，没有修改字段结构或兼容性约定。适用范围：单机本地运行、多项目目录、训练过程实时可视化、历史实验管理与对比、图像/结果/模型产物浏览；远程主机接入暂不纳入软件第一版。

**阅读顺序**：先读“第 0 章：命名和文档强制规范”，再读第 1 章目标、第 3 章日志协议、第 4 章系统结构、第 5 章页面功能。文内的英文缩写、技术名称都可以在 `docs/documentation_and_naming_standard.md` 第 6 节“统一术语表”找到解释。

**本项目必须执行的文档与命名规范**：[`docs/documentation_and_naming_standard.md`](docs/documentation_and_naming_standard.md)。任何参与开发的工程师或 AI 编程代理都应遵守；新增或修改组件须使用 [`组件说明模板`](docs/templates/component_design_template.md) 和 [`变更记录模板`](docs/templates/change_record_template.md)。

## 0. 命名、术语和设计文档的强制规范（优先阅读）

> **强制要求**：每个组件都必须有“中文功能名 + 明确的英文代码名 + 一句话职责 + 输入输出 + 与旧实现的差别”。不能再出现只有 `V2`、`P3`、`NewModule` 之类名称，迫使读者猜测各版本究竟改变了什么。

### 0.1 读懂项目的最小概念

| 术语 | 通俗解释 | 在查看器中的例子 |
|---|---|---|
| 项目（Project） | 一批研究任务所属的项目 | 灾害识别研究 |
| 实验组（Experiment） | 为验证同一问题安排的一组对照 | 编码器结构消融 |
| 单次运行（Run） | 一次具体训练或评估过程 | SegFormer 基线、随机种子 42 |
| 执行会话（Session） | 训练程序一次启动到退出；中断后恢复属于新的会话 | 恢复训练后的第二次启动 |
| 指标（Metric） | 连续记录的数值结果 | 训练损失、验证 mIoU、学习率 |
| 实验产物（Artifact） | 非数值时序的结果文件 | 预测图像、真实标签、模型检查点 |
| 日志适配器（Source Adapter） | 将某种日志格式转换为统一数据结构的模块 | TensorBoard 事件文件读取器 |
| 指标索引器（Metric Indexer） | 把新增日志变成能快速查询的记录 | 将 JSONL 新行存入 SQLite 索引 |

本文会在第一次出现时使用上述中文名称；必要的英文名称主要用作代码和接口标识，不作为向使用者解释功能的替代品。

### 0.2 命名规则：名字必须表达实际作用

| 场景 | 不允许 | 推荐名称 |
|---|---|---|
| Python 文件 | `parser_v2.py`、`m1.py` | `tensorboard_event_reader.py` |
| Python 类 | `IndexerV3`、`NewAdapter` | `TrainingMetricIndexer` |
| React 组件 | `View2.tsx` | `ExperimentComparisonPage.tsx` |
| 用户界面 | “SRC / IDX / ART” | “日志来源 / 指标索引 / 实验产物” |
| 实验记录 | `USE_V3`、`exp04` | `USE 波长编码与 SegFormer 对接｜随机种子 42` |
| 架构变更 | “换为新版编码器” | “用波长条件化输入编码器替换固定输入投影层” |

**说明**：上述 USE 名称只是**命名方式的示例**，不代表对某次真实实验架构的认定。实验名称用于阅读，模型差异必须以代码版本、配置、实际数据流和实验记录为准。

### 0.3 每次组件修改必须留下能回答六个问题的记录

依次说明：**原来是什么；改了什么；为什么改；影响哪些模块/数据；如何验证；如何回退**。不能只写“优化网络”或“升级 V2”。详细模板见 [`变更记录模板`](docs/templates/change_record_template.md)。

组件说明至少包含：中文名、代码名、职责、位置、输入、输出、处理流程、依赖、配置、失败行为、测试、与旧实现的区别。**如果是视觉模型组件，还必须说明张量形状、参数是否冻结、是否加载预训练权重以及下游如何使用输出。**

### 0.4 协议字段与命名规范之间的关系

`run.json`、`metrics.jsonl`、`events.jsonl` 及 `run_id`、`global_step`、`session_id` 等是对训练程序公开的**稳定机器接口**，为了兼容必须保留英文键名。它们的中文释义必须写在字段文档和界面中。新代码不应创造 `rid`、`gs` 等私人缩写。**文档变为 V1.1 不代表日志协议变为 V1.1：本次协议仍是 1.0。**

### 0.5 文档和代码必须同步交付

任何功能、组件、字段或架构调整，都要同时更新：**组件说明、架构图与数据流、术语表、变更记录、测试、使用说明**。未完成这些内容的改动应标记为“文档未完成”，不能宣布已交付。完整的评审清单见强制规范文档第 7 节。

## 1. 定位和不可妥协的边界

Training Viewer 是**本地日志消费者**，不是训练调度器。训练代码无需连接 HTTP 服务，只需按照协议输出文件。查看器对原始实验目录只读；生成的索引、界面标签、布局和备注保存在本地应用数据目录，故不会污染实验数据。训练程序可以不安装任何 SDK；提供可选的轻量 Python Writer 以减少重复代码。

- 一次训练运行记录（Run）是一次独立训练/评估执行，不等于某个模型名字；一次恢复训练属于同一个 Run，但增加新的 `session_id`。
- 分层为 `Project -> Experiment（逻辑组） -> Run`；通过 `run.json` 字段关联，目录路径可以移动。
- 结果支持任意任务；语义分割只是图像预览插件的一个使用场景。
- 原始文件是事实来源，SQLite 是可重建索引，不可反过来要求训练程序写入 SQLite。

## 2. 与现有开源方案的关系

| 项目 | 可复用能力 | V1 建议 |
|---|---|---|
| MLflow (`https://github.com/mlflow/mlflow`, Apache-2.0) | Run/Metric/Artifact 组织、实验比较、可运行基准 | 先进行基准验证；不直接 fork 整个 Web UI |
| Aim (`https://github.com/aimhubio/aim`, Apache-2.0) | 探索式曲线比较、曲线分组、标签/筛选交互 | 学习交互方式；避免依赖其内部存储 |
| TensorBoard (`https://github.com/tensorflow/tensorboard`, Apache-2.0) | event file 的官方读取生态和标量/图像类型 | 用现有 event accumulator 实现兼容 Adapter |
| DVCLive (`https://github.com/treeverse/dvclive`, Apache-2.0) | 本地文件记录的指标和 Artifact 组织方式 | 参考协议设计，后续增加 DVCLive Adapter |
| ECharts (`https://github.com/apache/echarts`, Apache-2.0) | 通用交互图表、SVG/Canvas、热力图 | V1 首选图表引擎 |
| uPlot (`https://github.com/leeoniya/uPlot`, MIT) | 高密度时序曲线 | 指标超量时按基准测试按需接入 |
| ClearML Server (`https://github.com/clearml/clearml-server`, SSPL) | 实验管理交互 | 只研究产品思想，暂不复制服务端代码 |

**许可证约束**：依赖或复制开源代码均需核对目标版本的 `LICENSE`/`NOTICE`、文件级版权头和传递依赖。特别注意 Apache-2.0 的通知义务。不要把“GitHub 公开可读”理解为无条件复制许可。

**备选路线**：可先使用 MLflow 本地服务 + 标准日志导入脚本快速验证交互。如果导入/自定义图像视图的适配成本过高，使用独立 FastAPI + SQLite + React 应用更稳妥。最终推荐后一方案。

## 3. 协议文件结构：Training Viewer Log Protocol（TVLP）1.0

```
experiments/
  project-A/
    7c9f6ad4-.../
      run.json              # 必需：静态元数据；在训练开始前创建
      metrics.jsonl         # 可选：标量时序指标，实时追加
      events.jsonl          # 可选：训练生命周期、心跳、产物引用，实时追加
      artifacts/            # 可选：图像、CSV、HTML、模型文件等原始产物
        predictions/
        labels/
      logs/                 # 可选：保留原始控制台日志
```

查看器从用户添加的任意根目录递归查找 `run.json` 来发现 Run；不能强制要求特定的 `project/run` 物理目录层级。`run_id` 全局唯一，建议 UUID。对于不同根目录中相同 `run_id` 的冲突，UI 应报警要求处理，不能静默覆盖。

### 3.1 run.json：静态元数据（必需）

`run.json` 创建后应保持核心标识和数据集信息不变；训练运行状态使用 `events.jsonl`，避免对 `run.json` 反复覆盖。

完整例子见 `examples/segformer_baseline/run.json`。主要字段：

| 字段 | 必需 | 语义 |
|---|---|---|
| `schema_version` | 是 | 固定为 `"1.0"` |
| `run_id` | 是 | 唯一且持久的运行 ID |
| `project` | 是 | 项目名称或标识 |
| `name` | 是 | 可读的运行名称，例如 `SegFormer 基线｜10 波段输入｜随机种子 42`；不能只有 `V2`、`V3` |
| `created_at` | 是 | 带时区的 RFC 3339 时间；优先 UTC `Z` |
| `experiment` | 否 | 消融组、超参数组等逻辑分组 |
| `task` | 否 | `semantic-segmentation`、`classification` 等任意任务名称 |
| `model` | 否 | 名称、架构、版本等模型元数据 |
| `dataset` | 否 | 数据集名称、版本、划分定义/指纹 |
| `config` | 否 | 任意 JSON 对象形式的超参数 |
| `source` | 否 | Git commit、dirty 状态、随机种子、框架信息等 |
| `tags` | 否 | 作者在文件中声明的原始标签 |
| `metric_definitions` | 否 | 指标方向、单位、定义、聚合方式和对比键 |
| `extensions` | 否 | 第三方扩展信息，建议使用命名空间键 |

**指标定义键采用 `phase/metric_name`**（如 `val/miou`），并可包含 `direction=min|max|none`、`unit=ratio|percent|ms|none`、`aggregation`、`definition`、`comparison_key` 等字段。`unit` 是精确数据单位，不是仅供 UI 使用的显示格式。`val/miou` 的聚合策略、忽略类别和数据划分不同，不得自动比较。未知定义的指标仍可绘制，但对齐或自动评优时应提供警示。

### 3.2 metrics.jsonl：标量时序指标（可选）

一行一个完整的 JSON 对象，连续追加，不得就地编辑已经写入的有效行：

```jsonl
{"timestamp":"2026-10-31T08:01:00Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"train","metrics":{"loss":0.78,"lr":0.0001}}
{"timestamp":"2026-10-31T08:01:30Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"val","metrics":{"loss":0.81,"miou":0.43,"f1":0.51}}
```

**必需字段**：`timestamp`、`phase`、`metrics`；同时必须至少存在一个 `global_step` 或 `epoch`。`metrics` 是非空数值字典；不得写入 `NaN`、`Infinity`、`null`、布尔值或数组作为指标值。缺失的指标直接不写，不能用 0 伪造。

**可选字段**：`event_id`（推荐唯一）、`session_id`（推荐每次进程启动唯一）、`global_step`、`epoch`、`epoch_progress`、`wall_time_sec`、`context`、`extensions`。服务端必须允许不同阶段使用同一个 Step，例如 Step=100 的训练 Loss 和验证 mIoU。

**计数约定**：`global_step` 为模型优化器更新的累计次数，开始前为 0，跨恢复训练保持不回退；`epoch` 从 1 开始表示当前训练轮次。`epoch_progress` 为可选的 `[0,1]` 轮次进度。纯评估任务可仅填写 `epoch`，还可按时间戳查看。`timestamp` 必须包含时区，建议存 UTC。

**断点续训**：同一个 `run_id`，新的 `session_id`；若训练代码重置 step，必须保留原始记录并在 UI 标识为分段曲线，而不是错误地按同一 Step 合并。Writer 应优先通过读取检查点或运行元数据恢复全局 Step。

**重复/多进程**：推荐仅 rank 0 写入记录；同一路径默认单写者。记录允许可选 `event_id`，缺少时按 `文件身份 + 行偏移 + 行内 metric_key` 实现幂等导入。多个进程直接并发追加同一 JSONL 文件不属于 V1 的保证范围。

### 3.3 events.jsonl：状态、心跳和产物引用（可选）

支持以下 `type`：

- `lifecycle`：`started`、`resumed`、`completed`、`failed`、`cancelled`。
- `heartbeat`：训练仍在工作的显式证据，建议每 15–60 秒记录一次；只是建议，不是正确性依赖。
- `artifact`：图像、表格、HTML、模型、其他文件的引用，关联 Epoch/Step、Phase 和样本。

```jsonl
{"type":"lifecycle","timestamp":"2026-10-31T08:00:00Z","session_id":"session-001","status":"started"}
{"type":"artifact","timestamp":"2026-10-31T08:02:30Z","path":"artifacts/predictions/sample-001.png","artifact_type":"image","tag":"segmentation-preview","phase":"val","epoch":2,"global_step":200,"group_id":"sample-001-epoch-2","sample_id":"sample-001","role":"prediction"}
{"type":"artifact","timestamp":"2026-10-31T08:02:30Z","path":"artifacts/labels/sample-001.png","artifact_type":"image","tag":"segmentation-preview","phase":"val","epoch":2,"global_step":200,"group_id":"sample-001-epoch-2","sample_id":"sample-001","role":"ground_truth"}
```

同一个 `group_id` 可以对齐原图 `input`、标注 `ground_truth`、预测 `prediction`；`sample_id` 用于跨 Epoch 比较同一个样本。`role` 为自由字符串，标准预设这些角色，也允许插件自定义。

产物文件采用**相对 Run 根目录的路径**；不允许绝对路径、`..` 路径穿越或跟随指向监视目录外的符号链接。相对路径在前端和导出接口都通过服务端白名单安全解析。模型权重只提供文件元数据/定位，禁止自动执行任意反序列化代码。

### 3.4 实时读取一致性规则

1. 使用 `watchdog` 文件系统事件提示有更新，同时提供低频轮询补偿，不能只依赖文件事件。
2. 维护每个文件的已消费字节偏移、文件身份和元数据；只解析追加的完整行。
3. 暂时不完整的最后一行等待补齐，不能立即判定为永久损坏；其他无效行报告行号和错误并隔离。
4. 检测文件截断、替换、移动、恢复及日志轮转；重建对应文件的索引，避免重复入库。
5. `run.json` 如需修改，用临时文件 + 原子替换；不能让解析器看到半写入 JSON。
6. 没有 `completed` 事件且没有近期心跳时，状态为 `unknown/stale`，**不能仅因日志停止就推断训练失败**。
7. SQLite 只保存索引与 UI 附加信息；删除缓存后应能根据日志完整重建。

### 3.5 正式 JSON Schema

在 `schemas/` 中提供 Draft 2020-12 标准文件：

- `run.schema.json`
- `metrics.schema.json`
- `events.schema.json`

可用 `tools/validate_log.py` 对一个 Run 目录中的 JSON 和 JSONL 进行校验。协议初稿已经覆盖字段类型、必需字段、枚举和基本结构；跨字段的时间单调性、语义可比性和路径安全由解析逻辑/测试实现，而不是仅靠 JSON Schema。

## 4. 插件化系统架构

```
训练程序（任意框架）
   │   生成标准协议文件（可选 tvlog Writer）
   ▼
本机目录 / 历史日志
   │
   ├── [Source Adapter] 标准 TVLP / TensorBoard / CSV / MLflow 导入
   │
   ├── [Normalizer] 统一 Run / MetricSample / Artifact / Event 对象
   │
   ├── [Indexer] 文件游标、增量消费、SQLite WAL 索引
   │
   ├── [Query/API] FastAPI REST + SSE 实时增量消息
   │
   └── [View Plugins] 实验列表 / 曲线 / 图片 / 表格 / 统计
               │
          React + TypeScript 前端
               │
     浏览器应用  ──  VS Code 启动器/快捷入口
```

### 4.1 独立插件边界

- **日志来源适配器（Source Adapter）**：发现已有 Run 和数据源（`discover`），暴露可增量读取流（`read_since(cursor)`）。第一批 `tvlp`、`tensorboard`、`csv`；复杂的历史文本解析在 V1 后续迭代。
- **数据标准化器（Normalizer）**：将所有来源转换为统一的内存/数据库模型，统一单位、阶段、时间轴，并附带原始来源和警告信息。
- **可视化插件（View Plugin）**：标量曲线、分割预览、通用图像画廊、矩阵热图、CSV 表格、图表面板。每种插件只读取标准查询 API，不直接解析日志。
- **导出插件（Exporter Plugin）**：PNG、SVG、CSV、JSON；表格和图像导出保留溯源信息。
- **VS Code 启动插件（Extension）**：注册 `Open Training Viewer`、`Add Folder`、`Compare Selected Runs` 等命令；负责启动/连接本机服务和打开浏览器。V1 不要求在 Webview 内复制整套前端。

软件第一版内建插件采用显式注册表以保证启动和安全可控；后续提供 Python entry points 或前端插件 SDK，支持第三方安装包。**插件化不等于第一版就必须实现任意第三方代码的热加载**。

### 4.2 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| Backend | Python + FastAPI + Pydantic v2 | 与训练生态契合；校验模型和 REST 易于维护 |
| Storage | SQLite (WAL) | 本地单用户免部署，支持指标索引与查询 |
| File watch | watchdog + polling fallback | 兼容 Windows 本机目录和日志追加 |
| Frontend | React + TypeScript | 承载大规模交互界面 |
| Chart | Apache ECharts | 曲线、对比、图像外统计和导出；大量点按需降采样 |
| Gallery | React 组件 + 浏览器图像显示 | 原图/预测/标签并列、透明度叠加、样本对应 |
| Service events | Server-Sent Events (SSE) | 单向推送新增 Run、Metric、Artifact 足够；断线后重新同步游标 |
| Packaging | pipx/uv tool + 本地静态前端资源 | 一条命令安装并启动，不要求单独配置 Node 服务 |
| Editor | VS Code Extension VSIX | 一键添加目录、启动服务、浏览器打开 |

**安全默认值**：只监听 `127.0.0.1`、不自动开放公网端口、仅可读取用户显式添加的根目录、对路径进行解析和检查、HTML 产物按不可信内容隔离（默认不直接执行其脚本）、输出转义、防止目录穿越及任意文件读取。

### 4.3 SQLite 的最小表模型

- `runs`：run_id、根目录、project/experiment/name、模型/数据集/配置 JSON、当前状态、发现时间。
- `metric_points`：run_id、phase、metric_name、global_step、epoch、timestamp、session_id、value、source_offset/source_id。
- `artifacts`：run_id、tag、type、path、phase、epoch/step、sample_id/group_id/role。
- `events`：生命周期与心跳。
- `ingestion_cursors`：source_id、file_identity、size、offset、mtime、health_state。
- `annotations`、`saved_views`、`collections`：UI 用户创建的备注、布局和实验集合，与原始文件隔离。

索引建议 `(run_id, phase, metric_name, global_step)` 和 `(project, experiment)`。同一 Metric 有多个 `session_id` 时查询不能默认丢弃其来源。对百万级曲线采用视窗范围查询、分桶及 LTTB/min-max 等降采样，优先保留极值；统计 Best/Last 必须使用原始数据。

## 5. 产品界面与功能规格

### 5.1 首页（Overview）

侧边栏是项目/实验组树；主区为运行中 Run、最近实验、指标卡片和用户保存的面板。可以添加多个本机目录并自动持久化扫描配置。

### 5.2 Experiments：实验管理

支持筛选项目、模型、数据集、任务、种子、状态、标签、日期；任意字段显示/隐藏、列排序、全局搜索、批量选中；用户备注与收藏独立保存。展示训练配置、Git 来源、运行时长、最后更新时间、最佳/最终指标。对于无显式结束事件的实验显示“状态未知/可能中断”。

### 5.3 Run Detail：单实验页面

- Metrics：自动按 phase 与 metric 分类，Step/Epoch/时间轴切换；原始曲线与可选择的平滑曲线。
- Configuration：完整超参数和模型/数据集/代码来源。
- Artifacts：预测图、原图、标签、混淆矩阵、CSV/HTML、文件清单及快速预览。
- Timeline：断点恢复、心跳、产物生成、训练完成/失败事件。
- Diagnostics：日志解析错误、缺失文件、Step 回退、指标语义不足、数据源质量。

### 5.4 Compare：多实验对比

多选 Run 叠加同指标，支持以 Step、Epoch、时间为横轴；曲线平滑、隐藏/显示、局部放大、鼠标同步悬停、Best/Last 比较、超参数差异表、收藏对比面板。不同训练长度必须显式处理，不默认插值或截断。比较聚合（多个种子均值/误差带）需用户主动选择。

**评优逻辑**：对于方向为 `min`/`max` 的指标，Best 使用原始（非平滑）采样；Last 为该 Run 最新有效时间序列记录；没有 `direction` 的指标不能擅自定义胜负。数据集版本、拆分、类集、ignore_index、度量定义不同或缺失时，给出明确可比性警告，而不是静默排名。

### 5.5 Results：结果与图像查看

基于 `artifact` 事件自动分组：按样本、Epoch、模型 Run 浏览；并列显示 Input / Ground Truth / Prediction，支持同尺寸图像透明叠加，按样本切换不同 Epoch 的结果。通用表格、图片、矩阵、HTML 必须有安全的预览或明确的下载入口。

### 5.6 可视化配置和导出

图例、坐标范围、对数轴、平滑窗口、单位换算（仅已声明兼容单位）、导出 PNG/SVG，表格导出 CSV/JSON。导出记录比较轴、过滤条件、是否经过平滑/降采样以及数据集信息，便于论文复现。

## 6. 公共 API（建议草案）

```
GET  /api/v1/projects
GET  /api/v1/runs?project=&experiment=&status=&q=
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/metrics?phase=val&key=miou&axis=global_step
GET  /api/v1/runs/{run_id}/artifacts
GET  /api/v1/artifacts/{artifact_id}/content
POST /api/v1/roots               # 添加允许扫描的本地目录
GET  /api/v1/roots
POST /api/v1/compare/query       # 多 Run 对齐查询
GET  /api/v1/stream              # SSE：更新通知与版本号
GET  /api/v1/diagnostics
```

服务端发出更新通知后，前端通过增量版本号/查询游标拉取必要变化，不需要在 SSE 中广播全部历史指标。API 响应应包含 `source_kind`、精度/单位元数据、`warnings` 等字段；用户可以追踪数据来自哪个日志文件和哪条事件。

## 7. 入口与使用方式

```bash
# 以下是计划实现的 CLI 交互，不代表当前已经可以安装。
training-viewer open D:/experiments
training-viewer open D:/projectA/runs D:/projectB/results
training-viewer validate D:/experiments/projectA/run123
```

启动服务默认在空闲本机端口（首选 8765）监听，打开浏览器。重复打开时探测同一用户实例并复用。VS Code 插件提供命令并调用同一个本地后端，退出 VS Code 不应直接破坏后台正在运行的训练任务。

训练程序兼容策略：

1. **零依赖**：按本规范直接写 `run.json`、`metrics.jsonl`、`events.jsonl`。
2. **轻量 Writer**：可选 `training-viewer-log` 包，负责创建 Run、原子写元数据、记录 metrics/artifact、缓冲与刷新、状态事件。
3. **历史数据适配**：读取 TensorBoard event 文件、CSV、普通 JSONL，按显式字段映射将既有实验导入 Viewer 索引，不修改原始文件。对自由文本日志的自动猜测作为可扩展能力，不承诺可靠解析所有格式。

## 8. 实施阶段（都属于完整 V1 目标）

| 阶段 | 交付内容 | 验收条件 |
|---|---|---|
| 1. 协议与基座 | JSON Schema、示例 Run、校验器、目录扫描、SQLite 游标 | 已有和实时追加的标准 Run 都能稳定导入；重启不重复入库 |
| 2. 实验 UI | 首页、Run 列表、搜索/筛选、详情和状态 | 多项目管理可用；查看配置和来源；不误判运行状态 |
| 3. 曲线和比较 | 多指标、实时刷新、多 Run 叠加、Best/Last、导出 | 断点续训和不同日志频率对齐正确，原始数据不丢失 |
| 4. 结果浏览 | Artifact 解析、图像/标签/预测并排、图像叠加、表格/矩阵 | 关联样本和 Epoch 准确；非法路径被拦截 |
| 5. 插件和发布 | TensorBoard/CSV Adapter、VS Code 启动器、CLI 打包 | 本机安装即用；可添加新来源/视图，不改核心数据层 |
| 6. 稳定性 | 大文件追尾、截断轮转、坏行、SQLite 重建、性能/安全测试 | 模拟训练中断/恢复/文件替换后无重复、无静默丢数据 |

## 9. 必须覆盖的测试场景

- 只有 train loss，没有 val/精度；不能凭空显示未记录的精度。
- 不同 Run 的指标名称相同、单位或计算定义不同，显示不可比提醒。
- 验证指标每个 epoch 一次，而训练指标每个 step 一次；前端正确绘制稀疏序列。
- train 和 val 共享相同 Step，不视为重复点。
- JSONL 最后一行只写了一半，训练随后完成该行；不得提前丢弃。
- 多次重启查看器，读取游标保持一致，不产生重复采样。
- 文件被截断/覆盖/轮转、目录移动，及时刷新并显示风险。
- 单个 Run 经多次恢复训练：`session_id` 改变，但完整时间序列保留。
- DDP 多进程日志：示例 Writer 仅主进程写入；对并发写同一文件显示不支持说明。
- 图片路径穿越和未授权根目录访问被拒绝；HTML 未受信任脚本不执行。
- 拥有大量点的 Run 能通过范围查询与降采样流畅绘制，Best/Last 仍基于全量真实数据。

## 10. 不纳入 V1 的功能

远程服务器读取、模型训练调度、GPU 动态采样 Agent、分布式多用户权限、实时预测、在线修改训练参数、云端协作、公共插件市场。这些功能可以在以后以独立插件添加，不应成为本地浏览器版本的前置条件。

## 11. 下一步实施建议

先以真实的 SegFormer/USE 训练样例输出 TVLP，验证 Step/Epoch/Phase 和预测图分组，再基于同一批数据分别运行 MLflow 原型和独立读取器，比较引入现有 UI 的改造成本。随后冻结 TVLP 1.0 的字段语义，实施增量索引及主界面。**必须优先保证数据正确性，而不是先堆叠炫目的图表。**


## 12. 为开发代理准备的执行规则和文档交付物

软件实施过程中应创建以下目录，并始终保持命名与文档一致。下面的文件路径是**建议的未来仓库结构**，不是声称当前已存在的代码。

```text
README.md                                 # 中文快速使用说明
docs/
  documentation_and_naming_standard.md   # 强制命名和文档规范
  glossary.md                             # 单独的术语索引（可由规范表导出）
  architecture.md                         # 功能模块、进程边界和真实数据流
  components/                             # 每个重要组件的职责与输入输出
  changes/                                # 每一次架构/行为变化的记录
  templates/
    component_design_template.md          # 组件说明模板
    change_record_template.md             # 变更记录模板
```

实施时把“组件身份卡”作为工程任务的一部分，而不是写完代码后才补充。举例：

| 中文名 | 代码名 | 输入 → 输出 | 一句话职责 |
|---|---|---|---|
| 标准训练日志增量读取器 | `StandardTrainingLogReader` | JSONL 文件 → 规范化指标记录 | 只读取文件新增的完整行，不解析界面数据 |
| 训练指标索引器 | `TrainingMetricIndexer` | 规范化指标记录 → SQLite 索引 | 为曲线与实验比较建立可重建的数据索引 |
| 实验对比页面 | `ExperimentComparisonPage` | 多运行查询结果 → 图表和统计表 | 帮助用户比较同一定义指标的不同运行 |
| 预测结果对照器 | `PredictionComparisonViewer` | 原图/标签/预测产物 → 对照界面 | 关联同一个样本与训练轮次的图像 |

**发布前必须人工检查**：随机选择一个新组件，让未参与开发的人仅查看“中文名称、职责、输入输出、修改记录”，验证其能准确说明这个组件做什么、与之前有什么不同。工具可以自动检查字段和命名形式，但无法代替这项语义可读性检查。

## 13. 本次设计文档修订记录

| 文档版本 | 变更摘要 | 日志协议版本 |
|---|---|---|
| 1.0 | 本地服务、日志数据文件、插件架构、实验界面、验收范围初稿 | 1.0 |
| **1.1** | 增加命名和术语强制规范、组件身份卡、版本语义、变更管理、评审门槛及模板；统一部分架构层的中文解释 | **1.0（不变）** |
