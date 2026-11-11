"""One learning cycle end to end, offline: fake Sheet rows in, tables out."""
import json
from pathlib import Path

from learning import run_cycle, sheets_puller

# true/pred = 1.2: inside the absolute [0.80, 1.25] band, but a 20% jump.
ROWS = [
    {"donation_id": f"d{i}", "true_weight_lbs": "12", "weight_lbs_raw": "10", "item_type": "Kale"}
    for i in range(3)
]


def run(tmp_path, monkeypatch, prior_bias=None):
    monkeypatch.setattr(sheets_puller, "pull_rows", lambda sheet_id: iter(ROWS))
    monkeypatch.setattr(run_cycle, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_cycle, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(run_cycle, "PUBLIC_STATE_DIR", tmp_path / "public" / "learned-state")
    if prior_bias is not None:
        (tmp_path / "public").mkdir(parents=True, exist_ok=True)
        (tmp_path / "public" / "bias-table.json").write_text(json.dumps(prior_bias))
    run_cycle.cycle_once("sheet-id", dry_run=True)
    return json.loads((tmp_path / "public" / "bias-table.json").read_text())


def test_repo_root_is_the_repo():
    assert (run_cycle.REPO_ROOT / "training-loop" / "learning" / "run_cycle.py").exists()
    assert run_cycle.PUBLIC_STATE_DIR == run_cycle.REPO_ROOT / "public" / "learned-state"


def test_first_cycle_writes_tables(tmp_path, monkeypatch):
    table = run(tmp_path, monkeypatch)
    assert table.keys() == {"kale"} and abs(table["kale"] - 1.2) < 1e-9  # EMA of equal ratios
    assert (tmp_path / "public" / "learned-state" / "learned-densities.json").exists()
    assert (tmp_path / "state" / "ground-truth-log.jsonl").exists()


def test_prior_caps_the_next_multiplier(tmp_path, monkeypatch):
    table = run(tmp_path, monkeypatch, prior_bias={"kale": 1.0})
    assert abs(table["kale"] - 1.05) < 1e-9
