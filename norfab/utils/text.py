"""
Collection of common text processing utils
"""

import re


def slugify(value: str) -> str:
    """Convert a string to Django slug format"""
    value = str(value).strip()
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")
