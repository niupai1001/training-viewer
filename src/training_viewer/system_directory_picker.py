"""本机系统目录选择对话框。

浏览器的 File System Access API 不能把任意本机绝对路径交给服务端，因此由本机
Python 进程弹出原生目录选择框。该功能只在有桌面会话时可用；无 GUI 时返回清晰错误，
不能假装普通网页输入框等于系统目录选择器。
"""
from __future__ import annotations

import subprocess
import sys

_PICKER_SCRIPT = """
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askdirectory(title="选择训练日志根目录")
print(path or "", flush=True)
root.destroy()
"""


class DirectoryPickerUnavailableError(RuntimeError):
    """当前环境无法显示系统目录选择框。"""


def select_directory_with_system_dialog(timeout_seconds: float = 120.0) -> str | None:
    """弹出本机目录选择框并返回绝对路径；用户取消时返回 None。"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _PICKER_SCRIPT],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DirectoryPickerUnavailableError(
            f"无法打开系统目录选择框：{error}。请改用输入框、CLI 或 VS Code 目录选择。"
        ) from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else "未知错误"
        raise DirectoryPickerUnavailableError(
            f"系统目录选择框不可用：{reason}。请改用输入框、CLI 或 VS Code 目录选择。"
        )
    selected = result.stdout.strip()
    return selected or None
