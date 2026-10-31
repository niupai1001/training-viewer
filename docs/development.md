# 开发环境、构建与调试

## 1. 工具链

| 工具 | 版本要求 | 用途 |
|---|---|---|
| Python | 3.11+ | 后端、CLI、测试 |
| Node.js | 20+ | 构建前端、打包 VSIX |
| npm | 随 Node | 前端依赖 |
| Git | 任意 | 版本管理（可选） |

可选：`uv`、`pipx`、`ruff`。

## 2. 后端开发环境

```powershell
cd training_viewer_v1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

`dev` extra 包含 pytest 与 httpx。TensorBoard 适配器需要额外安装：

```powershell
python -m pip install ".[tensorboard]"
```

运行测试：

```powershell
python -m pytest -q
ruff check src tests --select F,E9
```

## 3. 前端开发

```powershell
cd frontend
npm ci
npm run typecheck
npm run test
npm run dev
```

`npm run test` 是 Vitest + Testing Library 组件测试；`npm run e2e` 用 Playwright Core 调本机 Chrome 对已启动的查看器做真实页面冒烟（默认 `http://127.0.0.1:8799/`，可用 `TRAINING_VIEWER_URL` 覆盖；截图输出到 `.devtools/e2e`）。

性能基准（不进入普通测试）：

```powershell
python tools/benchmark_viewer.py --points 100000
python tools/benchmark_viewer.py --points 1000000
python tools/benchmark_tensorboard.py
python tools/cuda_writer_smoke.py
python tools/export_source_inventory.py --data-dir <数据目录> --root D:/outputs --output audit/run_inventory.csv
```

CUDA 矩阵在无 torch/CUDA 时返回 `skipped`；MLflow spike 需要可选 `mlflow-skinny`，只用于 ADR 对照，不进入生产依赖。结果与限制见 [`docs/performance.md`](performance.md)。

`.github/workflows/ci.yml` 在 Ubuntu/Windows/macOS × Python 3.11/3.13 运行后端测试，并在 Ubuntu 运行前端 typecheck/test/build；它不能替代本机 CUDA 验证。

Vite 开发服务器默认 `http://127.0.0.1:5173`，把 `/api` 代理到 `http://127.0.0.1:8765`。另开终端启动后端：

```powershell
training-viewer serve --no-browser
```

生产构建：

```powershell
npm run build
```

输出到 `src/training_viewer/web/`。该目录随 Python 包安装，运行时不要求 Node。

## 4. 安装与启动

```powershell
python -m pip install -e .
training-viewer open examples
```

人工查看用 `open`；训练 Agent 用 `attach`（后台启动、返回 JSON）：

```powershell
training-viewer attach examples --json
training-viewer status --json
training-viewer stop
```

训练侧写入器：

```python
from training_viewer.writer import TrainingRunWriter
```

它只依赖标准库，可单独复制 `src/training_viewer/writer.py`。完整接入流程见 [`AGENT_INTEGRATION.md`](../AGENT_INTEGRATION.md)。

实例复用：数据目录中的 `instance.json` 记录端口与进程号；`open`/`attach` 会先调用 `/api/v1/health` 探测。若旧实例已退出，会忽略陈旧记录并启动新实例。

## 5. 打包 Python 发行包

```powershell
python -m pip install build
python -m build
```

将生成 `dist/training_viewer-1.0.0-py3-none-any.whl` 与 sdist。安装验证：

```powershell
python -m venv C:\temp\tv-check
C:\temp\tv-check\Scripts\python.exe -m pip install dist\training_viewer-1.0.0-py3-none-any.whl
C:\temp\tv-check\Scripts\training-viewer.exe open examples --no-browser
```

包内必须包含：

- `training_viewer/web/index.html` 与 `web/assets/*`
- `training_viewer/schemas/*.schema.json`
- 所有 Python 模块

`pyproject.toml` 的 `package-data` 已声明这些文件；修改构建配置后应重新检查 wheel 内容（`python -m zipfile -l ...whl`）。

## 6. 数据目录与调试

| 路径 | 内容 |
|---|---|
| `%LOCALAPPDATA%\TrainingViewer\index.sqlite3` | 可重建的指标索引 |
| `%LOCALAPPDATA%\TrainingViewer\user_state.sqlite3` | 根目录、备注、收藏、保存视图；不可重建，删除前备份 |
| `%LOCALAPPDATA%\TrainingViewer\logical_runs.json` | 用户确认的逻辑实验归并规则 |
| `%LOCALAPPDATA%\TrainingViewer\instance.json` | 当前实例的 URL/端口/PID |
| `src/training_viewer/web/` | 构建后的前端 |

- 覆盖数据目录：`--data-dir` 或 `TRAINING_VIEWER_DATA_DIR`。
- 重建索引：停止服务，删除 `index.sqlite3`，重启并重新添加根目录；`user_state.sqlite3` 不会被清空。
- 查看 API：`/docs`。
- 日志：终端输出；后台线程异常以 `training_viewer.*` logger 记录。

### 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面显示“前端资源尚未构建” | 未构建或包未包含 `web/` | `cd frontend && npm run build`，重新安装 |
| 端口被占用 | 已有实例/其它进程 | CLI 自动顺延；或使用 `--port` |
| 中文输出乱码/报错 | Windows 控制台编码 | CLI 已改为 UTF-8；仍异常可设置 `PYTHONIOENCODING=utf-8` |
| TensorBoard 目录未显示 | 未安装可选依赖 | `pip install "training-viewer[tensorboard]"` |
| 应用数据目录不可写 | `PermissionError` 或 `sqlite3.OperationalError` | CLI 会提示；用 `--data-dir` 或 `TRAINING_VIEWER_DATA_DIR` 指向可写目录 |
| 运行显示“状态未知” | 没有完成事件且心跳超时 | 正常语义，不是失败；查看 status_reason |
| 对比显示“不可直接排名” | 单位/数据集/定义/任务不一致 | 检查指标定义与数据集信息 |
| 训练 Agent 调用 `open` 后卡住 | `open` 是前台阻塞命令 | 改用 `training-viewer attach <目录> --json` |

## 7. 修改协议字段的流程

TVLP 字段是公开机器接口，修改必须谨慎：

1. 先判断是否破坏兼容性；破坏性修改需要新协议版本与迁移说明，不能静默重命名。
2. 同步更新 `schemas/*.schema.json`、`src/training_viewer/schemas/` 副本、读取器校验、`docs/log-sources.md`、组件文档与测试。
3. 更新示例与 `tools/validate_log.py` 的兼容性。
4. 运行 `test_packaged_schemas_match_repository_schemas`，确保副本一致。
5. 在 `docs/changes/` 写变更记录，回答六个问题。

## 8. 新增组件的最低门槛

- 使用有职责含义的中文名和英文代码名；
- 在 `docs/components/` 增加说明，包含输入输出、配置、异常、测试、限制；
- 不明文使用 `V2`/`NewX` 等名称；
- 有自动化测试或明确的验证步骤；
- 在 `docs/changes/` 记录变更原因、影响与回退。
