# 组件说明：训练指标索引器（TrainingMetricIndexer）

## 一句话说明

把读取器产出的规范化记录写入 SQLite，维护每个日志文件的游标，防止重复导入，处理截断/替换，记录解析问题，并根据生命周期与心跳推导运行状态；不生成图表、不解析界面参数、不修改原始日志。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 训练指标索引器 |
| 代码类名 | `TrainingMetricIndexer` |
| 源文件 | `src/training_viewer/indexing/training_metric_indexer.py` |
| 所属模块 | 索引 |
| 上游 | `TrainingViewerService`；下游 | `IndexQueries`、SQLite |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

训练日志会持续追加，查看器也可能被杀掉重启。没有游标就会重复入库；没有幂等键就会在文件截断、复制、重读时产生重复曲线；没有统一的状态推导就会把“日志停止”误判成失败。本组件把这些规则集中在一个事务边界内。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 | 错误时 |
|---|---|---|---|---|
| 输入 | `DiscoveredRun` | 数据类 | 运行元数据与文件读取器 | 元数据非法时不会到达这里 |
| 输入 | `root_path` | `Path` | 命中该 Run 的根目录 | — |
| 输入 | 时钟 | 可调用对象 | 默认 UTC now；测试可注入固定时间 | — |
| 输出 | `IngestReport` | 数据类 | `run_id`、是否变化、是否新运行、本次问题 | 单个 Run 失败由服务记录诊断并继续其它运行 |
| 输出 | SQLite 行 | 表 | `runs`、`metric_points`、`artifacts`、`training_events`、`ingestion_cursors`、`ingestion_issues` | 事务回滚 |

## 数据表与幂等键

| 表 | 幂等键 |
|---|---|
| `metric_points` | `(run_id, source_file, source_offset, phase, metric_name)`；v1 库启动时自动迁移 |
| `artifacts` | `(run_id, source_file, source_offset)` |
| `training_events` | `(run_id, source_file, source_offset)` |
| `ingestion_cursors` | `file_path`（主键） |
| `ingestion_issues` | `source_key`（哈希） |

`source_offset` 对 JSONL 是行起始字节偏移，对 CSV 是数据行号，对 TensorBoard 是事件序号。

## 主要处理流程

1. **运行身份**：按 `run_id` 查询已有记录；如果同一目录已有另一个 `run_id`，删除旧运行的派生索引并记录“run_id 变化”问题。
2. **新建/更新**：写入项目、实验组、名称、模型、数据集、标签、种子、元数据 JSON；首次状态为 unknown。
3. **位置/来源变化**：运行目录或来源类型改变 → 删除该 Run 的派生索引并按新位置重建；备注按 `run_id` 保留。
4. **元数据变化**：更新字段；CSV 游标重置以应用新的列映射。
5. **清理消失文件**：游标中存在但本次不再提供的日志文件 → 删除其指标/产物/事件与游标，并记录“文件已不存在”警告。
6. **逐文件读取**：文件身份、大小、mtime 与游标一致 → 跳过；否则调用读取器。
7. **重置处理**：读取结果 `reset=True` → 删除该文件旧索引；首次读取不误报截断。
8. **插入记录**：`INSERT OR IGNORE`；产物路径经 `resolve_artifact_path` 校验，越界路径拒绝并记录问题；缺失产物仍保留引用并标记 `exists_on_disk=0`。
9. **更新游标**：保存文件身份、偏移、行号、大小、mtime、读取时间。
10. **刷新产物存在性**：最多 2000 个/运行，优先检查缺失项。
11. **推导状态**：见下节；即使没有新行，`refresh_statuses()` 也会因心跳超时把“运行中”更新为“未知”。活动 `activity` 由查询层按最后指标时间计算，不写回状态。
12. **维护问题表**：按哈希去重，最多保留 2000 条。

## 状态推导

| 条件 | 状态 | 原因文案 |
|---|---|---|
| 来源为 TensorBoard/CSV/通用文件 | `imported` | 无生命周期事件 |
| 最新 lifecycle 为 completed/failed/cancelled | 对应状态 | 含事件时间 |
| 最近 120 秒内有 heartbeat | `running` | 心跳是进程存在的显式证据 |
| 有近期指标、无近期心跳 | `unknown` | 指标更新不等于进程存在，不能标记运行中 |
| 有活动但已超时 | `unknown` | “日志停止不能证明训练失败” |
| 尚无任何事件/指标 | `unknown` | “尚未收到指标、心跳或生命周期事件” |

## 配置与依赖

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `STALE_AFTER_SECONDS` | 120 | 心跳/指标超过该时间视为不活跃 |
| `MAX_STORED_ISSUES` | 2000 | 问题表上限 |
| `MAX_ARTIFACT_REFRESH` | 2000 | 每次运行检查产物存在性的上限 |
| `now` | UTC 当前时间 | 测试注入时钟 |

依赖：`IndexDatabase`、读取器协议、路径安全守卫、Python 标准库。无第三方依赖。

## 和旧实现相比改变了什么

初始实现。首轮验证修正了三点：

1. 首次读取不再误报“文件被截断/替换”；
2. 半行补齐后删除过期的“等待补齐”提示；
3. `run.json` 校验异常不再中断整次同步。

参见[变更记录 0002](../changes/0002-first-verification-fixes.md)。

## 如何验证

- `tests/test_indexing.py`：幂等、追加、半行、截断、完成/运行中/未知状态、断点续训、Step 回退、CSV、TensorBoard、run_id 冲突、目录移动、坏元数据、备注保留、第三方适配器。
- `tests/test_downsampling.py`：降采样不改变 Best/Last。
- 手工：对 `examples/segformer_baseline` 多次执行“立即重新扫描”，点数保持不变。

## 已知限制与回退

- SQLite 写操作串行；单机单用户可接受。
- TensorBoard/CSV 文件变化时整体重读，超大文件性能有限。
- 没有删除已不在任何根目录下的运行；目录不可访问时保留索引并标记，避免丢失备注。
- 回退：删除索引数据库后重启；原始日志不受影响。若要撤销某次索引逻辑变更，回退代码提交并重建索引即可。

## 名称解释

- 游标（cursor）：已消费位置。
- 幂等（idempotent）：重复执行不会产生重复结果。
- `session_id`：执行会话标识，断点续训时改变。
- `reset`：检测到文件替换/截断后的重建标记。
