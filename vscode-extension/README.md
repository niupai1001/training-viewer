# Training Viewer for VS Code

本扩展把本机 Training Viewer 接到 VS Code：

- **Training Viewer: 打开查看器**：选择一个或多个训练日志目录，启动本机服务并在浏览器打开。
- **Training Viewer: 用当前工作区打开**：把当前工作区作为日志根目录。
- **Training Viewer: 添加训练日志目录**：把新目录添加到已运行的实例，不重复启动服务。
- **Training Viewer: 对比勾选的运行**：在侧边栏“运行与项目”中勾选多个运行，跳到实验对比页。
- **Training Viewer: 刷新运行列表**：手动刷新侧边栏。

## 前提

1. 已经安装 `training-viewer` 命令（在 Training Viewer 仓库执行 `pip install -e .`）。
2. VS Code 1.85 或更高版本。
3. 扩展通过终端运行命令，不修改训练日志；退出 VS Code 不会停止训练程序。

## 配置

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `trainingViewer.command` | `training-viewer` | 启动命令或可执行文件路径 |
| `trainingViewer.port` | `8765` | 首选本机端口；被占用时命令行会顺延 |
| `trainingViewer.dataDirectory` | 空 | 可选的应用数据目录 |

## 打包与安装

```powershell
cd vscode-extension
npm install --no-save @vscode/vsce
npx vsce package
code --install-extension training-viewer-vscode-1.0.0.vsix
```

如果 `code` 不在 PATH，可以在 VS Code 的“扩展”视图右上角选择“从 VSIX 安装”。

## 限制

- 扩展不复制 Web 前端，也不使用 Webview 重新实现页面；浏览器仍是主要界面。
- 侧边栏依赖本机后端正在运行。服务未启动时会显示“点击启动”的提示项。
- 扩展只支持 `http://127.0.0.1` 本机地址，不能连接远程服务器。
