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


def resolve_ip(
    address: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create an IP address in IPAM, return its NetBox ID or None."""
    if not address:
        return None
    existing = list(nb.ipam.ip_addresses.filter(q=f"{address}/"))
    if existing:
        return existing[0].id
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
        return new_ip.id
    except Exception as e:
        msg = f"failed to create IP address '{address}/{mask}': {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None