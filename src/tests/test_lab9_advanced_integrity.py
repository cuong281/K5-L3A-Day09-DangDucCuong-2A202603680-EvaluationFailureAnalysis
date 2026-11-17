"""M7: integrity checks beyond the public vectors (duplicates, crashed graders on a green run,
edited aggregates, slice relabelling, slice ratchet). Small hand-built reports, no shape run."""
import copy

import pytest

pytestmark = pytest.mark.student

ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": i != 3 or s != 2, "cost": 1.0,
         "slices": ["money_movement"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "seeds": [1, 2],
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9,
                    "no_significant_drop": True, "blocking": True}]}


def _report(rows):
    vals = [r["pass_rate"] for r in rows]
    return {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": rows,
            "metrics": {"pass_rate": round(sum(vals) / len(vals), 4)}, "evaluator_failures": []}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_advanced_honest_report_is_clean(gate):
    base = _report(copy.deepcopy(ROWS))
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_advanced_duplicated_rows_keep_count_but_are_caught(gate):
    base = _report(copy.deepcopy(ROWS))
    rows = [r for r in copy.deepcopy(ROWS) if r["pass_rate"]]
    rows.append(copy.deepcopy(rows[0]))                      # same count, failing row replaced
    assert any("duplicated" in p for p in gate.integrity_check(_report(rows), base, SPEC))


def test_advanced_evaluator_failures_on_a_green_run(gate):
    base = _report(copy.deepcopy(ROWS))
    pr = copy.deepcopy(base)
    pr["evaluator_failures"] = ["E-000@1:TrialPass:boom"]
    assert gate.integrity_check(pr, base, SPEC)


def test_advanced_edited_aggregate_is_caught(gate):
    base = _report(copy.deepcopy(ROWS))
    pr = copy.deepcopy(base)
    pr["metrics"]["pass_rate"] = 1.0                         # rows still hold a failure
    assert any("rows give" in p for p in gate.integrity_check(pr, base, SPEC))


def test_advanced_relabelled_slice_is_caught(gate):
    base = _report(copy.deepcopy(ROWS))
    rows = copy.deepcopy(ROWS)
    for r in rows:
        r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(_report(rows), base, SPEC))


@pytest.mark.parametrize("edit", [
    lambda s: s["slices"].clear(),
    lambda s: s["slices"][0].update(min=0.5),
    lambda s: s["slices"][0].pop("no_significant_drop"),
    lambda s: s["slices"][0].update(blocking=False),
    lambda s: s["metrics"][0]["threshold"].update(min=0.1),
    lambda s: s.update(eval_set_version="v2-renamed", metrics=[]),
])
def test_advanced_ratchet_covers_metrics_and_slices(gate, edit):
    base = _report(copy.deepcopy(ROWS))
    loose = copy.deepcopy(SPEC)
    edit(loose)
    assert any("ratchet" in p for p in gate.integrity_check(base, base, loose, SPEC))


def test_advanced_stricter_spec_is_allowed(gate):
    base = _report(copy.deepcopy(ROWS))
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["min"] = 0.85
    strict["slices"][0]["min"] = 0.95
    assert gate.integrity_check(base, base, strict, SPEC) == []
