# Báo cáo cá nhân — Nguyễn Minh Trí

**Họ và tên:** Nguyễn Minh Trí  
**Vai trò:** Sprint 4 owner: monitoring, freshness check, runbook, docs hoàn thiện và báo cáo tổng hợp  

---

## 1. Phụ trách

Tôi chịu trách nhiệm chính cho Sprint 4, bao gồm phần monitoring và hoàn thiện tài liệu. Công việc cụ thể của tôi là chạy `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2.json`, kiểm tra các trạng thái PASS/WARN/FAIL, và viết phần giải thích trong `docs/runbook.md`.

Tôi cũng đảm nhận việc soạn thảo phần `docs/pipeline_architecture.md`, cập nhật `docs/data_contract.md` và hoàn thiện `reports/group_report.md` trước khi nộp. Tôi ghi rõ quy trình chạy end-to-end và evidence artifacts ngay trong báo cáo.

---

## 2. Quyết định kỹ thuật

Trong phần monitoring, tôi định nghĩa rõ `freshness` là khoảng thời gian giữa `latest_exported_at` của cleaned records và thời điểm chạy pipeline. Nếu `age_hours >= sla_hours` thì manifest trả `FAIL`, còn `age_hours < sla_hours` thì `PASS`.

Tôi giữ freshness là metric giám sát, không phải gate halt của pipeline, vì mục đích lab là quan sát data observability. Nếu cần nâng cấp, bước tiếp theo sẽ là thêm cảnh báo `WARN` khi `age_hours` nằm trong vùng trung gian.

---

## 3. Sự cố / anomaly

Khi kiểm tra manifest Sprint 2, tôi thấy `freshness` có thể `FAIL` do file raw mẫu chứa `exported_at` cũ. Đây không phải lỗi syntax mà là case test rõ ràng: pipeline hoạt động đúng, nhưng data đã quá hạn SLA. Tôi ghi chi tiết anomaly này trong runbook và đề xuất khắc phục bằng cập nhật nguồn raw.

Một vấn đề khác là runbook ban đầu chưa nêu rõ cách chọn `run_id` và artifact path. Tôi bổ sung hướng dẫn copy/paste command và xác nhận `artifacts/manifests/manifest_sprint2.json` là input cho freshness check.

---

## 4. Before/after

**Before:** docs và report chỉ có outline, chưa kết nối rõ evidence artifact.

**After:** tôi hoàn thiện phần “Freshness & monitoring” trong `reports/group_report.md`, ghi rõ `artifacts/manifests/manifest_sprint2.json` và `artifacts/eval/after_clean.csv`. Tôi cũng cập nhật `docs/runbook.md` để bất kỳ reviewer nào cũng có thể chạy lại pipeline và hiểu PASS/WARN/FAIL.

---

## 5. Cải tiến thêm 2 giờ

Tôi bổ sung phần hướng dẫn peer review trong runbook, nêu các câu hỏi kiểm thử cho team và cách kiểm tra `grading_run.jsonl` sau khi ra mắt. Điều này giúp nhóm chuyển từ demo nhanh sang checklist production-ready.
