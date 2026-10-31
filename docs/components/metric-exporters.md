# 组件说明：指标导出器（MetricCsvExporter / MetricJsonExporter）

## 一句话说明

把多运行对比结果序列化为带溯源元数据的 CSV 或 JSON；不重新查询数据库、不计算平滑值、不修改对比结果。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 指标导出器 |
| 代码名 | `MetricCsvExporter`、`MetricJsonExporter`、`MetricExporterRegistry` |
| 源文件 | `src/training_viewer/export/metric_exporters.py` |
| 所属模块 | 导出 |
| 上游 | 指标导出路由；下游 | HTTP 响应 / 浏览器下载 |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

论文复现需要知道图中数据来自哪些运行、哪个横轴、是否经过抽样或平滑、指标单位与定义。只导出两列数字无法说明这些条件。导出器统一附带元数据，避免每个页面各自实现格式。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | `comparison` | `dict` | `/compare/query` 的完整响应 |
| 输入 | `metadata` | `dict` | 导出时间、横轴、运行/指标集合、最大点数、平滑参数、坐标轴类型 |
| 输出 | CSV 文本 | `str` | `#` 注释元数据 + 表头 + 数据行 |
| 输出 | JSON 文本 | `str` | `metadata`、`series`、`runs`、`hyperparameters`、`warnings` |

## 主要处理流程

1. 路由根据当前选择调用查询层构建 `comparison`。
2. 路由收集 `metadata`（含 TVLP 版本、是否抽样、平滑方法与窗口）。
3. 从注册表按键 `csv` / `json` 取导出器。
4. 导出器序列化并返回字符串；路由设置 `Content-Disposition: attachment` 与安全文件名。
5. 浏览器下载。

CSV 列：`run_id, run_name, metric_key, axis, x, value, global_step, epoch, timestamp, session_id`。`x` 在时间轴上是 Unix 秒。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 内置格式 | `csv`、`json` | `format_id` |
| entry point 组 | `training_viewer.metric_exporters` | 第三方格式 |
| 最大点数 | 请求参数 `max_points`（上限 20000） | 由查询层降采样 |

依赖：Python 标准库 `csv`、`json`。无第三方依赖。

## 和旧实现相比改变了什么

初始实现。平滑在浏览器端完成，因此导出只记录平滑参数和抽样后的点，不声称服务器重新计算了平滑曲线；元数据中明确提示“图表点可能经过分桶抽样”。

## 如何验证

- `tests/test_api.py::test_export_csv_and_json_include_provenance`：CSV 注释、平滑元数据、附件头；JSON 可解析。
- 手工：运行详情选择 `val/miou`，导出 CSV，检查表头与运行 ID。

## 已知限制与回退

- CSV 不包含完整指标定义文本；需要定义时使用 JSON。
- 平滑后的曲线值不会写入导出；导出的是查询层返回的原始/抽样点。需要使用平滑值时请在绘图/分析工具中重新计算，或在元数据中记录参数。
- 回退：删除导出文件即可，无持久化副作用。

## 名称解释

- CSV：逗号分隔值。
- JSON：结构化文本数据格式。
- 溯源：记录数据来源与处理参数，便于复现。
