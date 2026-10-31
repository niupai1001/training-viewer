# 审计事实与来源清单

## 当前证据边界

本仓库没有用户的 62 个真实 `outputs` 文件，也没有在用户机器上重新执行 CUDA 训练。
因此：

- 不伪造“62 个来源/53 次训练”的归并结论。
- `audit/run_inventory_examples.csv` 只是仓库 4 个示例 Run 的实际导出（7 个来源文件、4 个逻辑实验），用于验证工具与字段。
- 真实数据需要在用户机器上运行下面命令生成；工具只读取本地日志，不上传。

```powershell
python tools/export_source_inventory.py `
  --data-dir <Viewer 数据目录> `
  --root D:\outputs `
  --output audit\run_inventory.csv
```

输出每个来源文件的 parser、原始运行标识、逻辑实验 ID、是否归并、置信度、点数。
来源文件与逻辑实验数量不相等时，必须逐项解释；不能把“62 个来源”直接说成“62 次训练”。

## 已经量化的基线

- 读取器错误上限：60 条坏记录后 1000 条合法记录全部导入（四类读取器测试）。
- Windows 文本字节游标：CRLF、中文、多字节、尾部半行测试。
- CUDA：`tools/cuda_writer_smoke.py` 的隔离矩阵脚本；当前机器无 torch/CUDA，未执行。
- 百万点：见 [`docs/performance.md`](../docs/performance.md)。
- 页面任务基线：见 [`docs/changes/0006-deep-audit-hardening.md`](../docs/changes/0006-deep-audit-hardening.md) 的验证记录；真实 1440×900/1366×768 截图在浏览器验证后补充。

## 不应提交

真实实验路径、指标值、图像、checkpoint 和用户注释不应提交到仓库；只提交脱敏的来源清单或汇总。
