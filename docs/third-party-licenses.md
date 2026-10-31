# 第三方依赖与许可证

本项目遵循“优先复用成熟组件，但必须核查许可证”的原则。**没有复制 MLflow、Aim、TensorBoard Web UI 或其它项目的源码**；以下均为通过包管理器安装的依赖，或通过其公开 API 调用。

## 1. 运行时依赖

| 依赖 | 版本范围（声明） | 许可证 | 用途 | 分发方式 |
|---|---|---|---|---|
| FastAPI | `>=0.115` | MIT | REST API | pip |
| Uvicorn | `>=0.30` | BSD 3-Clause | ASGI 服务器 | pip |
| Pydantic | 随 FastAPI | MIT | 请求体校验 | pip |
| Starlette | 随 FastAPI | BSD 3-Clause | Web 框架底层 | pip |
| watchdog | `>=4.0` | Apache-2.0 | 文件事件提前唤醒 | pip |
| jsonschema | `>=4.20` | MIT | TVLP Schema 校验 | pip |
| TensorBoard | `>=2.15`（可选 extra） | Apache-2.0 | 事件文件标量读取 | pip，可选 |
| MLflow（spike） | 3.17.2，仅 `tools/mlflow_spike.py` | Apache-2.0 | ADR 对照原型；不进入运行时依赖 | pip，可选/隔离 |
| React | `^19.3.1` | MIT | 前端界面 | npm，构建时打包 |
| Apache ECharts | `^6.1.0` | Apache-2.0 | 曲线与导出 | npm，构建时打包进 `web/` |
| Vite | `^7.3.7` | MIT | 前端构建 | npm，开发依赖 |
| TypeScript | `~5.9.3` | Apache-2.0 | 类型检查 | npm，开发依赖 |
| @vitejs/plugin-react | `^5.2.0` | MIT | React 构建插件 | npm，开发依赖 |

## 2. 开发与测试依赖

| 依赖 | 许可证 | 用途 |
|---|---|---|
| pytest | MIT | 后端测试 |
| httpx | BSD 3-Clause | FastAPI TestClient 传输 |
| Ruff | MIT | Python 静态检查 |
| Vitest | MIT | 前端组件测试 |
| @testing-library/react / jest-dom | MIT | React 组件生命周期测试 |
| jsdom | MIT | 前端测试 DOM 环境 |
| playwright-core | Apache-2.0 | 真实浏览器 E2E（使用本机 Chrome，不下载浏览器） |
| @vscode/vsce | MIT | VSIX 打包（不进入 VSIX） |

## 3. Apache-2.0 通知义务

Apache ECharts 与 TensorBoard 使用 Apache License 2.0。项目：

- 在 [`LICENSE`](../LICENSE) 中提供 Apache License 2.0 全文；
- 在 [`NOTICE`](../NOTICE) 中列明包含 Apache ECharts 与可选 TensorBoard；
- 不修改 ECharts/TensorBoard 源码；
- 通过公开 API 使用 TensorBoard，不复制其源码；
- 前端构建产物包含 ECharts 代码，随项目一起按 Apache-2.0 分发。

发布二进制或安装包时，应同时保留 `LICENSE`、`NOTICE` 以及依赖包自带的许可证文件。

## 4. 设计参考而非代码复用

以下项目仅用于研究交互与产品设计，没有复制其服务端代码：

- MLflow（Apache-2.0）：Run/Metric/Artifact 组织与实验比较的产品思路。
- Aim（Apache-2.0）：探索式曲线比较与标签交互。
- DVCLive（Apache-2.0）：本地文件记录指标的组织方式。
- ClearML Server（SSPL）：只研究实验管理交互，未复制代码，也未引入 SSPL 依赖。

## 5. 示例数据声明

`examples/` 中的指标数值、运行名称和图像均为示例，不代表真实训练实验或真实数据集。图片来自设计资料附带的示例文件，不是第三方受版权保护的训练数据。

## 6. 许可证核查记录

| 日期 | 检查内容 | 结论 |
|---|---|---|
| 2026-10-31 | pip 依赖、npm 依赖、TensorBoard/MLflow/Aim/DVCLive/ClearML 许可证与传递依赖 | 未引入 SSPL/AGPL 代码；运行时依赖均为 MIT/BSD/Apache-2.0；无源码复制；Apache-2.0 通知已提供 |

修改依赖时必须在变更记录中更新本表，并重新核查新增依赖的许可证与传递依赖。
