from typing import Any, NoReturn


def transform(
    device_name: str,
    parsed_data: list[dict[str, str | None]],
    worker: Any,
    device_platform: str | None = None,
    device_manufacturer: str | None = None,
    device_type: str | None = None,
) -> NoReturn:
    """Deliberately fail while processing a device."""
    raise RuntimeError(f"{device_name} transformer failure")
