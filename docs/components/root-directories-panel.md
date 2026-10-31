# 日志根目录面板

- 中文名：日志根目录面板
- 代码名：`RootDirectoriesPanel`
- 位置：`frontend/src/components/RootDirectoriesPanel.tsx`
- 使用页面：监控首页空状态、设置与诊断页、首页高级设置

## 职责

管理本机日志根目录：粘贴路径、打开系统目录选择框、添加、移除、重新扫描，并显示当前根目录列表与错误。

## 交互

- “添加目录”：调用 `POST /roots`，成功后刷新列表。
- “选择本机目录”：调用 `POST /roots/select`；501 时提示改用输入框、CLI 或 VS Code。
- “移除”：二次确认，只删除索引，不删除原始日志。
- “重新扫描”：`POST /rescan`，全量发现。

## 限制

- 根目录持久化在 SQLite；`training-viewer open` 不带参数时恢复上次工作区。
- “选择本机目录”需要桌面会话；无 GUI 时不可用。
- 不提供浏览器 File System Access 的伪目录选择；路径以服务端本机为准。

## 测试

`tests/test_api.py` 覆盖添加/移除根目录和目录选择接口；`npm run e2e` 覆盖首页/实验库可打开。
