# 来源清单面板

- 中文名：来源清单
- 代码名：`SourceInventoryPanel`
- 位置：`frontend/src/components/SourceInventoryPanel.tsx`
- 数据：`GET /api/v1/audit/sources`

## 职责

展示每个原始来源文件的 parser、逻辑实验 ID、是否归并、置信度和点数，用于回答“来源文件数”和“逻辑实验数”为什么不相等。

- 只读；不写数据库。
- 来源清单也可用 `tools/export_source_inventory.py` 导出 CSV。

## 限制

- 点数按 Run 统计，不是按单个文件拆分。
- 没有真实 62 来源时不要在报告中伪造数量。
