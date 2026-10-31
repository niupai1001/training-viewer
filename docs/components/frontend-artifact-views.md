# 组件说明：实验产物视图插件（artifactViews）

## 一句话说明

按产物类型选择预览插件（图像、表格、HTML、模型、通用文件）；只负责展示和下载入口，不直接解析原始日志，也不执行不可信内容。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 实验产物视图插件 |
| 代码名 | `artifactViews`、`getArtifactViewPlugin`、`registerArtifactViewPlugin` |
| 源文件 | `frontend/src/view_plugins/artifactViews.tsx` |
| 所属模块 | 前端插件 |
| 上游 | 运行详情产物页、预测结果“全部产物”；下游 | 图像灯箱、表格预览、下载链接 |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

不同任务的结果类型不同：分割看图像、分类看混淆矩阵、检索看表格、报告看 HTML。把每种类型的展示放进独立插件，新增类型不需要修改产物列表页；同时 HTML/模型等危险内容有统一的安全处理。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | `artifact` | `Artifact` | 路径、类型、角色、存在性、内容 URL |
| 输入 | `onOpenImage` | 回调 | 打开图像灯箱 |
| 输入 | `onPreviewTable` | 回调 | 打开表格预览对话框 |
| 输出 | React 节点 | 组件 | 图像卡片、文件卡片、预览按钮、下载链接 |

## 插件注册表

| 插件 id | 支持条件 | 行为 |
|---|---|---|
| `artifact.image` | `artifact_type` 为 `image` 或 `figure`，且扩展名是常见图像 | 缩略图；点击打开大图；缺失时占位 |
| `artifact.table` | `artifact_type == "table"` | 表格预览按钮 + 下载 |
| `artifact.html` | `artifact_type == "html"` | 提示不作为可执行页面，提供下载 |
| `artifact.model` | `artifact_type == "model"` | 只显示文件大小与下载；说明不反序列化 |
| `artifact.generic-file` | 兜底 | CSV/TSV/JSON 提供预览，其它提供下载 |

`registerArtifactViewPlugin()` 可替换同 id 插件或插入新插件；新增插件需要重新构建前端。

## 主要处理流程

1. `ArtifactGallery` 按标签筛选产物。
2. 对每个产物调用 `getArtifactViewPlugin`，命中第一个 `supports()` 为 true 的插件。
3. 插件渲染卡片；图像点击交给灯箱，表格点击交给对话框。
4. 文件缺失时使用 `exists_on_disk` 或图片 `onError` 显示占位，不伪造内容。

## 配置与依赖

无配置项。依赖 React、`Artifact` 类型、`TablePreviewDialog`。没有第三方预览库。

## 和旧实现相比改变了什么

初始实现。V1 明确：

- HTML 和 SVG 不在查看器内执行脚本；
- 模型文件只显示元数据，不调用任何反序列化；
- 图像缺失时不显示破图或缓存占位。

## 如何验证

- 运行详情“实验产物”页：示例中的图像、表格卡片均可打开/下载。
- 表格：`confusion_matrix.csv` 显示 5×6 表格。
- `npm run typecheck`。
- 安全测试：HTML 产物接口以 `text/plain` 附件返回（`tests/test_api.py::test_html_artifact_is_not_served_as_executable_html`）。

## 已知限制与回退

- 没有音频、视频、3D 预览；这些类型走通用文件下载。
- 表格预览最多 200 行/40 列。
- 第三方视图插件在构建时打包，不能热加载。
- 回退：移除插件注册即可恢复通用文件卡片。

## 名称解释

- 视图插件（View Plugin）：只读查询 API、负责一种显示的组件。
- 灯箱（lightbox）：覆盖页面的图像大图查看层。
- 反序列化：把模型文件加载为可执行对象；查看器不做。
