# 最新产物预览

- 中文名：运行页最新预测样本
- 代码名：`LatestArtifactPreview`
- 位置：`frontend/src/components/LatestArtifactPreview.tsx`
- 使用页面：运行详情

## 职责

在运行页顶部直接展示最新一个含图像产物的样本分组（输入、真实标签、预测），让用户不必先切到“实验产物”标签。完整图库仍由“预测结果”页面承载。

## 输入 / 输出

- 输入：`runId`。
- 数据：`GET /api/v1/runs/{run_id}/artifact-groups`。
- 输出：最多 3 张缩略图；没有图像产物时返回 `null`，不占位。
- 链接：`#/results?run=...&tag=...` 打开完整结果。

## 限制

- 只预览图片/图表类型；表格、HTML、模型等交给产物标签页。
- 图库按 Epoch 降序选择最新分组；不加载模型文件，不执行 HTML/SVG。

## 测试

由 `npm run e2e` 覆盖运行页渲染；产物安全边界由 `tests/test_api.py` 覆盖。
