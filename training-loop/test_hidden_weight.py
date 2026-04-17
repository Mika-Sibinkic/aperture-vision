#!/usr/bin/env python3
"""Unit test: prove weight never leaks into the vision prompt.

We monkeypatch requests.post, feed a sample through evaluate_one, and assert
no digit+unit token matches the true weight in the captured request body.

Runs in CI on every commit. If this fails, the hidden-weight protocol is
broken and the training loop is not scientifically valid — halt.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import evaluator  # noqa: E402


WEIGHT_PATTERN = re.compile(r"\b(\d{1,4}(?:\.\d{1,3})?)\s*(lb|lbs|pound|pounds|kg|g|oz)\b", re.I)


class HiddenWeightTest(unittest.TestCase):
    def test_weight_not_in_prompt_openai(self) -> None:
        tmp_img = ROOT / "images"
        tmp_lbl = ROOT / "labels"
        tmp_img.mkdir(exist_ok=True)
        tmp_lbl.mkdir(exist_ok=True)

        # Synthetic sample with an OBVIOUS weight in the label.
        sha = "deadbeef" + "0" * 8
        (tmp_img / f"{sha}.jpg").write_bytes(b"\xff\xd8\xff\xd9")  # bare JPEG SOI/EOI
        (tmp_lbl / f"{sha}.json").write_text(json.dumps({
            "weight_lbs": 17.42, "item_type": "test can", "source": "unit_test",
            "source_url": "about:test", "sha": sha, "scraped_at": "2026-01-01T00:00:00Z",
        }))

        captured: dict[str, str] = {}

        def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
            captured["url"] = url
            captured["body"] = __import__("json").dumps(json)
            m = MagicMock()
            m.raise_for_status = lambda: None
            m.json = lambda: {"choices": [{"message": {"content": '{"weight_lbs":15.1,"item_type":"test","confidence":0.5}'}}]}
            return m

        import requests
        with patch.object(requests, "post", side_effect=fake_post), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            system = evaluator.load_system_prompt()
            fingerprint = evaluator.prompt_fingerprint(system)
            evaluator.evaluate_one(sha, "openai", "gpt-4o", system, fingerprint)

        # Scan the captured request body for any weight token.
        matches = WEIGHT_PATTERN.findall(captured.get("body", ""))
        leaked = [m for m in matches if m[0] == "17.42" or m[0] == "17" or m[0] == "17.4"]
        self.assertFalse(
            leaked,
            f"weight leaked into prompt: {matches} (body: {captured.get('body', '')[:500]})",
        )

        # Cleanup
        (tmp_img / f"{sha}.jpg").unlink()
        (tmp_lbl / f"{sha}.json").unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
