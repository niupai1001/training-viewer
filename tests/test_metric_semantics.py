from training_viewer.metrics.metric_semantics import resolve_metric_semantics, value_profile


def test_aliases_do_not_guess_unknown_or_replace_declared_display() -> None:
    loss = resolve_metric_semantics(
        "train/loss", "train", "loss", {"direction": "min", "unit": "none"}
    )
    assert loss["display_name_zh"] == "训练损失"
    assert loss["role"] == "train_loss"

    unknown = resolve_metric_semantics(
        "train/epoch_QUIVALENT", "train", "epoch_QUIVALENT", {}
    )
    assert unknown["display_name_zh"] == "epoch_QUIVALENT"
    assert unknown["source"] == "unknown"
    assert unknown["category"] == "custom"

    declared = resolve_metric_semantics(
        "val/miou", "val", "miou", {"display_name": "项目自定义分数", "direction": "max", "unit": "ratio"}
    )
    assert declared["display_name_zh"] == "项目自定义分数"
    assert declared["source"] == "declared"


def test_value_profile_uses_distinct_x_not_row_count() -> None:
    assert value_profile(200, 1, 1, 1)[1] == "single_point"
    assert value_profile(2, 2, 0, 0)[1] == "continuous"
    assert value_profile(1, 0, 0, 0)[1] == "single_point"
