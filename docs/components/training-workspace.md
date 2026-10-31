# 训练工作区

- 中文名：训练工作区
- 代码名：`TrainingWorkspacePage`
- 位置：`frontend/src/pages/TrainingWorkspacePage.tsx`
- 路由：`/`、`/runs`、`/runs/:id`、`/compare` 全部转发到这里

## 职责

用一个工作区替换原来的总览/实验管理/对比三页：

- 左侧 `RunSelector`：项目/实验组树、搜索、多选；
- 右侧单运行时：自动推荐 Loss/验证指标，最多显示 2 个核心图；最新事件产物与结果文件候选；
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

## 测试

`frontend/src/components/MetricChart.test.tsx`、`npm run e2e`（1440×900 与 1366×768，工作区/多选/诊断截图）。
