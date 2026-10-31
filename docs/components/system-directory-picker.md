# 本机系统目录选择器

- 中文名：本机系统目录选择框
- 代码名：`select_directory_with_system_dialog` / `DirectoryPickerUnavailableError`
- 位置：`src/training_viewer/system_directory_picker.py`
- 接口：`POST /api/v1/roots/select`

## 职责

浏览器不能把任意本机绝对路径交给服务端，因此由本机 Python 子进程调用 `tkinter.filedialog.askdirectory` 弹出原生目录选择框，返回用户选择的路径。

## 输入 / 输出

- 输入：无；可配置超时（默认 120 秒）。
- 输出：选中的绝对路径；用户取消返回 `None`，接口返回 400。
- 无桌面会话 / Tk 不可用：抛 `DirectoryPickerUnavailableError`，接口返回 501，并提示使用输入框、CLI 或 VS Code。

## 安全与限制

- 只在本机 `127.0.0.1` 服务中提供；不接受客户端传入的任意命令。
- 子进程使用固定脚本，不拼接用户输入。
- 无 GUI 的服务器/CI 不应调用；前端按钮失败后会显示可执行的替代方式，不假装网页输入框就是系统选择器。

## 测试

`tests/test_api.py::test_system_directory_picker_returns_selected_path` 用 monkeypatch 替换对话框，验证 200/400 分支；真实 GUI 未在 CI 中自动化。
