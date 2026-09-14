"""نقطهٔ ورود اجرای ربات: حلقهٔ long-polling + زمان‌بند.

استفاده:
    python -m schoolbot            # اجرای عادی
    python -m schoolbot --demo      # اجرای آزمایشی بدون شبکه (کلاینت جعلی)
"""

from __future__ import annotations

import argparse
import logging
import time

from .config import load_config
from .handlers import Bot
from .scheduler import Scheduler
from .storage import Storage
from .telegram import FakeTelegram, TelegramClient, TelegramError


def build_app(config, client):
    storage = Storage(config.db_path)
    bot = Bot(config, storage)
    scheduler = Scheduler(config, storage, client)
    return storage, bot, scheduler


def handle_update(bot: Bot, client, update: dict) -> None:
    """یک آپدیت تلگرام را پردازش و پاسخ را ارسال می‌کند."""
    if "callback_query" in update:
        query = update["callback_query"]
        chat_id = query.get("message", {}).get("chat", {}).get("id")
        data = query.get("data", "")
        if chat_id is None:
            return
        reply = bot.answer_callback(int(chat_id), data)
        client.answer_callback_query(query.get("id", ""), reply.text.split("\n")[0])
        client.send_message(int(chat_id), reply.text)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat = message.get("chat", {})
    if chat.get("type") != "private":
        return
    chat_id = chat.get("id")
    if chat_id is None:
        return
    from_user = message.get("from", {}) or {}
    user_name = from_user.get("first_name") or from_user.get("username") or "کاربر"
    text = message.get("text", "")

    reply = bot.handle(text, int(chat_id), from_user.get("id"), user_name)
    if reply.text:
        client.send_message(
            int(chat_id), reply.text, keyboard=reply.keyboard() or None, parse_mode=reply.parse_mode
        )


def run(config, client) -> None:  # pragma: no cover - حلقهٔ بی‌پایان
    storage, bot, scheduler = build_app(config, client)
    offset: int | None = None
    last_tick = 0.0
    logging.info("ربات آغاز شد. شناسهٔ مدیران: %s", config.admin_ids)

    try:
        while True:
            try:
                updates = client.get_updates(offset, timeout=30)
            except TelegramError as exc:
                logging.warning("خطای دریافت آپدیت: %s", exc)
                time.sleep(3)
                updates = []

            for update in updates:
                offset = int(update["update_id"]) + 1
                try:
                    handle_update(bot, client, update)
                except Exception as exc:  # noqa: BLE001 - یک خطا نباید ربات را بخواباند
                    logging.exception("خطا در پردازش آپدیت: %s", exc)

            now = time.monotonic()
            if now - last_tick >= config.tick_seconds:
                last_tick = now
                try:
                    sent = scheduler.tick()
                    if sent:
                        logging.info("زمان‌بند %d پیام ارسال کرد", sent)
                except Exception as exc:  # noqa: BLE001
                    logging.exception("خطا در زمان‌بند: %s", exc)
    finally:
        storage.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ربات اتوماسیون آموزشی مدرسه")
    parser.add_argument("--config", help="مسیر فایل تنظیمات JSON")
    parser.add_argument("--demo", action="store_true", help="اجرای آزمایشی بدون اتصال به تلگرام")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)

    if args.demo:
        run_demo(config)
        return 0

    if not config.bot_token:
        parser.error(
            "توکن ربات تنظیم نشده است. مقدار bot_token را در config.json یا "
            "متغیر محیطی MADRESE_BOT_TOKEN قرار دهید."
        )

    client = TelegramClient(config.bot_token)
    try:
        me = client.get_me()
    except TelegramError as exc:
        parser.error(f"اتصال به تلگرام برقرار نشد: {exc}\nتوکن ربات را بررسی کنید.")
    logging.info("اتصال به ربات @%s برقرار شد", me.get("username", "?"))
    run(config, client)
    return 0


def run_demo(config) -> None:  # pragma: no cover - نمایش تعاملی
    """نمایش تعاملی ربات در ترمینال، بدون نیاز به تلگرام."""
    client = FakeTelegram()
    storage, bot, scheduler = build_app(config, client)
    print("=== حالت آزمایشی (برای خروج: exit) ===")
    chat_id = 1
    try:
        while True:
            text = input("شما: ").strip()
            if text in ("exit", "quit", ""):
                break
            reply = bot.handle(text, chat_id, chat_id, "آزمایشی")
            client.send_message(chat_id, reply.text, keyboard=reply.keyboard() or None)
            print("ربات:", reply.text)
    finally:
        storage.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())