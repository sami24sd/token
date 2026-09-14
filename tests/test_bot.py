"""تست‌های پایه برای اجزای ربات."""

from __future__ import annotations

import json

from schoolbot.config import Config
from schoolbot.handlers import Bot, parse_command
from schoolbot.quiz import normalize_digits, parse_answer, score_summary
from schoolbot.schedule import (
    is_holiday,
    is_valid_hhmm,
    parse_weekday,
    persian_weekday_index,
    weekday_name,
)
from schoolbot.storage import Storage


def make_bot(tmp_path, admin_ids=(999,)):
    config = Config(admin_ids=admin_ids, data_dir=tmp_path, school_name="تست")
    storage = Storage(config.db_path)
    return Bot(config, storage), storage


# ---------------------------------------------------------------- schedule
def test_persian_weekday_index_and_names():
    from datetime import date

    # 2026-09-19 یک شنبه است (Saturday)
    assert persian_weekday_index(date(2026, 9, 19)) == 0
    assert weekday_name(date(2026, 9, 19)) == "شنبه"
    assert is_holiday(date(2026, 9, 19)) is False  # شنبه تعطیل نیست
    # 2026-09-25 جمعه
    assert persian_weekday_index(date(2026, 9, 25)) == 6
    assert is_holiday(date(2026, 9, 25)) is True


def test_parse_weekday_aliases():
    assert parse_weekday("sat") == 0
    assert parse_weekday("شنبه") == 0
    assert parse_weekday("thursday") == 5
    assert parse_weekday("جمعه") == 6
    assert parse_weekday("4") == 4


def test_hhmm_validation():
    assert is_valid_hhmm("08:00")
    assert is_valid_hhmm("23:59")
    assert not is_valid_hhmm("24:00")
    assert not is_valid_hhmm("8")


# -------------------------------------------------------------- parsing
def test_parse_command():
    assert parse_command("/start") == ("start", "")
    assert parse_command("/quiz ریاضی") == ("quiz", "ریاضی")
    assert parse_command("/report@MyBot") == ("report", "")
    assert parse_command("سلام") == ("", "سلام")


# ------------------------------------------------------------------ quiz
def test_normalize_digits_and_parse_answer():
    assert normalize_digits("۲") == "2"
    assert normalize_digits("۱۲۳") == "123"
    assert parse_answer("2", 3) == 1
    assert parse_answer("۲", 3) == 1
    assert parse_answer("4", 3) is None
    assert parse_answer("صفر", 3) is None


def test_score_summary():
    assert "شرکت نکرده" in score_summary(0, 0)
    assert "50.0" in score_summary(4, 2)


# --------------------------------------------------------------- storage
def test_storage_student_roundtrip(tmp_path):
    storage = Storage(tmp_path / "t.db")
    assert storage.get_student(1) is None
    storage.register_student(1, "علی", "دهم", user_id=42)
    student = storage.get_student(1)
    assert student.full_name == "علی"
    assert student.grade == "دهم"
    assert storage.count_students() == 1
    storage.close()


def test_storage_schedule_and_homework(tmp_path):
    storage = Storage(tmp_path / "t.db")
    storage.add_lesson("دهم", 0, 1, "ریاضی", "آقای احمدی", "08:00", "08:45")
    lessons = storage.lessons_for("دهم", 0)
    assert len(lessons) == 1
    assert lessons[0]["subject"] == "ریاضی"

    storage.add_homework("دهم", "ریاضی", "تمرین ۱", "2030-01-01", "صفحه ۱۰")
    hw = storage.homework_for_grade("دهم", "2026-01-01")
    assert len(hw) == 1

    # به‌روزرسانی همان زنگ نباید ردیف جدید بسازد
    storage.add_lesson("دهم", 0, 1, "فیزیک")
    assert len(storage.lessons_for("دهم", 0)) == 1
    assert storage.lessons_for("دهم", 0)[0]["subject"] == "فیزیک"
    storage.close()


def test_storage_grades_average(tmp_path):
    storage = Storage(tmp_path / "t.db")
    storage.register_student(1, "علی", "دهم")
    storage.add_grade(1, "ریاضی", "میان‌ترم", 18, 20)
    storage.add_grade(1, "فیزیک", "پایان‌ترم", 10, 20)
    assert storage.average_of(1) == 14.0
    assert storage.average_of(2) is None
    storage.close()


# ------------------------------------------------------------- quiz flow
def test_quiz_registration_and_answer(tmp_path):
    bot, storage = make_bot(tmp_path)

    # ثبت‌نام
    reply = bot.handle("/start", 10, 10, "علی")
    assert "نام و پایه" in reply.text
    reply = bot.handle("علی رضایی|دهم ریاضی", 10, 10, "علی")
    assert "ثبت‌نام انجام شد" in reply.text
    assert storage.get_student(10).grade == "دهم ریاضی"

    # افزودن سؤال توسط مدیر و پاسخ دانش‌آموز
    storage.add_quiz_question("دهم ریاضی", "ریاضی", "۲+۲ چند است؟", ["۳", "۴", "۵"], 1)
    quiz_reply = bot.handle("/quiz", 10, 10, "علی")
    assert "۲+۲" in quiz_reply.text
    assert quiz_reply.buttons, "دکمه‌های گزینه باید ساخته شوند"

    answer = bot.handle("2", 10, 10, "علی")
    assert "آفرین" in answer.text
    total, correct = storage.quiz_stats(10)
    assert (total, correct) == (1, 1)
    storage.close()


def test_quiz_wrong_answer(tmp_path):
    bot, storage = make_bot(tmp_path)
    bot.handle("/start", 11, 11, "سارا")
    bot.handle("سارا|دهم", 11, 11, "سارا")
    storage.add_quiz_question("دهم", "ریاضی", "۱+۱؟", ["۲", "۳"], 0)

    bot.handle("/quiz", 11, 11, "سارا")
    reply = bot.handle("2", 11, 11, "سارا")
    assert "نادرست" in reply.text
    total, correct = storage.quiz_stats(11)
    assert (total, correct) == (1, 0)
    storage.close()


def test_callback_answer(tmp_path):
    bot, storage = make_bot(tmp_path)
    bot.handle("/start", 12, 12, "مینا")
    bot.handle("مینا|دهم", 12, 12, "مینا")
    qid = storage.add_quiz_question("دهم", "ریاضی", "s", ["a", "b"], 1)
    bot.handle("/quiz", 12, 12, "مینا")
    reply = bot.answer_callback(12, f"quiz:{qid}:1")
    assert "آفرین" in reply.text
    storage.close()


# ----------------------------------------------------------- admin access
def test_admin_only_commands(tmp_path):
    bot, storage = make_bot(tmp_path, admin_ids=(999,))

    denied = bot.handle("/report", 10, 10, "دانش‌آموز")
    assert "مدیران" in denied.text

    allowed = bot.handle("/report", 999, 999, "مدیر")
    assert "گزارش" in allowed.text
    storage.close()


def test_add_lesson_validation(tmp_path):
    bot, storage = make_bot(tmp_path)
    bad = bot.handle("/addlesson خیلی کم", 999, 999, "مدیر")
    assert "قالب درست" in bad.text

    ok = bot.handle(
        "/addlesson دهم|شنبه|1|ریاضی|آقای احمدی|08:00|08:45", 999, 999, "مدیر"
    )
    assert "ثبت شد" in ok.text
    assert len(storage.lessons_for("دهم", 0)) == 1
    storage.close()


def test_add_question_validation(tmp_path):
    bot, storage = make_bot(tmp_path)
    ok = bot.handle(
        "/addquestion دهم|ریاضی|۲+۲ چند است؟|۳;۴;۵|2", 999, 999, "مدیر"
    )
    assert "ثبت شد" in ok.text
    assert storage.count_questions("دهم") == 1

    bad = bot.handle("/addquestion دهم|ریاضی|سؤال|فقط‌یک‌گزینه|1", 999, 999, "مدیر")
    assert "دو گزینه" in bad.text
    storage.close()


def test_set_grade_requires_registered_student(tmp_path):
    bot, storage = make_bot(tmp_path)
    missing = bot.handle("/setgrade 555|ریاضی|میان‌ترم|18|20", 999, 999, "مدیر")
    assert "ثبت‌نام نکرده" in missing.text

    storage.register_student(555, "رضا", "یازدهم")
    ok = bot.handle("/setgrade 555|ریاضی|میان‌ترم|18|20", 999, 999, "مدیر")
    assert "ثبت شد" in ok.text
    assert storage.average_of(555) == 18.0
    storage.close()


def test_unregistered_student_blocked(tmp_path):
    bot, _ = make_bot(tmp_path)
    reply = bot.handle("/today", 777, 777, "ناشناس")
    assert "ثبت‌نام" in reply.text