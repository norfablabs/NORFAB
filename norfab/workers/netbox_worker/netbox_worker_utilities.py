import fnmatch
import ipaddress
import logging
from typing import Any, Union

from norfab.core.worker import Job
from norfab.models import Result

log = logging.getLogger(__name__)

SYNC_DIFF_ACTIONS = ("create", "update", "delete")


def sync_diff_has_changes(diff: dict, ignore_deletions: bool = False) -> bool:
    """Return whether a sync diff contains a relevant actionable change."""
    if any(action in diff for action in SYNC_DIFF_ACTIONS):
        actions = ("create", "update") if ignore_deletions else SYNC_DIFF_ACTIONS
        return any(bool(diff.get(action)) for action in actions)

    # Combined sync tasks group action dictionaries by device or resource type.
    return any(
        sync_diff_has_changes(value, ignore_deletions=ignore_deletions)
        for value in diff.values()
        if isinstance(value, dict)
    )


def map_interface_name(
    name: Union[None, str],
    rules: list[dict],
    device_name: str,
    device_type: str,
) -> Union[None, str]:
    """Apply the first matching interface-name mapping rule."""
    for rule in rules:
        if (
            name
            and fnmatch.fnmatchcase(device_name, rule["device_name"])
            and fnmatch.fnmatchcase(device_type, rule["device_type"])
            and rule["match"] in name
        ):
            return name.replace(rule["match"], rule["replace"])
    return name


def apply_description_policy(
    live_description: Union[None, str],
    netbox_description: Union[None, str],
    preserve_description: Union[None, bool] = None,
) -> str:
    """Return the description selected by a NetBox sync preservation policy."""
    live_description = str(live_description or "")
    netbox_description = str(netbox_description or "")

    # Explicit preservation always keeps the description already in NetBox.
    if preserve_description is True:
        return netbox_description

    # By default, empty live data must not erase an existing description.
    if preserve_description is None:
        if not live_description:
            return netbox_description

    # Use live data when preservation is disabled or the default has live text.
    return live_description


def review_sync_task_result(
    job: Job,
    task_name: str,
    preview: Any,
) -> bool:
    """Request review for a prepared sync dry-run result."""
    approved = job.request_input(
        question=f"Apply {task_name} dry-run changes to NetBox?",
        default=False,
        metadata={"preview": preview},
    )
    if not approved:
        job.event(f"{task_name} changes were not approved; returning dry-run result")
        return False

    job.event(f"{task_name} changes approved; applying changes")
    return True


def resolve_vrf(
    name: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create a VRF, return its NetBox ID or None."""
    if not name:
        return None
    if name.lower() in ["global", "default"]:
        return None
    vrf_objects = list(nb.ipam.vrfs.filter(name=name))
    if vrf_objects:
        if len(vrf_objects) > 1:
            msg = f"Found multiple VRF in Netbox matching name '{name}', using VRF with ID {vrf_objects[0].id}"
            log.warning(msg)
            job.event(msg, severity="WARNING")
        return vrf_objects[0].id
    try:
        new_vrf = nb.ipam.vrfs.create(name=name)
        msg = f"created VRF '{name}' in NetBox"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_vrf.id
    except Exception as e:
        msg = f"failed to create VRF '{name}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None


def resolve_ip(
    address: Union[None, str, int],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    lookup_cache: Union[None, dict] = None,
) -> Union[int, None]:
    """Resolve or create an IP address in IPAM, return its NetBox ID or None."""
    if not address:
        return None
    if type(address) is int:
        return address
    if lookup_cache is None:
        lookup_cache = {}
    cache_key = ("ip", address)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]
    existing = list(nb.ipam.ip_addresses.filter(q=f"{address}/"))
    if existing:
        ip_id = existing[0].id
        lookup_cache[cache_key] = ip_id
        return ip_id
    # Try to find a containing prefix for mask length
    mask: str = None
    prefixes = list(nb.ipam.prefixes.filter(contains=address))
    if prefixes:
        # pick up longest prefix length for the mask
        mask = str(max([int(p.prefix.split("/")[1]) for p in prefixes]))
    if not mask:
        try:
            net = ipaddress.ip_network(address, strict=False)
            mask = "128" if net.version == 6 else "32"
        except Exception:
            mask = "32"
    try:
        new_ip = nb.ipam.ip_addresses.create(address=f"{address}/{mask}")
        msg = f"created IP address '{address}/{mask}' in NetBox IPAM"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        lookup_cache[cache_key] = new_ip.id
        return new_ip.id
    except Exception as e:
        msg = f"failed to create IP address '{address}/{mask}': {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        lookup_cache[cache_key] = None
        return None
