import ipaddress
import logging
from typing import Any, Dict, List, Union
from norfab.core.worker import Job
from norfab.models import Result

log = logging.getLogger(__name__)


def resolve_vrf(
    name: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create a VRF, return its NetBox ID or None."""
    if not name:
        return None
    if name.lower() in ["global", "default"]:
        return None
    vrf_obj = nb.ipam.vrfs.get(name=name)
    if vrf_obj:
        return vrf_obj.id
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
    vid: Union[None, int],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    site_id: Union[None, int] = None,
    vlan_group: Union[None, int, str] = None,
    _lookup_cache: Union[None, dict] = None,
) -> Union[int, None]:
    """Resolve or create a VLAN, return its NetBox ID or None."""
    if vid is None:
        return None
    if _lookup_cache is None:
        _lookup_cache = {}

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

    cache_key = (
        "vlan",
        vid,
        "group",
        group_id,
    ) if group_id else ("vlan", vid, "site", site_id)
    if cache_key in _lookup_cache:
        return _lookup_cache[cache_key]

    filter_kwargs = {"vid": vid}
    if group_id:
        filter_kwargs["group_id"] = group_id
    elif site_id:
        filter_kwargs["site_id"] = site_id

    nb_vlans = list(nb.ipam.vlans.filter(**filter_kwargs))
    if not nb_vlans and not group_id and site_id:
        nb_vlans = list(nb.ipam.vlans.filter(vid=vid))
    if nb_vlans:
        _lookup_cache[cache_key] = nb_vlans[0].id
        return nb_vlans[0].id

    payload = {"vid": vid, "name": f"VLAN_{vid}", "description": f"VLAN_{vid}"}
    if site_id:
        payload["site"] = site_id
    if group_id:
        payload["group"] = group_id

    try:
        new_vlan = nb.ipam.vlans.create(**payload)
        msg = f"created VLAN '{vid}' in NetBox"
        if group_id:
            msg += f" in VLAN group '{vlan_group}'"
        if site_id:
            msg += f" for site ID '{site_id}'"
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
    mask = None
    prefixes = list(nb.ipam.prefixes.filter(contains=address))
    if prefixes:
        mask = prefixes[0].prefix.split("/")[1]
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
