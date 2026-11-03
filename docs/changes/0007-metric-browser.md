# 0007：指标浏览器与数据类型分流（V1.1 / C10）

- 日期：2026-11-03
- 依据：`docs/agent-change-request/2026-11-03/01_Training_Viewer_Change_Contract.md` C10、`04_...交互专项设计`
- 状态：**首版实现；A16–A24 部分完成，未关闭项在文末列出**

## 做了什么

1. 新增 `MetricSemanticResolver`：声明优先、内建别名、未知保留原键；`train/epoch_QUIVALENT` 不被翻译成“等效 Epoch”。
2. 新增 `metric-catalog` API：搜索、阶段/语义组/类型筛选、游标分页、facets、目录项包含点数、不同 X 数、可用轴、`value_kind`、`suggested_view`。
3. `TrainingOverview` 替换旧 `RunMetricsTab`：
   - 六项摘要：时间跨度（明确非有效训练时长）、Epoch/Step、Train/Val Loss、最佳验证指标、LR；
   - Train/Val Loss 同图，单位/轴不一致强制分图；
   - 主验证指标卡；单点转评估表；
   - 右上“＋ 添加图表 / 指标”。
4. `MetricBrowserDrawer`：搜索、分组、阶段筛选、每批 40 加载、选择保留、新建图/加入现有图、单位不兼容拒绝。
5. 自定义图表按 Run 保存原始 key、轴、单位、类型、标题到浏览器本地用户状态；支持上移/下移/重命名/删除、缺失 key 警告。
6. 删除旧 `RunMetricsTab.tsx`；默认页面不再平铺指标 chips，也不存在 `chartLimit` 隐藏截断。

## 验证

| 用例 | 状态 | 证据 |
|---|---|---|
| A16 1000 指标，800 单点 | **部分通过** | 1000 指标夹具；API 40 项/46 KB；抽屉 DOM 约 705；单点进 evaluation |
| A17 搜索 rmse / SR_B6 / 中文 | **通过（后端/浏览器）** | `test_metric_catalog.py`；浏览器搜索 `accuracy`/`field_99` |
| A18 不同分组选 5 连续指标 | **部分** | 单位/轴分组逻辑；未做 5 条专门 E2E |
| A19 `combo.../mae` 单点 | **通过** | 单点 `value_kind=single_point`，评估表截图 |
| A20 200 行同一 Step | **通过** | `test_catalog_splits_single_point_and_repeated_x` |
| A21 保存视图重启/切换 | **部分** | 浏览器 reload 后恢复；服务端重启/重建索引未自动验证 |
| A22 GPU MiB + 秒 + Loss | **部分** | 新图按单位/轴分图，目标图拒绝异单位；未做专门测试 |
| A23 1440/1366 截图 | **通过** | workspace 截图；抽屉/评估截图 |
| A24 1k–10k 性能 | **部分** | 1k API 31 ms、40 行；10k 未测，未虚拟化 |

命令：

```powershell
pytest tests/test_metric_catalog.py tests/test_metric_semantics.py -q
cd frontend
npm run typecheck
npm run build
npm run e2e
npm run e2e:live
```

本机结果：后端 98 passed, 2 skipped（含新增 6 个指标测试）；前端 3 Vitest；E2E 通过。

## 图片

- [workspace-1440x900](../images/workspace-1440x900.png)
- [workspace-1366x768](../images/workspace-1366x768.png)
- [metric-browser](../images/metric-browser.png)
- [metric-evaluation](../images/metric-evaluation.png)

## 未完成 / 风险

- 训练时长仍是指标首末跨度，不是生命周期累计；`RunMonitoringSummary` 未实现。
- Loss 全程/后期/对数轻量切换已接入；自定义 Y 范围、迷你全程概览未实现。
- TLVP 1.1 四要素、Schema、Writer/Validator 尚未在本轮升级。
- 自定义视图在 localStorage，不是服务端用户状态库；换浏览器会丢失。
- 单点评估热力图、用户指标定义编辑、10k 指标虚拟化未做。
- 1000 指标 API 响应 46 KB/40 项为本机样本；不是通用性能承诺。
