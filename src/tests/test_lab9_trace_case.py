"""Regression test for docs/trace_case.md: seeded_regression C-002@11 (FM-03, ticket over DB).

The first wrong step is event 3 `model_override` (delay_days 5 from the ticket, DB says 2).
`fixed` must not take that step and must deny; the buggy variant must be caught.
"""
import pytest

pytestmark = pytest.mark.student


def _kinds(trial):
    return [e.get("kind") for e in trial["events"]]


def test_lab9_trace_case_seeded_regression_overrides_db_and_refunds():
    from lab9.trace_case import investigate

    case = investigate("seeded_regression", "C-002", 11)
    t = case["trial"]
    assert _kinds(t)[2] == "model_override"
    assert t["events"][2]["payload"] == {"delay_days": 5}
    assert t["snapshot"]["refund_vnd"] == 20000 != case["label"]["refund_vnd"]
    assert not t["lab8_pass"]


def test_lab9_trace_case_fixed_keeps_db_fact_and_denies():
    from lab9.trace_case import investigate

    case = investigate("fixed", "C-002", 11)
    t = case["trial"]
    assert "model_override" not in _kinds(t)
    assert t["result"]["status"] == "denied"
    assert t["snapshot"]["refund_vnd"] == 0
    assert t["lab8_pass"]
