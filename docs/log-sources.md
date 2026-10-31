# 日志来源与协议说明

查看器支持三种本机日志来源。识别优先级固定为：**标准训练日志（TVLP 1.0） > TensorBoard 事件文件 > CSV 指标表**。目录中只要存在有效的 `run.json`，就按标准协议解释，不会把其中的 CSV 或事件文件当成第二个运行。

## 1. 标准训练日志（TVLP 1.0）

### 1.1 目录结构

```text
experiments/
  project-A/
    <run_id>/
      run.json              # 必需；训练开始前创建
      metrics.jsonl         # 可选；标量指标，实时追加
      events.jsonl          # 可选；生命周期、心跳、产物引用
      metrics.csv           # 可选；没有 metrics.jsonl 时读取
      artifacts/            # 可选；图像、表格、HTML、模型
      logs/                 # 可选；原始控制台日志（本版本不解析）
```

查看器从用户添加的根目录递归查找 `run.json`，不要求固定物理层级。`run_id` 全局唯一。

### 1.2 run.json

必需字段：`schema_version`（固定 `"1.0"`）、`run_id`、`project`、`name`、`created_at`（带时区）。可选字段：`experiment`、`task`、`model`、`dataset`、`config`、`source`、`tags`、`metric_definitions`、`extensions`。

- 读取器拒绝未知顶层字段；第三方信息应放在 `extensions`。
- `created_at` 会统一转换为 UTC。
- `metric_definitions` 的键为 `phase/metric_name`，至少包含 `direction`（`min` / `max` / `none`）；`unit`、`aggregation`、`definition`、`comparison_key` 用于界面提示与可比性判断。
- 训练运行状态来自 `events.jsonl`，不要求反复改写 `run.json`。查看器读取时支持临时文件 + 原子替换。

字段级约束以 [`schemas/run.schema.json`](../schemas/run.schema.json) 为准。

### 1.3 metrics.jsonl

每行一个完整 JSON 对象，只能追加：

```json
{"timestamp":"2026-10-31T08:01:00Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"train","metrics":{"loss":0.78,"lr":0.0001}}
{"timestamp":"2026-10-31T08:01:30Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"val","metrics":{"loss":0.81,"miou":0.43,"f1":0.51}}
```

必需：`timestamp`、`phase`、`metrics`，且至少一个 `global_step` 或 `epoch`。指标值必须是有限数字，不能是布尔、数组、`null`、`NaN` 或 `Infinity`；缺失指标直接不写，不能用 0 代替。

同一步骤的 train 与 val 是不同阶段的两条记录，不会被当成重复点。

### 1.4 events.jsonl

支持：

- `lifecycle`：`started`、`resumed`、`completed`、`failed`、`cancelled`。
- `heartbeat`：训练仍在工作的显式证据，建议每 15–60 秒一次。
- `artifact`：图像、表格、HTML、模型等产物引用，可带 `group_id`、`sample_id`、`role`、`epoch`、`global_step`。

```json
{"type":"lifecycle","timestamp":"2026-10-31T08:00:00Z","session_id":"session-001","status":"started"}
{"type":"artifact","timestamp":"2026-10-31T08:02:30Z","path":"artifacts/predictions/sample-001.png","artifact_type":"image","tag":"segmentation-preview","phase":"val","epoch":2,"global_step":200,"group_id":"sample-001-epoch-2","sample_id":"sample-001","role":"prediction"}
```

`path` 必须是相对 Run 目录的路径。绝对路径、`..`、指向目录外的符号链接会被拒绝并记录问题。

字段级约束以 [`schemas/events.schema.json`](../schemas/events.schema.json) 为准。

### 1.5 metrics.csv

当目录中存在 `run.json`、没有 `metrics.jsonl`、但有 `metrics.csv` 时读取 CSV。列映射通过 `run.json` 指定：

```json
{
  "extensions": {
    "csv_metric_mapping": {
      "step_column": "step",
      "epoch_column": "epoch",
      "timestamp_column": "timestamp",
      "phase_column": "phase",
      "session_column": "session_id",
      "metric_columns": ["loss", "accuracy", "learning_rate"]
    }
  }
}
```

行为：

- 显式映射优先；映射列不存在时报告问题并暂不导入，不猜测替代列。
- 没有显式映射时，按常见列名别名识别 Step/Epoch/时间/阶段，并把全部稳定解析为数字的列视为指标。
- `phase` 缺失时记为 `unlabeled`，界面显示“未标注阶段”。
- `timestamp` 可以缺失；缺失时按 Step/Epoch 绘制，时间轴会提示不可用。不会用文件修改时间伪造每条记录的时间。
- 既没有 Step 也没有 Epoch 时，报告问题且不导入，不以行号伪造横轴。
- CSV 按追加日志处理；就地修改已有行不会更新已索引的点。需要修正历史值时应保留变更说明并重建索引。

### 1.6 实时读取规则

1. 以字节偏移（JSONL/纯文本）或行号（CSV）维护游标，只处理新增完整行。
2. 文件末尾半行等待补齐；补齐后再导入。
3. 坏行记录文件名与行号并隔离，**后续有效行继续解析**；单次读取最多展示 50 条错误详情，但只截断详情，不跳过记录；游标只推进到实际处理的完整行。
4. 纯文本读取使用二进制追加、逐行严格 UTF-8 解码；CRLF、中文、多字节、非法字节和半行不会让游标偏离物理字节位置。非法 UTF-8 行会报告，不会静默替换。
5. 检测文件截断、替换、轮转：文件身份变化或新大小小于游标 → 删除该文件索引并重读。
6. 查看器重启后游标仍然有效，不重复入库。
7. 不修改原始文件；索引数据库可删除重建，用户状态单独保存。

## 2. TensorBoard 事件文件

- 识别条件：目录中存在 `events.out.tfevents.*`，且没有 `run.json`。
- 需要可选依赖：`pip install "training-viewer[tensorboard]"`。未安装时目录级诊断会给出安装命令，其它来源照常工作。
- 复用 TensorBoard 官方 `EventFileLoader` 与张量转换，只读取标量（`simple_value` 或单元素数值张量）。
- 标签按第一个 `/` 拆分为阶段和指标：`train/loss` → 阶段 `train`、指标 `loss`；没有斜杠时阶段记为 `unlabeled`。
- 非标量事件（图像、直方图等）跳过并提示。
- 事件文件没有 `run.json`，所以：
  - `run_id` 由目录绝对路径哈希生成（`tensorboard-<hash>`）；
  - 项目名取上一级目录名，运行名取目录名；
  - `created_at` 取事件文件修改时间；
  - 界面标记“元数据由目录推导”。
- 移动目录会改变合成的 `run_id`。需要稳定身份时，可在同目录补充标准 `run.json`（此时改由标准来源读取）。
- 游标使用事件序号。文件变化后从头读取，只写入新序号，唯一键保证不重复。超大事件文件的完整重读是已知性能限制。

## 3. 无 run.json 的 CSV 目录

- 识别条件：目录中有 `metrics.csv`，且没有 `run.json`、没有 TensorBoard 事件文件。
- 使用启发式列识别（`step` / `epoch` / `timestamp` / `phase` 等英文别名）和全部数值列。
- 合成 `run_id`（`csv-<hash>`）、项目名（上一级目录名）、运行名（目录名）；状态显示 `imported`（已导入，无生命周期事件）。
- 移动目录会改变合成身份。需要稳定身份时补充 `run.json` 并使用显式列映射。

## 3.1 任意文件名的 CSV / TSV / JSONL / 普通文本

没有 `run.json` 时，来源适配器还会对目录内直接子文件做**内容嗅探**；每个通过嗅探的文件生成一个独立 Run（同一目录可有多个文件，例如 `train.log` 与 `metrics.csv`）：

| 文件 | 识别条件 | 读取器 |
|---|---|---|
| `*.csv` / `*.tsv` | 表头有 `step`/`epoch` 别名，且有训练指标列或时间/阶段列；纯业务 CSV 拒绝 | CSV 指标读取器 |
| `*.jsonl` | 至少一条 JSON 对象含 `step`/`global_step`/`epoch` 和数值指标（扁平或 `metrics` 字典） | 通用 JSONL 读取器 |
| `*.log` / `*.txt` / `*.out` | 规则模板能解析出明确写出的 Step/Epoch 和指标键值 | 纯文本日志读取器 |

- 识别到的 Run 会标记来源 `generic-csv` / `generic-tsv` / `generic-jsonl` / `plain-text`，状态为 `imported`（没有生命周期事件）。
- 不修改原始文件；按字节偏移（JSONL/文本）或行号（CSV）增量读取，半行等待补齐。
- 普通文本只识别 `loss`、`accuracy`、`miou`、`f1`、`lr` 等明确指标键；复杂格式请输出 CSV/TSV 或标准 TVLP，避免用猜测补全。
- 识别是保守的：没有 Step/Epoch、没有数值指标、或看起来是业务表格的文件不会导入。当前**没有**“人工确认字段映射”的持久化界面；这种文件需要先转成带明确列名的 CSV/TSV。

## 4. 来源适配器与发现

- 适配器接口见 [`docs/components/source-adapters.md`](components/source-adapters.md)。
- 扫描器不跟随符号链接目录，跳过 `.git`、`node_modules`、`.venv`、`__pycache__` 等常见目录；匹配到 Run 后不再向下扫描其 `artifacts/`。
- 扫描深度默认 12 层，单根目录最多扫描 50000 个目录；达到限制会记录警告，不会静默截断。
- 两个目录出现相同 `run_id` 时，保留一个并在诊断页与运行详情报警；另一个目录不被索引。
- **增量优先**：每 2 秒轮询只重读已知 Run 目录；完整目录树发现默认每 300 秒兜底一次，watchdog 的目录创建/移动/删除事件会提前触发全量发现。手动“重新扫描”、添加/移除根目录也立即全量。

## 5. 运行状态、活动与心跳

生命周期状态和“最近是否有新数据”是两件事：

| 生命周期证据 | 状态 | 说明 |
|---|---|---|
| 最新 lifecycle 为 `completed` | 已完成 | 即使日志不再更新 |
| 最新 lifecycle 为 `failed` / `cancelled` | 失败 / 已取消 | 日志不删除 |
| 最近 120 秒内有 heartbeat | 运行中 | heartbeat 是进程仍在工作的显式证据 |
| 有近期指标、但没有近期 heartbeat | 状态未知（可能中断） | 指标更新不等于训练进程仍存在 |
| 没有完成事件且超过 120 秒无活动 | 状态未知（可能中断） | **不能判定训练失败** |
| TensorBoard / 无 run.json 的 CSV | 已导入 | 没有生命周期事件 |
| 运行目录不可访问 | 状态未知 | 保留索引，不删除 |

另有一个独立的**活动**标签：`最近仍在更新`（≤120 秒有新指标）、`已停止更新`、`已结束`（终态）、`活动未知`。它只描述日志，不冒充训练进程状态。

### 5.1 横轴自动选择

请求 `axis=auto`（界面默认）时，后端按**每个指标真实存在的字段**选择横轴：

- 有 `global_step` → 优化步；
- 否则有 `epoch` → 训练轮次；
- 否则有 `timestamp` → 时间；
- 都有时优先优化步；不存在 Step 时不会伪造 Step。

因此同一个 Run 的 `train/loss` 可以画在优化步、`val/miou` 可以画在训练轮次；每个系列在响应里带自己的 `axis`。对比查询按所有运行该指标的总覆盖选择共同横轴，并在某运行缺少该轴时给出 `axis_partial_coverage` 警告，不插值补齐。

## 6. 训练侧写入器与 Agent 接入

训练代码可以使用 [`TrainingRunWriter`](components/training-run-writer.md)（`src/training_viewer/writer.py`）生成上述文件。它只依赖 Python 标准库，可单独复制；不会启动查看器。

训练 Agent 完成日志写入和校验后，执行：

```bash
training-viewer attach <日志根目录> --json
```

`attach` 会复用或后台启动本机服务、注册日志根目录并返回可打开的 URL。完整步骤、代码骨架、验收清单与禁止事项见 [`AGENT_INTEGRATION.md`](../AGENT_INTEGRATION.md)。

## 7. 示例

| 目录 | 来源 | 目的 |
|---|---|---|
| [`examples/segformer_baseline`](../examples/segformer_baseline) | TVLP | 两个 Epoch、预测图与标签图、无完成事件 |
| [`examples/segformer_wavelength_encoder`](../examples/segformer_wavelength_encoder) | TVLP | 四个 Epoch、完成事件、表格产物 |
| [`examples/csv_training_log`](../examples/csv_training_log) | TVLP + CSV | 显式列映射 |
| [`examples/tensorboard_scalars`](../examples/tensorboard_scalars) | TensorBoard | 真实格式事件文件、可选依赖 |

以上均为示例数据，指标数值和图片不代表真实训练结果。
