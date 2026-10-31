# 通用日志文件来源与读取器

- 中文名：通用日志文件来源
- 代码名：`GenericLogFileSourceAdapter`
- 位置：`src/training_viewer/source_adapters/generic_log_file_adapter.py`
- 读取器：`GenericJsonlMetricReader`、`PlainTextLogReader`，CSV/TSV 复用 `CsvMetricLogReader`

## 职责

在没有 `run.json` 的目录里做保守内容嗅探，把用户已有的训练日志变成 Run：

- 任意文件名 `.csv` / `.tsv`：表头有 Step/Epoch 别名，且有训练指标列或时间/阶段列；纯业务表拒绝。
- 任意文件名 `.jsonl`：至少一条记录含 Step/Epoch 和数值指标（扁平或 `metrics`）。
- `.log` / `.txt` / `.out`：规则模板能解析出明确写出的 Step/Epoch 与指标键值。

同一目录里的每个通过嗅探的文件生成一个独立 Run，共享目录；不修改原始文件。

## 输入 / 输出

- 输入：一个目录。
- 输出：`DiscoveredRun` 列表；每个含合成元数据、一个 `LogFileSpec` 和对应读取器。
- 合成身份：`generic-<kind>-<路径哈希>`，项目取父目录名，运行名取文件 stem。

## 处理与限制

- CSV/TSV 按行号增量；JSONL/文本按字节偏移增量，半行等待补齐。
- 普通文本只识别 `loss`、`accuracy`、`miou`、`f1`、`lr` 等明确键；`val_loss` 会拆成 `val` 阶段 + `loss`。
- 没有 Step/Epoch、没有数值指标、或看起来像业务表格的文件不会导入。
- 识别失败不会伪造字段映射；当前没有持久化的人工映射模板（见变更记录 0005 的未完成项）。
- 纯文本是启发式读取，复杂格式请先转成 CSV/TSV 或 TVLP。

## 测试

`tests/test_axis_and_generic.py` 覆盖 CSV、JSONL、纯文本、业务 CSV 拒绝、共享目录与自动横轴。
