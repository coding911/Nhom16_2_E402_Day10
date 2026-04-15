# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** 16_2  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Lại Đức Anh | Sprint 1–2 owner: ingestion, schema mapping, cleaning rules, quarantine, validate, idempotent embed | laiducanh26112004@gmail.com |
| Hoàng Ngọc Thạch | Sprint 3 owner: inject corruption, before/after retrieval eval, quality report | hnthach97@gmail.com |
| Nguyễn Minh Trí | Sprint 4 owner: monitoring, freshness check, runbook, docs hoàn thiện và báo cáo cuối | coding0911@gmail.com |

**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/coding911/Nhom16_2_E402_Day10  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

Pipeline đọc file `data/raw/policy_export_dirty.csv` (12 dòng raw, gồm duplicate, dữ liệu thiếu, ngày sai format, doc_id lạ, version cũ, và marker migration lỗi). Qua `transform/cleaning_rules.py`, mỗi dòng lần lượt qua 9 rule: allowlist doc_id → chuẩn hoá ngày → quarantine HR cũ → quarantine text rỗng → quarantine stale migration marker → quarantine chunk quá ngắn → quarantine missing exported_at → dedupe → fix refund 14→7. Kết quả ghi vào `artifacts/cleaned/` và `artifacts/quarantine/`. Sau đó `quality/expectations.py` chạy 8 expectation (6 baseline + 2 mới); nếu không có halt thì embed upsert vào ChromaDB (`day10_kb`), ghi manifest và kiểm freshness SLA. `run_id` lấy từ log: `run_id=sprint2`.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

```bash
python etl_pipeline.py run --run-id sprint2
```

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau (số liệu) | Chứng cứ |
|-----------------------------------|-----------------|---------------|----------|
| **R1: stale_migration_marker** — quarantine chunk chứa "bản sync cũ", "lỗi migration", "policy-v3" | `sprint1`: cleaned=6, quarantine=4; Row 3 lọt vào Chroma với nội dung "(ghi chú: bản sync cũ policy-v3)" | `sprint2`: cleaned=5, quarantine=5; Row 3 → quarantine với `reason=stale_migration_marker` | `artifacts/quarantine/quarantine_sprint2.csv` dòng 2 |
| **R2: chunk_too_short** — quarantine chunk_text < 20 ký tự | Không bắt được Row 11 ("Reset.", 6 chars) — lọt vào pipeline | Row 11 → quarantine với `reason=chunk_too_short, chunk_length=6` | `artifacts/quarantine/quarantine_sprint2.csv` dòng 6 |
| **R3: missing_exported_at** — quarantine chunk không có exported_at | Không bắt được Row 12 (exported_at rỗng) — freshness không tính được | Row 12 → quarantine với `reason=missing_exported_at` | `artifacts/quarantine/quarantine_sprint2.csv` dòng 7 |
| **E7: no_stale_migration_marker** (halt) — cleaned không chứa "bản sync cũ" | Nếu chạy `--no-refund-fix --skip-validate` với bộ Sprint 3: Row 3 lọt vào cleaned → **E7 FAIL** (`violations=1`) | Sprint 2 chuẩn: `expectation[no_stale_migration_marker] OK (halt) :: violations=0` | `artifacts/logs/run_sprint2.log` |
| **E8: min_distinct_doc_ids_3** (warn) — ít nhất 3 doc_id khác nhau | Nếu inject xoá hết chunks của 2 doc_id: `distinct_doc_ids=1 → WARN` | Sprint 2 chuẩn: `expectation[min_distinct_doc_ids_3] OK (warn) :: distinct_doc_ids=4` | `artifacts/logs/run_sprint2.log` |

| **R4: stale_hr_leave_text_10d** — quarantine hr_leave_policy chunk có "10 ngày phép năm" (xung đột nội dung bản 2025 với ngày 2026) | inject-bad: Row 14 lọt vào Chroma → `q_leave_version hits_forbidden=yes` | sprint3-clean: Row 14 quarantined → `q_leave_version hits_forbidden=no` | `artifacts/eval/before_inject_bad.csv` vs `after_clean.csv` |

**Rule chính (baseline + mở rộng):**

- **Baseline (6 rule):** allowlist doc_id, chuẩn hoá ngày DD/MM/YYYY→ISO, quarantine HR stale (date < 2026-01-01), quarantine text rỗng, dedupe chunk_text, fix refund 14→7 ngày.
- **Mới (4 rule):** stale_migration_marker, chunk_too_short (< 20 chars), missing_exported_at, stale_hr_leave_text_10d.

**Ví dụ 1 lần expectation fail và cách xử lý:**

Sprint 3 (inject): chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` → Row 3 không bị Rule 1 bắt vì `skip-validate` chỉ bỏ qua expectation halt, không bỏ qua cleaning rule. Tuy nhiên nếu tắt Rule 1 trong code, E7 `no_stale_migration_marker` sẽ FAIL với `violations=1`, pipeline HALT. Xử lý: re-enable Rule 1 và chạy lại `run --run-id sprint2`.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Cờ `--no-refund-fix` giữ nguyên "14 ngày làm việc" trong chunk text; `--skip-validate` cho phép embed dù expectation FAIL. Sau đó chạy lại pipeline chuẩn và so sánh eval.

**Kết quả định lượng (từ CSV / bảng):**

| Câu hỏi | Trạng thái | contains_expected | hits_forbidden | top1_doc_expected |
|---------|------------|-------------------|----------------|-------------------|
| `q_refund_window` | Before (inject-bad) | yes | **yes** | — |
| `q_refund_window` | After (sprint3-clean) | yes | **no** | — |
| `q_leave_version` | Before (inject-bad) | yes | **yes** | yes |
| `q_leave_version` | After (sprint3-clean) | yes | **no** | yes |

Files: `artifacts/eval/before_inject_bad.csv` và `artifacts/eval/after_clean.csv`.

Retrieval cải thiện rõ rệt sau clean: cả 2 câu then chốt đổi `hits_forbidden` từ **yes → no**, chứng minh pipeline loại được chunk stale ra khỏi Chroma trước khi agent truy vấn.

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

SLA freshness mặc định là **24 giờ** (biến môi trường `FRESHNESS_SLA_HOURS=24`). Pipeline đo freshness tại boundary **publish** — tức là so sánh `latest_exported_at` trong cleaned records với thời điểm chạy pipeline.

- **PASS:** `age_hours < sla_hours` — data đủ mới, agent có thể tin tưởng vector store.
- **WARN:** _(hiện chưa có threshold riêng; có thể mở rộng: 24h < age < 48h)_
- **FAIL:** `age_hours >= sla_hours` — data cũ hơn SLA. Trong manifest `sprint2`: `age_hours=121.21, sla_hours=24.0` → FAIL vì CSV mẫu có `exported_at=2026-04-10T08:00:00` (cố tình cũ để minh hoạ). Trên production, trạng thái FAIL kích hoạt alert qua `#data-alerts` và ngăn agent deploy mới đọc data lỗi thời.

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

Day 10 dùng collection `day10_kb` (tách khỏi collection Day 09) để đảm bảo **publish boundary** rõ ràng — agent Day 09 không bị ảnh hưởng khi pipeline Day 10 inject corruption hoặc chạy thử nghiệm. Sau khi pipeline Day 10 ổn định (sprint2 `PIPELINE_OK`), collection `day10_kb` có thể được multi-agent Day 09 tham chiếu thêm bằng cách đổi biến môi trường `CHROMA_COLLECTION=day10_kb` trong `.env` của Day 09 — cùng một `chroma_db` path, không cần re-embed.

---

## 6. Rủi ro còn lại & việc chưa làm

- `grading_run.jsonl` chưa tạo — `grading_questions.json` công khai sau 17:00; chạy `python grading_run.py --out artifacts/eval/grading_run.jsonl` sau khi file được publish.
- Freshness SLA hiện `FAIL` vì CSV mẫu dùng `exported_at=2026-04-10T08:00:00` (cố tình cũ để minh hoạ). Giải thích đầy đủ trong `docs/runbook.md` mục Mitigation. Trong lab, `freshness_check=FAIL` không chặn `PIPELINE_OK` vì freshness là monitoring, không phải halt gate.
- Eval dùng keyword-based (không LLM-judge) — có thể false-positive nếu keyword xuất hiện trong context không liên quan (ghi nhận trong `docs/quality_report.md` mục Hạn chế).
- Rule 2 (`chunk_too_short`) và Rule 3 (`missing_exported_at`) chưa có inject scenario riêng trong eval CSV — minh chứng qua `artifacts/quarantine/quarantine_sprint2.csv` dòng 6–7.
