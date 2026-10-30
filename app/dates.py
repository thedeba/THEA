from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def parse_timestamp(value: str | None, *, end_of_day: bool = False) -> float | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            day = date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"Invalid date/time: {value}") from exc
        parsed = datetime.combine(day, time.min, tzinfo=timezone.utc)
        if end_of_day:
            return (parsed + timedelta(days=1)).timestamp() - 0.000001
        return parsed.timestamp()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if end_of_day and len(text) == 10:
        return (parsed + timedelta(days=1)).timestamp() - 0.000001
    return parsed.timestamp()
