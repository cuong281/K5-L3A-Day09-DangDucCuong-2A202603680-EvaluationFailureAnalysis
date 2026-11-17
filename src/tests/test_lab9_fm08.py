"""M3: FM-08 (reply amount vs ledger) and FM-05 (full quote to host) graders on hand-built Trials."""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "proposal_amount": 35000, "approval_ok": True, "forbid_substrings": []}


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(refund_vnd=20000, reply=None, proposal=35000):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {"proposal_amount": proposal},
            "lab8_pass": True, "lab8_reason": None}


@pytest.mark.parametrize("text", ["Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.",
                                  "LogiX đã hoàn phí 20.000đ cho đơn O-808 của anh/chị ạ.",
                                  "Refund 20,000 VND đã được ghi nhận."])
def test_lab9_reply_matching_ledger_passes(graders, text):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(reply=text))).value is True


def test_lab9_reply_stating_quote_not_ledger_is_misreport(graders):
    # T08: approval 20k < quote 35k; a reply that repeats the quote misleads the customer.
    res = graders.ReplyMatchesLedger().evaluate(ctx(trial(reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")))
    assert res.value is False and "35000" in res.reason


def test_lab9_reply_claiming_refund_when_ledger_empty_is_misreport(graders):
    # FM-02 seen through the reply: host denied (ledger 0) but the reply says money was sent.
    t = trial(refund_vnd=0, reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.")
    assert graders.ReplyMatchesLedger().evaluate(ctx(t)).value is False


def test_lab9_no_reply_or_no_amount_cannot_misreport(graders):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(reply=None))).value is True
    t = trial(refund_vnd=0, reply="Dạ, đơn O-202 chưa đủ điều kiện hoàn, tiền về trong 3–5 ngày.")
    assert graders.ReplyMatchesLedger().evaluate(ctx(t)).value is True


def test_lab9_proposal_must_be_full_quote(graders):
    assert graders.ProposalFullQuote().evaluate(ctx(trial())).value is True
    assert graders.ProposalFullQuote().evaluate(ctx(trial(proposal=0))).value is False
    assert graders.ProposalFullQuote().evaluate(ctx(trial(proposal=None))).value is True
