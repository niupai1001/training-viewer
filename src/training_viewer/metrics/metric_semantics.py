"""指标语义解析：声明优先，其次安全别名，未知字段不猜测科学含义。"""
from __future__ import annotations

from typing import Any

LOSS_NAMES = {"loss", "train_loss", "val_loss", "validation_loss", "test_loss"}
VALIDATION_SCORE_NAMES = {
    "miou": ("平均交并比", "Mean IoU"),
    "mean_iou": ("平均交并比", "Mean IoU"),
    "accuracy": ("准确率", "Accuracy"),
    "acc": ("准确率", "Accuracy"),
    "f1": ("F1 分数", "F1 score"),
    "dice": ("Dice 系数", "Dice coefficient"),
    "precision": ("精确率", "Precision"),
    "recall": ("召回率", "Recall"),
    "auc": ("AUC", "AUC"),
    "psnr": ("峰值信噪比", "PSNR"),
    "ssim": ("结构相似性", "SSIM"),
}
LEARNING_RATE_NAMES = {"lr", "learning_rate", "learningrate", "train_lr"}


def _norm(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def _loss_phase(phase: str) -> tuple[str, str, str]:
    normalized = phase.strip().lower()
    if normalized in ("train", "training"):
        return "train_loss", "训练损失", "Train loss"
    if normalized in ("val", "valid", "validation", "eval"):
        return "val_loss", "验证损失", "Validation loss"
    if normalized in ("test", "testing"):
        return "test_loss", "测试损失", "Test loss"
    return "loss", "损失", "Loss"


def _builtin_display(normalized: str, phase: str) -> tuple[str, str] | None:
    if normalized in LOSS_NAMES or normalized.endswith("_loss") or normalized == "loss":
        _, zh, en = _loss_phase(phase)
        return zh, en
    if normalized in LEARNING_RATE_NAMES or normalized.endswith("_lr"):
        return "学习率", "Learning rate"
    if normalized in VALIDATION_SCORE_NAMES:
        return VALIDATION_SCORE_NAMES[normalized]
    return None


def resolve_metric_semantics(
    raw_key: str,
    phase: str,
    metric_name: str,
    definition: dict[str, Any] | None = None,
) -> dict:
    """返回可序列化语义；definition 是 TVLP 明确声明，只有它能覆盖别名。"""
    definition = definition or {}
    normalized = _norm(metric_name)
    declared = any(
        definition.get(key)
        for key in ("display_name", "description", "definition", "category", "unit")
    )
    category = definition.get("category")
    display_zh = definition.get("display_name")
    display_en = definition.get("display_name_en")
    description = definition.get("description")
    unit = definition.get("unit")
    direction = definition.get("direction")
    aggregation = definition.get("aggregation")
    comparison_key = definition.get("comparison_key")
    is_primary = bool(definition.get("is_primary", False))
    role = "other"
    source = "declared" if declared else "unknown"
    confidence = "declared" if declared else "unknown"

    if source == "unknown":
        if normalized in LOSS_NAMES or normalized.endswith("_loss") or normalized == "loss":
            role, display_zh, display_en = _loss_phase(phase)
            category = "loss"
            direction = direction or "min"
            description = "损失值；具体组成以训练配置为准。"
            source = confidence = "builtin_alias"
        elif normalized in LEARNING_RATE_NAMES or normalized.endswith("_lr"):
            category = "learning_rate"
            description = "学习率；多参数组或调度定义以训练配置为准。"
            role = "learning_rate"
            display_zh, display_en = "学习率", "Learning rate"
            source = confidence = "builtin_alias"
        elif normalized in VALIDATION_SCORE_NAMES:
            display_zh, display_en = VALIDATION_SCORE_NAMES[normalized]
            category = "validation_score"
            direction = direction or "max"
            description = "验证/评估指标；类别、ignore_index 或 averaging 需由训练配置声明。"
            role = "validation_score"
            source = confidence = "builtin_alias"
        elif any(
            token in normalized
            for token in ("throughput", "samples_per_second", "gpu_mem", "gpu_memory", "peak_gpu")
        ):
            category = "performance"
            description = "吞吐或资源指标；单位与采集范围以原始记录为准。"
            source = confidence = "builtin_alias"
        elif metric_name.startswith("capacity/"):
            # 路径只能说明分组，不能证明具体科学含义。
            category = "performance"
            description = "按路径归入资源/容量分组；具体含义未提供定义。"
            source = "unknown"
        else:
            category = "custom"
            display_zh = metric_name
            display_en = metric_name
            description = "未提供定义，保留原始键；请勿按名称猜测含义。"
            source = confidence = "unknown"
    else:
        display_zh = display_zh or metric_name
        display_en = display_en or metric_name
        if category is None:
            if normalized in LOSS_NAMES or normalized.endswith("_loss"):
                category = "loss"
            elif normalized in LEARNING_RATE_NAMES or normalized.endswith("_lr"):
                category = "learning_rate"
            elif normalized in VALIDATION_SCORE_NAMES:
                category = "validation_score"
            else:
                category = "custom"
        builtin_display = _builtin_display(normalized, phase)
        if builtin_display:
            if not definition.get("display_name"):
                display_zh, display_en = builtin_display
            if not description:
                description = "含义来自安全别名；具体实现以训练配置为准。"
        description = description or ""
        if category == "loss":
            role = _loss_phase(phase)[0]
        elif category == "validation_score":
            role = "validation_score"
        elif category == "learning_rate":
            role = "learning_rate"

    if definition.get("is_primary"):
        role = "primary_validation"
    semantic_group = {
        "loss": "training_trend",
        "validation_score": "training_trend",
        "learning_rate": "training_trend",
        "performance": "performance",
        "system": "performance",
    }.get(category, "other")
    return {
        "raw_key": raw_key,
        "phase": phase,
        "metric_name": metric_name,
        "display_name_zh": display_zh or metric_name,
        "display_name_en": display_en or metric_name,
        "category": category,
        "semantic_group": semantic_group,
        "description": description or "",
        "definition": definition.get("definition"),
        "unit": unit,
        "direction": direction or "none",
        "aggregation": aggregation,
        "comparison_key": comparison_key,
        "source": source,
        "confidence": confidence,
        "is_primary": is_primary,
        "default_visibility": bool(definition.get("default_visibility", False)),
        "role": role,
        "group_path": [part for part in raw_key.split("/") if part],
    }


def value_profile(
    point_count: int,
    distinct_step: int,
    distinct_epoch: int,
    distinct_time: int,
) -> tuple[list[str], str, int, str]:
    """按不同有效 X 值区分连续序列与单点，行数不参与趋势判断。"""
    axes = []
    if distinct_step:
        axes.append("global_step")
    if distinct_epoch:
        axes.append("epoch")
    if distinct_time:
        axes.append("timestamp")
    distinct = max(distinct_step, distinct_epoch, distinct_time)
    if distinct >= 2:
        return axes, "continuous", distinct, "line"
    if point_count > 0:
        return axes, "single_point", distinct, "evaluation_table"
    return axes, "no_data", distinct, "raw"
