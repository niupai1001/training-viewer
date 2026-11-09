# Training Viewer Desktop

Windows 本机训练查看器。通过桌面图标打开，添加训练输出目录后自动查看实验与实时指标。

## 新版功能

- 实验、方案与单次训练记录分层组织，不使用种子作为默认标签。
- TVLP 2.0 协议与独立标准库写入器；训练无需连接查看器服务。
- 原生目录选择、扫描预览及新训练接入指引。
- 核心曲线、辅助数字、指标搜索与按实验保存视图。
- 损失默认查看后期细节，支持全程缩略趋势、区间缩放、手动坐标、对数轴及 PNG 导出。
- 关闭应用后训练继续，下次打开自动补读。

## 使用

安装 `TrainingViewerNext-Setup.exe`，从桌面打开 Training Viewer，点击“添加实验”。
新训练可在应用中生成接入代码并保存 `tvlp_writer.py`。已有 TVLP 2.0 日志直接选择目录。

首轮支持 Windows x64、本地目录与 TVLP 2.0。不迁移旧数据，完整历史快照库与多运行对比在后续阶段实现。

## 开发与协议

参见 [TVLP 2.0 与构建说明](docs/TVLP-2.0.md)、[元数据 Schema](docs/tvlp-2.0.schema.json)。
安装依赖：`python -m pip install -r requirements-next.txt`。前端在 `frontend` 中运行
`npm ci` 与 `npx vite build --config vite.next.config.ts`。设置 `PYTHONPATH=src` 后运行 `python desktop_entry.py`。

构建安装包：`tools/build_next.ps1 -Compiler <ISCC.exe>`。使用 PyInstaller、Inno Setup 和 WebView2 离线安装组件。
普通使用者不需要 Python、Node.js 或命令行。

旧版源码与说明保留供参考：[旧版说明](README-legacy.md)。新版独立使用 `%LOCALAPPDATA%/TrainingViewerNext`。
