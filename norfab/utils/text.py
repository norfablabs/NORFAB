"""
Collection of common text processing utils
"""

import re
from typing import Union


def slugify(value: str) -> str:
    """Convert a string to Django slug format"""
    value = str(value).strip()
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def format_duration(seconds: Union[int, float]) -> str:
    """
    Convert a duration in seconds to a compact human-readable string.

    Year and month values use fixed-length units of 365 and 30 days.

    Examples:
        65 -> "1min 5sec"
        90061 -> "1d 1h 1min 1sec"
        34218061 -> "1y 1mo 5d 1h 1min 1sec"
    """
    total_seconds = max(0, int(seconds))
    if total_seconds == 0:
        return "0 sec"

    parts = []
    for suffix, unit_seconds in (
        ("y", 31536000),
        ("mo", 2592000),
        ("d", 86400),
        ("h", 3600),
        (" min", 60),
        (" sec", 1),
    ):
        value, total_seconds = divmod(total_seconds, unit_seconds)
        if value == 0:
            continue
        parts.append(f"{value}{suffix}")

    return " ".join(parts)
