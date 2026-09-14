"""موتور آزمون: آماده‌سازی سؤال، بررسی پاسخ و تولید کارنامهٔ آزمون."""

from __future__ import annotations

import json

# دکمه‌های عددی فارسی برای انتخاب گزینه
OPTION_LABELS = ("۱", "۲", "۳", "۴", "۵", "۶")

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def normalize_digits(text: str) -> str:
    """ارقام فارسی/عربی را به ارقام لاتین تبدیل می‌کند."""
    out = []
    for ch in str(text):
        if ch in _PERSIAN_DIGITS:
            out.append(str(_PERSIAN_DIGITS.index(ch)))
        elif ch in _ARABIC_DIGITS:
            out.append(str(_ARABIC_DIGITS.index(ch)))
        else:
            out.append(ch)
    return "".join(out)


def parse_answer(text: str, option_count: int) -> int | None:
    """پاسخ کاربر را به ایندکس گزینه (۰-based) تبدیل می‌کند؛ None یعنی نامعتبر."""
    cleaned = normalize_digits(text).strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    # کاربر می‌تواند ۱..N بفرستد؛ صفر هم به‌عنوان گزینهٔ اول پذیرفته نمی‌شود.
    if 1 <= value <= option_count:
        return value - 1
    return None


def format_question(row, prefix: str = "🧠 آزمون") -> str:
    """متن قابل‌ارسال سؤال را می‌سازد."""
    options = json.loads(row["options"])
    lines = [f"{prefix} — {row['subject']}", "", row["question"], ""]
    for idx, option in enumerate(options):
        label = OPTION_LABELS[idx] if idx < len(OPTION_LABELS) else str(idx + 1)
        lines.append(f"{label}) {option}")
    lines.append("")
    lines.append("پاسخ را با شمارهٔ گزینه بفرستید (مثلاً ۲).")
    return "\n".join(lines)


def correct_index_of(row) -> int:
    return int(row["correct_index"])


def correct_option_text(row) -> str:
    options = json.loads(row["options"])
    return str(options[int(row["correct_index"])])


def score_summary(total: int, correct: int) -> str:
    if total == 0:
        return "هنوز در هیچ آزمونی شرکت نکرده‌اید."
    percent = correct * 100 / total
    return (
        f"📊 کارنامهٔ آزمون‌ها\n"
        f"تعداد پاسخ‌ها: {total}\n"
        f"پاسخ درست: {correct}\n"
        f"درصد موفقیت: {percent:.1f}٪"
    )
