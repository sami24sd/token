"""کلاینت سبک تلگرام (HTTP long-polling) بدون وابستگی بیرونی.

تنها از کتابخانهٔ استاندارد استفاده می‌کند تا نصب ربات ساده باشد و
بتوان به‌راحتی آن را با یک کلاینت جعلی در تست‌ها جایگزین کرد.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    """ارسال پیام و دریافت آپدیت‌ها از Bot API تلگرام."""

    def __init__(self, token: str, timeout: int = 35, api_base: str = API_BASE):
        if not token:
            raise TelegramError("توکن ربات تنظیم نشده است")
        self.token = token
        self.timeout = timeout
        self.api_base = api_base.rstrip("/")

    # ------------------------------------------------------------ internals
    def _call(self, method: str, payload: dict | None = None, timeout: int | None = None):
        url = f"{self.api_base}/bot{self.token}/{method}"
        data = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"خطای تلگرام ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"عدم دسترسی به تلگرام: {exc.reason}") from exc

        if not body.get("ok", False):
            raise TelegramError(f"پاسخ ناموفق تلگرام: {body}")
        return body.get("result")

    # ---------------------------------------------------------------- public
    def get_me(self) -> dict:
        return self._call("getMe", timeout=10) or {}

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict]:
        payload: dict[str, object] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 10) or []

    def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: list[list[dict[str, str]]] | None = None,
        parse_mode: str | None = None,
    ) -> dict:
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._call("sendMessage", payload) or {}

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        self._call("answerCallbackQuery", payload, timeout=10)


class FakeTelegram:
    """کلاینت جعلی برای تست و اجرای آزمایشی بدون شبکه."""

    def __init__(self):
        self.sent: list[dict] = []
        self.callback_answers: list[tuple[str, str]] = []

    def send_message(self, chat_id, text, keyboard=None, parse_mode=None):
        record = {"chat_id": chat_id, "text": text, "keyboard": keyboard}
        self.sent.append(record)
        return record

    def answer_callback_query(self, callback_query_id, text=""):
        self.callback_answers.append((callback_query_id, text))

    def get_me(self):
        return {"username": "fake_school_bot"}

    def last_text(self) -> str:
        return self.sent[-1]["text"] if self.sent else ""