# 组件说明索引

每个重要组件都有独立说明，包含中文名、代码名、职责边界、输入输出、处理流程、配置、异常、测试与已知限制。组件说明与代码同步维护；发现不一致时以代码和测试为事实来源，并应立即修正文档。

| 中文功能名 | 代码名 | 位置 | 一句话职责 |
|---|---|---|---|
| 标准训练日志增量读取器 | `StandardTrainingLogReader` | `log_readers/standard_training_log_reader.py` | 只把 JSONL 新增的完整行转换为指标/事件记录 |
| 运行元数据读取器 | `RunMetadataReader` | `run_metadata.py` | 读取并校验 `run.json`，不写回 |
| CSV 指标日志读取器 | `CsvMetricLogReader` | `log_readers/csv_metric_reader.py` | 按显式映射或数值列读取 CSV 指标 |
| TensorBoard 事件读取器 | `TensorBoardEventReader` | `log_readers/tensorboard_event_reader.py` | 用官方实现读取事件文件中的标量 |
| 日志来源适配器 | `StandardTvlpSourceAdapter` / `TensorBoardSourceAdapter` / `CsvSourceAdapter` / `GenericLogFileSourceAdapter` | `source_adapters/` | 判断目录属于哪种来源并给出读取器 |
| 本机系统目录选择器 | `select_directory_with_system_dialog` | `system_directory_picker.py` | 在桌面环境弹出原生目录框，无 GUI 时明确报错 |
| 运行目录扫描器 | `RunDirectoryScanner` | `discovery/run_directory_scanner.py` | 从根目录递归发现 Run，不跟随符号链接 |
| 训练指标索引器 | `TrainingMetricIndexer` | `indexing/training_metric_indexer.py` | 增量写入 SQLite、维护游标、去重、推导状态 |
| 索引查询 | `IndexQueries` | `indexing/index_queries.py` | 提供运行、曲线、指标目录、对比、产物、诊断查询 |
| 指标语义解析器 | `resolve_metric_semantics` | `metrics/metric_semantics.py` | 声明/别名/未知分流，不猜测科学含义 |
| 运行监控摘要 | `get_monitoring_summary` | `indexing/index_queries.py` | KPI 与生命周期/日志跨度统一摘要 |
| 日志更新监听器 | `LogUpdateWatcher` | `watch/log_update_watcher.py` | 轮询 + 文件事件触发同步 |
| 查看器应用服务 | `TrainingViewerService` | `service.py` | 协调扫描/索引/状态/SSE/根目录 |
| 路径安全守卫 | `path_guard` | `security/path_guard.py` | 拒绝绝对路径、穿越和越界符号链接 |
| 指标导出器 | `MetricCsvExporter` / `MetricJsonExporter` | `export/metric_exporters.py` | 把对比结果导出为带溯源的 CSV/JSON |
| 用户状态存储 | `UserStateStore` | `user_state.py` | 备注、收藏、保存视图与可重建索引分库 |
| 逻辑实验解析器 | `LogicalRunOverrideStore` | `identity/logical_runs.py` | 用户确认的文件组归并为逻辑实验，sidecar 可撤销 |
| 结果文件发现器 | `discover_result_files` | `results/discovery.py` | 事件之外发现预测/标签/输入图片候选，明确未确认 |
| 训练日志写入器 | `TrainingRunWriter` | `writer.py` | 训练程序侧生成合法的 TVLP Run、指标、事件与产物引用；默认无后台心跳线程 |
| 训练 Agent 接入命令 | `attach` / `status` / `stop` | `cli.py` | 后台启动/复用查看器并挂载日志目录，返回 URL |
| 协议校验器 | `validate_run_directory` | `log_validation.py` | 按 Schema 和路径规则校验一个 Run 目录 |
| 指标曲线组件 | `MetricChart` | `frontend/src/components/MetricChart.tsx` | 绘制、缩放、平滑与导出曲线；空数据也保留容器 |
| 日志根目录面板 | `RootDirectoriesPanel` | `frontend/src/components/RootDirectoriesPanel.tsx` | 输入/系统选择/移除/重新扫描根目录 |
| 逻辑实验映射面板 | `LogicalRunMappingPanel` | `frontend/src/components/LogicalRunMappingPanel.tsx` | 用户确认来源文件归并，可撤销 |
| 训练工作区 | `TrainingWorkspacePage` | `frontend/src/pages/TrainingWorkspacePage.tsx` | 唯一左栏、右侧概览/多选对比、高级抽屉 |
| 训练概览 | `TrainingOverview` | `frontend/src/components/TrainingOverview.tsx` | 六项摘要、Loss/验证核心图、自定义图表 |
| 指标浏览器 | `MetricBrowserDrawer` | `frontend/src/components/MetricBrowserDrawer.tsx` | 搜索/分组/分页选择指标，连续/单点分流 |
| 单点评估表 | `MetricEvaluationTable` | `frontend/src/components/MetricEvaluationTable.tsx` | 单次结果表格 |
| 来源清单面板 | `SourceInventoryPanel` | `frontend/src/components/SourceInventoryPanel.tsx` | 原始文件 → 逻辑实验的可审计清单 |
| 结果候选面板 | `ResultCandidatePanel` | `frontend/src/components/ResultCandidatePanel.tsx` | 展示未确认的路径发现图片 |
| 最新产物预览 | `LatestArtifactPreview` | `frontend/src/components/LatestArtifactPreview.tsx` | 运行页顶部展示最新预测样本 |
| 实验对比页面 | `WorkspaceComparison`（工作区内） | `frontend/src/pages/TrainingWorkspacePage.tsx` | 多运行叠加、Best/Last、超参数差异 |
| 预测结果对照器 | `PredictionComparisonViewer` | `frontend/src/components/PredictionComparisonViewer.tsx` | 按样本/Epoch 并排或叠加图像 |
| 实验产物视图插件 | `artifactViews` | `frontend/src/view_plugins/artifactViews.tsx` | 按产物类型选择预览组件 |
| 页面组合 | 各 Page 组件 | `frontend/src/pages/` | 总览、实验管理、运行详情、结果、诊断 |

## 文档清单

- [标准训练日志增量读取器](standard-training-log-reader.md)
- [运行元数据读取器](run-metadata-reader.md)
- [CSV 指标日志读取器](csv-metric-log-reader.md)
- [TensorBoard 事件读取器](tensorboard-event-reader.md)
- [日志来源适配器](source-adapters.md)
- [通用日志文件来源](generic-log-file-source.md)
- [本机系统目录选择器](system-directory-picker.md)
- [运行目录扫描器](run-directory-scanner.md)
- [训练指标索引器](training-metric-indexer.md)
- [索引查询](index-queries.md)
- [指标目录与语义分流](metric-catalog.md)
- [运行监控摘要](run-monitoring-summary.md)
- [指标浏览器](metric-browser.md)
- [训练概览](training-overview.md)
- [日志更新监听器](log-update-watcher.md)
- [查看器应用服务](training-viewer-service.md)
- [路径安全守卫](path-guard.md)
- [指标导出器](metric-exporters.md)
- [训练日志写入器](training-run-writer.md)
- [训练 Agent 接入命令](cli-agent-attach.md)
- [协议校验器](log-validator.md)
- [指标曲线组件](frontend-metric-chart.md)
- [日志根目录面板](root-directories-panel.md)
- [最新产物预览](latest-artifact-preview.md)
- [用户状态存储](user-state-store.md)
- [逻辑实验解析器](logical-run-resolver.md)
- [逻辑实验映射面板](logical-run-mapping-panel.md)
- [结果文件发现](result-file-discovery.md)
- [训练工作区](training-workspace.md)
- [来源清单面板](source-inventory-panel.md)
- [结果候选面板](result-candidate-panel.md)
- [实验对比页面](frontend-experiment-comparison.md)
- [预测结果对照器](frontend-prediction-comparison.md)
- [实验产物视图插件](frontend-artifact-views.md)
- [前端页面组合](frontend-pages.md)
