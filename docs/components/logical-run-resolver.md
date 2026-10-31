# 逻辑实验身份与来源归并

- 中文名：逻辑实验解析器
- 代码名：`LogicalRunOverrideStore`、`LogicalRunOverride`
- 位置：`src/training_viewer/identity/logical_runs.py`
- 数据：`<数据目录>/logical_runs.json`（sidecar，不写训练目录）

## 职责

把多个原始日志文件明确归并为一个 `LogicalRun`，并保证可审计、可撤销：

- 规范 `run.json` 的 `run_id` 仍是最高优先级；
- 无 `run.json` 的通用文件默认**不自动合并**，每个文件独立；
- 只有用户通过 `POST /logical-runs/overrides` 明确确认的文件组才归并；
- 归并后的 Run 元数据记录 `merged_source_run_ids`、`merged_files`、`merge_confidence=user-confirmed`；
- 删除覆盖规则后删除合并索引，重新按独立文件导入。

## 输入 / 输出

- 输入：`DiscoveredRun` 列表、Viewer 数据目录中的覆盖 JSON。
- 输出：归并后的 `DiscoveredRun` 列表、审计说明（merged/rejected）。
- 限制：当前只允许同一目录内的文件归并；跨目录会拒绝并保留独立来源，避免相对路径逃出 Run 目录。

## 失败与安全

- 覆盖文件路径必须在已添加根目录内、必须是真实文件；否则 API 返回 400。
- 同一文件被映射到多个逻辑实验时拒绝该组。
- sidecar 写入使用临时文件 + 原子替换；原始日志不被修改。

## 测试

`tests/test_logical_runs.py`、`tests/test_audit_features.py` 覆盖归并、撤销、sidecar 位置、原始文件不变、扫描不漏子 Run。
