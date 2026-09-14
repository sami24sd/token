"""تست‌های زمان‌بند و پردازش آپدیت‌های تلگرام."""

from __future__ import annotations

from datetime import date

from schoolbot.config import Config
from schoolbot.handlers import Bot
from schoolbot.runner import handle_update
from schoolbot.scheduler import Clock, Scheduler
from schoolbot.storage import Storage
from schoolbot.telegram import FakeTelegram


class FixedClock:
    def __init__(self, day: date, hhmm: str):
        self._day = day
        self._hhmm = hhmm

    def today(self):
        return self._day

    def hhmm(self):
        return self._hhmm


def make_env(tmp_path, clock, **overrides):
    config = Config(
        admin_ids=(999,),
        data_dir=tmp_path,
        daily_send_time="07:00",
        quiz_send_time="18:00",
        weekly_report_weekday="friday",
        weekly_report_time="20:00",
        **overrides,
    )
    storage = Storage(config.db_path)
    client = FakeTelegram()
    # 2026-09-19 شنبه / 2026-09-25 جمعه
    scheduler = Scheduler(config, storage, client, clock=FixedClock(**clock))
    return config, storage, client, scheduler


def test_daily_broadcast_on_saturday(tmp_path):
    config, storage, client, scheduler = make_env(
        tmp_path, {"day": date(2026, 9, 19), "hhmm": "07:00"}
    )
    storage.register_student(1, "علی", "دهم")
    storage.add_lesson("دهم", 0, 1, "ریاضی")

    sent = scheduler.tick()
    assert sent == 1
    assert "برنامهٔ امروز" in client.last_text()
    assert "ریاضی" in client.last_text()
    storage.close()


def test_daily_not_resent_same_day(tmp_path):
    config, storage, client, scheduler = make_env(
        tmp_path, {"day": date(2026, 9, 19), "hhmm": "07:00"}
    )
    storage.register_student(1, "علی", "دهم")
    assert scheduler.tick() == 1
    assert scheduler.tick() == 0  # بار دوم همان روز ارسال نمی‌شود
    storage.close()


def test_holiday_daily_short_message(tmp_path):
    # 2026-09-25 جمعه → تعطیل
    config, storage, client, scheduler = make_env(
        tmp_path, {"day": date(2026, 9, 25), "hhmm": "07:00"}
    )
    storage.register_student(1, "علی", "دهم")
    scheduler.tick()
    assert "تعطیل" in client.last_text()
    storage.close()


def test_quiz_broadcast(tmp_path):
    config, storage, client, scheduler = make_env(
        tmp_path, {"day": date(2026, 9, 19), "hhmm": "18:00"}
    )
    storage.register_student(1, "علی", "دهم")
    storage.add_quiz_question("دهم", "ریاضی", "۲+۲؟", ["۳", "۴"], 1)

    sent = scheduler.tick()
    assert sent == 1
    assert "آزمون" in client.last_text()
    assert client.sent[-1]["keyboard"], "دکمه‌های آزمون باید ارسال شوند"
    storage.close()


def test_weekly_report_to_admin(tmp_path):
    config, storage, client, scheduler = make_env(
        tmp_path, {"day": date(2026, 9, 25), "hhmm": "20:00"}
    )
    storage.register_student(1, "علی", "دهم")
    storage.add_grade(1, "ریاضی", "میان‌ترم", 20, 20)

    sent = scheduler.tick()
    assert sent == 1
    assert client.sent[0]["chat_id"] == 999
    assert "گزارش هفتگی" in client.last_text()
    storage.close()


def test_handle_update_message_and_callback(tmp_path):
    config = Config(admin_ids=(), data_dir=tmp_path)
    storage = Storage(config.db_path)
    bot = Bot(config, storage)
    client = FakeTelegram()

    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": 5, "type": "private"},
            "from": {"id": 5, "first_name": "علی"},
            "text": "/start",
        },
    }
    handle_update(bot, client, update)
    assert "خوش آمدید" in client.last_text()

    # پیام گروهی باید نادیده گرفته شود
    before = len(client.sent)
    handle_update(
        bot,
        client,
        {
            "update_id": 2,
            "message": {
                "chat": {"id": -100, "type": "group"},
                "from": {"id": 5},
                "text": "/start",
            },
        },
    )
    assert len(client.sent) == before
    storage.close()