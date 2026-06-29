"""Minimal example job for the open-source release."""


def run(url: str, name: str = "world", **params) -> dict:
    return {"message": f"Hello, {name}!"}
