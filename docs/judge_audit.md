# Judge audit

Chạy (từ `src/`):

```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0, PASS floors
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 30   # exit 1, FAIL floors
```

FAIL là lớp dương: việc của judge là **tìm** reply lỗi. Backend là replay, verdict của judge lưu sẵn trong CSV.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | **dùng** (chỉ warn, không blocking) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ và R dưới sàn) | **loại** |

### Ma trận nhầm lẫn

| | Người FAIL | Người PASS |
|---|---|---|
| **tone_ok**: judge FAIL | tp 24 | fp 4 |
| **tone_ok**: judge PASS | fn 6 | tn 66 |
| **helpful**: judge FAIL | tp 9 | fp 0 |
| **helpful**: judge PASS | fn **21** | tn 70 |

Tỉ lệ lỗi hiệu chỉnh bằng Rogan-Gladen (sens = recall, spec = tn/(tn+fp)):

- tone_ok: quan sát 0.28, hiệu chỉnh 0.30. Judge lệch rất ít.
- helpful: quan sát 0.09, hiệu chỉnh 0.30. Judge chỉ thấy khoảng 1/3 số reply thật sự không hữu ích.

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em", thêm "nha" là quá suồng sã với khách khiếu nại; judge hiểu thành thân thiện. **Rubric:** thêm luật xưng hô "LogiX / anh/chị"; xưng "em/bạn" hoặc dùng tiểu từ "nha/nhé" là FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ … rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Luật ở #1 bắt được; thêm H-017 làm ví dụ FAIL trong rubric. |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi "Dạ, vui lòng"; "không cần nhắn thêm" là giọng ra lệnh. **Rubric:** chấm cả câu chứ không chấm theo từ lịch sự ở đầu câu; câu cấm khách liên hệ là FAIL. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". **Rubric:** không bắt buộc xin lỗi; câu ngắn, đủ ý, lễ phép là PASS. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Style guide CS LogiX cho phép từ "refund". **Rubric:** đưa danh sách thuật ngữ tiếng Anh được phép (refund, ship) vào prompt của judge. |
| 6 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (khi xét ngữ cảnh) | Ghi chú của bộ dữ liệu: người gán nhãn đọc nhầm ticket. **Hành động:** sửa nhãn người thành FAIL trước lần hiệu chỉnh sau. Không đổi rubric, vì lỗi nằm ở nhãn chứ không ở judge. |
| 7 | H-094 "Da, LogiX da hoan 40.000đ … xin loi vi su bat tien." | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). **Rubric:** reply không dấu là FAIL. Kiểm tra này nên làm bằng code (regex chữ có dấu) trước khi gọi judge. |
| 8 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger ghi 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết số tiền sai. 18/21 ca FN của helpful là loại này. **Không sửa rubric judge:** đây là FM-08, phải chấm bằng code (grader FM-08 so số trong reply với `snapshot.refund_vnd`). |
| 9 | HL-016 / HL-098: reply xin lỗi dài 3 câu, số tiền sai so với ledger | PASS | FAIL | Người | Judge thưởng cho độ dài và lời xin lỗi (verbosity bias). 13/21 ca FN là reply dài như vậy. **Rubric:** "helpful" = khách biết kết quả đúng và việc tiếp theo; độ dài và số lời xin lỗi không cộng điểm. |
| 10 | HL-047 / HL-091 / HL-097 "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả (hoàn hay từ chối, bao nhiêu tiền). **Rubric:** reply không nêu rõ trạng thái là FAIL. |

## Kết luận

- **Tiêu chí bị loại: `helpful`.**
  - Ma trận: tp 9, fp 0, fn 21, tn 70. Precision = 1.0 nghe tốt nhưng gây hiểu nhầm: judge gần như luôn nói PASS, nên khi nó nói FAIL thì đúng, nhưng nó bỏ sót 21/30 reply lỗi (recall 0.3, κ 0.375).
  - Dùng làm gate thì một bản tệ hơn vẫn qua: tỉ lệ lỗi quan sát 0.09 trong khi thật sự là khoảng 0.30 (Rogan-Gladen).
  - Nguyên nhân chính là 18/21 FN nằm ở số tiền sai so với ledger, và judge không có ledger trong input. Lỗi này phải chấm bằng code (FM-08, M3), không bằng judge: "tiền và approval luôn chấm bằng code".
- **Tiêu chí dùng được: `tone_ok`.**
  - Đạt cả 3 sàn: κ 0.757, P 0.857, R 0.8.
  - Chỉ dùng làm metric theo dõi (không blocking), vì 6 FN còn lại là lỗi xưng hô và giọng điệu mà rubric hiện tại chưa nói rõ (#1–#3, #7).
  - Sau khi sửa rubric theo bảng trên thì phải hiệu chỉnh lại trên nhãn mới, không dùng lại 100 dòng này.
- **Rủi ro còn lại:**
  - Judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí), nên cần nhãn người mới để có tập held-out thật.
  - H-081 cho thấy chính nhãn người cũng có lỗi; cần người thứ hai gán nhãn để đo κ giữa hai người làm trần.
  - Nhãn tone_ok có thể lệch theo người gán (ví dụ xưng "bạn" được chấp nhận ở vùng miền hoặc kênh khác).
