#!/usr/bin/env python3
"""Отправляет сообщение в Telegram через бота.

Использование:
    python3 send.py "текст сообщения"
или через переменную окружения MESSAGE.

Нужны переменные окружения:
    TELEGRAM_TOKEN   — токен бота от @BotFather
    TELEGRAM_CHAT_ID — твой chat_id (бот пишет только туда)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

MAX_LEN = 4096  # лимит Telegram на одно сообщение


class TelegramError(Exception):
    pass


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise TelegramError("не заданы секреты TELEGRAM_TOKEN или TELEGRAM_CHAT_ID")

    text = text.strip()
    if not text:
        raise TelegramError("пустое сообщение")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for start in range(0, len(text), MAX_LEN):
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": text[start : start + MAX_LEN],
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Адрес с токеном в лог не выводим — только ответ Telegram.
            body = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram вернул ошибку {exc.code}: {body}") from None
        except urllib.error.URLError as exc:
            raise TelegramError(f"не удалось связаться с Telegram: {exc.reason}") from None
        if not result.get("ok"):
            raise TelegramError(f"Telegram вернул ошибку: {result}")


def main() -> int:
    text = " ".join(sys.argv[1:]) or os.environ.get("MESSAGE", "")
    try:
        send(text)
    except TelegramError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    print("Сообщение отправлено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
