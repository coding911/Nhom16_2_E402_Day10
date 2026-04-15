# Runbook — Lab Day 10 (incident tối giản)

**Maintainer:** HoangNgocThach  
**Cập nhật:** 2026-04-15  
**Áp dụng cho:** pipeline `etl_pipeline.py`, collection `day10_kb`, manifest tại `artifacts/manifests/`

---

## Symptom

Agent trả lời sai chính sách — ví dụ:
- Trả lời "**14 ngày làm việc**" khi khách hỏi hoàn tiền (đúng là 7 ngày).
- Trả lời "**10 ngày phép năm**" khi hỏi nghỉ phép nhân viên dưới 3 năm (đúng là 12 ngày).
- Retrieval trả về chunk cũ hoặc chunk chứa nội dung bị gắn "bản sync cũ / lỗi migration".

---

## Detection

Các metric sau đây báo có vấn đề:

| Metric | Vị trí | Dấu hiệu bất thường |
|--------|--------|---------------------|
| `hits_forbidden=yes` | `artifacts/eval/` CSV hoặc `grading_run.jsonl` | Chunk stale đang nằm trong Chroma |
| `expectation[...] FAIL (halt)` | `artifacts/logs/run_{run_id}.log` | Pipeline nên đã HALT — nhưng nếu dùng `--skip-validate` thì không |
| `freshness_check=FAIL` | `artifacts/logs/run_{run_id}.log` | Data quá cũ so với SLA (`age_hours >= sla_hours`) |
| `embed_prune_removed=0` sau inject | `artifacts/logs/run_{run_id}.log` | Prune không hoạt động — vector bẩn vẫn còn |
| `top1_doc_expected=no` | eval CSV | Top-1 result không phải doc mong đợi |

**Cách chạy eval nhanh:**
```bash
python eval_retrieval.py --out artifacts/eval/check_now.csv
```

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/manifest_{run_id}.json` | Có `run_id`, `cleaned_records`, `quarantine_records`; `freshness_check` PASS/FAIL |
| 2 | Mở `artifacts/quarantine/quarantine_{run_id}.csv` | Row bị lọc có `reason=stale_migration_marker / stale_hr_leave_text_10d / stale_hr_policy_effective_date` |
| 3 | Đọc `artifacts/logs/run_{run_id}.log` | Expectation nào FAIL; `embed_prune_removed` = ? |
| 4 | Chạy `python eval_retrieval.py --out artifacts/eval/check_now.csv` | So sánh `hits_forbidden` với CSV baseline |
| 5 | Kiểm tra dirty CSV `data/raw/policy_export_dirty.csv` | Có row mới chứa "14 ngày làm việc", "10 ngày phép năm", "bản sync cũ" không? |

**Ví dụ thực tế (Sprint 3 inject):**
- Log `run_inject-bad.log`: `expectation[refund_no_stale_14d_window] FAIL (halt)` và `expectation[hr_leave_no_stale_10d_annual] FAIL (halt)` — pipeline dùng `--skip-validate` nên vẫn tiếp tục embed → vector bẩn vào Chroma.
- Eval `before_inject_bad.csv`: `q_refund_window hits_forbidden=yes`, `q_leave_version hits_forbidden=yes`.

---

## Mitigation

**Trường hợp 1 — Stale chunk đã vào Chroma:**
```bash
# Chạy lại pipeline sạch (không có inject flags):
python etl_pipeline.py run --run-id sprint3-clean
# Prune sẽ xoá vector bẩn; log ghi embed_prune_removed=N
# Verify:
python eval_retrieval.py --out artifacts/eval/after_clean.csv
```

**Trường hợp 2 — Freshness FAIL (data stale):**
```bash
# Kiểm tra age_hours trong manifest:
cat artifacts/manifests/manifest_{run_id}.json | python -m json.tool
# Nếu data thật đã cũ: cần re-export từ nguồn hoặc tạm banner "data stale" cho agent
# Trong lab: FAIL là intentional (CSV mẫu exported_at=2026-04-10). Ghi rõ trong quality report.
# Để đổi SLA: FRESHNESS_SLA_HOURS=48 python etl_pipeline.py run --run-id sprint3-clean
```

**Trường hợp 3 — Pipeline HALT (expectation fail):**
```bash
# Xác định expectation nào fail từ log, sửa dirty CSV hoặc thêm cleaning rule,
# sau đó chạy lại:
python etl_pipeline.py run --run-id fix-{YYYYMMDD}
```

---

## Prevention

1. **Thêm expectation halt** cho mọi loại stale content mới — đừng chỉ dùng warn vì warn không ngăn embed.
2. **Không dùng `--skip-validate` trên production** — cờ này chỉ dành cho demo Sprint 3.
3. **Alert freshness:** khi `freshness_check=FAIL`, gửi alert tới `#data-alerts`. Trong lab dùng env `FRESHNESS_SLA_HOURS`; production dùng scheduler (cron / Airflow) giám sát manifest mỗi giờ.
4. **Kiểm tra `embed_prune_removed`** sau mỗi run — nếu prune_removed > 0 mà không có thay đổi dirty CSV, cần điều tra tại sao vector bị xoá (có thể cleaning rule thay đổi ngưỡng).
5. **Versioned data contract** (`contracts/data_contract.yaml`) — khi thêm doc_id mới, cập nhật `allowed_doc_ids` và `owners` trước khi đưa vào production. Owner phê duyệt quarantine cho doc_id của mình.
6. **Nối Day 11 (nếu có):** thêm LLM-judge vào eval để phát hiện các trường hợp keyword match nhưng nội dung không đúng ngữ nghĩa (false-positive trong keyword eval hiện tại).
