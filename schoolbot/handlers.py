"""هستهٔ منطق ربات: هر دستور یک تابع خالص است که متن پاسخ برمی‌گرداند.

توابع این ماژول به شبکه وابسته نیستند؛ همین باعث می‌شود بتوان
بدون اتصال به تلگرام، کل رفتار ربات را تست کرد.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from . import quiz as quiz_mod
from .config import Config
from .messages import (
    format_grades,
    format_homework,
    format_lessons,
    format_week,
    today_title,
)
from .schedule import (
    WEEKDAYS_FA,
    is_holiday,
    is_valid_hhmm,
    now_in,
    parse_weekday,
)
from .storage import Storage

HELP_TEXT = """🎓 ربات آموزشی مدرسه

دستورات دانش‌آموز:
/start — ثبت‌نام
/help — راهنما
/today — برنامهٔ امروز
/week — برنامهٔ هفتگی
/homework — تکالیف فعال
/grades — نمرات من
/average — معدل من
/quiz [درس] — آزمون تمرینی
/score — کارنامهٔ آزمون‌ها
/profile — پروفایل من
/mystats — آمار من

دستورات مدیر مدرسه:
/addlesson پایه|روز|زنگ|درس|معلم|ساعت‌شروع|ساعت‌پایان
/addlearning پایه|درس|عنوان|مهلت|توضیح      (تکلیف)
/addquestion پایه|درس|سؤال|گزینه۱;گزینه۲;...|شمارهٔ پاسخ
/setgrade شناسهٔ‌چت|درس|عنوان|نمره|نمرهٔ‌کل
/broadcast متن                            (پیام همگانی)
/report — گزارش مدیریتی
/export — خروجی JSON از داده‌ها
"""

REGISTER_RE = re.compile(r"^([^|]+)\|([^|]+)$")


@dataclass
class Reply:
    """پاسخ یک دستور: متن + دکمه‌های اختیاری + پرچم شخصی‌سازی."""

    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)
    parse_mode: str | None = None

    def keyboard(self) -> list[list[dict[str, str]]]:
        return [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in self.buttons
        ]


def parse_command(raw_text: str) -> tuple[str, str]:
    """متن خام را به (دستور, آرگومان) تبدیل می‌کند."""
    text = (raw_text or "").strip()
    if not text:
        return "", ""
    if not text.startswith("/"):
        return "", text
    parts = text.split(maxsplit=1)
    command = parts[0].lstrip("/").split("@")[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""
    return command, argument


def _split_args(argument: str, count: int) -> list[str] | None:
    """آرگومان را با جداکنندهٔ | به تعدادی بخش تقسیم می‌کند."""
    parts = [p.strip() for p in argument.split("|")]
    if len(parts) != count:
        return None
    return parts


def _require_student(storage: Storage, chat_id: int) -> tuple[str, str] | None:
    student = storage.get_student(chat_id)
    if student is None:
        return None
    return student.full_name, student.grade


class Bot:
    """مدیریت دستورات با دسترسی به ذخیره‌سازی و تنظیمات."""

    def __init__(self, config: Config, storage: Storage):
        self.config = config
        self.storage = storage

    # ------------------------------------------------------------ helpers
    def is_admin(self, chat_id: int, user_id: int | None) -> bool:
        if not self.config.admin_ids:
            return False
        return chat_id in self.config.admin_ids or (
            user_id is not None and user_id in self.config.admin_ids
        )

    def _admin_only(self, chat_id: int, user_id: int | None) -> str | None:
        if not self.is_admin(chat_id, user_id):
            return "⛔️ این دستور فقط برای مدیران مدرسه در دسترس است."
        return None

    # ------------------------------------------------------------ dispatch
    def handle(
        self,
        text: str,
        chat_id: int,
        user_id: int | None = None,
        user_name: str = "کاربر",
    ) -> Reply:
        command, argument = parse_command(text)

        if command == "start":
            return self._cmd_start(chat_id, user_name, argument)

        # اگر کاربر در جریان ثبت‌نام است، پیام غیردستوری را به‌عنوان نام|پایه می‌گیریم.
        if (
            self.storage.get_state(f"registering:{chat_id}")
            and command == ""
            and argument
        ):
            return self._cmd_start(chat_id, user_name, text)

        if command in ("help", "") and not argument:
            return Reply(HELP_TEXT)
        if command == "" and argument:
            # پاسخ عددی به آزمون فعال
            pending = self.storage.get_state(f"pending_quiz:{chat_id}")
            if pending:
                return self._answer_quiz(chat_id, int(pending), text)
            return Reply("🤖 متوجه نشدم. برای دیدن راهنما /help را بفرستید.")

        student = _require_student(self.storage, chat_id)

        handlers = {
            "today": self._cmd_today,
            "week": self._cmd_week,
            "homework": self._cmd_homework,
            "grades": self._cmd_grades,
            "average": self._cmd_average,
            "quiz": self._cmd_quiz,
            "score": self._cmd_score,
            "profile": self._cmd_profile,
            "mystats": self._cmd_mystats,
        }

        if command in handlers:
            if student is None:
                return Reply("ابتدا با /start ثبت‌نام کنید.")
            return handlers[command](chat_id, argument, student)

        admin_handlers = {
            "addlesson": lambda: self._cmd_add_lesson(chat_id, user_id, argument),
            "addhomework": lambda: self._cmd_add_homework(chat_id, user_id, argument),
            "addlearning": lambda: self._cmd_add_homework(chat_id, user_id, argument),
            "addquestion": lambda: self._cmd_add_question(chat_id, user_id, argument),
            "setgrade": lambda: self._cmd_set_grade(chat_id, user_id, argument),
            "broadcast": lambda: self._cmd_broadcast(chat_id, user_id, argument),
            "report": lambda: self._cmd_report(chat_id, user_id),
            "export": lambda: self._cmd_export(chat_id, user_id),
        }

        if command in admin_handlers:
            return admin_handlers[command]()

        return Reply("🤖 دستور ناشناخته. برای دیدن راهنما /help را بفرستید.")

    # ----------------------------------------------------------- commands
    def _cmd_start(self, chat_id: int, user_name: str, argument: str) -> Reply:
        student = self.storage.get_student(chat_id)
        if student is not None:
            return Reply(
                f"👋 {student.full_name} عزیز، خوش آمدید!\n"
                f"پایهٔ شما: {student.grade}\n\n"
                "برای دیدن برنامهٔ امروز /today را بزنید."
            )

        match = REGISTER_RE.match(argument) if argument else None
        if not match:
            self.storage.set_state(f"registering:{chat_id}", "1")
            return Reply(
                "🎓 به ربات آموزشی خوش آمدید!\n\n"
                "لطفاً نام و پایهٔ خود را در یک پیام و به این شکل بفرستید:\n"
                "«علی رضایی|دهم ریاضی»\n\n"
                "(نام | پایه)"
            )

        self.storage.delete_state(f"registering:{chat_id}")
        full_name, grade = match.group(1).strip(), match.group(2).strip()
        self.storage.register_student(chat_id, full_name, grade)
        return Reply(
            f"✅ ثبت‌نام انجام شد، {full_name} عزیز!\n"
            f"پایهٔ شما: {grade}\n\n"
            "برای دیدن برنامهٔ امروز /today را بزنید."
        )

    def _cmd_today(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        _, grade = student
        today = now_in(self.config.timezone).date()
        if is_holiday(today):
            text = format_lessons([], today_title(today)) + "\n🌴 امروز تعطیل است."
        else:
            weekday = (today.weekday() + 2) % 7
            lessons = self.storage.lessons_for(grade, weekday)
            text = format_lessons(lessons, today_title(today))

        due_today = self.storage.homework_due_on(grade, today.isoformat())
        if due_today:
            text += "\n\n" + format_homework(due_today, "⏰ تکالیف سررسید امروز")
        return Reply(text)

    def _cmd_week(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        _, grade = student
        return Reply(format_week(self.storage.week_schedule(grade)))

    def _cmd_homework(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        _, grade = student
        return Reply(format_homework(self.storage.homework_for_grade(grade)))

    def _cmd_grades(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        return Reply(format_grades(self.storage.grades_of(chat_id)))

    def _cmd_average(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        avg = self.storage.average_of(chat_id)
        if avg is None:
            return Reply("هنوز نمره‌ای برای شما ثبت نشده است.")
        return Reply(f"📈 معدل شما: {avg:.2f} از ۲۰")

    def _cmd_quiz(
        self, chat_id: int, argument: str, student: tuple[str, str]
    ) -> Reply:
        _, grade = student
        subject = argument.strip() or None
        if self.storage.count_questions(grade) == 0:
            return Reply("هنوز سؤالی برای پایهٔ شما ثبت نشده است.")

        row = self.storage.random_question(grade, subject)
        if row is None:
            return Reply(f"سؤالی برای درس «{subject}» ثبت نشده است.")

        self.storage.set_state(f"pending_quiz:{chat_id}", str(row["id"]))
        options = json.loads(row["options"])
        buttons = [
            [(quiz_mod.OPTION_LABELS[i] if i < len(quiz_mod.OPTION_LABELS) else str(i + 1),
              f"quiz:{row['id']}:{i}")]
            for i in range(len(options))
        ]
        return Reply(quiz_mod.format_question(row), buttons=buttons)

    def _answer_quiz(self, chat_id: int, question_id: int, answer_text: str) -> Reply:
        row = self.storage.get_question(question_id)
        if row is None:
            self.storage.delete_state(f"pending_quiz:{chat_id}")
            return Reply("سؤال یافت نشد. دوباره /quiz را بزنید.")

        options = json.loads(row["options"])
        index = quiz_mod.parse_answer(answer_text, len(options))
        if index is None:
            return Reply(
                f"پاسخ نامعتبر است. عددی بین ۱ تا {len(options)} بفرستید."
            )

        is_correct = index == int(row["correct_index"])
        self.storage.record_attempt(chat_id, question_id, is_correct)
        self.storage.delete_state(f"pending_quiz:{chat_id}")

        if is_correct:
            return Reply("✅ آفرین! پاسخ درست بود.")
        return Reply(
            f"❌ پاسخ نادرست بود.\n"
            f"پاسخ درست: {quiz_mod.correct_option_text(row)}"
        )

    def answer_callback(self, chat_id: int, data: str) -> Reply:
        """پاسخ به دکمه‌های شیشه‌ای (callback_data) آزمون."""
        if not data.startswith("quiz:"):
            return Reply("دکمهٔ ناشناخته.")
        try:
            _, question_id, index = data.split(":")
            return self._answer_quiz(chat_id, int(question_id), str(int(index) + 1))
        except (ValueError, TypeError):
            return Reply("خطا در پردازش پاسخ.")

    def _cmd_score(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        total, correct = self.storage.quiz_stats(chat_id)
        return Reply(quiz_mod.score_summary(total, correct))

    def _cmd_profile(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        name, grade = student
        return Reply(f"👤 نام: {name}\n🏫 پایه: {grade}\n🆔 شناسهٔ چت: {chat_id}")

    def _cmd_mystats(self, chat_id: int, argument: str, student: tuple[str, str]) -> Reply:
        total, correct = self.storage.quiz_stats(chat_id)
        avg = self.storage.average_of(chat_id)
        lines = ["📊 آمار من", f"تکالیف/نمرات: {len(self.storage.grades_of(chat_id))} مورد"]
        if avg is not None:
            lines.append(f"معدل: {avg:.2f}")
        lines.append(f"آزمون‌ها: {correct} پاسخ درست از {total}")
        return Reply("\n".join(lines))

    # ------------------------------------------------------------- admin
    def _cmd_add_lesson(self, chat_id: int, user_id: int | None, argument: str) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        parts = [p.strip() for p in argument.split("|")]
        if len(parts) < 4:
            return Reply(
                "قالب درست:\n"
                "/addlesson پایه|روز|زنگ|درس|معلم|ساعت‌شروع|ساعت‌پایان\n"
                "مثال:\n/addlesson دهم ریاضی|شنبه|1|ریاضی|آقای احمدی|08:00|08:45"
            )
        while len(parts) < 7:
            parts.append("")
        grade, day, period, subject, teacher, start, end = parts[:7]

        try:
            weekday = parse_weekday(day)
            period_num = int(period)
        except ValueError:
            return Reply("روز هفته یا شمارهٔ زنگ نامعتبر است.")

        if start and not is_valid_hhmm(start):
            return Reply("ساعت شروع باید به قالب HH:MM باشد.")
        if end and not is_valid_hhmm(end):
            return Reply("ساعت پایان باید به قالب HH:MM باشد.")

        self.storage.add_lesson(grade, weekday, period_num, subject, teacher, start, end)
        return Reply(
            f"✅ درس ثبت شد: {subject} — {weekday_name_of(weekday)} زنگ {period_num} "
            f"برای پایهٔ {grade}"
        )

    def _cmd_add_homework(self, chat_id: int, user_id: int | None, argument: str) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        parts = [p.strip() for p in argument.split("|")]
        if len(parts) < 4:
            return Reply(
                "قالب درست:\n/addlearning پایه|درس|عنوان|مهلت|توضیح\n"
                "مثال:\n/addlearning دهم ریاضی|ریاضی|تمرین فصل ۲|1404-07-01|صفحهٔ ۳۰"
            )
        while len(parts) < 5:
            parts.append("")
        grade, subject, title, due_date, description = parts[:5]

        if not _is_iso_date(due_date):
            return Reply("مهلت باید به قالب YYYY-MM-DD باشد.")
        if not self.storage.students_of_grade(grade):
            # ثبت تکلیف برای پایهٔ بدون دانش‌آموز مجاز است اما اطلاع می‌دهیم.
            pass

        self.storage.add_homework(grade, subject, title, due_date, description)
        return Reply(f"✅ تکلیف ثبت شد: [{subject}] {title} — مهلت {due_date}")

    def _cmd_add_question(self, chat_id: int, user_id: int | None, argument: str) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        parts = [p.strip() for p in argument.split("|")]
        if len(parts) != 5:
            return Reply(
                "قالب درست:\n/addquestion پایه|درس|سؤال|گزینه۱;گزینه۲;...|شمارهٔ پاسخ\n"
                "مثال:\n/addquestion دهم ریاضی|ریاضی|۲+۲ چند است؟|۳;۴;۵|2"
            )
        grade, subject, question, options_raw, correct_raw = parts
        options = [o.strip() for o in options_raw.split(";") if o.strip()]
        if len(options) < 2:
            return Reply("حداقل دو گزینه لازم است (جدا شده با ;).")

        correct = quiz_mod.normalize_digits(correct_raw).strip()
        if not correct.isdigit() or not 1 <= int(correct) <= len(options):
            return Reply(f"شمارهٔ پاسخ باید بین ۱ تا {len(options)} باشد.")

        self.storage.add_quiz_question(grade, subject, question, options, int(correct) - 1)
        return Reply("✅ سؤال آزمون ثبت شد.")

    def _cmd_set_grade(self, chat_id: int, user_id: int | None, argument: str) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        parts = [p.strip() for p in argument.split("|")]
        if len(parts) < 4:
            return Reply(
                "قالب درست:\n/setgrade شناسهٔ‌چت|درس|عنوان|نمره|نمرهٔ‌کل\n"
                "مثال:\n/setgrade 12345|ریاضی|میان‌ترم|18.5|20"
            )
        while len(parts) < 5:
            parts.append("")
        target_raw, subject, title, score_raw, max_raw = parts[:5]

        target = quiz_mod.normalize_digits(target_raw).strip()
        if not target.lstrip("-").isdigit():
            return Reply("شناسهٔ چت نامعتبر است.")
        if self.storage.get_student(int(target)) is None:
            return Reply("دانش‌آموزی با این شناسهٔ چت ثبت‌نام نکرده است.")
        try:
            score = float(quiz_mod.normalize_digits(score_raw))
            max_score = float(quiz_mod.normalize_digits(max_raw)) if max_raw else 20.0
        except ValueError:
            return Reply("نمره باید عددی باشد.")

        self.storage.add_grade(int(target), subject, title, score, max_score)
        return Reply(f"✅ نمره ثبت شد برای چت {target}: {title} = {score:g}")

    def _cmd_broadcast(self, chat_id: int, user_id: int | None, argument: str) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)
        if not argument.strip():
            return Reply("متن پیام را بعد از دستور بنویسید: /broadcast متن پیام")
        return Reply(f"📢 ارسال همگانی آماده است:\n\n{argument.strip()}")

    def _cmd_report(self, chat_id: int, user_id: int | None) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        students = self.storage.all_students()
        grades: dict[str, list[str]] = {}
        for student in students:
            grades.setdefault(student.grade, []).append(student.full_name)

        lines = [f"📋 گزارش مدرسه — {self.config.school_name}", ""]
        lines.append(f"تعداد دانش‌آموزان: {len(students)}")
        lines.append(f"تعداد پایه‌ها: {len(grades)}")
        for grade, names in sorted(grades.items()):
            lines.append(f"• {grade}: {len(names)} دانش‌آموز")
        return Reply("\n".join(lines))

    def _cmd_export(self, chat_id: int, user_id: int | None) -> Reply:
        error = self._admin_only(chat_id, user_id)
        if error:
            return Reply(error)

        import json

        data = {
            "school": self.config.school_name,
            "students": [
                {
                    "chat_id": s.chat_id,
                    "name": s.full_name,
                    "grade": s.grade,
                }
                for s in self.storage.all_students()
            ],
            "generated_at": now_in(self.config.timezone).isoformat(timespec="seconds"),
        }
        return Reply(
            "📤 خروجی دادهٔ دانش‌آموزان:\n\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
        )


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def weekday_name_of(index: int) -> str:
    from .schedule import WEEKDAYS_FA

    return WEEKDAYS_FA[index] if 0 <= index < len(WEEKDAYS_FA) else "نامشخص"


def add_days(day: date, days: int) -> date:
    return day + timedelta(days=days)
