"""Prove the true weight never reaches the vision API.

evaluate_one is run against a sample whose label says 17.42 lb, with
requests.post faked for each provider. The captured request body must not
mention that weight. If this fails, the hidden-weight protocol is broken and
the training loop's numbers mean nothing.
"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluator  # noqa: E402

WEIGHT_PATTERN = re.compile(r"\b(\d{1,4}(?:\.\d{1,3})?)\s*(lb|lbs|pound|pounds|kg|g|oz)\b", re.I)
ANSWER = '{"weight_lbs":15.1,"item_type":"test","confidence":0.5}'
FAKE_RESPONSES = {
    "openai": {"choices": [{"message": {"content": ANSWER}}]},
    "anthropic": {"content": [{"text": ANSWER}]},
}


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_weight_not_in_request(provider, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "IMAGE_DIR", tmp_path)
    monkeypatch.setattr(evaluator, "LABEL_DIR", tmp_path)
    monkeypatch.setattr(evaluator, "RESIDUAL_LOG", tmp_path / "residuals.jsonl")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    sha = "deadbeef00000000"
    (tmp_path / f"{sha}.jpg").write_bytes(b"\xff\xd8\xff\xd9")  # bare JPEG SOI/EOI
    (tmp_path / f"{sha}.json").write_text(json.dumps({"weight_lbs": 17.42, "item_type": "test can"}))

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["body"] = __import__("json").dumps(json)
        return MagicMock(raise_for_status=lambda: None, json=lambda: FAKE_RESPONSES[provider])

    system = evaluator.load_system_prompt()
    with patch.object(evaluator.requests, "post", side_effect=fake_post):
        record = evaluator.evaluate_one(sha, provider, "model", system, evaluator.prompt_fingerprint(system))

    body = captured["body"]
    assert "17.42" not in body
    leaked = [m for m in WEIGHT_PATTERN.findall(body) if m[0] in ("17", "17.4", "17.42")]
    assert not leaked, f"weight leaked into prompt: {leaked}"
    assert record["weight_lbs_true"] == 17.42  # label was read, after the call
