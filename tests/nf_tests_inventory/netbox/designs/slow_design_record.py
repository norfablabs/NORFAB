import time
from typing import Any


def slow_design_record(context: dict, netbox: Any, dry_run: bool, delay: int) -> dict:
    """Delay a design record without NetBox writes to exercise job timeouts."""
    time.sleep(delay)
    return {"delay": delay}
