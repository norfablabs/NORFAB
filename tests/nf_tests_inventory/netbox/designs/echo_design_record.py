from typing import Any


def echo_design_record(
    context: dict, netbox: Any, dry_run: bool, **kwargs: Any
) -> dict:
    """Return a custom design record's arguments for deployment tests."""
    return {"context": context, "dry_run": dry_run, "arguments": kwargs}
