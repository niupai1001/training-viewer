# 组件说明：日志来源适配器（Source Adapters）

## 一句话说明

判断一个目录属于哪种日志来源，并给出该 Run 的元数据与文件读取器；不写索引、不解析记录内容，也不修改目录。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 日志来源适配器 |
| 代码名 | `StandardTvlpSourceAdapter`、`TensorBoardSourceAdapter`、`CsvSourceAdapter`、`GenericLogFileSourceAdapter`、`SourceAdapterRegistry` |
| 源文件 | `src/training_viewer/source_adapters/builtin_adapters.py`、`source_adapters/base.py` |
| 所属模块 | 日志来源 |
| 上游 | `RunDirectoryScanner`；下游 | 读取器与 `TrainingMetricIndexer` |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

不同训练框架留下不同格式的日志。如果把格式判断、元数据合成和读取细节混在索引器里，新增来源就会修改核心数据层。适配器把“来源发现”隔离成稳定接口，索引器只看到统一的 `DiscoveredRun`。

不负责：扫描根目录、增量写入、去重、状态推导、界面显示。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 | 错误/缺失时 |
|---|---|---|---|---|
| 输入 | `run_directory` | `Path` | 候选目录 | — |
| 输出 | `DiscoveredRun \| None` | 数据类 | 匹配时返回运行、元数据、文件读取器 | 不匹配返回 `None` |
| 输出异常 | `InvalidRunDirectoryError` | 异常 | `run.json` 存在但非法 | 扫描器记录目录问题并停止向下扫描 |
| 输出异常 | `ReaderUnavailableError` | 异常 | 例如缺少 tensorboard | 扫描器记录安装提示 |

## 四个内置来源

### 标准训练日志来源（StandardTvlpSourceAdapter）

- 条件：目录中存在 `run.json`。
- 使用 `RunMetadataReader` 校验元数据。
- 文件：`metrics.jsonl`；若不存在但有 `metrics.csv`，使用 CSV 读取器并传入 `extensions.csv_metric_mapping`；`events.jsonl` 总是可用（若存在）。
- `run_id` 来自 `run.json`，移动目录不改变身份。
- `metadata_synthetic=False`。

### TensorBoard 来源（TensorBoardSourceAdapter）

- 条件：目录第一层存在 `events.out.tfevents.*` 且没有 `run.json`。
- 未安装 `tensorboard` → `ReaderUnavailableError`，目录诊断给出安装命令。
- 合成元数据：
  - `run_id = "tensorboard-" + sha1(目录绝对路径小写)[:16]`；
  - `project = 上一级目录名`，`experiment = null`；
  - `name = 目录名`；
  - `created_at = 最早事件文件 mtime`（UTC）；
  - `metadata_synthetic=True`，`extensions.note` 说明元数据由目录推导。
- 每个事件文件一个 `TensorBoardEventReader`。

### CSV 来源（CsvSourceAdapter）

- 条件：存在 `metrics.csv`、没有 `run.json`、没有 TensorBoard 事件文件。
- 合成身份规则同 TensorBoard，前缀为 `csv-`。

### 通用日志文件来源（GenericLogFileSourceAdapter）

- 条件：没有 `run.json`，目录内直接子文件通过内容嗅探（任意 CSV/TSV/JSONL/`.log`/`.txt`/`.out`）。
- 每个通过嗅探的文件一个 Run，共享父目录；同一目录可有多个 Run。
- 纯业务 CSV（如 `name,price,step`）不导入。
- 详见 [通用日志文件来源](generic-log-file-source.md)。
- 使用启发式列识别；没有显式映射。
- `metadata_synthetic=True`。

## 主要处理流程

1. 注册表按固定优先级遍历适配器：TVLP → TensorBoard → CSV → 通用文件。
2. 第一个返回非空的适配器胜出；标准/TensorBoard/CSV 匹配后不再下钻，但通用文件父目录会继续下探以发现独立子 Run。
3. 适配器构造 `LogFileSpec` 列表，把文件路径与对应读取器实例绑定。
4. 索引器为每个文件读取游标并写入统一表；不需要知道来源格式。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 注册顺序 | TVLP、TensorBoard、CSV、通用文件 | 决定同一目录的优先级 |
| 合成项目名 | 上一级目录名 | 无 run.json 时 |
| entry point 组 | `training_viewer.source_adapters` | 第三方适配器安装式注册 |
| 插件 manifest | `name/version/adapter_id/capabilities` | 第三方应提供；缺失时状态 `missing-manifest`，加载失败记录在 `/plugins` |

依赖：标准库；TensorBoard 来源需要可选的 `tensorboard` 包。

## 和旧实现相比改变了什么

初始实现。V1 明确了三条规则：

1. 有 `run.json` 的目录永不按 TensorBoard/CSV 解释，避免同一目录出现两个运行；
2. TensorBoard/CSV 的合成元数据在界面显式标记，不假装是作者声明的身份；
3. 第三方适配器可通过 `SourceAdapterRegistry.register()` 或 Python entry point 接入；插件 manifest 与失败状态可查询，单个插件失败不阻止内置来源。

## 如何验证

- `tests/test_indexing.py::test_csv_metrics_with_explicit_column_mapping`
- `test_csv_without_run_json_uses_synthetic_metadata`
- `test_tensorboard_scalars_are_ingested`
- `test_custom_source_adapter_can_register_without_core_changes`
- 示例目录：4 个来源示例。

## 已知限制与回退

- 无 `run.json` 来源的 `run_id` 依赖绝对路径，移动目录后会变成“新运行”。
- TensorBoard 只识别目录第一层事件文件；嵌套 `version_0/` 目录需要把根目录添加到其父级（扫描器会继续下钻直到找到事件文件）。
- 回退：移除根目录或删除索引；原始日志不受影响。

## 名称解释

- Source Adapter：日志来源适配器。
- 合成元数据：源文件没有作者声明的项目/名称时，由目录规则推导，并在界面标记。
- entry point：Python 安装包声明的扩展入口。
