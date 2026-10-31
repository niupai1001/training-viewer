# 变更记录 0002：首轮真实文件与界面验证修复

- 变更编号：0002
- 日期：2026-10-31
- 关联需求/问题：在真实示例日志、自动化测试与无头浏览器验证中发现的误报、崩溃和显示问题
- 代码提交：工作区修复（未建立 Git 提交）
- 变更类别：行为修改 / 修复

## 1. 原来是什么

初始交付版本（变更 0001）在以下位置存在具体缺陷：

1. **首次读取误报截断**：`TrainingMetricIndexer` 对 `ReadResult.reset` 一律记录“文件被截断/替换”，但首次读取没有旧游标，`reset` 必然为 true。示例运行首次导入即产生两条假警告。
2. **半行提示永久残留**：文件末尾半行补齐后，旧的“等待补齐”问题记录不会被删除，诊断页长期显示过期警告。
3. **坏 run.json 中断同步**：`RunMetadataReader` 内部抛 `ValueError`，扫描器只捕获 `InvalidRunDirectoryError`，一个坏元数据目录会让整次 `synchronize()` 失败。
4. **跨任务自动排名**：对比查询只比较单位、数据集和指标定义；分类任务的 `train/loss` 与分割任务的 `train/loss` 会被标为“可比较并排名”。
5. **地址栏指标被覆盖**：对比页在指标列表尚未加载完成时会把用户/保存视图指定的 `series` 重置为默认指标。
6. **CLI 中文输出崩溃**：Windows 重定向/管道场景下 `print` 使用 cp1252，输出中文时抛 `UnicodeEncodeError`，被 `except ValueError` 误判为“添加目录失败”。
7. **图表底部重叠**：横轴名称与 dataZoom 滑动条重叠。
8. **运行列表缺少定义提示**：主要指标没有携带 `definition` 文本，悬停提示为空。
9. **VSIX 含 48 MB node_modules**：打包时未排除开发依赖。
10. **运行选择器名称被截断**：窄侧边栏中只显示“SegFormer ...”，无法区分运行。

## 2. 现在改变什么

- 只在**已有游标**且检测到截断/替换时记录警告；首次读取不再误报。
- 读取器补齐半行后，索引器删除该文件的“尚未写完”问题；诊断不再长期残留。
- `RunMetadataReader.read()` 把 `ValueError` 包装为 `InvalidRunDirectoryError`；扫描器记录目录问题并继续其它运行。
- 对比查询收集任务类型；任务不一致时新增 `task_mismatch` 警告，并将 `ranking_allowed` 置为 false。
- Origin 校验改为解析主机名后精确比对，修复“`http://127.0.0.1.evil.example` 因前缀匹配被放行”的问题。
- 对比页增加 `explicitSeriesRef`：地址栏指定 `series` 时不做自动默认替换；运行选择变化仍可手动选择指标。
- CLI 启动时把 stdout/stderr 重新配置为 UTF-8（`errors="replace"`），重定向场景不再崩溃。
- 图表底部网格从 54 增至 86，横轴名称下移，滑动条上移。
- 主要指标增加 `definition` 字段，运行列表与总览显示定义提示。
- 增加 `.vscodeignore`，VSIX 只包含 `extension.js`、`package.json`、README、LICENSE、icon。
- 运行选择器改为可换行、隐藏冗余指标值，名称完整显示。

保留：TVLP 1.0 协议不变、数据库 schema 不变、原始日志只读、安全边界不变。

## 3. 为什么这样改

以上问题均来自实际运行与测试：

- 首次导入假警告会误导用户以为日志被破坏；
- 坏元数据导致整次同步失败，违反“一个坏目录不影响其它实验”；
- 跨任务排名会产生错误的科学结论；
- 地址栏覆盖破坏保存视图的可复现性；
- CLI 编码问题使 Windows 用户无法启动；
- 图表重叠与截断影响可读性。

未采用的替代方案：

- 对首次读取的 `reset` 直接不删除旧数据：会掩盖真实的文件替换；因此只在无游标时跳过警告，仍执行幂等删除。
- 用前端判断任务一致性：任务字段属于后端查询与可比性规则，应在查询层统一实现。
- 放弃 CSV/TensorBoard 支持以简化：违反 V1 格式适配目标。

## 4. 影响范围

- `log_readers/standard_training_log_reader.py`：无协议变化。
- `indexing/training_metric_indexer.py`：首次读取/半行问题处理。
- `run_metadata.py`：异常类型包装。
- `indexing/index_queries.py`：主指标定义、任务可比性。
- `api/app.py`：Origin 校验改为精确主机名比较。
- `cli.py`：控制台编码。
- 前端：对比页、图表、运行选择器、运行列表提示。
- `vscode-extension/.vscodeignore`：打包内容。
- 数据：无需迁移；已有索引继续可用。任务可比性在查询时计算，不需要重建。

## 5. 验证结果

- `pytest -q`：62 passed，2 skipped。
  - 新增/更新覆盖：`test_append_and_trailing_partial_line`、`test_invalid_run_json_becomes_directory_diagnostic`、`test_compare_is_not_ranked_when_dataset_or_unit_differs`、`test_status_completed_and_running_from_heartbeat`、`test_host_and_origin_checks_reject_foreign_pages`（含前缀伪装域名）。
- Chrome 无头验证：对比页地址栏 `series=val/miou` 保持，两个 SegFormer 运行显示 0.52 / 0.61；页面无异常。
- CLI：后台管道启动服务成功，中文正常输出。
- 重打包 VSIX：7 个文件、11.57 KB（排除 node_modules）。
- 运行环境与数据版本：与变更 0001 相同；示例数据未修改。

## 6. 回退方式

按文件回退：

- 读取器/索引器：恢复首次读取警告与半行提示逻辑，删除“删除半行问题”的 SQL。
- 元数据：移除 `except ValueError` 包装。
- 查询层：移除 `task_mismatch` 与 `tasks <= 1` 条件。
- API：恢复 Origin 前缀匹配（不推荐；会重新引入伪装域名风险）。
- CLI：移除 `_configure_console_encoding()` 调用。
- 前端：回退对比页 `explicitSeriesRef`、图表 `grid.bottom`、选择器 CSS。
- VSIX：删除 `.vscodeignore` 后重新打包（会重新包含开发依赖）。

回退不涉及数据迁移；原始日志不受影响。若回退导致索引语义变化，删除 `index.sqlite3` 可重建。

## 7. 文档同步情况

- [x] 组件说明：读取器、索引器、查询、CLI/图表相关章节已更新
- [x] 架构图与数据流：任务可比性与半行提示说明已更新
- [x] 术语表：无需新增术语
- [x] 使用说明：README 测试结果与 VSIX 大小已更新
- [x] 相关测试：新增/调整上述用例
