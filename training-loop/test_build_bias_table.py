import json

import build_bias_table as bbt


def test_clamp_caps_at_max_delta():
    out, warnings = bbt.clamp_deltas({"kale": 5.0}, {"kale": 1.0}, 0.2)
    assert out == {"kale": 1.2}
    assert len(warnings) == 1


def test_zero_predictions_count(tmp_path, monkeypatch):
    rows = [{"item_type_label": "kale", "weight_lbs_true": 10, "weight_lbs_pred": 10}] * 5
    rows += [{"item_type_label": "kale", "weight_lbs_true": 10, "weight_lbs_pred": 0}] * 5
    log = tmp_path / "residuals.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(bbt, "RESIDUAL_LOG", log)

    table, stats = bbt.build_table(min_samples=5)
    assert stats["kale"]["samples"] == 10
    assert table["kale"] > 1
