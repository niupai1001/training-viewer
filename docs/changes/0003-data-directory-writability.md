# 变更记录 0003：应用数据目录不可写时给出明确错误

- 变更编号：0003
- 日期：2026-10-31
- 关联需求/问题：最终安装验证时，默认应用数据目录存在但当前用户进程不可写，CLI 直接抛出 `PermissionError` / `sqlite3.OperationalError` 堆栈
- 代码提交：工作区修复（未建立 Git 提交）
- 变更类别：行为修改 / 修复

## 1. 原来是什么

`ApplicationPaths.resolve()` 只执行 `mkdir(parents=True, exist_ok=True)`。如果目录已经存在但没有写权限，或操作系统在创建数据库文件时拒绝写入：

- `mkdir` 可能成功，随后 `sqlite3.connect` 报 `unable to open database file`；
- CLI 没有捕获这些异常，用户只看到 Python 堆栈，不知道可以用 `--data-dir` 解决。

在受限的测试环境中，`%LOCALAPPDATA%\TrainingViewer` 由另一个进程创建但对 Python 进程不可写，触发了该问题。

## 2. 现在改变什么

- `ApplicationPaths.resolve()` 增加写权限探测：创建带进程号的临时探测文件、写入、删除。
- 创建失败或探测失败时抛出 `ApplicationDataDirectoryError`，消息包含目录路径、系统错误和两种解决方式（`--data-dir`、`TRAINING_VIEWER_DATA_DIR`）。
- CLI `main()` 捕获该异常，输出中文提示并以退出码 2 结束，不打印 Python 堆栈。
- 探测文件使用进程号命名，避免并发启动时互相删除。

保留：默认数据目录规则、数据库 schema、所有正常可写环境的行为。

## 3. 为什么这样改

应用启动失败时，用户需要知道“哪个目录不可写、如何改”，而不是阅读 sqlite3 内部错误。该检查也让不可写问题在启动早期暴露，而不是在第一次同步时才失败。

未采用的替代方案：

- 回退到临时目录：会隐藏配置问题，并让索引在重启后丢失；
- 自动改用工作区目录：应用不应猜测用户的数据位置；
- 只捕获 `PermissionError`：`sqlite3.OperationalError` 仍会漏出。

## 4. 影响范围

- `src/training_viewer/application_paths.py`：新增异常与探测。
- `src/training_viewer/cli.py`：异常捕获与退出码。
- 数据/协议：无变化；正常目录不会留下探测文件。
- 测试：所有测试使用显式临时数据目录，行为不变。

## 5. 验证结果

- `pytest -q`：62 passed，2 skipped。
- `ruff check src tests --select F,E9`：通过。
- 手工：在不指定 `--data-dir` 且目录不可写的环境运行 CLI，输出中文错误并退出 2（不再是堆栈）。
- 正常目录：`training-viewer open examples --data-dir <可写目录>` 正常启动并服务。

## 6. 回退方式

- 移除 `_ensure_writable_directory` 与 `ApplicationDataDirectoryError`，恢复直接 `mkdir`；
- 移除 CLI 的异常捕获。
- 无数据迁移；索引数据库不受影响。

## 7. 文档同步情况

- [x] 组件说明：应用路径行为属于服务启动前置条件，已在开发文档排障表补充
- [x] 架构图与数据流：无变化
- [x] 术语表：无需新增
- [x] 使用说明：README/开发文档补充 `--data-dir` 排障
- [x] 相关测试：现有 CLI/服务测试覆盖正常路径；不可写路径通过手工验证
