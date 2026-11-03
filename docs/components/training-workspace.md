# 训练工作区

- 中文名：训练工作区
- 代码名：`TrainingWorkspacePage`
- 位置：`frontend/src/pages/TrainingWorkspacePage.tsx`
- 路由：`/`、`/runs`、`/runs/:id`、`/compare` 全部转发到这里

## 职责

用一个工作区替换原来的总览/实验管理/对比三页：

- 左侧 `RunSelector`：项目/实验组树、搜索、多选；
- 右侧单运行时：`TrainingOverview` 显示六项摘要、Train/Val Loss 同图和主验证指标；不再平铺指标按钮；指标通过抽屉添加为自定义图表；
- 右侧多选时：自动取共同 Loss/验证指标并叠加，显示不可直接比较原因；不切到独立“比较页”；
- 高级按钮打开 `AdvancedAnalysisDrawer`：配置、诊断、来源清单、目录链接；
- 首次打开恢复 `localStorage` 上次主动选择的 Run；没有记录时才选活跃/最近；示例 Run（合成元数据）不会优先抢占真实运行。

## 输入 / 输出

- 输入：`/runs` 列表、`/runs/{id}`、`/metric-keys`、`/metrics`、`/compare/query`、结果候选接口。
- 输出：交互页面；不写日志、不改 SQLite。

## 状态与限制

- 选择状态保存在浏览器本地，不写入服务端。
- 多选最多 8 个；缺指标不插值。
- 旧总览/实验库/对比/运行详情页文件已删除；旧路由转发到工作区。
- 指标选择偏好保存在浏览器本地；对比默认优先使用上次选中的验证指标，否则用 Train Loss + 验证 max 指标。
- 单 Run 与多选对比图都监听 `dataZoom`，通过 `x_min/x_max` 只查询当前区间并显示重置入口。
- 单 Run 使用 `TrainingOverview`，默认不再有 `metric-chip` 按钮云；图表设置/自定义视图见 [metric-browser](metric-browser.md) 与 [training-overview](training-overview.md)。
- 项目/实验组深链接同时过滤 `project` 与 `experiment`；运行树标题可点击筛选；列表初次 1000 条，支持递增加载到 5000。
- 行名点击切换当前实验，复选框专门加入对比；比较默认指标取所有选中 Run 的共同指标。

## 测试

`frontend/src/components/MetricChart.test.tsx`、`npm run e2e`（1440×900 与 1366×768，工作区/多选/诊断截图）。
