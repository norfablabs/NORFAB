"""
Collection of common text processing utils
"""

import re
from itertools import product
from typing import Union

BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def expand_bracket(group: str) -> list:
    """Expand a single bracket group content into a list of string alternatives."""
    results = []
    for token in group.split(","):
        token = token.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", token)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            step = 1 if end >= start else -1
            width = len(m.group(1))  # preserve leading zeros e.g. [00-03]
            results.extend(str(i).zfill(width) for i in range(start, end + step, step))
        else:
            results.append(token)
    return results


def expand_interface_range(pattern: str) -> list:
    """
    Expand a bracket-notation pattern into a list of concrete strings.

    Bracket groups ``[...]`` may contain:

    - A comma-separated list of alternatives: ``[ge,xe]``
    - A numeric range: ``[0-3]``
    - A mix of both: ``[ge,xe,0-3]``  (each token is treated as a literal
      unless it matches ``N-M`` with integer N and M)

    Multiple bracket groups in one pattern are expanded as a cartesian product.
    A pattern with no bracket groups is returned as a single-element list.

    Examples::

        expand_interface_range("[ge,xe]-0/0/[0-1]")
        # ["ge-0/0/0", "ge-0/0/1", "xe-0/0/0", "xe-0/0/1"]

        expand_interface_range("Ethernet[1-4]/1.101")
        # ["Ethernet1/1.101", "Ethernet2/1.101", "Ethernet3/1.101", "Ethernet4/1.101"]

        expand_interface_range("eth0")
        # ["eth0"]
    """
    parts = BRACKET_RE.split(pattern)  # alternates: literal, group, literal, group, ...
    literals = parts[0::2]  # even indices are literal segments
    groups = parts[1::2]  # odd indices are bracket group contents

    if not groups:
        return [pattern]

    expanded_groups = [expand_bracket(g) for g in groups]

    results = []
    for combo in product(*expanded_groups):
        s = literals[0]
        for i, val in enumerate(combo):
            s += val + literals[i + 1]
        results.append(s)
    return results


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
