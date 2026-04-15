# Quality Report — Lab Day 10

**run_id:** sprint3-clean  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Before (inject-bad) | After (sprint3-clean) | Ghi chú |
|--------|---------------------|-----------------------|---------|
| raw_records | 14 | 14 | Cùng dirty CSV (14 rows) |
| cleaned_records | 7 | 6 | inject-bad embed Row 13+14 bẩn; clean loại cả hai |
| quarantine_records | 7 | 8 | clean thêm Rule 4 bắt Row 14 |
| Expectation halt? | **YES** — 2 fail (skip-validate) | **NO** — tất cả pass | inject: `refund_no_stale_14d_window` + `hr_leave_no_stale_10d_annual` FAIL |

---

## 2. Before / after retrieval

File đính kèm:
- **Before:** `artifacts/eval/before_inject_bad.csv` (run_id=inject-bad)
- **After:** `artifacts/eval/after_clean.csv` (run_id=sprint3-clean)

### Câu hỏi then chốt: refund window (`q_refund_window`)

| Trạng thái | top1_doc_id | top1_preview | contains_expected | hits_forbidden |
|------------|-------------|--------------|-------------------|----------------|
| **Before** (inject-bad) | policy_refund_v4 | "Hoàn tiền phải được yêu cầu trong vòng **14 ngày** làm việc..." | yes | **yes** |
| **After** (sprint3-clean) | policy_refund_v4 | "Yêu cầu được gửi trong vòng **7 ngày** làm việc..." | yes | **no** |

**Giải thích:** inject-bad dùng `--no-refund-fix` giữ nguyên Row 13 ("14 ngày làm việc") và embed nó. Chroma trả về chunk stale làm top-1 → `hits_forbidden=yes`. Sau khi pipeline sạch chạy với refund-fix, Row 13 được sửa thành "7 ngày" và Row 14 bị quarantine → Chroma chỉ còn chunk đúng → `hits_forbidden=no`.

---

### Merit: HR leave version (`q_leave_version`)

| Trạng thái | top1_doc_id | top1_preview | contains_expected | hits_forbidden | top1_doc_expected |
|------------|-------------|--------------|-------------------|----------------|-------------------|
| **Before** (inject-bad) | hr_leave_policy | "Nhân viên dưới 3 năm... **12 ngày** phép năm..." | yes | **yes** | yes |
| **After** (sprint3-clean) | hr_leave_policy | "Nhân viên dưới 3 năm... **12 ngày** phép năm..." | yes | **no** | yes |

**Giải thích:** inject-bad embed Row 14 (hr_leave_policy, "10 ngày phép năm", 2026-02-01) vì `--skip-validate` bỏ qua E6 halt. Top-k blob chứa cả "12 ngày" lẫn "10 ngày phép năm" → `hits_forbidden=yes`. Sau khi Rule 4 (`stale_hr_leave_text_10d`) được thêm, Row 14 bị quarantine trong clean run → blob chỉ còn "12 ngày" → `hits_forbidden=no`.

---

## 3. Freshness & monitor

| run_id | latest_exported_at | age_hours | sla_hours | status |
|--------|--------------------|-----------|-----------|--------|
| inject-bad | 2026-04-10T08:00:00 | 121.4 | 24 | **FAIL** |
| sprint3-clean | 2026-04-10T08:00:00 | 121.5 | 24 | **FAIL** |

SLA được set 24 giờ (`FRESHNESS_SLA_HOURS=24`). CSV mẫu cố tình dùng `exported_at=2026-04-10T08:00:00` (cũ hơn 5 ngày) để minh hoạ kịch bản data stale. Trên production, FAIL sẽ kích hoạt alert `#data-alerts` và block agent deploy đọc data lỗi thời. Trong lab, `freshness_check=FAIL` không ngăn `PIPELINE_OK` vì freshness là thông tin monitoring, không là halt gate.

---

## 4. Corruption inject (Sprint 3)

**Cách inject:**

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

| Loại corruption | Row | Cơ chế | Expectation bị fail |
|-----------------|-----|--------|---------------------|
| Stale refund window | Row 13 — "14 ngày làm việc" (không có migration marker) | `--no-refund-fix` giữ nguyên "14 ngày" trong chunk_text | `refund_no_stale_14d_window` FAIL |
| Stale HR leave version | Row 14 — "10 ngày phép năm", effective_date 2026-02-01 | Vượt qua date rule (ngày 2026), `--skip-validate` bỏ qua E6 | `hr_leave_no_stale_10d_annual` FAIL |

**Cách phát hiện:** log inject-bad ghi rõ:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```

**Cách fix:** chạy lại clean pipeline (không có inject flags) — Rule 4 (`stale_hr_leave_text_10d`) quarantine Row 14, refund-fix sửa Row 13 → tất cả expectation pass → embed clean index.

---

## 5. Hạn chế & việc chưa làm

- `freshness_check=FAIL` là intentional trên CSV mẫu (xem mục 3). Chưa cấu hình WARN threshold (24h < age < 48h).
- Chưa chạy `grading_run.py` (public sau 17:00).
- Eval dùng keyword-based (không LLM-judge) — có thể có false-positive nếu keyword xuất hiện trong context không liên quan.
- Rule 2 (`chunk_too_short`, < 20 chars) và Rule 3 (`missing_exported_at`) chưa có inject scenario riêng trong eval CSV — được minh chứng qua quarantine log.
