from typing import Any


def transform(
    device_name: str,
    parsed_data: list[dict[str, str | None]],
    worker: Any,
) -> list[dict[str, object]]:
    """Deliberately return data that violates the inventory record model."""
    return [{"slot": "chassis", "serial": 123}]
