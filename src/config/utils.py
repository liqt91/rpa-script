"""Internal utilities."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime, replaces deprecated `datetime.utcnow()`.

    Returns a naive datetime so it round-trips cleanly through SQLAlchemy
    `DateTime` columns (which don't carry tz info unless `timezone=True`)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
