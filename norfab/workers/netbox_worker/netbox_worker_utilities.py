import fnmatch
import ipaddress
import logging
from collections.abc import Iterable
from typing import Any, Union

from norfab.core.worker import Job
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

log = logging.getLogger(__name__)


def prepare_vlan_map(
    vlan_map: Union[None, list],
    vlan_groups: Union[None, dict] = None,
) -> list[dict]:
    """Normalize VLAN map rules and resolve their effective VLAN IDs."""
    rules = []
    for rule in vlan_map or []:
        rule_data = rule.model_dump() if hasattr(rule, "model_dump") else dict(rule)
        explicit_vlan_ids = {
            int(vlan_id)
            for vlan_range in rule_data.get("match_vlan_ids") or []
            for vlan_id in expand_alphanumeric_range(f"[{vlan_range}]")
        }
        if vlan_groups is None:
            rule_data["expanded_vlan_ids"] = explicit_vlan_ids or None
        else:
            group = vlan_groups[rule_data["set_vlan_group"]]
            group_ranges = getattr(group, "vid_ranges", None)
            if group_ranges is None:
                group_ranges = [[1, 4094]]
            group_vlan_ids = set()
            for bounds in group_ranges:
                if (
                    not isinstance(bounds, (list, tuple))
                    or len(bounds) != 2
                    or not all(isinstance(value, int) for value in bounds)
                    or not 1 <= bounds[0] <= bounds[1] <= 4094
                ):
                    raise ValueError(
                        f"invalid vid_ranges for VLAN group '{rule_data['set_vlan_group']}'"
                    )
                group_vlan_ids.update(range(bounds[0], bounds[1] + 1))
            rule_data["expanded_vlan_ids"] = (
                group_vlan_ids & explicit_vlan_ids
                if explicit_vlan_ids
                else group_vlan_ids
            )
        rules.append(rule_data)
    return rules


def match_vlan_map(
    rules: list[dict],
    vlan_id: Union[None, int],
    vlan_name: Union[None, str],
    device_name: str,
    interface_name: Union[None, str],
) -> Union[None, str]:
    """Return the group from the first VLAN mapping rule that matches.

    Rules are evaluated in order. A rule can constrain the VLAN ID or name and
    the device or interface name using glob patterns. Criteria that are not
    configured do not restrict a rule. VLAN ID, VLAN name, and interface-name
    criteria are skipped when the caller does not have that value available;
    for example, a named VLAN has no ID until it is resolved from NetBox.
    """
    for rule in rules:
        # Named VLANs have no VID until the selected NetBox group resolves them.
        # Do not reject a name-based rule before that lookup can take place.
        vlan_id_match = True
        if vlan_id is not None and rule.get("expanded_vlan_ids") is not None:
            vlan_id_match = vlan_id in rule["expanded_vlan_ids"]
        # Do not reject a rule when the caller did not provide a VLAN name.
        vlan_name_match = True
        if vlan_name is not None and rule.get("vlan_names"):
            vlan_name_match = any(
                fnmatch.fnmatchcase(vlan_name, pattern)
                for pattern in rule["vlan_names"]
            )

        # A device name is always available, so apply this criterion whenever set.
        device_name_match = True
        if rule.get("match_device_names"):
            device_name_match = any(
                fnmatch.fnmatchcase(device_name, pattern)
                for pattern in rule["match_device_names"]
            )

        # Interface-free callers, such as VLAN sync, cannot evaluate this criterion.
        interface_name_match = True
        if interface_name is not None and rule.get("match_interface_names"):
            interface_name_match = any(
                fnmatch.fnmatchcase(interface_name, pattern)
                for pattern in rule["match_interface_names"]
            )
        if (
            vlan_id_match
            and vlan_name_match
            and device_name_match
            and interface_name_match
        ):
            return rule["set_vlan_group"]
    return None


def find_vlan(
    vlans: Iterable,
    vid: int,
    name: Union[None, str] = None,
    excluded_ids: Union[None, set] = None,
) -> Any:
    """Return the first available VLAN matching VID and, when supplied, name."""
    excluded_ids = excluded_ids or set()
    for vlan in vlans:
        if vlan.id in excluded_ids or int(vlan.vid) != vid:
            continue
        if name is None or str(vlan.name).strip() == name:
            return vlan
    return None


def build_vlan_payload(
    vid: int,
    name: str,
    description: str,
    site_id: Union[None, int] = None,
    group_id: Union[None, int] = None,
) -> dict:
    """Build a VLAN create payload for a group or site scope."""
    payload = {"vid": vid, "name": name, "description": description}
    if group_id:
        payload["group"] = group_id
    elif site_id:
        payload["site"] = site_id
    return payload


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


def resolve_vlan(
    vid: Union[None, int, str],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    site_id: Union[None, int] = None,
    vlan_group: Union[None, int, str] = None,
    _lookup_cache: Union[None, dict] = None,
    return_vid: bool = False,
) -> Union[int, None]:
    """Resolve a VLAN name or resolve/create a VLAN VID in NetBox."""
    if vid is None:
        return None
    if _lookup_cache is None:
        _lookup_cache = {}

    # find vlan group
    group_id = None
    if vlan_group:
        group_cache_key = ("vlan_group", vlan_group)
        if group_cache_key not in _lookup_cache:
            group_obj = None
            if isinstance(vlan_group, int) or str(vlan_group).isdigit():
                group_obj = nb.ipam.vlan_groups.get(id=int(vlan_group))
            if group_obj is None:
                group_obj = nb.ipam.vlan_groups.get(name=str(vlan_group))
            if group_obj is None:
                group_obj = nb.ipam.vlan_groups.get(slug=str(vlan_group))
            if group_obj is None:
                msg = f"VLAN group '{vlan_group}' does not exist in NetBox"
                job.event(msg, severity="ERROR")
                log.error(f"{worker_name} - {msg}")
                ret.errors.append(msg)
                _lookup_cache[group_cache_key] = None
            else:
                _lookup_cache[group_cache_key] = group_obj.id
        group_id = _lookup_cache[group_cache_key]
        if group_id is None:
            return None

    # When given a VLAN name not VID integer, look up an existing NetBox VLAN.
    # A missing VLAN cannot be created because its numeric VID is unknown.
    if isinstance(vid, str):
        cache_key = (
            ("vlan_name", vid, "group", group_id)
            if group_id
            else ("vlan_name", vid, "site", site_id)
        )
        if cache_key in _lookup_cache:
            nb_vlan = _lookup_cache[cache_key]
            if nb_vlan is None:
                return None
            return int(nb_vlan.vid) if return_vid else nb_vlan.id

        filter_kwargs = {"name": vid}
        if group_id:
            filter_kwargs["group_id"] = group_id
        elif site_id:
            filter_kwargs["site_id"] = site_id

        try:
            vlan_candidates = nb.ipam.vlans.filter(**filter_kwargs)
            if not group_id and not site_id:
                vlan_candidates = (
                    vlan for vlan in vlan_candidates if not vlan.site and not vlan.group
                )
            nb_vlan = next(iter(vlan_candidates), None)
        except Exception as e:
            msg = (
                f"Failed to fetch Netbox vlan using filters "
                f"'{filter_kwargs}', error: {e}"
            )
            log.error(msg)
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            return None

        _lookup_cache[cache_key] = nb_vlan
        if nb_vlan:
            return int(nb_vlan.vid) if return_vid else nb_vlan.id

        msg = f"failed to find VLAN named '{vid}' in NetBox using filters '{filter_kwargs}'"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None

    cache_key = (
        (
            "vlan",
            vid,
            "group",
            group_id,
        )
        if group_id
        else ("vlan", vid, "site", site_id)
    )
    if cache_key in _lookup_cache:
        return _lookup_cache[cache_key]

    # Fetch scoped candidates and consistently select the first matching VID.
    filter_kwargs = {"vid": vid}
    try:
        if group_id:
            filter_kwargs["group_id"] = group_id
            vlan_candidates = nb.ipam.vlans.filter(**filter_kwargs)
        elif site_id:
            filter_kwargs["site_id"] = site_id
            vlan_candidates = nb.ipam.vlans.filter(**filter_kwargs)
        # Try to source a global VLAN not assigned to a site or group.
        else:
            vlan_candidates = (
                vlan
                for vlan in nb.ipam.vlans.filter(**filter_kwargs)
                if not vlan.site and not vlan.group
            )
        nb_vlan = find_vlan(vlan_candidates, vid)
        if nb_vlan:
            _lookup_cache[cache_key] = nb_vlan.id
    except Exception as e:
        msg = f"Failed to fetch Netbox vlan using filters '{filter_kwargs}', error: {e}"
        log.error(msg)
        job.event(msg, severity="ERROR")
        ret.errors.append(msg)
        return None

    # check if managed to find a matching vlan
    if cache_key in _lookup_cache:
        return _lookup_cache[cache_key]

    # create new vlan if no existing vlan found
    payload = build_vlan_payload(
        vid=vid,
        name=f"VLAN_{vid}",
        description=f"VLAN_{vid}",
        site_id=site_id,
        group_id=group_id,
    )

    try:
        new_vlan = nb.ipam.vlans.create(**payload)
        msg = f"created VLAN '{vid}' in NetBox"
        if group_id:
            msg += f" in VLAN group '{vlan_group}'"
        elif site_id:
            msg += f" for site '{new_vlan.site.name}'"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        _lookup_cache[cache_key] = new_vlan.id
        return new_vlan.id
    except Exception as e:
        msg = f"failed to create VLAN '{vid}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        _lookup_cache[cache_key] = None
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
