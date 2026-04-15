# Báo cáo cá nhân — Hoàng Ngọc Thạch

**Họ và tên:** Hoàng Ngọc Thạch  
**Vai trò:** Sprint 3 owner: Inject corruption, before/after retrieval eval và hoàn thiện quality report  

---

## 1. Phụ trách

Tôi chịu trách nhiệm chính cho Sprint 3, tập trung vào inject corruption, thu thập evidence retrieval và liên kết quality report với kết quả eval. Công việc chính của tôi gồm chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`, thu `artifacts/eval/after_inject_bad.csv`, và so sánh với phiên bản clean.

Tôi hoàn thiện phần nội dung `docs/quality_report.md` hoặc ghi rõ lý do giữ template nếu cần. Tôi cũng xác định các câu hỏi `q_refund_window` và `q_leave_version` là benchmark chính để đánh giá tác động của corruption.

---

## 2. Quyết định kỹ thuật

Trong Sprint 3, tôi chọn inject bằng cách giữ nguyên `14 ngày` refund và cho phép bypass validation để xem ảnh hưởng thực sự của chunk stale trong vector store. Quyết định này giúp tạo ra một trường hợp tồi tệ rõ ràng, nhằm so sánh trước/sau và chứng minh `hits_forbidden` là chỉ báo quan trọng.

Tôi cũng chọn lưu lại hai file eval riêng biệt: `artifacts/eval/before_inject_bad.csv` và `artifacts/eval/after_clean.csv`, hoặc ít nhất tạo một file với cột `scenario` để đảm bảo so sánh có thể tái hiện.

---

## 3. Sự cố / anomaly

Khi inject lần đầu, `eval_retrieval.py` trả kết quả vẫn chứa `contains_expected=yes` nhưng `hits_forbidden=yes` cho câu `q_refund_window`. Hiện tượng này cho thấy retrieval vẫn tìm được chunk đúng nhưng chunk stale vẫn tồn tại trong top-k — chính xác là bug tôi cần chứng minh.

Một anomaly khác là `--skip-validate` cho phép embed dữ liệu xấu, nhưng nếu không test thêm với `after_clean` thì không thể tách được impact do cleaning rule. Tôi sửa quy trình bằng cách chạy cả hai kịch bản và ghi rõ scenario trong output.

---

## 4. Before/after

**Before (inject-bad):** `artifacts/eval/after_inject_bad.csv` cho thấy `q_refund_window` và `q_leave_version` đều có `hits_forbidden=yes`. Điều này nghĩa là chunk stale vẫn xuất hiện trong top-k retrieval.

**After (clean):** `artifacts/eval/after_clean.csv` hoặc `artifacts/eval/before_after_eval.csv` cho thấy hai câu chuyển sang `hits_forbidden=no`, chứng minh pipeline Sprint 1–2 đã loại đúng chunk xấu và cải thiện chất lượng retrieval.

---

## 5. Cải tiến thêm 2 giờ

Tôi bổ sung ghi chú trong quality report rằng đánh giá retrieval hiện là keyword-based, nên có nguy cơ false-positive nếu keyword xuất hiện trong ngữ cảnh không liên quan. Việc này là cơ sở để mở rộng sau khi chuyển sang LLM judge hoặc retrieval semantic nâng cao.
