# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| **CS — Chính sách hoàn tiền** (`policy_refund_v4`) | CSV export từ hệ thống quản lý policy nội bộ (`policy/refund-v4.pdf`) | Chunk mang nội dung version cũ (14 ngày thay vì 7 ngày); trùng lặp do export nhiều lần; thiếu `effective_date` | `quarantine_records` tăng bất thường; expectation `refund_no_stale_14d_window` FAIL |
| **IT Helpdesk FAQ** (`it_helpdesk_faq`) | CSV export từ hệ thống ticket IT (`support/helpdesk-faq.md`) | Ngày hiệu lực sai định dạng (DD/MM/YYYY thay vì YYYY-MM-DD); chunk_text rỗng do lỗi extract | `quarantine_records` tăng với lý do `invalid_effective_date_format` hoặc `missing_chunk_text` |
| **HR — Chính sách nghỉ phép** (`hr_leave_policy`) | CSV export từ hệ thống HR (`hr/leave-policy-2026.pdf`) | Xung đột version: bản 2025 (10 ngày phép) lẫn với bản 2026 (12 ngày phép) cùng tồn tại trong export | `quarantine_records` tăng với lý do `stale_hr_policy_effective_date`; expectation `hr_leave_no_stale_10d_annual` FAIL |
| **IT SLA P1 2026** (`sla_p1_2026`) | CSV export từ hệ thống SLA (`support/sla-p1-2026.pdf`) | doc_id không khớp allowlist nếu đổi tên file nguồn | `quarantine_records` tăng với lý do `unknown_doc_id` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | Hash SHA-256 ổn định từ `doc_id + chunk_text + seq`, dạng `{doc_id}_{seq}_{16hex}` |
| doc_id | string | Có | Khóa logic tài liệu; phải thuộc allowlist trong `cleaning_rules.ALLOWED_DOC_IDS` |
| chunk_text | string | Có | Nội dung đoạn văn sau clean; độ dài tối thiểu 8 ký tự |
| effective_date | date | Có | ISO 8601 `YYYY-MM-DD`; tự động chuẩn hoá từ `DD/MM/YYYY` nếu có thể |
| exported_at | datetime | Có | Timestamp lúc export từ hệ thống nguồn, dùng tính freshness SLA |

---

## 3. Quy tắc quarantine vs drop

Record bị flag bởi bất kỳ rule nào trong `transform/cleaning_rules.py` sẽ bị chuyển sang **quarantine** (không drop hẳn), lưu vào `artifacts/quarantine/quarantine_{run_id}.csv` kèm cột `reason`.

| Reason | Mô tả | Hành động |
|--------|-------|-----------|
| `unknown_doc_id` | doc_id không thuộc allowlist | Quarantine; cần Data Owner review và cập nhật allowlist nếu doc mới hợp lệ |
| `missing_effective_date` | Trường `effective_date` rỗng | Quarantine; yêu cầu hệ thống nguồn cung cấp lại bản có đầy đủ ngày |
| `invalid_effective_date_format` | Ngày không parse được (không phải YYYY-MM-DD hay DD/MM/YYYY) | Quarantine; Engineering fix format trước khi re-ingest |
| `stale_hr_policy_effective_date` | HR chunk có `effective_date < 2026-01-01` (bản HR 2025) | Quarantine; HR Owner xác nhận đã có bản 2026 thay thế |
| `missing_chunk_text` | chunk_text rỗng | Quarantine; loại bỏ sau 7 ngày nếu không có re-export |
| `duplicate_chunk_text` | Nội dung trùng bản đã xử lý | Quarantine (giữ bản đầu tiên); không cần approve |

**Ai approve merge lại:** Data Owner của từng `doc_id` (xem bảng source map trên). Không có record nào được tự động unquarantine.

---

## 4. Phiên bản & canonical

| doc_id | File canonical | Version hiện tại | Ghi chú |
|--------|---------------|-----------------|---------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` (nguồn gốc: `policy/refund-v4.pdf`) | v4 — cửa sổ hoàn tiền **7 ngày** | Bất kỳ chunk nào nhắc đến "14 ngày làm việc" là stale từ v3 |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` (nguồn gốc: `hr/leave-policy-2026.pdf`) | 2026 — **12 ngày phép** cho NV < 3 năm | Bản 2025 (10 ngày) bị quarantine theo `stale_hr_policy_effective_date` |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` (nguồn gốc: `support/helpdesk-faq.md`) | 2026-01-20 | Cập nhật mỗi quý hoặc khi có thay đổi quy trình |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` (nguồn gốc: `support/sla-p1-2026.pdf`) | 2026 | SLA P1: 15 phút initial response, 4 giờ resolution |

**Nguyên tắc:** mọi thay đổi policy phải cập nhật file canonical trước, sau đó chạy lại pipeline để embed version mới. Không sửa trực tiếp vào CSV export.
