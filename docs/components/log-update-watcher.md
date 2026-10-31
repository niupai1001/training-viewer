# 组件说明：日志更新监听器（LogUpdateWatcher）

## 一句话说明

在后台按固定间隔触发目录同步，并在 watchdog 可用时用文件系统事件提前唤醒；不解析日志、不处理 HTTP 请求。

## 基本信息

| 项目 | 内容 |
|---|---|
| 中文功能名 | 日志更新监听器 |
| 代码类名 | `LogUpdateWatcher` |
| 源文件 | `src/training_viewer/watch/log_update_watcher.py` |
| 所属模块 | 实时更新 |
| 上游 | `TrainingViewerService.start_background_sync()`；下游 | `TrainingViewerService.synchronize()` |
| 首次引入版本 | 1.0.0 |

## 为什么需要它

只看文件系统事件会漏掉网络盘、编辑器写入、批量解压等场景；只靠轮询又会让新指标出现得不够及时。本组件把轮询作为正确性保证，把 watchdog 作为降低延迟的提示。

## 输入与输出

| 方向 | 名称 | 类型 | 说明 |
|---|---|---|---|
| 输入 | 服务实例 | `TrainingViewerService` | 提供 `list_roots()` 与 `synchronize()` |
| 输入 | 间隔 | 浮点秒，默认 2 | 最长等待时间 |
| 输入 | 文件事件 | watchdog 事件 | 任意事件只设置唤醒标志 |
| 输出 | 同步调用 | 副作用 | 扫描、索引、SSE 通知 |
| 输出 | 线程生命周期 | 线程 | `start()` / `stop()` |

## 主要处理流程

1. `start()` 创建守护线程并启动 watchdog 观察器（若可用）。
2. 线程启动后立即同步一次。
3. 循环：等待唤醒事件，最长等待间隔；清除标志；调用 `service.synchronize()`。
4. 异常被捕获并记录，线程继续下一轮，保证后台不因单次失败退出。
5. `refresh_watches()` 在根目录增删时重建观察器；观察失败只警告，轮询仍工作。
6. `stop()` 设置停止标志、唤醒线程、等待退出并停止观察器。

## 配置与依赖

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `interval_seconds` | 2 | CLI `--interval` 可调 |
| watchdog | 必需依赖 | 若被裁剪，退化为纯轮询并记录警告 |

依赖：`watchdog`、`threading`、`logging`。不依赖 FastAPI。

## 和旧实现相比改变了什么

初始实现。V1 明确“轮询是正确性保证、文件事件只是优化”的顺序，避免把 watchdog 当作唯一触发源。

## 如何验证

- 自动化测试不启动后台线程（`start_background_sync=False`），同步逻辑由显式 `synchronize()` 覆盖。
- 手工：启动服务，向 `metrics.jsonl` 追加一行，约 1–2 秒内总览/运行详情更新，SSE 状态显示已连接。
- 停止/重启：`Ctrl+C` 后观察器线程退出，无残留写锁。

## 已知限制与回退

- 每 2 秒完整发现一次目录；复杂目录树可调整间隔或缩小根目录。
- watchdog 在某些网络文件系统上不可靠，因此不能只依赖它。
- 回退：设置 `start_background_sync=False`（嵌入测试）或关闭进程；不影响手动“立即重新扫描”。

## 名称解释

- watchdog：Python 文件系统事件库。
- 轮询：按固定时间间隔检查变化。
- 守护线程：随主进程退出而结束的后台线程。
