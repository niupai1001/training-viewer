# 指标目录与语义分流

## 做什么

`metric_catalog` 把一个 Run 的原始指标键整理成可搜索目录，并区分：

- **连续曲线**：至少有两个不同的有效横轴值（Step / Epoch / 时间），可作为折线候选；
- **单次评估**：只有一个有效横轴值，或 200 行都落在同一个 Step；默认进入表格/散点，不伪装成训练趋势；
- **资源/吞吐**：明确路径或别名归入性能组，但不把不同单位强行叠加；
- **未知字段**：保留原始键，标记“定义未提供”，不猜测科学含义。

## 输入

`GET /api/v1/runs/{run_id}/metric-catalog`

| 参数 | 说明 |
|---|---|
| `query` | 大小写不敏感，搜索中文名、原始键、说明、分组路径 |
| `category` | 语义类别：`loss`、`validation_score`、`learning_rate`、`performance`、`custom` |
| `group` | 展示分组：`training_trend`、`performance`、`evaluation`、`other` |
| `phase` | `train`、`val`、`test` 或原始阶段 |
| `value_kind` | `continuous`、`single_point` |
| `limit` / `cursor` | 每批 1–100，游标分页 |

## 输出

每项包含 `raw_key`、`display_name_zh`、`description`、`definition_source`、`unit`、`direction`、`point_count`、`distinct_x_count`、`available_axes`、`value_kind`、`suggested_view`、`group_path`、`role`、`is_primary`。

`definition_source`：

- `declared`：TVLP `metric_definitions` 明确声明；
- `builtin_alias`：安全内建别名，例如 loss / accuracy / lr；
- `unknown`：没有定义，保留原键，不翻译成权威含义。

`role` 只用于默认监控槽位：`train_loss`、`val_loss`、`validation_score`、`learning_rate`、`primary_validation`。没有声明 `is_primary` 时不会把某个未知分数强行标成主指标。

## 实现与边界

- 查询在 SQLite 中对 `metric_points` 做一次分组，读取不同 X 值计数；不逐指标执行 Best/Last 查询。
- 目录按 Run 缓存，索引同步后失效。
- 1,000 指标夹具：API 返回 40 项 / 约 46 KB，搜索 31 ms（本机 Windows，非跨平台基准）。
- 路径前缀只用于分组，不证明 `L8`/`SR_B6` 等业务含义。
- 用户补充指标定义、动态指标组尚未实现；当前只读声明 + 内建别名 + 未知。

## 验证

- `tests/test_metric_catalog.py`：连续/单点/重复 Step、1000 指标分页、搜索、未知字段。
- `tests/test_metric_semantics.py`：声明优先、未知不猜测、`value_profile` 以不同 X 判断。
- 截图：[metric-browser.png](../images/metric-browser.png)、[metric-evaluation.png](../images/metric-evaluation.png)。
