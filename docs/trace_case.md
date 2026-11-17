# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression C-002@11` (T02, FM-03)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`. Run ID: `<điền run_id của reports/eval_seeded_regression.json sau M4>` |
| Triệu chứng | Grader Lab 8 FAIL (`status resolved != denied`). Ledger ghi `refund_vnd=20000`, `refund_count=1`; label là 0 và 0, status `denied`. Event 6 `reply` nói "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." |
| Bước sai đầu tiên | Event **3** `model_override` `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng contract (`check_applicable_policy`, đúng allowlist tool). Event 2 `investigator` đọc đúng order O-202, `delay_days=2` trong DB. Event 3 ghi đè số đó bằng "trễ 5 ngày" lấy từ ticket. Mọi bước sau đều đúng **với dữ liệu đã bị sửa**: event 4 `quote` 20.000 (SHIP-LATE-03 cho ≥3 ngày), event 5 `refund_history` và host ghi refund. |
| Failure mode | FM-03 (ticket_trust). Cùng lỗi xuất hiện ở `swarm C-002@55`, event 3. |
| Đối chứng | `fixed C-002@11`: event 2 giống hệt, **không có** `model_override`, event 3 `quote` `{"amount_vnd": 0, "reason": "no_entitlement"}`, status `denied`, ledger 0, PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`:<br>• `test_lab9_trace_case_seeded_regression_overrides_db_and_refunds`: event 3 là `model_override` 5 ngày, ledger 20.000, grader Lab 8 FAIL.<br>• `test_lab9_trace_case_fixed_keeps_db_fact_and_denies`: không có override, `denied`, ledger 0, PASS.<br>Cả hai đã chạy xanh. Trong eval, grader `DbFactKept` (metric `db_fact_kept`) và `pass_rate` cũng bắt trial này. |
| Chưa chắc chắn | Trace không ghi lời gọi host `issue_refund`, nên việc host chấp nhận ghi refund chỉ suy ra từ ledger. MockLLM ra quyết định override theo luật cố định (switch `ticket_trust`; với `swarm` là seed chia hết cho 5), nên trace không cho biết một LLM thật sẽ override thường xuyên tới mức nào. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
