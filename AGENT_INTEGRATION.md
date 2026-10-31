# 给训练 Agent 的接入契约：Training Viewer / TVLP 1.0

> **把本文件完整交给训练 Agent。** 目标是：Agent 修改训练程序，让它按 Training Viewer Log Protocol（TVLP，训练日志协议）1.0 写出日志，然后运行一条 `training-viewer attach` 命令把日志目录挂到本机查看器，最后把可打开的 URL 交给用户。用户不需要手动打开服务、不需要手动找日志文件。

## 0. 你必须交付的结果

1. 训练代码中接入日志写入（推荐 `TrainingRunWriter`，或直接按协议写文件）。
2. 日志目录中存在合法的 `run.json`、`metrics.jsonl`，可选 `events.jsonl` 和 `artifacts/`。
3. **在训练开始前**运行 `training-viewer attach <日志根目录> --json`，拿到 `status: "ok"` 和 `url`，让训练过程中的曲线实时出现。
4. 训练结束后运行 `training-viewer validate <Run目录>` 得到 **0 error**，再用 `status --json` 确认服务仍在运行。
5. 在最终回复中告诉用户：日志根目录、Run 名称、校验结果、可视化 URL。

推荐顺序：

```text
创建日志根目录 → attach（后台服务）→ 启动训练 → 写入指标/心跳/产物 → 训练结束 → validate → 交付 URL
```

不要只说“已支持”，要给出实际生成的文件与命令输出。

## 1. 不可违反的边界

- 日志协议固定为 **TVLP 1.0**；不要改字段名、不要发明“简化版”。
- 原始训练日志只追加，不就地修改历史行；不要删除已有实验目录。
- 不伪造指标：没有记录的验证指标就不要写；不能把缺失值填成 0。
- 不把训练代码变成查看器 HTTP 客户端；训练只写文件，查看器只读文件。
- 不运行 `training-viewer open`（它会占用前台）；Agent 使用 `attach`。
- 不直接写查看器的 SQLite；索引必须由查看器从日志重建。
- 不把产物写成绝对路径或 `..` 路径。

## 2. 先确认协议

必读：

- [`docs/log-sources.md`](docs/log-sources.md)：TVLP 目录、必需字段、半行、会话、状态。
- [`schemas/run.schema.json`](schemas/run.schema.json)、[`schemas/metrics.schema.json`](schemas/metrics.schema.json)、[`schemas/events.schema.json`](schemas/events.schema.json)。

每个 Run 目录至少：

```text
<log_root>/<run_id>/
  run.json          # 必需，运行身份/项目/配置/指标定义
  metrics.jsonl     # 至少一行训练指标
  events.jsonl      # 推荐：生命周期、心跳、产物引用
  artifacts/        # 可选：预测图/标签图/表格
```

## 3. 选择日志根目录

优先使用用户指定的目录或环境变量 `TRAINING_VIEWER_LOG_ROOT`。如果用户没有指定，使用训练仓库中的 `runs/training-viewer` 并明确告诉用户。**在 attach 之前先创建目录**。

不要使用查看器的数据目录（`index.sqlite3` 所在目录）作为日志根目录。

## 4. 安装写入器

### 方式 A（推荐）：安装 Training Viewer 包

```bash
python -m pip install training-viewer
```

如果当前环境不能联网，使用用户给的本地 wheel：

```bash
python -m pip install /path/to/training_viewer-1.0.0-py3-none-any.whl
```

如果训练环境与查看器环境不同：训练环境只需要写入器（方式 B 的单文件即可），`attach` 必须在查看器所在机器执行。此时告诉用户日志根目录，或使用查看器环境的完整路径：

```powershell
C:\path\to\viewer\.venv\Scripts\training-viewer.exe attach D:\runs\my-project --json
```

### 方式 B：只复制单文件写入器

`src/training_viewer/writer.py` 只依赖 Python 标准库，可以复制到训练仓库中作为独立模块使用。它不会启动查看器、不会连接网络。

写入器不要求训练环境安装 FastAPI；它只是日志写入辅助。训练程序仍然可以完全离线运行。

## 5. 最小接入代码

把下面代码放到训练入口，替换项目名、运行名、指标与保存逻辑。**不要伪造占位指标。**

```python
import os
from pathlib import Path

from training_viewer.writer import TrainingRunWriter

LOG_ROOT = Path(os.environ.get("TRAINING_VIEWER_LOG_ROOT", "runs/training-viewer"))
PROJECT = "你的项目名"
RUN_NAME = "SegFormer 基线｜10 波段｜随机种子 42"
# 断点续训时从检查点/配置读取同一个 run_id，并设置 resume=True
RESUME_RUN_ID = os.environ.get("TRAINING_VIEWER_RUN_ID")
RUN_DIR = LOG_ROOT / RESUME_RUN_ID if RESUME_RUN_ID else None

metric_definitions = {
    "train/loss": {"direction": "min", "unit": "none"},
    "val/miou": {
        "direction": "max",
        "unit": "ratio",
        "aggregation": "macro",
        "definition": "classes 0..4, ignore_index=255",
    },
    "val/f1": {"direction": "max", "unit": "ratio", "definition": "classes 0..4"},
}

with TrainingRunWriter(
    LOG_ROOT,
    project=PROJECT,
    name=RUN_NAME,
    experiment="消融组名称（可选）",
    task="semantic-segmentation",
    model={"name": "SegFormer", "architecture": "MiT-B2"},
    dataset={"name": "数据集名", "version": "v1", "split_definition": "split-v1"},
    config={"epochs": 100, "batch_size": 8, "optimizer": {"name": "AdamW", "lr": 1e-4}},
    source={"git_commit": "...", "seed": 42, "framework": "pytorch"},
    tags=["baseline", "10-band"],
    metric_definitions=metric_definitions,
    run_id=RESUME_RUN_ID,
    run_directory=RUN_DIR,
    resume=bool(RESUME_RUN_ID),
    heartbeat_interval_seconds=30,
) as run:
    # 让检查点或配置记住 run.run_id / run.run_directory，断点续训时复用
    for epoch in range(1, epochs + 1):
        for batch in train_loader:
            optimizer.step()
            global_step += 1
            if global_step % log_every == 0:
                run.log_metrics(
                    "train",
                    {"loss": float(loss.item()), "lr": optimizer.param_groups[0]["lr"]},
                    global_step=global_step,
                    epoch=epoch,
                )

        metrics = validate(model, val_loader)  # 返回真实计算的指标
        run.log_metrics(
            "val",
            {"loss": metrics["loss"], "miou": metrics["miou"], "f1": metrics["f1"]},
            global_step=global_step,
            epoch=epoch,
        )

        # 保存预测图：必须写在 Run 目录内的相对路径
        prediction_path = run.artifact_path(
            f"artifacts/predictions/sample-001-epoch-{epoch}.png"
        )
        save_prediction_image(prediction_path)
        run.log_artifact(
            f"artifacts/predictions/sample-001-epoch-{epoch}.png",
            artifact_type="image",
            tag="segmentation-preview",
            phase="val",
            epoch=epoch,
            global_step=global_step,
            group_id=f"sample-001-epoch-{epoch}",
            sample_id="sample-001",
            role="prediction",
        )
```

上下文管理器会自动写 `started`、心跳和 `completed`；训练异常时写 `failed` 并重新抛出异常。如果必须手动控制，也可以 `run.start()` / `run.finish()`，但必须保证 `finish` 执行。

### 只记录训练 Loss 的最小示例

如果当前只有训练损失，就只写训练损失；不要凭空添加验证指标：

```python
with TrainingRunWriter(
    LOG_ROOT,
    project=PROJECT,
    name=RUN_NAME,
    metric_definitions={"train/loss": {"direction": "min", "unit": "none"}},
) as run:
    for step, batch in enumerate(loader, start=1):
        loss = train_step(batch)
        run.log_metrics("train", {"loss": float(loss)}, global_step=step, epoch=1)
```

## 6. 指标映射规则

| 字段 | 规则 |
|---|---|
| `phase` | `train` / `val` / `test` 等真实阶段；不要把所有指标都写成 `train` |
| `global_step` | 优化器参数更新次数；不是 batch 下标、不是 epoch |
| `epoch` | 从 1 开始的训练轮次 |
| `metrics` | 只写真实计算出的有限数字；不能写 `NaN`、`Infinity`、布尔值 |
| `metric_definitions` | 键必须是 `phase/metric_name`；`direction` 只能是 `min` / `max` / `none` |
| `unit` | `ratio`、`percent`、`ms` 等精确单位；ratio 是 0–1，不要自行换算成百分数 |
| `definition` | 写清类别范围、ignore_index、平均方式、数据划分 |

同一个 Step 的训练指标和验证指标可以同时存在，这是合法的：

```jsonl
{"timestamp":"2026-10-31T08:01:00Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"train","metrics":{"loss":0.78}}
{"timestamp":"2026-10-31T08:01:30Z","session_id":"session-001","global_step":100,"epoch":1,"phase":"val","metrics":{"loss":0.81,"miou":0.43}}
```

## 7. 保存预测结果图

1. 用 `run.artifact_path("artifacts/...")` 得到绝对路径并创建父目录，再用 `matplotlib` / `PIL` / `cv2` 保存。
2. 用 `run.log_artifact(...)` 记录引用；文件必须已经或即将位于该路径。
3. 推荐角色：`input`（原图）、`ground_truth`（标签）、`prediction`（预测）、`confusion_matrix`（混淆矩阵）。
4. 同一个样本同一轮次的图使用相同 `group_id`，例如 `sample-001-epoch-2`；`sample_id` 用于跨 Epoch 关联。
5. 混淆矩阵如果保存为 CSV，`artifact_type="table"`；如果保存为 PNG，`artifact_type="image"`。

## 8. 断点续训

- 同一个 Run 复用 **相同 `run_id`** 和 **相同 `run_directory`**，设置 `resume=True`。
- 写入器自动生成新的 `session_id`，不会把两次会话混在一起。
- 如果训练代码重置了 `global_step`，保留真实值；查看器按会话分段，不会错误合并。
- 把 `run_id` 保存到检查点或训练配置中，否则重启后会变成新 Run。

## 9. 训练开始前：挂载查看器（Agent 的关键一步）

先创建日志根目录，然后执行：

```bash
training-viewer attach <log_root> --json
```

- 如果查看器未运行，`attach` 会启动**后台**服务并返回；不会阻塞训练 Agent。
- 如果实例已运行，会复用并只添加目录。
- 默认端口 8765，被占用会自动顺延；返回的 `url` 是真实地址。
- 默认应用数据目录不可写时，追加 `--data-dir <可写目录>`。
- **此时 `run_total` 可能为 0**，因为训练还没有写出第一个 Run；不要把它当成失败。训练开始后查看器会自动发现新 Run。

成功返回示例：

```json
{
  "status": "ok",
  "url": "http://127.0.0.1:8765/",
  "started": true,
  "roots": [{"id": 1, "path": "D:\\runs\\my-project"}],
  "data_dir": "C:\\Users\\me\\AppData\\Local\\TrainingViewer",
  "pid": 12345,
  "run_total": 0,
  "server_log": "C:\\Users\\me\\AppData\\Local\\TrainingViewer\\server.log"
}
```

验证服务：

```bash
training-viewer status --json
```

运行中应返回 `"status": "running"`。如果训练已经在跑，跳过本节，直接执行同样的 attach 命令；查看器会读取已经追加的日志并继续增量更新。

## 10. 训练结束后：校验与交付

```bash
training-viewer validate <log_root>/<run_id> --json
training-viewer status --json
```

要求 `error_count == 0`，`status` 为 `running`，且 `run_total` 至少为 1。查看器会继续在后台运行；只有用户明确要求时才执行：

```bash
training-viewer stop --json
```

**把 `url` 原样告诉用户。** 用户打开后应能看到：
- 运行列表中有本次 Run；
- 状态为“运行中”或“已完成”；
- 指标曲线有真实数据点，并且训练中会实时增长；
- “预测结果”页能看到保存的图像。

如果 `training-viewer` 不在 PATH，使用安装环境的完整路径，或在训练环境执行 `python -m training_viewer validate ...`。

## 11. 验收清单

- [ ] `run.json` 存在，`schema_version` 为 `"1.0"`，`run_id` 全局唯一。
- [ ] `metrics.jsonl` 至少一条记录；每条有 `timestamp`、`phase`、`metrics` 和 Step 或 Epoch。
- [ ] 没有 `NaN`、`Infinity`、布尔指标、绝对产物路径。
- [ ] 同一个 Step 的 train/val 是不同 `phase` 的两条记录。
- [ ] `training-viewer validate` 返回 0 error。
- [ ] `training-viewer attach` 返回 `status: "ok"`。
- [ ] `training-viewer status` 显示 running，`run_total` 增加。
- [ ] 用户能打开返回的 URL 并看到曲线；若有验证指标才显示验证曲线，不虚增。
- [ ] 断点续训复用同一 `run_id`，新 `session_id`，历史点未丢失。
- [ ] 最后回复用户：日志根目录、Run 根目录、校验结果、URL。

## 12. 禁止事项

- ❌ 运行 `training-viewer open` 或 `serve` 阻塞 Agent 的会话。
- ❌ 直接把指标写进 `index.sqlite3`。
- ❌ 修改或删除用户已有的历史日志。
- ❌ 用 `global_step=0` 记录所有点、用 batch 下标冒充优化步。
- ❌ 把验证指标写成训练指标，或把缺失指标填 0。
- ❌ 把产物路径写成绝对路径、`../`、网络 URL。
- ❌ 声称“已接入”但没有实际文件、校验和 attach 输出。
- ❌ 在日志中写入 `NaN`、`Infinity`、布尔值或数组作为指标值。

## 13. 最终回复模板

```text
Training Viewer 已接入。

- 日志根目录：D:\runs\my-project
- Run 目录：D:\runs\my-project\7c9f6ad4-...
- 协议校验：0 error（training-viewer validate --json）
- 后台服务：running（attach --json 返回 status=ok）
- 可视化地址：http://127.0.0.1:8765/

本次记录了 train/loss、val/miou、val/f1；预测图在 artifacts/predictions/，已通过 events.jsonl 关联。
限制：<如果没有验证指标，明确说明；如果训练环境不能安装查看器，说明只写日志，需要用户在本机 attach>
```

## 14. 如果训练环境不能安装或运行 Training Viewer

可以只完成文件写入。此时：

1. 仍按上面的 `run.json` + `metrics.jsonl` + `events.jsonl` 协议写日志（可以复制 `writer.py`，只依赖标准库）。
2. 运行 `python -m pip install training-viewer` 到**查看器所在机器**，或让用户在本机安装。
3. 告诉用户日志根目录，并让用户执行：

```bash
training-viewer attach <log_root> --json
```

不要假装已经完成可视化；要区分“日志已生成”和“查看器已挂载”。
