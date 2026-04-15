"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")

# Rule 1 (mới): từ khóa chỉ dấu tài liệu đã bị migration lỗi hoặc sync từ version cũ.
# Tác động đo được: Row 3 trong dirty CSV chứa "bản sync cũ" + "lỗi migration" →
#   quarantine_records tăng 4→5, cleaned_records giảm 6→5 so với baseline sprint1.
_STALE_MIGRATION_PATTERNS = re.compile(
    r"bản sync cũ|lỗi migration|policy-v3|outdated_sync|stale_import",
    re.IGNORECASE,
)

# Rule 2 (mới): ngưỡng tối thiểu chunk hữu ích = 20 ký tự.
# Tác động đo được: Row 11 ("Reset.", 6 chars) mới thêm vào dirty CSV → quarantine +1.
CHUNK_MIN_USEFUL_LENGTH = 20

# Rule 3 (mới): exported_at bắt buộc — dùng để tính freshness SLA.
# Tác động đo được: Row 12 (exported_at rỗng) mới thêm vào dirty CSV → quarantine +1.


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ / conflict version).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) [Mới] Quarantine: chunk chứa stale migration marker (bản sync cũ / lỗi migration / policy-v3).
    6) [Mới] Quarantine: chunk_text < 20 ký tự (quá ngắn, không hữu ích cho retrieval).
    7) [Mới] Quarantine: exported_at rỗng (không tính được freshness SLA).
    8) [Mới] Quarantine: hr_leave_policy chunk chứa "10 ngày phép năm" (xung đột nội dung bản 2025).
    9) Loại trùng nội dung chunk_text (giữ bản đầu).
    10) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        # Rule 4 (mới) — stale_hr_leave_text:
        # Quarantine hr_leave_policy chunk còn ghi "10 ngày phép năm" dù effective_date đã 2026
        # (xung đột nội dung: bản 2025 bị copy nhầm sang row có ngày 2026).
        # Tác động đo được: Row 14 (hr_leave_policy, "10 ngày phép năm", 2026-02-01) bị
        #   quarantine trong clean run → q_leave_version: hits_forbidden đổi yes→no.
        if doc_id == "hr_leave_policy" and "10 ngày phép năm" in text:
            quarantine.append({**raw, "reason": "stale_hr_leave_text_10d"})
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # Rule 1 (mới) — stale_migration_marker:
        # Quarantine chunk còn dấu vết migration lỗi / sync từ version cũ.
        if _STALE_MIGRATION_PATTERNS.search(text):
            quarantine.append({**raw, "reason": "stale_migration_marker"})
            continue

        # Rule 2 (mới) — chunk_too_short:
        # Quarantine chunk quá ngắn (< 20 ký tự) — không đủ nội dung để retrieval hữu ích.
        if len(text) < CHUNK_MIN_USEFUL_LENGTH:
            quarantine.append({**raw, "reason": "chunk_too_short", "chunk_length": len(text)})
            continue

        # Rule 3 (mới) — missing_exported_at:
        # Quarantine chunk không có exported_at — không thể tính freshness SLA.
        if not exported_at:
            quarantine.append({**raw, "reason": "missing_exported_at"})
            continue

        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
