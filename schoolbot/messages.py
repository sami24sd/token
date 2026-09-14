"""کمک‌تابع‌های ساخت متن پیام برای دانش‌آموزان و مدیر."""

from __future__ import annotations

from datetime import date

from .schedule import WEEKDAYS_FA, weekday_name


def format_lessons(rows, title: str) -> str:
    if not rows:
        return f"{title}\nکلاسی ثبت نشده است (تعطیل یا بدون برنامه)."
    lines = [title, ""]
    for row in rows:
        time_part = ""
        if row["start_time"]:
            time_part = f" ({row['start_time']}–{row['end_time']})" if row["end_time"] else f" ({row['start_time']})"
        teacher = f" — {row['teacher']}" if row["teacher"] else ""
        lines.append(f"{row['period']}. {row['subject']}{teacher}{time_part}")
    return "\n".join(lines)


def format_homework(rows, title: str = "📚 تکالیف") -> str:
    if not rows:
        return f"{title}\nتکلیف فعالی ثبت نشده است."
    lines = [title, ""]
    for row in rows:
        desc = f"\n   ↳ {row['description']}" if row["description"] else ""
        lines.append(f"• [{row['subject']}] {row['title']} — مهلت: {row['due_date']}{desc}")
    return "\n".join(lines)


def weekday_name_of_index(index: int) -> str:
    index = int(index)
    return WEEKDAYS_FA[index] if 0 <= index < len(WEEKDAYS_FA) else "نامشخص"


def format_week(rows) -> str:
    if not rows:
        return "برنامهٔ هفتگی ثبت نشده است."
    lines = ["🗓 برنامهٔ هفتگی", ""]
    current_day = None
    for row in rows:
        if row["weekday"] != current_day:
            current_day = row["weekday"]
            lines.append(f"— {weekday_name_of_index(current_day)} —")
        lines.append(f"  {row['period']}. {row['subject']}")
    return "\n".join(lines)


def format_grades(rows) -> str:
    if not rows:
        return "📝 نمره‌ای ثبت نشده است."
    lines = ["📝 نمرات", ""]
    for row in rows:
        lines.append(
            f"• {row['subject']} | {row['title']}: "
            f"{row['score']:g} از {row['max_score']:g}"
        )
    return "\n".join(lines)


def today_title(day: date | None = None) -> str:
    day = day or date.today()
    return f"📌 برنامهٔ امروز ({weekday_name(day)} {day.isoformat()})"
