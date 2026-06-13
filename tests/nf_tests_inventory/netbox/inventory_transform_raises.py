from typing import Any, NoReturn


def transform(
    device_name: str,
    parsed_data: list[dict[str, str | None]],
    worker: Any,
) -> NoReturn:
    """Deliberately fail while processing a device."""
    raise RuntimeError(f"{device_name} transformer failure")
