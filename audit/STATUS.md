# 深度审计交付状态（Round 8）

- 基准审阅：`Training_Viewer_Deep_Audit_and_Refactor_2026-10-31.md`
- 当前提交：见 `git log -1`
- 原则：完成项给出证据；没有证据的项标为 Partial/Blocked，不把代码存在当成实机验证。

## 1. 硬门槛

| 项目 | 状态 | 证据 / 说明 |
|---|---|---|
| P0-01 错误 50 条后有效行丢失 | **完成** | 四类读取器继续解析有效行；`tests/test_reader_error_limits.py`：60 坏 + 1000 好，四格式通过；重读幂等 |
| P0-02 CUDA `0xC0000005` | **Blocked** | 本机无 torch/CUDA，未复现；writer 默认无后台线程、手动 `log_heartbeat`；`tools/cuda_writer_smoke.py` 矩阵脚本待真实环境运行 |
| P1-03 Windows 文本字节游标 | **完成** | `plain_text_log_reader.py` 二进制读取；CRLF/中文/多字节/非法 UTF-8/半行测试 |
| P1-04 来源/逻辑实验身份 | **Partial** | 通用文件默认一文件一 Run；显式 `run_id/session_id` 提取到来源清单；用户确认后 sidecar 归并可撤销；扫描继续下探子 Run。缺真实 62 来源，未做自动合并 |
| P1-05 百万点性能 | **Partial** | 物化桶 + 覆盖索引 + 区间查询；1M 首屏约 3.1 s、索引约 44 s、库约 1.66 GB；仍非秒开 |
| P1-06 结果发现 | **Partial** | TensorBoard image 事件缓存 + 目录/文件名候选（未确认标记）；无 histogram/audio、多光谱/GeoTIFF 波段/掩膜 |
| P1-07 插件生态 | **Partial** | Python 来源插件 manifest/状态/失败隔离与 `/plugins`；前端产物插件仍编译期内建（审阅允许首版如此） |
| P1-08 比较交互 | **完成（首版）** | 统一工作区多选自动叠加；默认 Loss + 验证指标；Best/Last、超参数差异、不可排名原因；对比缩放接区间 |
| P1-09 上次 Run | **完成** | 浏览器本地记住主动选择；示例 Run 不优先抢占真实运行 |
| P2-10 缓存/用户状态混用 | **完成** | `index.sqlite3` 可重建；`user_state.sqlite3` 保存根目录/备注/收藏/视图；删索引测试通过 |

## 2. 架构与界面

| 项目 | 状态 | 证据 |
|---|---|---|
| ADR-001 存储后端 | **完成** | MLflow 10k 隔离原型导入 9.3 s vs SQLite 0.4 s；决策保留 SQLite，不引入生产 MLflow；[ADR-001](docs/adr/ADR-001-storage-backend.md) |
| 统一工作区 | **完成（首版）** | `/`、`/runs`、`/runs/:id`、`/compare` 转发；旧四页删除；E2E 1440×900 / 1366×768 |
| 结果页 | **完成** | TVLP artifact + TensorBoard image + 路径候选；未确认不进入结论 |
| 来源映射 UI | **完成** | 设置页选择文件、确认/撤销逻辑实验；sidecar 不写原始目录 |
| 跨平台 | **Blocked（未验证）** | `.github/workflows/ci.yml` 添加 Ubuntu/Windows/macOS × Python 3.11/3.13；本次没有实际运行远端 CI |

## 3. 可复现证据

```powershell
python -m pytest -q
python -m ruff check src tests tools --select F,E9
cd frontend
npm run typecheck
npm test
npm run build
npm run e2e
python tools/benchmark_viewer.py --points 1000000
python tools/cuda_writer_smoke.py
```

当前本机结果：

- `91 passed, 2 skipped`
- 前端 3 个 Vitest 通过
- E2E 通过（真实 Chrome，含滚轮缩放/重置）
- 1M：索引 44.4 s，首次查询 3.14 s，库 1.66 GB
- 来源清单示例：7 个来源、4 个逻辑实验

## 4. 阻塞条件（需要用户环境）

1. **真实 62 个 `outputs` 来源不在本机**：无法生成真实 `audit/run_inventory.csv`，也无法解释 53→62；工具为 `tools/export_source_inventory.py`。
2. **无 CUDA/torch 环境**：无法复现 `0xC0000005`，不能宣称修复。
3. **跨平台 CI 未实际运行**：矩阵文件存在，不等于 macOS/Linux 已验证。
4. **多光谱/GeoTIFF 需求**：未提供真实影像与类别色盘/坐标规范，不能猜实现。

## 5. 明确未做

- 自动逻辑归并（有意只允许用户确认）。
- 多光谱波段合成、掩膜色盘、GeoTIFF 坐标。
- TensorBoard histogram/audio。
- 前端动态插件安装。
- 百万点物化桶的持久化版本/增量重建优化（当前按需聚合）。
- 真实 62 来源的身份解释与 53→62 差异报告。

这些必须在获得真实数据/环境后继续，不能用合成数据替代结论。
