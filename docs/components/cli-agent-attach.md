# 组件说明：训练 Agent 接入命令（attach / status / stop）

## 一句话说明

`training-viewer attach` 把一个训练日志根目录接入本机查看器：复用或后台启动服务、添加目录，并返回可打开的 URL；`status` / `stop` 检查或停止该实例。它不解析日志、不修改训练文件。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 训练 Agent 接入命令 |
| 代码名 | `_attach_command`、`_status_command`、`_stop_command` |
| 源文件 | `src/training_viewer/cli.py` |
| 所属模块 | 命令行入口 |
| 上游 | 训练 Agent / 研究者；下游 | `TrainingViewerService`、REST `/roots`、`/health` |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

`training-viewer open` 是前台阻塞命令，适合人工打开，不适合训练 Agent：Agent 调用后会一直等不到结束，也无法把 URL 返回给用户。`attach` 解决这个问题：

- 已有实例 → 复用，只添加目录；
- 没有实例 → 用 `serve` 启动**后台**进程，最多等待约 25 秒健康检查；
- 输出机器可读 JSON；
- 不依赖浏览器也能返回 URL；
- 服务在 Agent 会话结束后继续运行。

推荐在**训练开始前**执行，让训练过程中的指标实时出现；此时 `run_total` 可能为 0，训练写出第一个 Run 后会自动增长。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | `paths` | 目录列表 | 一个或多个训练日志根目录，必须已存在 |
| 输入 | `--port` / `--host` | 整数/字符串 | 默认 8765 / 127.0.0.1 |
| 输入 | `--data-dir` | 路径 | 应用数据目录；默认系统目录 |
| 输入 | `--no-start` | 布尔 | 不启动新服务，只连接现有实例 |
| 输入 | `--json` | 布尔 | 输出 JSON，不打开浏览器 |
| 输入 | `--no-browser` | 布尔 | 人类模式下也不打开浏览器 |
| 输出 | JSON | 对象 | `status`、`url`、`started`、`roots`、`pid`、`run_total`、`server_log` |

成功示例：

```json
{
  "status": "ok",
  "url": "http://127.0.0.1:8765/",
  "started": true,
  "roots": [{"id": 1, "path": "D:\\runs\\my-project"}],
  "data_dir": "C:\\Users\\me\\AppData\\Local\\TrainingViewer",
  "pid": 12345,
  "run_total": 1,
  "server_log": "C:\\Users\\me\\AppData\\Local\\TrainingViewer\\server.log"
}
```

## 主要处理流程

1. 解析并校验应用数据目录和每个日志根目录（必须存在且是目录）。
2. 读取 `instance.json` 并调用 `/api/v1/health`；确认 `application == "training-viewer"`。
3. 无实例时：
   - 用系统临时端口探测选择空闲端口（Windows 不使用 `SO_REUSEADDR`，避免误判）；
   - 以 `sys.executable -m training_viewer serve ... --no-browser` 启动后台进程；
   - 子进程 stdout/stderr 写入 `<data_dir>/server.log`；
   - Windows 使用 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`，POSIX 使用新会话；
   - 轮询 `/health`，超时则输出日志尾部并返回 2。
4. 对每个根目录 `POST /api/v1/roots`，触发同步；统计当前运行数。
5. `--json` 输出一行 JSON；否则打印中文信息并按需打开浏览器。
6. `status`：读取实例文件 + health + 运行数；未运行返回 1。
7. `stop`：验证实例 health 后按 PID 发送 SIGTERM，等待最多 5 秒，清理实例文件；未运行返回 1。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 首选端口 | 8765 | 被占用自动顺延 |
| 健康检查超时 | 25 秒 | 后台启动失败时读取日志 |
| 临时端口范围 | 首选端口 + 0–24 | 避开已占用端口 |
| 服务日志 | `<data_dir>/server.log` | 追加写入 |

依赖：Python 标准库 `subprocess`、`socket`、`urllib`、`signal`；查看器自身。无第三方新增依赖。

## 和旧实现相比改变了什么

初始实现只有前台 `open`/`serve`。新增 `attach` 是因为训练 Agent 需要非阻塞、可脚本解析、可返回 URL 的接入方式；新增 `status`/`stop` 用于确认后台实例生命周期。原有 `open`/`serve` 行为保留。

## 如何验证

- 手动（已实际执行）：`training-viewer attach <examples> --data-dir <可写目录> --port 8787 --json` 返回 `status=ok`、`run_total=4`；`status --json` 返回 running；`stop --json` 后 status 返回 stopped（退出码 1）。
- 手动（已实际执行）：先 attach 空目录（`run_total=0`），再用 `TrainingRunWriter` 实时写 7 个 Step；查看器自动发现运行，指标点从 4 增长到 14，状态由 running 变为 completed。
- 手动（已实际执行）：用 `TrainingRunWriter` 创建 1 个 Run → `attach` → `/runs` 返回该运行，状态 `completed`，指标键 `train/loss`、`val/miou`。
- 自动化：CLI validate 测试；attach 的后台进程启动依赖真实操作系统，未放入 pytest，避免测试进程泄漏。

## 已知限制与回退

- `attach` 假设训练日志目录在本机可见；跨机器场景只能完成日志写入，由用户在查看器所在机器执行 attach。
- `stop` 依据实例文件中的 PID；PID 被系统复用时存在极小误杀风险，因此先验证 health 和数据目录。
- 后台进程不会被 `attach` 自动回收；需要 `training-viewer stop` 或手动结束。
- 端口探测与实际绑定之间仍有极短竞态；启动失败会给出 `server.log` 尾部而不是静默失败。
- 回退：使用前台 `training-viewer open/serve`，或停止后台进程；不影响日志与索引。

## 名称解释

- attach：接入/挂载，把日志目录加入查看器。
- detached process：脱离当前终端会话的后台进程。
- health check：调用 `/api/v1/health` 确认服务可用。
- JSON 模式：只输出一行机器可读 JSON，供 Agent 解析。
