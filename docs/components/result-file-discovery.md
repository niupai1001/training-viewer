# 结果文件发现

- 中文名：结果文件发现器
- 代码名：`discover_result_files`
- 位置：`src/training_viewer/results/discovery.py`
- 接口：`GET /api/v1/runs/{run_id}/result-candidates`

## 职责

当训练目录已有预测图/标签图，但没有 TVLP artifact 事件时，提供两条通道：

- **TensorBoard image 事件**：用官方 `EventFileLoader` 读取 `image`/迁移后的 `DT_STRING` tensor，缓存到 `<数据目录>/result-cache/<run_id>/`；标记 `confidence=event-image`、`requires_confirmation=false`，原始事件文件不改。
- **目录/文件名候选**：扫描 Run 目录中的图片，按 `prediction/ground_truth/input` 猜测角色；每条标记 `requires_confirmation=true`、置信度 `filename-hint/path-convention/low` 和说明。

## 安全边界

- 只扫描 Run 目录内部；内容请求仍走 `resolve_artifact_path`，拒绝绝对路径、`..` 和越界符号链接。
- 只允许图片 MIME 内联；HTML/SVG/脚本不通过该接口执行。
- 不自动把候选写入指标或排名；需要用户/事件确认。

## 限制

- 多光谱/GeoTIFF 的波段合成、掩膜色盘、空间坐标没有实现；不要默认加载全量栅格。
- 目录/文件名规则可能误判；UI 明确显示“未确认”。TensorBoard image 事件属于事件关联，但仍需业务确认图像语义。
- 未解析 TensorBoard histogram/audio；当前只覆盖 image 事件与文件候选。

## 测试

`tests/test_audit_features.py` 覆盖文件名候选、未确认标记、图片内容与路径穿越拒绝，以及 TensorBoard image 事件缓存。
