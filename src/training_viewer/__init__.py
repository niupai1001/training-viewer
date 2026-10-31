"""Training Viewer：本机训练实验查看器。

本包只消费训练程序写出的日志文件，不参与训练调度，也不会修改原始实验目录。
"""

__version__ = "1.0.0"

# 协议版本必须与 schemas/*.schema.json 及 run.json 中的 schema_version 保持一致。
TVLP_SCHEMA_VERSION = "1.0"

APP_DISPLAY_NAME = "Training Viewer 训练实验查看器"
