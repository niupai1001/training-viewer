# VS Code 扩展使用与打包

源码：[`vscode-extension/`](../vscode-extension/)；已构建包：[`training-viewer-vscode-1.0.0.vsix`](../vscode-extension/training-viewer-vscode-1.0.0.vsix)。

## 1. 安装

```powershell
code --install-extension vscode-extension\training-viewer-vscode-1.0.0.vsix
```

或：VS Code 扩展视图 → 右上角 `…` → “从 VSIX 安装”。

前提：已安装 `training-viewer` 命令。Python 包安装方式见 [README](../README.md)。

## 2. 命令

| 命令 | 行为 |
|---|---|
| `Training Viewer: 打开查看器` | 选择一个/多个训练日志目录；若服务未运行，在终端启动 `training-viewer open ... --no-browser`，健康检查通过后打开浏览器 |
| `Training Viewer: 用当前工作区打开` | 把当前工作区目录作为根目录 |
| `Training Viewer: 添加训练日志目录` | 复用已运行实例，调用 `POST /api/v1/roots` 添加目录 |
| `Training Viewer: 对比勾选的运行` | 侧边栏勾选运行后，打开 `#/compare?runs=...` |
| `Training Viewer: 刷新运行列表` | 重新读取运行树 |

## 3. 侧边栏

活动栏中的 Training Viewer 图标打开“运行与项目”：

- 按项目 → 实验组 → 运行分组；
- 运行显示状态与主要指标；
- 复选框用于“对比勾选的运行”；
- 点击运行在浏览器打开详情；
- 服务未运行时显示“点击启动”。

## 4. 配置

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `trainingViewer.command` | `training-viewer` | 命令名或绝对路径 |
| `trainingViewer.port` | `8765` | 首选端口；被占用时扩展在 8765–8776 范围内探测实际实例 |
| `trainingViewer.dataDirectory` | 空 | 可选应用数据目录 |

## 5. 打包

```powershell
cd vscode-extension
npm install --no-save --no-audit --no-fund @vscode/vsce
npx vsce package --allow-missing-repository
```

`.vscodeignore` 已排除 `node_modules`，VSIX 约 12 KB，只包含 `extension.js`、`package.json`、README、LICENSE 与图标。`@vscode/vsce` 仅用于打包，不进入扩展运行时。

## 6. 设计边界

- 扩展不复制 Web 前端，也不在 Webview 中重建页面；浏览器是主界面。
- 扩展只连接 `http://127.0.0.1`，不支持远程主机。
- 启动命令通过 VS Code 终端执行，用户可以看到错误输出；扩展本身不读取或修改训练日志。
- 退出 VS Code 不会停止训练，也不会自动停止后台 Training Viewer 实例；需要时请在终端停止。
- 若命令安装了但不在 PATH，设置 `trainingViewer.command` 为可执行文件绝对路径。

## 7. 验证

- 打包产物：7 个文件、11.57 KB。
- 语法检查：`node --check vscode-extension/extension.js`。
- 手工：在 VS Code 中安装 VSIX → 打开示例目录 → 浏览器打开 `#/runs` → 勾选两个运行 → 对比页出现两条曲线。
- 当前环境未执行 `code --install-extension`（避免修改用户编辑器）；VSIX 已生成并通过 `vsce` 打包验证。

## 8. 回退

- 卸载扩展：`code --uninstall-extension training-viewer.training-viewer-vscode`。
- 删除 VSIX 与 `vscode-extension/node_modules` 即可清理开发依赖。
- 扩展不保存实验数据；应用数据位于 Training Viewer 数据目录，独立于扩展。
