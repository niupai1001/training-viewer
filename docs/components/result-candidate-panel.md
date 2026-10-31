# 结果候选面板

- 中文名：结果文件候选
- 代码名：`ResultCandidatePanel`
- 位置：`frontend/src/components/ResultCandidatePanel.tsx`
- 数据：`GET /api/v1/runs/{run_id}/result-candidates`

## 职责

在事件没有引用图片时，展示按目录/文件名推断的预测图候选，并明确标注“未确认”和置信度。

- 只显示图片；内容通过安全 content 路由加载。
- 不把候选角色写入指标、排名或产物表。
- 没有候选时返回 `null`，不占布局。

## 限制

- 文件名推断可能错误；当前没有“一键确认并转为 artifact”的写回流程。
- 多光谱/GeoTIFF 波段合成未实现。
