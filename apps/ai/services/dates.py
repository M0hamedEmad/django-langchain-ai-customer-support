"""Booking date parsing shared by nodes, tools, and migrations."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def parse_booking_date(value: Optional[str]) -> Optional[datetime]:
    """Parse free-text booking dates (ISO, Arabic, natural language)."""
    if not value or isinstance(value, datetime):
        return value or None
    text = value.strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    try:
        import dateparser

        return dateparser.parse(text)
    except Exception:
        return None
