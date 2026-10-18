#!/usr/bin/env python3
"""Читает reminders.yaml и отправляет в Telegram напоминания, которым пришло время.

Запускается по расписанию из GitHub Actions (каждый час). Чтобы не прислать одно
и то же дважды, отметки об отправке хранятся в sent.json — workflow сам
сохраняет его в репозиторий.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import yaml

from send import TelegramError, send

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "reminders.yaml"
STATE_PATH = ROOT / "sent.json"

# Насколько поздно напоминание ещё можно отправить (GitHub иногда задерживает запуски).
GRACE = timedelta(hours=24)
# Сколько хранить отметки об отправке.
KEEP_STATE = timedelta(days=14)

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def parse_time(value) -> time:
    if isinstance(value, int):  # YAML читает 09:00 без кавычек как число минут
        hours, minutes = divmod(value, 60)
        return time(hours, minutes)
    hours, minutes = str(value).strip().split(":")
    return time(int(hours), int(minutes))


def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def latest_occurrence(rem: dict, now: datetime, tz: timezone) -> datetime | None:
    """Последний момент срабатывания напоминания, не позже now (или None)."""
    at = parse_time(rem.get("time", "09:00"))

    if "date" in rem:
        moment = datetime.combine(parse_date(rem["date"]), at, tz)
        return moment if moment <= now else None

    if rem.get("daily"):
        days = set(range(7))
    elif "weekly" in rem:
        raw = rem["weekly"]
        names = raw if isinstance(raw, list) else [raw]
        try:
            days = {WEEKDAYS[str(n).strip().lower()[:3]] for n in names}
        except KeyError as exc:
            raise ValueError(f"неизвестный день недели {exc}") from None
    else:
        raise ValueError("нужно указать date, daily или weekly")

    start = parse_date(rem["from"]) if "from" in rem else None
    end = parse_date(rem["until"]) if "until" in rem else None

    for back in range(8):
        day = now.date() - timedelta(days=back)
        if day.weekday() not in days:
            continue
        moment = datetime.combine(day, at, tz)
        if moment > now or (end and day > end):
            continue
        if start and day < start:
            return None
        return moment
    return None


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    tz = timezone(timedelta(hours=float(config.get("utc_offset", 0))))
    now = datetime.now(tz)
    reminders = config.get("reminders") or []

    duplicates = [n for n, c in Counter(r.get("name") for r in reminders).items() if c > 1]
    if duplicates:
        print(f"Ошибка: у напоминаний повторяются названия: {duplicates}", file=sys.stderr)
        return 1

    state = load_state()
    first_run = state is None
    state = state or {}
    failures = 0

    for rem in reminders:
        name = rem.get("name") or "без названия"
        if rem.get("enabled", True) is False:
            continue
        try:
            moment = latest_occurrence(rem, now, tz)
        except (ValueError, TypeError) as exc:
            print(f"[{name}] ошибка в настройках: {exc}", file=sys.stderr)
            failures += 1
            continue
        if moment is None or now - moment > GRACE:
            continue

        key = f"{name}|{moment.isoformat()}"
        if key in state:
            continue

        if first_run:
            # Первый запуск: не присылаем то, что «должно было» прийти до установки бота.
            print(f"[{name}] первый запуск — отмечаю без отправки")
        else:
            try:
                send(str(rem.get("text") or name))
            except TelegramError as exc:
                print(f"[{name}] не отправлено: {exc}", file=sys.stderr)
                failures += 1
                continue
            print(f"[{name}] отправлено")
        state[key] = now.isoformat()

    cutoff = now - KEEP_STATE
    state = {k: v for k, v in state.items() if datetime.fromisoformat(v) >= cutoff}
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
