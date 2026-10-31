"""导出可审计的来源清单：原始文件 → 逻辑实验，不包含指标数值。

用法：
    python tools/export_source_inventory.py --data-dir <Viewer数据目录> --output audit/run_inventory.csv
    python tools/export_source_inventory.py --data-dir <...> --root D:/outputs --output ...

每个文件一行，列出 parser、原始运行标识、逻辑实验 ID、是否归并、置信度、点数。
没有真实数据时不要伪造 62 个来源；本工具只报告实际索引。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService

FIELDS = [
    "source_path",
    "parser",
    "run_id",
    "raw_run_identifier",
    "logical_run_id",
    "merged",
    "confidence",
    "project",
    "name",
    "point_count",
    "bytes_read",
    "file_size",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--output", default="audit/run_inventory.csv")
    args = parser.parse_args()

    service = TrainingViewerService(ApplicationPaths.resolve(args.data_dir))
    for root in args.root:
        service.add_root(root)
    rows = service.queries.source_inventory()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logical = {row["logical_run_id"] for row in rows}
    print(f"source_files={len(rows)} logical_runs={len(logical)} output={output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
