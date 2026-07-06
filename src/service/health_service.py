"""Health check service."""


def get_health() -> dict:
    """Return the standard health check payload."""
    return {"status": "ok"}
