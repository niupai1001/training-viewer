# 变更记录 0004：训练 Agent 自动接入（写入器 + attach）

- 变更编号：0004
- 日期：2026-10-31
- 关联需求/问题：用户明确不需要手动启动查看器；训练 Agent 应按协议写入日志、自动挂载查看器并把 URL 交给用户
- 代码提交：工作区变更（未建立 Git 提交）
- 变更类别：功能增加 / 行为修改

## 1. 原来是什么

第一版只有查看器侧：

- 训练程序需要自己手写 `run.json`、`metrics.jsonl`、`events.jsonl`，没有训练侧写入辅助；
- 启动只有前台阻塞的 `training-viewer open` / `serve`；
- 训练 Agent 若执行 `open` 会一直占用会话，无法完成“写日志 → 挂载 → 返回 URL”；
- 用户必须手动添加日志目录、手动打开浏览器。

这不符合“告诉训练 Agent 加入这个东西，它把东西放进去，我能可视化”的使用方式。

## 2. 现在改变什么

新增训练侧与 Agent 侧入口：

- `src/training_viewer/writer.py`：`TrainingRunWriter`，只依赖标准库，可单独复制；原子写元数据、指标、心跳、生命周期、产物引用，支持断点续训会话。
- `training-viewer attach <日志根目录> --json`：复用或**后台启动**服务，添加目录，返回 `status/url/pid/run_total`；不阻塞 Agent。
- `training-viewer status` / `training-viewer stop`：检查/停止后台实例。
- `AGENT_INTEGRATION.md`：交给训练 Agent 的完整接入契约，包含代码接入、指标映射、产物、恢复训练、校验、attach、验收清单和禁止事项。
- 训练侧写入器文档、attach 命令文档、架构数据流、术语表、README 同步更新。
- 新增 5 个写入器测试与 1 个端口探测测试；总计 68 个测试。

保留：TVLP 1.0 协议字段、读取器、SQLite schema、前端与安全边界不变；原始日志只读原则不变。

## 3. 为什么这样改

用户的实际工作流是“训练 Agent 接活并自动接入”，而不是“人先开服务再手动加目录”。前台 `open` 对 Agent 不可用；手写 JSONL 又容易漏时区、半行、会话和状态事件。因此需要：

1. 训练侧低门槛、无服务依赖的写入器；
2. Agent 可调用、非阻塞、可解析的挂载命令；
3. 明确、可执行的 Agent 接入契约。

未采用的替代方案：

- 让训练代码通过 HTTP 推送指标：违反“训练程序不依赖查看器服务、离线也能训练”的边界。
- Agent 直接写 SQLite：索引必须可从日志重建，直接写库会破坏该保证。
- 让 Agent 自己 `start /B` 起服务：平台差异大、错误不可诊断；由 `attach` 统一处理端口、日志、健康检查。
- 只给文档、不提供写入器：Agent 仍要手写协议，容易产生不可复现的日志。

## 4. 影响范围

- 新增 `src/training_viewer/writer.py`、`tests/test_writer.py`、`AGENT_INTEGRATION.md`。
- `cli.py`：新增 `attach`、`status`、`stop`；修复端口探测在 Windows 上因 `SO_REUSEADDR` 误判空闲端口的问题。
- 文档：README、架构、组件索引、写入器/attach 组件说明、术语表、开发文档。
- 数据/协议：无 schema 变化；写入器生成标准 TVLP 1.0；无需迁移索引。
- 入口：训练 Agent 只需 `pip install training-viewer`（或复制 `writer.py`）并执行 `attach`。

## 5. 验证结果

- `pytest -q`：**68 passed，2 skipped**（新增写入器 5 项）。
- `ruff check src tests --select F,E9`：通过。
- 端到端真实文件验证：
  1. 用 `TrainingRunWriter` 生成 `agent-run-0001`（2 个 Step、train/val 指标、预测图、完成事件）；
  2. `training-viewer validate` 0 error；
  3. `training-viewer attach <日志根> --data-dir <可写目录> --port 8789 --json` 返回 `status=ok`、`run_total=1`；
  4. `status --json` 返回 running；
  5. `/api/v1/runs` 显示该运行 `completed`，指标键包含 `train/loss`、`val/miou`；
  6. `stop --json` 后 status 返回 stopped。
- **实时闭环验证**：先 attach 一个空日志根目录（`run_total=0`），再启动写入器模拟训练；2 秒内查看器自动发现新 Run，轮询期间指标点从 4 增至 14，状态从 `running` 变为 `completed`，无需重启服务或手动刷新。
- 端口探测修复验证：8787 被其它服务监听时，attach 自动改用 8788，不再出现“探测空闲但子进程 bind 失败”。

## 6. 回退方式

- 回退写入器：训练代码改回直接写 JSONL；删除 `writer.py` 与测试。
- 回退 attach/status/stop：删除 `cli.py` 中对应命令与 `AGENT_INTEGRATION.md`；继续使用 `open`/`serve`。
- 数据：无迁移；已生成的日志仍可被查看器读取。删除索引数据库可重建。
- 风险：回退 `attach` 会恢复前台阻塞方式，不适合训练 Agent 自动接入。

## 7. 文档同步情况

- [x] 组件说明：新增 `training-run-writer.md`、`cli-agent-attach.md`
- [x] 架构与数据流：写入器、attach、后台进程
- [x] 术语表：Writer、attach、detached process
- [x] 使用说明：README、`AGENT_INTEGRATION.md`、开发文档
- [x] 测试：`tests/test_writer.py`，CLI 手工端到端验证

