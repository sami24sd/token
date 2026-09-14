"""تنظیمات ربات: از فایل JSON و متغیرهای محیطی خوانده می‌شود."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"


@dataclass(frozen=True)
class Config:
    bot_token: str = ""
    admin_ids: tuple[int, ...] = ()
    timezone: str = "Asia/Tehran"
    school_name: str = "دبیرستان نمونه"
    data_dir: Path = BASE_DIR / "data"
    # زمان ارسال برنامهٔ روزانه به دانش‌آموزان
    daily_send_time: str = "07:00"
    # زمان ارسال آزمون روزانه
    quiz_send_time: str = "18:00"
    # روز و ساعت ارسال گزارش هفتگی برای مدیر
    weekly_report_weekday: str = "thursday"
    weekly_report_time: str = "20:00"
    # فاصلهٔ بررسی زمان‌بندی‌ها در حلقهٔ سرویس (ثانیه)
    tick_seconds: int = 30

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir).expanduser() / "school.db"


def _coerce_admins(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, int)):
        value = [value]
    ids = []
    for item in value:  # type: ignore[union-attr]
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(ids)


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """تنظیمات را از فایل JSON می‌خواند و با متغیرهای محیطی بازنویسی می‌کند."""
    config_path = Path(path) if path else Path(
        os.getenv("MADRESE_CONFIG", DEFAULT_CONFIG_PATH)
    )

    raw: dict[str, object] = {}
    if config_path.is_file():
        raw = json.loads(config_path.read_text(encoding="utf-8"))

    cfg = Config(
        bot_token=str(raw.get("bot_token", "")),
        admin_ids=_coerce_admins(raw.get("admin_ids")),
        timezone=str(raw.get("timezone", "Asia/Tehran")),
        school_name=str(raw.get("school_name", "دبیرستان نمونه")),
        data_dir=Path(str(raw.get("data_dir") or BASE_DIR / "data")),
        daily_send_time=str(raw.get("daily_send_time", "07:00")),
        quiz_send_time=str(raw.get("quiz_send_time", "18:00")),
        weekly_report_weekday=str(raw.get("weekly_report_weekday", "thursday")),
        weekly_report_time=str(raw.get("weekly_report_time", "20:00")),
        tick_seconds=int(raw.get("tick_seconds", 30)),  # type: ignore[arg-type]
    )

    env_token = os.getenv("MADRESE_BOT_TOKEN")
    env_admins = os.getenv("MADRESE_ADMIN_IDS")
    if env_token:
        cfg = replace(cfg, bot_token=env_token)
    if env_admins:
        cfg = replace(cfg, admin_ids=_coerce_admins(env_admins.split(",")))

    return cfg
