"""Shared datetime utilities."""

from typing import Any
from datetime import datetime


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 datetime string (or datetime object) into a datetime or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None
