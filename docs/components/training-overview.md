# 训练概览与自定义图表（TrainingOverview）

## 职责

`TrainingOverview` 是训练工作区的默认内容：六项监控摘要、Train/Val Loss、主验证指标、自定义图表入口。它替代旧的 `RunMetricsTab` 指标按钮云；旧组件已删除。

## 输入

- `run: RunDetail`：来自现有运行详情 API。
- 指标目录：`GET /runs/{run_id}/metric-catalog`，首屏只取 100 项，核心角色优先。
- 核心曲线：`GET /runs/{run_id}/metrics`，只请求识别出的 Train Loss、Val Loss、主验证指标、LR。
- 自定义视图：`localStorage["training-viewer.chart-views.v1.<run_id>"]`，保存原始 key、轴、单位、类型和标题。

## 输出

- 六项摘要：**时间跨度**（明确标“指标首末，不是有效训练时长”）、Epoch/Step、Train Loss、Validation Loss、最佳验证指标、Learning Rate；缺失显示“未记录”。
- 默认 Loss 卡：Train/Val 同图；横轴或单位不一致时强制分图；无 Val 时明确“未记录验证损失”；提供“全程 / 后期 / 对数”轻量切换，后期只取最后 20% 横轴范围并显式标注，原始数据不改。
- 主验证指标卡；只有单点时使用评估表，不画伪趋势。
- 自定义图表：按 Run 恢复、可上移/下移/重命名/删除；缺失 key 显示警告。
- “＋ 添加图表 / 指标”打开 `MetricBrowserDrawer`。

## 边界

- 时间 KPI 来自 `GET /runs/{id}/summary`：有生命周期时显示“累计运行时长”，否则明确显示“日志跨度”；开放会话按最后指标估算并标 partial。
- TVLP 1.1 的四段说明可展开；旧 1.0/历史运行没有该结构，显示“未提供”，不补造。
- Loss 的“后期”是显示层过滤最后 20% 横轴；“对数”遇到零/负值由 `MetricChart` 退回线性并提示；自定义 Y 范围、迷你全程概览尚未实现。
- 自定义视图存在浏览器本地，不是服务端 SQLite 用户状态；清站点数据会丢。
- 自定义图表只按单位/轴分图，不做跨单位双 Y 轴。

## 验证

- E2E：六项摘要、默认无指标 chips、打开抽屉、搜索、添加自定义图。
- `e2e:live`：imported JSONL 无心跳追加后摘要 Train Loss 自动从 1 更新到 0.8。
- 截图：[workspace-1440x900.png](../images/workspace-1440x900.png)、[workspace-1366x768.png](../images/workspace-1366x768.png)、[metric-browser.png](../images/metric-browser.png)、[metric-evaluation.png](../images/metric-evaluation.png)。
