# 组件说明：TensorBoard 事件读取器（TensorBoardEventReader）

## 一句话说明

复用 TensorBoard 官方事件文件加载器，把事件文件中的标量值转换为指标记录；不导入图像/直方图，不修改事件文件，也不推断训练状态。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | TensorBoard 事件读取器 |
| 代码类名 | `TensorBoardEventReader` |
| 源文件 | `src/training_viewer/log_readers/tensorboard_event_reader.py` |
| 所属模块 | 日志读取 |
| 上游 | `TensorBoardSourceAdapter`；下游 | `TrainingMetricIndexer` |
| 首次引入版本 | 1.0.0 |
| 可选依赖 | `tensorboard >= 2.15`（安装 extra：`training-viewer[tensorboard]`） |

## 为什么需要它

TensorBoard 事件文件是二进制 TFRecord，自行实现容易在 CRC、压缩和 Summary 版本上出错。项目规范要求优先复用成熟实现，因此只调用 TensorBoard 的 `EventFileLoader` 与 `tensor_util.make_ndarray`，把解析成本限制在“提取标量”这一层。

它不负责：非标量图像产物的可视化、超参数（hparams）解析、运行元数据（事件文件没有项目/名称）。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 | 错误时 |
|---|---|---|---|---|
| 输入 | `file_path` | `Path` | `events.out.tfevents.*` 文件 | 不存在 → warning |
| 输入 | `run_directory` | `Path` | 计算相对来源路径 | — |
| 输入 | `cursor` | `FileCursor \| None` | `offset` 为已处理事件序号；`size` 为文件大小 | 文件变小/身份变化 → 重置并从 0 读 |
| 输出 | 指标记录 | `MetricPoint` 列表 | 每个标量 Summary 值一条 | — |
| 输出 | 问题 | `ParseIssue` 列表 | 读取中断、跳过的非标量数量 | — |

`timestamp` 来自 `event.wall_time`（Unix 秒转 UTC）；`global_step` 来自 `event.step`；不填写 `epoch`。标签 `train/loss` 拆为阶段 `train`、指标 `loss`；没有斜杠时阶段为 `unlabeled`。

## 主要处理流程

1. 构造时尝试导入 `tensorboard`；缺失时引发 `ReaderUnavailableError`，扫描器记录安装提示。
2. `stat` 文件，比较文件身份与大小；需要重置时从事件序号 0 开始。
3. `EventFileLoader` 从头迭代事件，用递增序号跳过游标之前的事件。
4. 对每个 Summary Value：
   - `simple_value` → 有限浮点数；
   - 单元素数值张量 → 转 `float`；
   - 其它类型 → 计数为“已跳过非标量”。
5. 生成记录，`source_offset` 为事件序号（不是字节偏移），唯一键防止重复。
6. 捕获读取中断（训练进程仍在写入）并保留已解析部分，游标停在已处理事件数。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 事件文件匹配 | `events.out.tfevents.*` | 只扫描 Run 目录第一层 |
| 可选依赖 | 未安装 | 缺少时来源不可用，记录目录诊断 |

第三方依赖及许可证：TensorBoard（Apache-2.0）。项目只调用公开 API，不复制源码。

## 和旧实现相比改变了什么

初始实现，无旧版本。V1 使用“事件序号游标 + 从头重读”的方式，换取实现简单和事件文件截断时的可恢复性；没有实现字节级 seek。

## 如何验证

- `tests/test_indexing.py::test_tensorboard_scalars_are_ingested`（无 tensorboard 时跳过）
- 示例：`examples/tensorboard_scalars`，真实事件文件，包含 `train/loss`、`val/miou`、`val/f1`。
- 手工：安装 `training-viewer[tensorboard]` 后添加该目录，确认 3 个指标各 11 个点。

## 已知限制与回退

- 文件每次变化都会从头读取；超大事件文件的性能是已知限制。
- 只读取标量；图像、直方图、文本、PR 曲线不导入。
- 事件文件没有运行元数据，目录移动会改变合成 `run_id`。
- TensorBoard 版本升级可能改变内部 API；`TensorBoardEventReader` 使用稳定度较高的 `EventFileLoader`，但仍需在升级时运行测试。
- 回退：卸载可选依赖或删除目录根配置；内置来源不受影响。

## 名称解释

- TensorBoard：TensorFlow 生态的训练可视化工具。
- TFRecord：TensorBoard 事件文件的二进制记录格式。
- Summary：事件中的一条记录，可包含标量、图像等值。
