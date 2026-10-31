# REST API 说明

基础地址：`http://127.0.0.1:<端口>/api/v1`。仅接受本机访问。所有响应为 UTF-8 JSON；文件下载与静态前端除外。

交互式接口文档：应用启动后访问 `/docs`（FastAPI 自动生成）。

## 1. 运行与目录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康状态、索引版本、最后同步时间、数据目录 |
| GET | `/meta` | 应用版本、TVLP 版本、来源适配器、导出格式、横轴与平滑方法 |
| GET | `/projects` | 项目 → 实验组树、运行计数、已添加根目录 |
| GET | `/facets` | 不同的模型、数据集、任务、标签，用于筛选下拉框 |
| GET | `/runs` | 运行列表；参数见下 |
| GET | `/runs/{run_id}` | 运行详情：配置、指标键、会话、产物标签、数据源、警告、问题 |
| GET | `/runs/{run_id}/timeline` | 生命周期、心跳与产物事件合并时间线 |
| GET | `/roots` | 已添加的扫描根目录 |
| POST | `/roots` | 添加根目录，请求 `{"path": "D:\\experiments"}`；返回 201 |
| POST | `/roots/select` | 打开本机系统目录选择框，返回 `{"path": "..."}`；无桌面环境返回 501 |
| DELETE | `/roots/{root_id}` | 移除根目录及其索引；原始文件不删除 |
| POST | `/rescan` | 立即全量同步，返回版本与发现运行数 |
| GET | `/saved-views` / GET `/saved-views/{id}` / POST / DELETE `/saved-views/{id}` | 保存的对比视图；按 id 恢复完整状态 |
| PUT | `/runs/{run_id}/annotation` | 保存备注/收藏，请求 `{"note": "...", "favorite": true}` |
| GET | `/diagnostics` | 目录级问题、run_id 冲突、需要关注的运行 |
| GET | `/audit/sources` | 来源文件 → 逻辑实验清单（parser、置信度、点数、是否归并） |
| GET | `/logical-runs/overrides` / POST / DELETE `/logical-runs/overrides/{id}` | 用户确认的逻辑实验归并规则；sidecar 存在数据目录 |
| GET | `/plugins` | Python 来源适配器清单、manifest、加载状态/错误；不包含前端动态插件 |
| GET | `/runs/{run_id}/result-candidates` | 事件之外的结果图片候选 + TensorBoard image 事件缓存；目录推断为 `requires_confirmation=true` |
| GET | `/runs/{run_id}/result-candidates/content?path=...` | 安全内联候选图片；只允许图片后缀且在 Run 目录内 |
| GET | `/runs/{run_id}/result-candidates/tensorboard-content?cache_file=...` | 安全内联 TensorBoard image 缓存；缓存名白名单 |

### `/runs` 查询参数

`project`、`experiment`、`status`、`q`（名称/ID/项目/模型/数据集模糊搜索）、`tag`、`task`、`model`、`dataset`、`favorite`、`sort`（字段前加 `-` 表示降序，默认 `-last_updated_at`）、`limit`（1–1000，默认 200）、`offset`。

运行摘要包含 `status`/`status_label`/`status_reason` 与独立的 `activity`/`activity_label`。`activity` 只描述最近是否有新指标（`updating`/`idle`/`finished`/`unknown`），不能当作训练进程存在证明。

`/health` 额外返回 `index_database`、`user_state_database`、`index_rebuildable=true`、`user_state_rebuildable=false`；删除索引库不应清空备注/收藏/保存视图。

运行摘要还包含 `primary_metric`：第一个声明 min/max 方向的验证指标；没有方向时退化为最近写入的指标，只显示最终值。

### 错误

| 状态码 | 场景 |
|---|---|
| 400 | 参数非法（如未知横轴、目录不存在/不是目录） |
| 403 | 非本机 Host/Origin、产物位于已注册根目录之外、路径穿越 |
| 404 | 运行/产物/保存视图不存在，或产物文件当前缺失 |
| 413 | 表格预览文件大于 5 MiB |
| 422 | 请求体校验失败、表格无法解析 |

## 2. 指标曲线与导出

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/runs/{run_id}/metric-keys` | 指标键、单位、方向、定义、点数、Best/Last |
| GET | `/runs/{run_id}/metrics?series=val/miou&series=train/loss&axis=auto&max_points=2000&x_min=100&x_max=500` | 单运行多指标曲线；可选区间 |
| POST | `/compare/query` | 多运行对比 |
| GET | `/runs/{run_id}/metrics/export?series=...&axis=...&format=csv&smoothing_method=ema&smoothing_window=5&scale=linear` | 下载单运行数据 |
| POST | `/compare/export` | 下载对比数据 |

`axis` 可为 `global_step`、`epoch`、`timestamp`、`auto`（默认）。`auto` 按每个指标真实存在的字段选择：优先 `global_step`，否则 `epoch`，否则 `timestamp`；不会伪造 Step。时间轴返回 Unix 秒，前端按浏览器本地时区显示。响应中每个 series 带自己的 `axis`。

`x_min` / `x_max` 可选，按当前轴的单位限制查询区间；时间轴用 Unix 秒。区间查询仍返回该区间内的 `total_points`，不会伪造区间外的点。当前前端尚未把 ECharts 缩放事件接到该参数，API 已就绪。

### 曲线响应要点

```json
{
  "run_id": "...",
  "axis": "auto",
  "series": [
    {
      "key": "val/miou",
      "axis": "epoch",
      "phase": "val",
      "metric_name": "miou",
      "unit": "ratio",
      "direction": "max",
      "points": [{"x": 100, "value": 0.43, "global_step": 100, "epoch": 1, "timestamp": "...", "session_id": "session-001"}],
      "total_points": 2,
      "returned_points": 2,
      "downsampled": false,
      "best": {"value": 0.52, "global_step": 200, "epoch": 2, "timestamp": "..."},
      "last": {"value": 0.52, "global_step": 200, "epoch": 2, "timestamp": "..."},
      "warnings": []
    }
  ],
  "warnings": []
}
```

- `points` 可能经过最小-最大分桶降采样；`total_points` 是原始数量。
- `best` / `last` 始终来自原始数据，与降采样和平滑无关。
- 曲线按 `session_id` 分段绘制；不同会话不会被错误合并。
- 缺少指标或横轴不可用时返回空 `points` 和 `warnings`，不插值。

### 对比请求

```json
{
  "run_ids": ["run-a", "run-b"],
  "series": ["val/miou"],
  "axis": "epoch",
  "max_points": 1500
}
```

响应包含：

- `series[]`：每个指标的运行曲线、`ranking_allowed` 与 `warnings`；
- `runs[]`：运行摘要；
- `hyperparameters.rows[]`：`{path, values, different}`；
- `run_fields`：项目、实验组、任务、模型、数据集、种子、状态；
- `warnings[]`：缺失运行等全局警告。

可比性规则：单位、数据集（名称/版本/划分）、指标定义/聚合、任务类型任一不同都会警告；只有全部一致且方向明确时 `ranking_allowed` 为 `true`。缺少指标的运行不会补点。

### 导出元数据

CSV 以 `#` 注释行提供：导出时间、横轴、运行集合、指标键、最大点数、是否抽样、平滑方法/窗口、坐标轴类型、TVLP 版本。JSON 顶层包含 `metadata`、`series`、`runs`、`hyperparameters`、`warnings`。

## 3. 产物

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/runs/{run_id}/artifacts?tag=&sample_id=&group_id=&epoch=&artifact_type=` | 产物清单 |
| GET | `/runs/{run_id}/artifact-groups?tag=` | 按 `group_id` 聚合，含 `roles` |
| GET | `/artifacts/{id}/content` | 图像内联；HTML/SVG 以纯文本附件返回 |
| GET | `/artifacts/{id}/download` | 以 `application/octet-stream` 下载 |
| GET | `/artifacts/{id}/table-preview` | 前 200 行/40 列 CSV/TSV/JSON 预览 |

安全响应头：

- `X-Content-Type-Options: nosniff`
- `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'`

内容接口会校验：运行目录位于已注册根目录；路径为 Run 目录内相对路径；解析后的真实路径仍在 Run 目录内。文件名在数据库中被篡改也无法绕过。

## 4. 实时更新（SSE）

`GET /api/v1/stream`，`Content-Type: text/event-stream`：

```text
event: ready
data: {"version": 12}

event: update
data: {"version": 13, "changed_runs": ["..."], "run_count": 4, "diagnostics_changed": false}
```

事件只通知版本变化，不广播指标数据。前端收到后重新查询 REST。每 15 秒发送注释行保活。

## 5. 安全约束

- 监听地址默认 `127.0.0.1`。
- `Host` 只允许 `127.0.0.1`、`localhost`、`::1`（测试环境含 `testserver`）。
- 带外部 `Origin` 的请求返回 403。
- 无鉴权机制：这是单用户本机工具，不应暴露到局域网或公网。
