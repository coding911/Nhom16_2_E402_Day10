# Báo cáo cá nhân — Lại Đức Anh

**Họ và tên:** Lại Đức Anh  
**Vai trò:** Sprint 1–2 owner: Ingestion, cleaning rules, validation và embed idempotent  

---

## 1. Phụ trách

Tôi chịu trách nhiệm chính cho Sprint 1 và 2, bao gồm đọc dữ liệu raw, mapping schema và thiết kế luồng cleansing. Cụ thể, tôi triển khai phần core của `etl_pipeline.py` cho ingest, logging run, tạo manifest và đưa các record vào `artifacts/cleaned/` cùng `artifacts/quarantine/`.

Trong `transform/cleaning_rules.py`, tôi thêm rule mới để bắt stale migration marker, quarantine chunk quá ngắn và quarantine missing exported_at. Tôi cũng đảm bảo rule fix refund 14→7 được áp dụng trước khi embed.

Trên `quality/expectations.py`, tôi kiểm soát hai expectation mới để phát hiện stale migration marker và đánh giá độ đa dạng doc_id. Tôi liên kết output cleaned với manifest và log, đảm bảo run repeatable và dễ truy vết.

---

## 2. Quyết định kỹ thuật

Tôi chọn model “quarantine trước, warn sau” cho những lỗi làm sai dữ liệu đầu vào. Với `exported_at` sai format, giải pháp là loại khỏi cleaned để không ảnh hưởng freshness. Với chunk quá ngắn và text rỗng, tôi dùng quarantine vì những record này không đủ context cho retrieval an toàn.

Đối với idempotency, tôi giữ nguyên cách upsert `chunk_id` và thêm bước prune vector id cũ không còn trong batch sau mỗi publish. Quyết định này giảm rủi ro `hits_forbidden=true` do vector stale còn sót lại.

---

## 3. Sự cố / anomaly

Khi test lần đầu, tôi phát hiện `eligible` record có `doc_id` lạ và `exported_at` trống vẫn vào cleaned, khiến `freshness_check` báo lỗi. Tôi sửa rule để quarantine bất kỳ record nào thiếu `exported_at`, đồng thời cập nhật expectation để cảnh báo nếu distinct doc_id giảm xuống dưới ngưỡng.

Một issue khác là duplicate text có cùng `chunk_id` bị chồng lên khi embed. Tôi xử lý bằng cách duy trì `chunk_id` cố định và prune id không xuất hiện trong batch hiện tại.

---

## 4. Before/after

**Trước:** pipeline ban đầu cho phép một số record stale vào cleaned, dẫn đến retrieval có `hits_forbidden=yes` cho câu `q_refund_window`.

**Sau:** sau khi bổ sung rule quarantine stale migration marker và fix refund window, file `artifacts/eval/after_clean.csv` cho thấy `hits_forbidden=no` cho `q_refund_window` và `q_leave_version`. Log run chuẩn cũng hiển thị expectation novel OK.

---

## 5. Cải tiến thêm 2 giờ

Tôi mở rộng module để đọc cutoff HR `2026-01-01` từ `contracts/data_contract.yaml` thay vì hard-code. Việc này giúp rule linh hoạt hơn khi chuyển sang dữ liệu thực tế và dễ cập nhật SLA trong tương lai.
