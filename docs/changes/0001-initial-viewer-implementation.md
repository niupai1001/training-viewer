# 变更记录 0001：初始交付可运行的 Training Viewer V1.0.0

- 变更编号：0001
- 日期：2026-10-31
- 关联需求/问题：按设计规范 V1.1 实现第一版完整的本机训练实验查看器
- 代码提交：工作区初始交付（本仓库尚未建立 Git 提交；回退以文件清单为准）
- 变更类别：功能增加

## 1. 原来是什么

仓库中只有设计文档、TVLP 1.0 的三个 JSON Schema、`tools/validate_log.py` 和一个示例 Run（`examples/segformer_baseline`）。没有后端、前端、数据库、CLI、测试或安装配置，无法运行查看器。

原来的数据流只有“训练程序 → JSONL 文件”，没有任何读取、索引或界面层。

## 2. 现在改变什么

新增一个可安装、可运行的本机应用：

- Python 包 `training_viewer`，命令行 `training-viewer open / serve / validate`。
- FastAPI 应用，绑定 `127.0.0.1`，提供 `/api/v1/*` REST 与 `/api/v1/stream` SSE。
- SQLite 索引：运行、指标点、产物、事件、文件游标、解析问题、备注、保存视图。
- 三类日志来源：标准 TVLP、TensorBoard 事件文件、CSV 指标表。
- React + TypeScript + ECharts 前端：总览、实验管理、运行详情、实验对比、预测结果、诊断。
- 图像并排/叠加对照、表格预览、PNG/SVG/CSV/JSON 导出、超参数差异与可比性警告。
- 日志来源、导出器、前端产物视图三个插件注册表；来源/导出器支持 Python entry point。
- VS Code 扩展源码与 VSIX 包。
- 62 个自动化测试、中文组件文档、术语表、架构与 API 文档。

保留：TVLP 1.0 协议字段未修改；原始示例与 `tools/validate_log.py` 未删除；原有规范文档未改动。

新增示例（均为示例数据）：`examples/segformer_wavelength_encoder`、`examples/csv_training_log`、`examples/tensorboard_scalars`。

## 3. 为什么这样改

设计规范要求第一版具备完整闭环：日志读取、实时曲线、实验比较、结果浏览、格式适配、插件化、CLI/VS Code 入口和文档。原仓库没有实现层，必须在保持协议与安全边界不变的前提下建立可运行系统，而不是只输出方案。

未采用的替代方案：

- 直接 fork MLflow/Aim Web UI：许可证允许部分复用，但其数据模型和存储与 TVLP 不一致，导入/图像视图改造成本高于独立实现；因此只参考产品思想。
- 用纯内存读取、每次全量重算：无法满足断点续训、日志追加与重启后的幂等要求。
- 要求训练程序安装 SDK：违反“训练程序只输出文件、无需联网”的边界。

## 4. 影响范围

- **代码**：新增 `src/training_viewer/`、`frontend/`、`tests/`、`vscode-extension/`；更新 `pyproject.toml`。
- **协议**：TVLP 字段和版本保持不变；新增的是消费者实现。安装包内增加 `schemas/` 副本，并有测试防止与仓库版本漂移。
- **数据**：新增应用数据目录中的 SQLite 索引、`instance.json`、备注与保存视图。原始日志目录只读。
- **界面**：全新 Web UI；界面中文，代码标识英文。
- **兼容性**：新旧日志格式不变；已有示例继续可用。

## 5. 验证结果

- `pytest -q`：62 passed，2 skipped（Windows 环境不允许创建符号链接的两个安全测试）。
- `npm run typecheck`：通过。
- `npm run build`：通过，生成 `src/training_viewer/web/`。
- `training-viewer validate examples/segformer_baseline`：通过。
- 启动服务后通过 HTTP 验证：运行列表、指标曲线、两运行对比、Best/Last、超参数差异、产物内容、表格预览、CSV/JSON 导出、Host/Origin 拒绝。
- Chrome 无头（DevTools Protocol）加载总览、运行详情、实验对比、预测结果、诊断页面：无 `Runtime.exceptionThrown`，页面文本与截图符合预期。
- 运行环境：Windows 11，Python 3.13.15，Node 25.3.0，TensorBoard 2.21.0（可选依赖）。

## 6. 回退方式

- 代码：移除 `src/`、`frontend/`、`tests/`、`vscode-extension/`，恢复 `pyproject.toml` 到变更前状态；原有 `schemas/`、`examples/`、`tools/`、规范文档未被删除。
- 数据：删除应用数据目录中的 `index.sqlite3` 与 `instance.json` 可清除索引与界面数据；原始训练日志不受影响。
- 若已构建 VSIX/前端资源：删除 `src/training_viewer/web/` 与 VSIX 即可，不影响后端 API（页面会提示前端未构建）。

## 7. 文档同步情况

- [x] 组件说明（`docs/components/`，含索引）
- [x] 架构图与数据流（`docs/architecture.md`）
- [x] 术语表（`docs/glossary.md`）
- [x] 使用说明（`README.md`、`docs/log-sources.md`、`docs/development.md`）
- [x] 相关测试（`tests/`）
- [x] API 文档（`docs/api.md`）
- [x] 第三方许可证（`docs/third-party-licenses.md`、`NOTICE`）
