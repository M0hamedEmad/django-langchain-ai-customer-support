"""Booking date parsing shared by nodes, tools, and migrations."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_booking_date(value: str | None) -> datetime | None:
    """Parse free-text booking dates (ISO, Arabic, natural language).

    Always timezone-aware (UTC) so USE_TZ datetimes never warn on save.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    try:
        import dateparser

        return dateparser.parse(
            text, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
    except Exception:
        return None
