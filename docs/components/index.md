# 组件说明索引

每个重要组件都有独立说明，包含中文名、代码名、职责边界、输入输出、处理流程、配置、异常、测试与已知限制。组件说明与代码同步维护；发现不一致时以代码和测试为事实来源，并应立即修正文档。

| 中文功能名 | 代码名 | 位置 | 一句话职责 |
|---|---|---|---|
| 标准训练日志增量读取器 | `StandardTrainingLogReader` | `log_readers/standard_training_log_reader.py` | 只把 JSONL 新增的完整行转换为指标/事件记录 |
| 运行元数据读取器 | `RunMetadataReader` | `run_metadata.py` | 读取并校验 `run.json`，不写回 |
| CSV 指标日志读取器 | `CsvMetricLogReader` | `log_readers/csv_metric_reader.py` | 按显式映射或数值列读取 CSV 指标 |
| TensorBoard 事件读取器 | `TensorBoardEventReader` | `log_readers/tensorboard_event_reader.py` | 用官方实现读取事件文件中的标量 |
| 日志来源适配器 | `StandardTvlpSourceAdapter` / `TensorBoardSourceAdapter` / `CsvSourceAdapter` | `source_adapters/builtin_adapters.py` | 判断目录属于哪种来源并给出读取器 |
| 运行目录扫描器 | `RunDirectoryScanner` | `discovery/run_directory_scanner.py` | 从根目录递归发现 Run，不跟随符号链接 |
| 训练指标索引器 | `TrainingMetricIndexer` | `indexing/training_metric_indexer.py` | 增量写入 SQLite、维护游标、去重、推导状态 |
| 索引查询 | `IndexQueries` | `indexing/index_queries.py` | 提供运行、曲线、对比、产物、诊断查询 |
| 日志更新监听器 | `LogUpdateWatcher` | `watch/log_update_watcher.py` | 轮询 + 文件事件触发同步 |
| 查看器应用服务 | `TrainingViewerService` | `service.py` | 协调扫描/索引/状态/SSE/根目录 |
| 路径安全守卫 | `path_guard` | `security/path_guard.py` | 拒绝绝对路径、穿越和越界符号链接 |
| 指标导出器 | `MetricCsvExporter` / `MetricJsonExporter` | `export/metric_exporters.py` | 把对比结果导出为带溯源的 CSV/JSON |
| 训练日志写入器 | `TrainingRunWriter` | `writer.py` | 训练程序侧生成合法的 TVLP Run、指标、事件与产物引用 |
| 训练 Agent 接入命令 | `attach` / `status` / `stop` | `cli.py` | 后台启动/复用查看器并挂载日志目录，返回 URL |
| 协议校验器 | `validate_run_directory` | `log_validation.py` | 按 Schema 和路径规则校验一个 Run 目录 |
| 指标曲线组件 | `MetricChart` | `frontend/src/components/MetricChart.tsx` | 绘制、缩放、平滑与导出曲线 |
| 实验对比页面 | `ComparisonPage` | `frontend/src/pages/ComparisonPage.tsx` | 多运行叠加、Best/Last、超参数差异 |
| 预测结果对照器 | `PredictionComparisonViewer` | `frontend/src/components/PredictionComparisonViewer.tsx` | 按样本/Epoch 并排或叠加图像 |
| 实验产物视图插件 | `artifactViews` | `frontend/src/view_plugins/artifactViews.tsx` | 按产物类型选择预览组件 |
| 页面组合 | 各 Page 组件 | `frontend/src/pages/` | 总览、实验管理、运行详情、结果、诊断 |

## 文档清单

- [标准训练日志增量读取器](standard-training-log-reader.md)
- [运行元数据读取器](run-metadata-reader.md)
- [CSV 指标日志读取器](csv-metric-log-reader.md)
- [TensorBoard 事件读取器](tensorboard-event-reader.md)
- [日志来源适配器](source-adapters.md)
- [运行目录扫描器](run-directory-scanner.md)
- [训练指标索引器](training-metric-indexer.md)
- [索引查询](index-queries.md)
- [日志更新监听器](log-update-watcher.md)
- [查看器应用服务](training-viewer-service.md)
- [路径安全守卫](path-guard.md)
- [指标导出器](metric-exporters.md)
- [训练日志写入器](training-run-writer.md)
- [训练 Agent 接入命令](cli-agent-attach.md)
- [协议校验器](log-validator.md)
- [指标曲线组件](frontend-metric-chart.md)
- [实验对比页面](frontend-experiment-comparison.md)
- [预测结果对照器](frontend-prediction-comparison.md)
- [实验产物视图插件](frontend-artifact-views.md)
- [前端页面组合](frontend-pages.md)
