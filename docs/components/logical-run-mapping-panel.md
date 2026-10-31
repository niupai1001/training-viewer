# 逻辑实验映射面板

- 中文名：来源映射与逻辑实验
- 代码名：`LogicalRunMappingPanel`
- 位置：`frontend/src/components/LogicalRunMappingPanel.tsx`
- 使用页面：设置与诊断

## 职责

让用户查看来源清单，勾选同一目录的文件，输入逻辑实验 ID/显示名并确认归并；列出已保存规则并可撤销。

- 保存：`POST /logical-runs/overrides`；规则写入 Viewer 数据目录的 `logical_runs.json`。
- 撤销：`DELETE /logical-runs/overrides/{id}`；重新按独立文件导入。
- 不修改原始日志；后端只接受已添加根目录内的真实文件。

## 限制

- 当前只支持同一目录内的文件归并；跨目录会被后端拒绝。
- 不自动猜测归并；默认每个文件独立。
