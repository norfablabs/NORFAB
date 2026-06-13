from typing import Any


def process(
    device_name: str,
    parsed_data: list[dict[str, str | None]],
    worker: Any,
) -> list[dict[str, str | None]]:
    """Deliberately export the wrong function name."""
    return parsed_data
