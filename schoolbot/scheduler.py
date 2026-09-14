"""سرویس زمان‌بند: ارسال خودکار برنامهٔ روزانه، تکالیف، آزمون و گزارش هفتگی."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .config import Config
from .messages import format_homework, format_lessons, today_title
from .quiz import OPTION_LABELS, format_question
from .schedule import (
    is_holiday,
    now_in,
    parse_weekday,
    weekday_name,
)
from .storage import Storage
from .telegram import TelegramClient

log = logging.getLogger("schoolbot.scheduler")


@dataclass
class Clock:
    """ساعت ساده برای تست‌پذیری."""

    config: Config

    def today(self):
        return now_in(self.config.timezone).date()

    def hhmm(self) -> str:
        return now_in(self.config.timezone).strftime("%H:%M")


def _already_sent(storage: Storage, key: str, day) -> bool:
    return storage.get_state(f"{key}:{day.isoformat()}") == "1"


def _mark_sent(storage: Storage, key: str, day) -> None:
    storage.set_state(f"{key}:{day.isoformat()}", "1")


class Scheduler:
    """بررسی زمان‌بندی‌ها و ارسال پیام‌های خودکار."""

    def __init__(
        self,
        config: Config,
        storage: Storage,
        client: TelegramClient,
        clock: Clock | None = None,
    ):
        self.config = config
        self.storage = storage
        self.client = client
        self.clock = clock or Clock(config)

    def tick(self) -> int:
        """یک بار بررسی می‌کند و تعداد پیام‌های ارسالی را برمی‌گرداند."""
        sent = 0
        today = self.clock.today()
        current = self.clock.hhmm()

        if current == self.config.daily_send_time and not _already_sent(self.storage, "daily", today):
            sent += self._send_daily(today)
            _mark_sent(self.storage, "daily", today)

        if current == self.config.quiz_send_time and not _already_sent(self.storage, "quiz", today):
            sent += self._send_quiz(today)
            _mark_sent(self.storage, "quiz", today)

        weekly_day = parse_weekday(self.config.weekly_report_weekday)
        if (
            (today.weekday() + 2) % 7 == weekly_day
            and current == self.config.weekly_report_time
            and not _already_sent(self.storage, "weekly", today)
        ):
            sent += self._send_weekly_report()
            _mark_sent(self.storage, "weekly", today)

        return sent

    # ------------------------------------------------------------ senders
    def _send_daily(self, today) -> int:
        """ارسال برنامهٔ روز + تکالیف سررسید به همهٔ دانش‌آموزان."""
        count = 0
        holiday = is_holiday(today)
        weekday = (today.weekday() + 2) % 7

        for student in self.storage.all_students():
            if holiday:
                text = f"🌴 امروز {weekday_name(today)} تعطیل است."
            else:
                lessons = self.storage.lessons_for(student.grade, weekday)
                text = format_lessons(lessons, today_title(today))

            due = self.storage.homework_due_on(student.grade, today.isoformat())
            if due:
                text += "\n\n" + format_homework(due, "⏰ تکالیف سررسید امروز")

            self.client.send_message(student.chat_id, text)
            count += 1
        log.info("برنامهٔ روزانه برای %d دانش‌آموز ارسال شد", count)
        return count

    def _send_quiz(self, today) -> int:
        """ارسال یک سؤال آزمون به هر دانش‌آموز، بر اساس پایهٔ او."""
        count = 0
        for student in self.storage.all_students():
            row = self.storage.random_question(student.grade)
            if row is None:
                continue

            options = json.loads(row["options"])

            buttons = [
                [
                    (
                        OPTION_LABELS[i] if i < len(OPTION_LABELS) else str(i + 1),
                        f"quiz:{row['id']}:{i}",
                    )
                ]
                for i in range(len(options))
            ]
            self.storage.set_state(f"pending_quiz:{student.chat_id}", str(row["id"]))
            self.client.send_message(student.chat_id, format_question(row), keyboard=buttons)
            count += 1
        log.info("آزمون روزانه برای %d دانش‌آموز ارسال شد", count)
        return count

    def _send_weekly_report(self) -> int:
        """ارسال گزارش هفتگی به مدیران."""
        lines = [f"📊 گزارش هفتگی {self.config.school_name}", ""]
        students = self.storage.all_students()
        lines.append(f"تعداد دانش‌آموزان: {len(students)}")

        grades: dict[str, int] = {}
        for student in students:
            grades[student.grade] = grades.get(student.grade, 0) + 1
        for grade, qty in sorted(grades.items()):
            lines.append(f"• {grade}: {qty} دانش‌آموز")

        # میانگین نمرات کل مدرسه
        averages = [
            avg
            for avg in (self.storage.average_of(s.chat_id) for s in students)
            if avg is not None
        ]
        if averages:
            lines.append(f"میانگین نمرات مدرسه: {sum(averages) / len(averages):.2f} از ۲۰")

        text = "\n".join(lines)
        for admin_id in self.config.admin_ids:
            self.client.send_message(admin_id, text)
        return len(self.config.admin_ids)
