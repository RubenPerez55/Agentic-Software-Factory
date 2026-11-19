"""Deterministic checks on the eval dataset (no Gemini calls; runs in CI)."""

import json
from pathlib import Path

DATASETS = Path(__file__).resolve().parent / "datasets"
ROOT = Path(__file__).resolve().parents[2]
VALID_RECOMMENDATIONS = {"PROCEED", "HUMAN_CLARIFICATION_REQUIRED"}


def _load(name: str) -> dict:
    return json.loads((DATASETS / name).read_text(encoding="utf-8"))


def test_every_eval_case_has_expectation():
    case_ids = {c["eval_case_id"] for c in _load("basic-dataset.json")["eval_cases"]}
    expectations = _load("expectations.json")["cases"]
    assert case_ids == set(expectations), "dataset and expectations must cover the same cases"
    for case_id, exp in expectations.items():
        assert exp["recommendation"] in VALID_RECOMMENDATIONS, case_id
        assert list(ROOT.glob(f"change_requests/{exp['change_request']}-*.md")), case_id


def test_cr005_ambiguous_case_must_stop():
    cases = {c["eval_case_id"]: c for c in _load("basic-dataset.json")["eval_cases"]}
    prompt = cases["ambiguous_requirement"]["prompt"]["parts"][0]["text"]
    assert "CR-005" in prompt

    exp = _load("expectations.json")["cases"]["ambiguous_requirement"]
    assert exp["recommendation"] == "HUMAN_CLARIFICATION_REQUIRED"
    assert exp["expected_state"] == "AWAITING_CLARIFICATION"
    assert "write implementation code" in exp["must_not"]
