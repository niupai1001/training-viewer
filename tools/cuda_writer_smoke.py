"""Windows + PyTorch + CUDA + TrainingRunWriter 隔离矩阵。

每个场景都在独立子进程中运行，开启 faulthandler；父进程只收集退出码和输出。
禁止在训练主进程里循环触发崩溃。没有 CUDA 的环境会返回 skipped，而不是假称通过。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCENARIOS = {
    "cpu_writer_default": """
import torch
from training_viewer.writer import TrainingRunWriter
with TrainingRunWriter(log_root=LOG_ROOT, project="cuda-smoke", name="cpu-default",
                       metric_definitions={"train/loss": {"direction": "min"}}) as writer:
    writer.log_metrics("train", {"loss": 0.5}, global_step=1, epoch=1)
""",
    "cuda_only": """
import torch
torch.cuda.init()
x = torch.nn.Linear(8, 4).cuda()(torch.randn(2, 8, device="cuda"))
print(float(x.sum().item()))
""",
    "cuda_writer_default": """
import torch
from training_viewer.writer import TrainingRunWriter
x = torch.nn.Linear(8, 4).cuda()(torch.randn(2, 8, device="cuda"))
with TrainingRunWriter(log_root=LOG_ROOT, project="cuda-smoke", name="cuda-default",
                       metric_definitions={"train/loss": {"direction": "min"}}) as writer:
    writer.log_metrics("train", {"loss": float(x.sum().item())}, global_step=1, epoch=1)
""",
    "cuda_writer_async_heartbeat": """
import torch
from training_viewer.writer import TrainingRunWriter
x = torch.nn.Linear(8, 4).cuda()(torch.randn(2, 8, device="cuda"))
with TrainingRunWriter(log_root=LOG_ROOT, project="cuda-smoke", name="cuda-async",
                       metric_definitions={"train/loss": {"direction": "min"}},
                       heartbeat_interval_seconds=1) as writer:
    writer.log_metrics("train", {"loss": float(x.sum().item())}, global_step=1, epoch=1)
""",
    "cuda_plain_file": """
import torch
x = torch.nn.Linear(8, 4).cuda()(torch.randn(2, 8, device="cuda"))
with open(LOG_ROOT / "plain.txt", "a", encoding="utf-8") as handle:
    handle.write(str(float(x.sum().item())) + "\\n")
""",
    "cuda_writer_before_cuda": """
import torch
from training_viewer.writer import TrainingRunWriter
with TrainingRunWriter(log_root=LOG_ROOT, project="cuda-smoke", name="created-before-cuda",
                       metric_definitions={"train/loss": {"direction": "min"}}) as writer:
    x = torch.nn.Linear(8, 4).cuda()(torch.randn(2, 8, device="cuda"))
    writer.log_metrics("train", {"loss": float(x.sum().item())}, global_step=1, epoch=1)
""",
}


def run_scenario(name: str, code: str, log_root: Path) -> dict:
    source = (
        "import json, torch\n"
        f"LOG_ROOT = __import__('pathlib').Path({str(log_root)!r})\n"
        "print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda, "
        "'available': torch.cuda.is_available()}))\n"
        + code
    )
    environment = dict(os.environ, PYTHONFAULTHANDLER="1")
    try:
        completed = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", source],
            capture_output=True,
            text=True,
            timeout=90,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"scenario": name, "status": "timeout"}
    stderr_tail = completed.stderr[-2000:]
    return {
        "scenario": name,
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": stderr_tail,
    }


def main() -> int:
    try:
        import torch
    except ImportError:
        print(json.dumps({"status": "skipped", "reason": "torch 未安装"}, ensure_ascii=False))
        return 0
    if not torch.cuda.is_available():
        print(json.dumps({"status": "skipped", "reason": "CUDA 不可用"}, ensure_ascii=False))
        return 0
    log_root = Path("cuda-writer-smoke-runs").resolve()
    log_root.mkdir(exist_ok=True)
    results = [run_scenario(name, code, log_root) for name, code in SCENARIOS.items()]
    print(
        json.dumps(
            {
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "device": torch.cuda.get_device_name(0),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all(item["status"] == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
