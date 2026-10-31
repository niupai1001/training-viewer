# 结果文件发现

- 中文名：结果文件发现器
- 代码名：`discover_result_files`
- 位置：`src/training_viewer/results/discovery.py`
- 接口：`GET /api/v1/runs/{run_id}/result-candidates`

## 职责

当训练目录已有预测图/标签图，但没有 TVLP artifact 事件时，按常见目录与文件名提供**候选**图片：

- 支持 `.png/.jpg/.jpeg/.webp/.gif/.bmp`；
- 角色只做猜测：`prediction`（pred/output/logits）、`ground_truth`（gt/label/mask）、`input`（input/rgb/image）；
- 每条候选都带 `requires_confirmation=True`、`confidence=filename-hint|path-convention|low` 和说明；
- 已由事件注册的产物路径不重复列出。

## 安全边界

- 只扫描 Run 目录内部；内容请求仍走 `resolve_artifact_path`，拒绝绝对路径、`..` 和越界符号链接。
- 只允许图片 MIME 内联；HTML/SVG/脚本不通过该接口执行。
- 不自动把候选写入指标或排名；需要用户/事件确认。

## 限制

- 多光谱/GeoTIFF 的波段合成、掩膜色盘、空间坐标没有实现；不要默认加载全量栅格。
- 文件名规则可能误判；UI 明确显示“未确认”。
- 未做 TensorBoard image 事件解析；当前只覆盖事件注册的 artifact 与文件候选两条通道中的后者。

## 测试

`tests/test_audit_features.py` 覆盖候选角色、未确认标记、图片内容与路径穿越拒绝。
