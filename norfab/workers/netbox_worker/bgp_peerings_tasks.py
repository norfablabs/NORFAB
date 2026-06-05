import fnmatch
import ipaddress
import logging
from typing import Any, Dict, List, Union

from jinja2 import Environment, StrictUndefined

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import (
    CreateBgpPeeringInput,
    CreateBgpPeeringResult,
    GetBgpPeeringsInput,
    GetBgpPeeringsResult,
    NetboxFastApiArgs,
    SyncBgpPeeringsInput,
    SyncBgpPeeringsResult,
    UpdateBgpPeeringInput,
    UpdateBgpPeeringResult,
)
from .netbox_worker_utilities import resolve_ip, resolve_vrf

log = logging.getLogger(__name__)

BGP_NAME_TEMPLATE_ENV = Environment(undefined=StrictUndefined, autoescape=False)


# ---------------------------------------------------------------------------
# Module-level helper functions — used by create_bgp_peering, update_bgp_peering,
# and sync_bgp_peerings
# ---------------------------------------------------------------------------


def resolve_asn(
    asn_str: Union[None, str],
    nb: Any,
    rir_id: Union[None, int],
    job: Job,
    ret: Result,
    worker_name: str,
    lookup_cache: Union[None, dict] = None,
) -> Union[int, None]:
    """Resolve or create an ASN, return its NetBox ID or None."""
    if not asn_str:
        return None
    try:
        asn_int = int(asn_str)
    except (ValueError, TypeError):
        return None
    if lookup_cache is None:
        lookup_cache = {}
    cache_key = ("asn", asn_int)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]
    existing = list(nb.ipam.asns.filter(asn=asn_int))
    if existing:
        asn_id = existing[0].id
        lookup_cache[cache_key] = asn_id
        return asn_id
    if not rir_id:
        msg = f"cannot create ASN '{asn_str}': no RIR provided, use 'rir' parameter"
        job.event(msg, severity="WARNING")
        log.warning(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        lookup_cache[cache_key] = None
        return None
    try:
        new_asn = nb.ipam.asns.create(asn=asn_int, rir=rir_id)
        msg = f"created ASN '{asn_str}' in NetBox IPAM"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        lookup_cache[cache_key] = new_asn.id
        return new_asn.id
    except Exception as e:
        msg = f"failed to create ASN '{asn_str}': {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        lookup_cache[cache_key] = None
        return None


def resolve_prefix_list(
    name: Union[None, str],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    family: Union[None, str] = None,
) -> Union[int, None]:
    """Resolve or create a prefix list; optionally scoped by address family."""
    if not name:
        return None
    if family:
        results = list(nb.plugins.bgp.prefix_list.filter(name=name, family=family))
    else:
        results = list(nb.plugins.bgp.prefix_list.filter(name=name))
    existing = results[0] if results else None
    if existing:
        return existing.id
    create_kwargs = {"name": name}
    if family is not None:
        create_kwargs["family"] = family
    try:
        new_obj = nb.plugins.bgp.prefix_list.create(**create_kwargs)
        msg = f"created prefix list '{name}' in NetBox"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_obj.id
    except Exception as e:
        msg = f"failed to create prefix list '{name}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None


def resolve_route_policy(
    name: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create a routing policy."""
    if not name:
        return None
    results = list(nb.plugins.bgp.routing_policy.filter(name=name))
    existing = results[0] if results else None
    if existing:
        return existing.id
    try:
        new_obj = nb.plugins.bgp.routing_policy.create(name=name)
        msg = f"created routing policy '{name}' in NetBox"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_obj.id
    except Exception as e:
        msg = f"failed to create routing policy '{name}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None


def resolve_peer_group(
    name: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create a peer group."""
    if not name:
        return None
    results = list(nb.plugins.bgp.peer_group.filter(name=name))
    existing = results[0] if results else None
    if existing:
        return existing.id
    try:
        new_obj = nb.plugins.bgp.peer_group.create(name=name)
        msg = f"created peer group '{name}' in NetBox"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_obj.id
    except Exception as e:
        msg = f"failed to create peer group '{name}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None


def get_addr_family(address: str) -> str:
    """Return 'ipv4' or 'ipv6' based on the IP address version."""
    try:
        return "ipv6" if ipaddress.ip_address(address).version == 6 else "ipv4"
    except Exception:
        return "ipv4"


def get_p2p_peer_ip(cidr: str) -> Union[None, str]:
    """Return the peer IP for a P2P subnet (/30, /31, /127) or None for other prefixes."""
    try:
        iface = ipaddress.ip_interface(cidr)
        prefix_len = iface.network.prefixlen
        version = iface.version
        if version == 4 and prefix_len in (30, 31):
            hosts = [h for h in iface.network.hosts() if h != iface.ip]
            return str(hosts[0]) if hosts else None
        if version == 6 and prefix_len == 127:
            addresses = [a for a in iface.network if a != iface.ip]
            return str(addresses[0]) if addresses else None
        return None
    except Exception:
        return None


def _cached_bgp_ip_object(address: Union[None, str], lookup_cache: dict) -> Any:
    """Return a cached pynetbox IP address object for a bare IP address."""
    if not address:
        return None
    return lookup_cache.get(("ip_address_object", str(address)))


def _cached_bgp_device_info(device_name: Union[None, str], lookup_cache: dict) -> dict:
    """Return cached device ID/site/data dict used by create/update payload code."""
    if not device_name:
        return {}
    device_obj = lookup_cache.get(("device_object", device_name))
    if not device_obj:
        return {}
    site_name = device_obj.site.name
    return {
        "id": lookup_cache.get(("device", device_name), device_obj.id),
        "site_id": lookup_cache.get(("site", site_name), device_obj.site.id),
        "data": dict(device_obj),
    }


def _bgp_session_template_context(session: dict, lookup_cache: dict) -> dict:
    """Build the Jinja2 context for BGP session name rendering."""
    context = dict(session)
    device_name = session.get("device")
    remote_device_name = session.get("remote_device_name")
    if not remote_device_name:
        ip_obj = _cached_bgp_ip_object(session.get("remote_address"), lookup_cache)
        assigned_object = getattr(ip_obj, "assigned_object", None)
        remote_device = getattr(assigned_object, "device", None)
        remote_device_name = getattr(remote_device, "name", None)
    context.pop("device", None)
    context.pop("remote_device", None)
    context.pop("device_name", None)
    context.pop("remote_device_name", None)
    device_obj = lookup_cache.get(("device_object", device_name))
    remote_device_obj = lookup_cache.get(("device_object", remote_device_name))
    if device_obj is not None:
        context["device"] = device_obj
    if remote_device_obj is not None:
        context["remote_device"] = remote_device_obj
    return context


def render_bgp_session_name(
    name_template: str, session: dict, lookup_cache: dict
) -> str:
    """Render a BGP session name using a Jinja2 template and cached NetBox objects."""
    context = _bgp_session_template_context(session, lookup_cache)
    return BGP_NAME_TEMPLATE_ENV.from_string(name_template).render(**context)


def _remote_device_name_from_ip(ip_obj: Any) -> Union[None, str]:
    assigned_object = getattr(ip_obj, "assigned_object", None)
    remote_device = getattr(assigned_object, "device", None)
    return getattr(remote_device, "name", None)


def resolve_asn_from_source(
    device_data: Dict[str, Any], asn_source: Union[str, Dict[str, Any]], nb: Any
) -> Union[None, str]:
    """
    Resolve an ASN from device data or a NetBox IPAM query.

    asn_source can be:

    - str  — dot-separated path through device_data dict/list
    - dict — kwargs passed to nb.ipam.asns.get(**asn_source); uses asn_obj.asn
    """
    if isinstance(asn_source, dict):
        asn_obj = nb.ipam.asns.get(**asn_source)
        if asn_obj is not None:
            return str(asn_obj.asn)
    else:
        node = device_data
        for key in asn_source.split("."):
            if isinstance(node, dict):
                node = node.get(key)
            elif isinstance(node, list):
                try:
                    node = node[int(key)]
                except (ValueError, IndexError):
                    node = None
            else:
                node = None
            if node is None:
                break
        if node is not None:
            return str(node)
    return None


def resolve_local_ip_via_peer(
    device_name: str, remote_address: str, nb: Any
) -> Union[None, str]:
    """
    Resolve a local IP address for a device by looking up the subnet of the peer IP.

    Queries NetBox for the ``remote_address`` IP to determine its containing prefix,
    then searches for IP addresses assigned to interfaces of ``device_name`` that
    fall within the same prefix.  Returns the host part of that IP if exactly one
    match is found, ``None`` otherwise.

    Args:
        device_name: Local device name.
        remote_address: Remote peer IP address string (without mask).
        nb: pynetbox API instance.

    Returns:
        Local IP address string (without mask) or ``None``.
    """
    # Find the containing prefix for the remote IP
    prefixes = list(nb.ipam.prefixes.filter(contains=remote_address))
    if not prefixes:
        log.error(
            f"failed to resolve local ip via peer - no prefix found containing '{remote_address}' in NetBox IPAM"
        )
        return None

    # Use the most specific (longest prefix) containing subnet
    prefix_obj = max(prefixes, key=lambda p: int(p.prefix.split("/")[1]))
    subnet = ipaddress.ip_network(prefix_obj.prefix, strict=False)
    # Find all IPs assigned to device_name interfaces within that subnet
    device_ips = list(
        nb.ipam.ip_addresses.filter(
            device=device_name,
            parent=str(subnet),
        )
    )

    if not device_ips:
        log.error(
            f"failed to resolve local ip via peer - no IP address found for device '{device_name}' "
            f"within subnet '{subnet}' (peer '{remote_address}')"
        )
        return None

    if len(device_ips) > 1:
        found = [ip.address for ip in device_ips]
        log.error(
            f"failed to resolve local ip via peer - multiple IPs found for device '{device_name}' "
            f"within subnet '{subnet}' (peer '{remote_address}'): {found}; "
            "cannot determine local address unambiguously"
        )
        return None

    return device_ips[0].address.split("/")[0]


def normalise_nb_bgp_session(nb_session: dict, vrf_custom_field: str = "vrf") -> dict:
    """Normalise a NetBox BGP session plain dict into a flat comparable dict.

    Accepts either a raw ``dict(pynetbox_obj)`` or a session dict returned by
    ``get_bgp_peerings``.  All nested objects are flattened to scalars so the
    result can be compared directly with ``make_diff``.

    Args:
        nb_session: Raw NetBox BGP session dict.
        vrf_custom_field: Name of the BGP session custom field that holds the
            VRF object reference (e.g. ``"vrf"`` or ``"tenant_vrf"``).  The
            field must be of type **Object** in NetBox pointing to the VRF
            content-type.  The value is always read from
            ``custom_fields[vrf_custom_field]``.
    """
    ret = {
        "id": nb_session["id"],
        "name": nb_session["name"],
        "description": nb_session.get("description") or "",
        "local_address": nb_session["local_address"]["address"].split("/")[0],
        "local_as": nb_session["local_as"]["asn"],
        "remote_address": nb_session["remote_address"]["address"].split("/")[0],
        "remote_as": nb_session["remote_as"]["asn"],
        "status": nb_session["status"]["value"],
        "peer_group": (
            nb_session["peer_group"]["name"] if nb_session.get("peer_group") else None
        ),
        "import_policies": [p["name"] for p in nb_session.get("import_policies") or []],
        "export_policies": [p["name"] for p in nb_session.get("export_policies") or []],
        "prefix_list_in": (
            nb_session["prefix_list_in"]["name"]
            if nb_session.get("prefix_list_in")
            else None
        ),
        "prefix_list_out": (
            nb_session["prefix_list_out"]["name"]
            if nb_session.get("prefix_list_out")
            else None
        ),
    }

    if vrf_custom_field:
        ret["vrf"] = (
            (nb_session.get("custom_fields") or {}).get(vrf_custom_field) or {}
        ).get("name")

    return ret


def bgp_session_matches_filters(
    session: dict,
    filter_by_remote_as: Union[None, List[int]] = None,
    filter_by_peer_group: Union[None, list] = None,
    filter_by_description: Union[None, str] = None,
    ignore_peer_nets: Union[None, list] = None,
) -> bool:
    """Return True when a normalised BGP session matches sync filters."""
    if filter_by_remote_as and session["remote_as"] not in filter_by_remote_as:
        return False
    if filter_by_peer_group and session.get("peer_group") not in filter_by_peer_group:
        return False
    if filter_by_description and not fnmatch.fnmatch(
        session.get("description") or "", filter_by_description
    ):
        return False
    if ignore_peer_nets:
        peer_ip_addr = ipaddress.ip_address(session["remote_address"])
        if any(peer_ip_addr in net for net in ignore_peer_nets):
            return False
    return True


def resolve_bgp_session_payload_fields(
    fields: dict,
    nb: Any,
    rir_id: Union[None, int],
    job: Job,
    ret: Result,
    worker_name: str,
    addr_family: str,
    lookup_cache: Union[None, dict] = None,
    vrf_custom_field: str = "vrf",
) -> dict:
    """Resolve BGP session field name/value pairs to a partial NetBox API payload dict.

    Accepts a flat ``{field: desired_value}`` mapping and resolves each value to the
    corresponding NetBox object ID.  Returns a partial payload dict ready to be merged
    into a create or update payload.

    ``import_policies`` / ``export_policies`` values may be either a list of policy
    names or a pipe-separated string; both forms are handled.

    ``lookup_cache`` is an optional dict shared across multiple calls within the same
    task invocation to avoid redundant NetBox lookups for IP address / ASN / VRF /
    peer group / routing policy / prefix list objects.
    """
    if lookup_cache is None:
        lookup_cache = {}
    payload = {}
    for field, value in fields.items():
        if field in ("local_address", "remote_address"):
            ip_id = resolve_ip(value, nb, job, ret, worker_name, lookup_cache)
            if ip_id:
                payload[field] = ip_id
        elif field in ("local_as", "remote_as"):
            asn_id = resolve_asn(value, nb, rir_id, job, ret, worker_name, lookup_cache)
            if asn_id:
                payload[field] = asn_id
        elif field in ("description", "status"):
            payload[field] = value
        elif field == "vrf":
            if not vrf_custom_field:
                pass
            elif value:
                cache_key = ("vrf", value)
                if cache_key not in lookup_cache:
                    lookup_cache[cache_key] = resolve_vrf(
                        value, nb, job, ret, worker_name
                    )
                vrf_id = lookup_cache[cache_key]
                payload.setdefault("custom_fields", {})[vrf_custom_field] = vrf_id
            else:
                payload.setdefault("custom_fields", {})[vrf_custom_field] = None
        elif field == "peer_group":
            if value:
                cache_key = ("peer_group", value)
                if cache_key not in lookup_cache:
                    lookup_cache[cache_key] = resolve_peer_group(
                        value, nb, job, ret, worker_name
                    )
                payload["peer_group"] = lookup_cache[cache_key]
            else:
                payload["peer_group"] = None
        elif field in ("import_policies", "export_policies"):
            policies = (
                value
                if isinstance(value, list)
                else [p for p in value.split("|") if p] if value else []
            )
            ids = []
            for p_name in policies:
                cache_key = ("route_policy", p_name)
                if cache_key not in lookup_cache:
                    lookup_cache[cache_key] = resolve_route_policy(
                        p_name, nb, job, ret, worker_name
                    )
                if lookup_cache[cache_key]:
                    ids.append(lookup_cache[cache_key])
            payload[field] = ids
        elif field in ("prefix_list_in", "prefix_list_out"):
            if value:
                cache_key = ("prefix_list", value, addr_family)
                if cache_key not in lookup_cache:
                    lookup_cache[cache_key] = resolve_prefix_list(
                        value, nb, job, ret, worker_name, family=addr_family
                    )
                payload[field] = lookup_cache[cache_key]
            else:
                payload[field] = None
    return payload


def _resolve_rir_id(
    rir: Union[None, str],
    nb: Any,
    job: Job,
    worker_name: str,
    lookup_cache: Union[None, dict] = None,
) -> Union[None, int]:
    """Resolve RIR name to its NetBox ID; log a warning when not found."""
    if not rir:
        return None
    if lookup_cache is None:
        lookup_cache = {}
    cache_key = ("rir", rir)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]
    rir_obj = nb.ipam.rirs.get(name=rir)
    if rir_obj:
        lookup_cache[cache_key] = rir_obj.id
        return rir_obj.id
    msg = f"RIR '{rir}' not found in NetBox, ASN creation will fail if needed"
    job.event(msg, severity="WARNING")
    log.warning(f"{worker_name} - {msg}")
    lookup_cache[cache_key] = None
    return None


def _resolve_vrf_custom_field(
    vrf_custom_field: str, nb: Any, job: Job, worker_name: str
) -> Union[str, bool]:
    """Check that vrf_custom_field exists as a custom field in NetBox.

    Queries the NetBox extras API.  Returns the field name unchanged when found,
    or ``False`` when the custom field does not exist so callers can skip VRF
    handling entirely.
    """
    if not vrf_custom_field:
        return False
    try:
        cf = nb.extras.custom_fields.get(name=vrf_custom_field)
    except Exception as exc:
        msg = f"failed to verify custom field '{vrf_custom_field}' in NetBox: {exc}"
        job.event(msg, severity="WARNING")
        log.warning(f"{worker_name} - {msg}")
        return False
    if cf is None:
        msg = f"BGP session custom field '{vrf_custom_field}' not found in NetBox, VRF handling disabled"
        job.event(msg, severity="WARNING")
        log.warning(f"{worker_name} - {msg}")
        return False
    return vrf_custom_field


def preseed_bgp_lookup_cache(
    nb: Any,
    bgp_sessions: List[dict],
    lookup_cache: dict,
    job: Job,
    bulk_filter: Any,
    worker_name: str,
) -> None:
    """Bulk-populate lookup_cache for validated BGP session IP, device, ASN, and VRF IDs."""
    lookup_cache = lookup_cache if lookup_cache is not None else {}
    ip_values, device_names, asn_values, vrf_values = set(), set(), set(), set()

    for session in bgp_sessions:
        local_address = session.get("local_address")
        remote_address = session["remote_address"]
        if local_address and ("ip_address_object", local_address) not in lookup_cache:
            ip_values.add(local_address)
        if ("ip_address_object", remote_address) not in lookup_cache:
            ip_values.add(remote_address)

        device_name = (
            session["device_name"] if "device_name" in session else session["device"]
        )
        remote_device_name = session.get("remote_device_name")
        if ("device_object", device_name) not in lookup_cache:
            device_names.add(device_name)
        if (
            remote_device_name
            and ("device_object", remote_device_name) not in lookup_cache
        ):
            device_names.add(remote_device_name)

        if "local_as" in session and session["local_as"] is not None:
            local_as = int(session["local_as"])
            if ("asn", local_as) not in lookup_cache:
                asn_values.add(local_as)

        if "remote_as" in session and session["remote_as"] is not None:
            remote_as = int(session["remote_as"])
            if ("asn", remote_as) not in lookup_cache:
                asn_values.add(remote_as)

        vrf = session.get("vrf")
        if (
            vrf
            and str(vrf).lower() not in ["global", "default"]
            and ("vrf", vrf) not in lookup_cache
        ):
            vrf_values.add(vrf)

    try:
        if ip_values:
            nb_ips = bulk_filter(
                nb.ipam.ip_addresses,
                "address",
                list(ip_values),
                fields="id,address,assigned_object",
            )
            for ip_obj in nb_ips:
                address = ip_obj.address.split("/")[0]
                lookup_cache[("ip_address_object", address)] = ip_obj
                lookup_cache[("ip", address)] = ip_obj.id
                remote_device_name = _remote_device_name_from_ip(ip_obj)
                if (
                    remote_device_name
                    and ("device_object", remote_device_name) not in lookup_cache
                ):
                    device_names.add(remote_device_name)
            job.event(
                f"pre-seeded BGP IP lookup cache with {len(nb_ips)} NetBox IP object(s)"
            )

        if device_names:
            nb_devices = bulk_filter(
                nb.dcim.devices,
                "name",
                list(device_names),
                fields="id,name,platform,site,device_type",
            )
            found_names = set()
            for device_obj in nb_devices:
                name = device_obj.name
                site_name = device_obj.site.name
                lookup_cache[("device_object", name)] = device_obj
                lookup_cache[("device", name)] = device_obj.id
                lookup_cache[("site", site_name)] = device_obj.site.id
                found_names.add(name)
            for name in device_names:
                if name not in found_names:
                    lookup_cache[("device_object", name)] = None
            job.event(
                f"pre-seeded BGP device lookup cache with {len(nb_devices)} NetBox device object(s)"
            )

        if asn_values:
            nb_asns = bulk_filter(
                nb.ipam.asns, "asn", list(asn_values), fields="id,asn"
            )
            for asn_obj in nb_asns:
                lookup_cache[("asn", int(asn_obj.asn))] = asn_obj.id
            job.event(
                f"pre-seeded BGP ASN lookup cache with {len(nb_asns)} NetBox ASN object(s)"
            )

        if vrf_values:
            nb_vrfs = bulk_filter(
                nb.ipam.vrfs, "name", list(vrf_values), fields="id,name"
            )
            for vrf_obj in nb_vrfs:
                lookup_cache[("vrf", vrf_obj.name)] = vrf_obj.id
            job.event(
                f"pre-seeded BGP VRF lookup cache with {len(nb_vrfs)} NetBox VRF object(s)"
            )
    except Exception as exc:
        msg = f"failed to pre-seed BGP lookup cache: {exc}"
        job.event(msg, severity="WARNING")
        log.warning(f"{worker_name} - {msg}")


class NetboxBgpPeeringsTasks:

    @Task(
        input=GetBgpPeeringsInput,
        output=GetBgpPeeringsResult,
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        mcp={
            "annotations": {
                "title": "Get BGP Peerings",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def get_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve device BGP peerings from NetBox using REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): NetBox instance name.
            devices (list, optional): List of devices to retrieve BGP peerings for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - refresh: Ignore data in cache and replace it with data fetched from NetBox.
                - force: Use data in cache without checking if it is up to date.

        Returns:
            dict: Dictionary keyed by device name with BGP peerings details.

        Example return data for single bgp peering - same data as returned by NetBox built-in REST
        API explorer:

        ```
        "fceos4-fceos5-eth105": {
            "comments": "",
            "created": "2026-04-08T10:29:13.404863Z",
            "custom_fields": {},
            "description": "BGP peering between fceos4 and fceos5 on eth105",
            "device": {
                "description": "",
                "display": "fceos4 (UUID-123451)",
                "id": 119,
                "name": "fceos4",
                "url": "http://netbox.lab:8000/api/dcim/devices/119/"
            },
            "display": "fceos4 (UUID-123451):fceos4-fceos5-eth105",
            "export_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "id": 7,
            "import_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "last_updated": "2026-04-18T21:39:38.947199Z",
            "local_address": {
                "address": "10.0.2.1/30",
                "description": "",
                "display": "10.0.2.1/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 489,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/489/"
            },
            "local_as": {
                "asn": 65100,
                "description": "BGP ASN for fceos4",
                "display": "AS65100",
                "id": 3,
                "url": "http://netbox.lab:8000/api/ipam/asns/3/"
            },
            "name": "fceos4-fceos5-eth105",
            "peer_group": {
                "description": "Test BGP peer group 1 for standard peerings",
                "display": "TEST_BGP_PEER_GROUP_1",
                "id": 3,
                "name": "TEST_BGP_PEER_GROUP_1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/bgppeergroup/3/"
            },
            "prefix_list_in": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "prefix_list_out": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "remote_address": {
                "address": "10.0.2.2/30",
                "description": "",
                "display": "10.0.2.2/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 490,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/490/"
            },
            "remote_as": {
                "asn": 65101,
                "description": "BGP ASN for fceos5",
                "display": "AS65101",
                "id": 4,
                "url": "http://netbox.lab:8000/api/ipam/asns/4/"
            },
            "site": {
                "description": "",
                "display": "SALTNORNIR-LAB",
                "id": 13,
                "name": "SALTNORNIR-LAB",
                "slug": "saltnornir-lab",
                "url": "http://netbox.lab:8000/api/dcim/sites/13/"
            },
            "status": {
                "label": "Active",
                "value": "active"
            },
            "tags": [],
            "tenant": {
                "description": "",
                "display": "SALTNORNIR",
                "id": 10,
                "name": "SALTNORNIR",
                "slug": "saltnornir",
                "url": "http://netbox.lab:8000/api/tenancy/tenants/10/"
            },
            "url": "http://netbox.lab:8000/api/plugins/bgp/bgpsession/7/",
            "virtualmachine": null
        }
        ```
        """
        instance = instance or self.default_instance
        devices = devices or []
        log.info(
            f"{self.name} - Get BGP peerings: Fetching BGP peerings for {len(devices)} device(s) from '{instance}' NetBox"
        )
        cache = self.cache_use if cache is None else cache
        ret = Result(
            task=f"{self.name}:get_bgp_peerings",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # Check if BGP plugin is installed
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(f"{instance} NetBox instance has no BGP Plugin installed")
            ret.failed = True
            return ret

        self.cache.expire()

        # Get device details to collect device IDs
        devices_result = self.get_devices(
            job=job, devices=devices, instance=instance, cache=False
        )
        if devices_result.errors:
            ret.errors.append(
                f"Failed to retrieve device details: {devices_result.errors}"
            )
            return ret

        nb = self._get_pynetbox(instance)

        for device_name in devices:
            # Skip devices not found in NetBox
            if device_name not in devices_result.result:
                msg = f"Device '{device_name}' not found in NetBox"
                job.event(msg, resource=instance, severity="WARNING")
                log.warning(msg)
                ret.errors.append(msg)
                continue

            device_id = devices_result.result[device_name]["id"]
            cache_key = f"get_bgp_peerings::{device_name}"
            cached_data = self.cache.get(cache_key)

            # Mode: force with cached data - use cache directly
            if cache == "force" and cached_data is not None:
                ret.result[device_name] = cached_data
                job.event(
                    f"using cached BGP peerings for '{device_name}' (forced)",
                    resource=instance,
                )
                continue

            # Mode: cache disabled - fetch without caching
            if cache is False:
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                job.event(
                    f"retrieved {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: refresh or no cached data - fetch and cache
            if cache == "refresh" or cached_data is None:
                if cache == "refresh" and cached_data is not None:
                    self.cache.delete(cache_key, retry=True)
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(
                    f"fetched and cached {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: cache=True with cached data - smart update (only fetch changed sessions)
            ret.result[device_name] = dict(cached_data)
            job.event(
                f"retrieved {len(cached_data)} BGP session(s) from cache for '{device_name}'",
                resource=instance,
            )

            # Fetch brief session info to compare timestamps
            brief_sessions = nb.plugins.bgp.session.filter(
                device_id=device_id, fields="id,last_updated,name"
            )
            netbox_sessions = {
                s.id: {"name": s.name, "last_updated": s.last_updated}
                for s in brief_sessions
            }

            # Build lookup maps
            cached_by_id = {s["id"]: name for name, s in cached_data.items()}
            session_ids_to_fetch = []
            sessions_to_remove = []

            # Find stale sessions (exist in both but timestamps differ) and deleted sessions
            for session_name, cached_session in cached_data.items():
                cached_id = cached_session["id"]
                if cached_id in netbox_sessions:
                    if (
                        cached_session["last_updated"]
                        != netbox_sessions[cached_id]["last_updated"]
                    ):
                        session_ids_to_fetch.append(cached_id)
                else:
                    sessions_to_remove.append(session_name)

            # Find new sessions in NetBox not in cache
            for nb_id in netbox_sessions:
                if nb_id not in cached_by_id:
                    session_ids_to_fetch.append(nb_id)

            # Remove deleted sessions
            for session_name in sessions_to_remove:
                ret.result[device_name].pop(session_name, None)
                log.info(
                    f"removed deleted session '{session_name}' from cache for '{device_name}'"
                )

            # Fetch updated/new sessions
            if session_ids_to_fetch:
                job.event(
                    f"fetching {len(session_ids_to_fetch)} updated BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                for session in self.bulk_filter(
                    nb.plugins.bgp.session, "id", session_ids_to_fetch
                ):
                    ret.result[device_name][session.name] = dict(session)

            # Update cache if any changes occurred
            if session_ids_to_fetch or sessions_to_remove:
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(f"updated cache for '{device_name}'", resource=instance)
            else:
                job.event(
                    f"using cache, it is up to date for '{device_name}'",
                    resource=instance,
                )

        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateBgpPeeringInput,
        output=CreateBgpPeeringResult,
        mcp={
            "annotations": {
                "title": "Create BGP Peering",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def create_bgp_peering(
        self,
        job: Job,
        instance: Union[None, str] = None,
        # single-session mode
        name: Union[None, str] = None,
        device: Union[None, str] = None,
        local_address: Union[None, str] = None,
        remote_address: Union[None, str] = None,
        local_as: Union[None, int] = None,
        remote_as: Union[None, int] = None,
        status: str = "active",
        description: Union[None, str] = None,
        vrf: Union[None, str] = None,
        peer_group: Union[None, str] = None,
        import_policies: Union[None, list] = None,
        export_policies: Union[None, list] = None,
        prefix_list_in: Union[None, str] = None,
        prefix_list_out: Union[None, str] = None,
        # interface-driven resolution
        local_interface: Union[None, str] = None,
        asn_source: Union[None, str, dict] = None,
        name_template: Union[None, str] = "{{device}}_{{vrf}}_{{remote_address}}",
        # mirror session
        create_reverse: bool = True,
        # bulk mode
        bulk_create: Union[None, list] = None,
        # shared
        rir: Union[None, str] = None,
        message: Union[None, str] = None,
        branch: Union[None, str] = None,
        dry_run: bool = False,
        vrf_custom_field: str = "vrf",
        lookup_cache: Union[None, dict] = None,
    ) -> Result:
        """
        Create one or many BGP sessions in NetBox.

        Supports single-session mode (individual keyword arguments) and bulk mode
        (``bulk_create`` list of dicts).  IP addresses and ASNs are resolved from
        IPAM or created on demand.  When ``local_interface`` is provided the local
        address is resolved from IPAM; for P2P subnets (/30, /31, /127) the remote
        address is derived automatically.

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            name (str, optional): Session name. Derived from ``name_template`` when omitted.
            device (str, optional): Local device name. Required in single-session mode.
            local_address (str, optional): Local IP address string. Derived from ``local_interface`` when omitted.
            remote_address (str, optional): Remote IP address string. Derived from P2P peer when ``local_interface`` is used.
            local_as (int, optional): Local AS number string. Derived from ``asn_source`` when omitted.
            remote_as (int, optional): Remote AS number string. Derived from ``asn_source`` on remote device when omitted.
            status (str): Session status. Default ``'active'``.
            description (str, optional): Session description.
            vrf (str, optional): VRF name.
            peer_group (str, optional): Peer group name (resolved or created).
            import_policies (list, optional): List of import routing-policy names.
            export_policies (list, optional): List of export routing-policy names.
            prefix_list_in (str, optional): Inbound prefix-list name.
            prefix_list_out (str, optional): Outbound prefix-list name.
            local_interface (str, optional): Local interface name or bracket-range pattern.
            asn_source (str or dict, optional): Dot-path string through device data or
                dict of kwargs for ``nb.ipam.asns.get`` for automatic ASN resolution.
            name_template (str, optional): Jinja2 template string for session names.
                Default ``'{{device}}_{{vrf}}_{{remote_address}}'``.
            create_reverse (bool): When ``True`` also create a mirror session on the
                remote device with local and remote IPs/ASNs swapped. Default ``True``.
            bulk_create (list, optional): List of session dicts for bulk creation.
            rir (str, optional): RIR name used when auto-creating ASNs.
            message (str, optional): Changelog message recorded on every NetBox write.
            branch (str, optional): NetBox branching plugin branch name.
            dry_run (bool): When ``True`` return session names without writing.
            vrf_custom_field (str): Name of the BGP session custom field that stores
                the VRF object reference.  The custom field must be of type Object in
                NetBox pointing to the VRF content-type.  The value is always a single
                VRF object reference written into ``custom_fields[vrf_custom_field]``.
                Default ``'vrf'`` means ``custom_fields['vrf']``.

        Returns:
            Normal run::

                {"created": ["name1", ...], "exists": ["name2", ...]}

            Dry run::

                {"create": ["name1", ...], "exists": ["name2", ...]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:create_bgp_peering",
            result={},
            resources=[instance],
        )

        # Validate BGP plugin
        job.event(f"validating NetBox BGP plugin for '{instance}'")
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            msg = f"'{instance}' NetBox instance has no BGP plugin installed"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        nb = self._get_pynetbox(instance, branch=branch)

        if message:
            job.event("setting NetBox changelog message for BGP session create")
            nb.http_session.headers["X-Changelog-Message"] = message

        lookup_cache = lookup_cache if lookup_cache is not None else {}
        name_template = name_template or "{{device}}_{{vrf}}_{{remote_address}}"

        # Validate VRF custom field and RIR
        job.event("validating BGP session VRF custom field and RIR")
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )
        rir_id = _resolve_rir_id(rir, nb, job, self.name, lookup_cache)

        # Build initial bgp_sessions list
        bgp_sessions = bulk_create or [
            {
                "name": name,
                "device": device,
                "local_address": local_address,
                "remote_address": remote_address,
                "local_as": local_as,
                "remote_as": remote_as,
                "status": status,
                "description": description,
                "vrf": vrf,
                "peer_group": peer_group,
                "import_policies": import_policies,
                "export_policies": export_policies,
                "prefix_list_in": prefix_list_in,
                "prefix_list_out": prefix_list_out,
                "local_interface": local_interface,
            }
        ]
        job.event(
            f"preparing {len(bgp_sessions)} BGP session create request(s), dry_run={dry_run}"
        )

        # Step 5a: Resolve interfaces, IPs, and discover remote devices for every
        # bgp_session in one pass.  Range expansion turns one bgp_session into many when a bracket
        # pattern is used in local_interface.
        job.event("resolving BGP session interface and peer details")
        base_bgp_sessions = []

        for bgp_session in bgp_sessions:
            bgp_session_device = bgp_session["device"]
            bgp_session_local_interface = bgp_session.get("local_interface")

            if bgp_session_local_interface:
                # Expand bracket-range pattern e.g. "Ethernet[1-4]/1.101"
                intf_names = expand_alphanumeric_range(bgp_session_local_interface)

                # Batch fetch interfaces and their IPs in two calls instead of 2N
                intf_by_name = {
                    i.name: i
                    for i in self.bulk_filter(
                        endpoint=nb.dcim.interfaces,
                        filter_by_key="name",
                        filter_by_values=intf_names,
                        device=bgp_session_device,
                        fields="id,name",
                    )
                }
                found_intf_ids = [i.id for i in intf_by_name.values()]
                ips_by_intf_id: Dict[int, list] = {}
                if found_intf_ids:
                    for _ip in self.bulk_filter(
                        endpoint=nb.ipam.ip_addresses,
                        filter_by_key="interface_id",
                        filter_by_values=found_intf_ids,
                        fields="id,address,assigned_object_id",
                    ):
                        ips_by_intf_id.setdefault(_ip.assigned_object_id, []).append(
                            _ip
                        )

                for intf_name in intf_names:
                    intf = intf_by_name.get(intf_name)
                    if not intf:
                        msg = f"interface '{intf_name}' not found on device '{bgp_session_device}'"
                        job.event(msg, severity="WARNING")
                        log.warning(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue

                    ip_list = ips_by_intf_id.get(intf.id, [])
                    if not ip_list:
                        msg = f"no IP address assigned to interface '{intf_name}' on '{bgp_session_device}'"
                        job.event(msg, severity="WARNING")
                        log.warning(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue

                    ip_cidr = ip_list[0].address  # e.g. "10.0.0.1/31"
                    local_addr = ip_cidr.split("/")[0]

                    bgp_session_remote_address = bgp_session.get("remote_address")

                    if not bgp_session_remote_address:
                        peer_ip = get_p2p_peer_ip(ip_cidr)
                        if peer_ip:
                            bgp_session_remote_address = peer_ip
                    if not bgp_session_remote_address:
                        msg = (
                            f"remote_address not provided and could not derive peer IP "
                            f"from interface '{intf_name}' address '{ip_cidr}' on "
                            f"device '{bgp_session_device}'"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue

                    new_bgp_session = dict(bgp_session)
                    new_bgp_session["device"] = bgp_session_device
                    new_bgp_session["device_name"] = bgp_session_device
                    new_bgp_session["local_address"] = local_addr
                    new_bgp_session["remote_address"] = bgp_session_remote_address
                    new_bgp_session.setdefault("remote_device_name", None)
                    base_bgp_sessions.append(new_bgp_session)
            else:
                if not bgp_session.get("remote_address"):
                    msg = (
                        f"remote_address not provided for BGP session on device "
                        f"'{bgp_session_device}'"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue
                bgp_session_copy = dict(bgp_session)
                bgp_session_copy["device_name"] = bgp_session_device
                bgp_session_copy.setdefault("remote_device_name", None)
                base_bgp_sessions.append(bgp_session_copy)

        preseed_bgp_lookup_cache(
            nb, base_bgp_sessions, lookup_cache, job, self.bulk_filter, self.name
        )

        reverse_sessions = []
        if create_reverse:
            for bgp_session in base_bgp_sessions:
                remote_device_name = bgp_session.get(
                    "remote_device_name"
                ) or _remote_device_name_from_ip(
                    _cached_bgp_ip_object(bgp_session["remote_address"], lookup_cache)
                )
                if not remote_device_name:
                    session_label = (
                        bgp_session.get("name")
                        or bgp_session.get("remote_address")
                        or "unknown"
                    )
                    msg = (
                        "failed to resolve reverse session remote device name for "
                        f"'{session_label}'"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue
                mirror_session = dict(bgp_session)
                mirror_session["device"] = remote_device_name
                mirror_session["device_name"] = remote_device_name
                mirror_session["local_address"] = bgp_session["remote_address"]
                mirror_session["remote_address"] = bgp_session["local_address"]
                mirror_session["local_as"] = bgp_session.get("remote_as")
                mirror_session["remote_as"] = bgp_session.get("local_as")
                mirror_session["remote_device_name"] = bgp_session["device_name"]
                mirror_session["local_interface"] = None
                mirror_session["name"] = None
                reverse_sessions.append(mirror_session)
        bgp_sessions = base_bgp_sessions + reverse_sessions

        all_device_names = {
            name: _cached_bgp_device_info(name, lookup_cache)
            for bgp_session in bgp_sessions
            for name in (
                bgp_session["device_name"],
                bgp_session.get("remote_device_name"),
            )
            if name
        }
        job.event(f"resolved {len(bgp_sessions)} BGP session create candidate(s)")

        # Step 5c: Pre-fetch existing sessions for idempotency (single API call)
        existing_session_names = set()
        if all_device_names:
            job.event(
                f"checking existing BGP sessions on {len(all_device_names)} device(s)"
            )
            try:
                existing = self.bulk_filter(
                    nb.plugins.bgp.session,
                    "device",
                    list(all_device_names),
                    fields="name,id",
                )
                existing_session_names = {s.name for s in existing}
                job.event(
                    f"found {len(existing_session_names)} existing BGP session(s)"
                )
            except Exception as exc:
                msg = (
                    f"could not pre-fetch BGP sessions for {list(all_device_names)}: "
                    f"{exc}; will check per-session"
                )
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")

        # Step 6: Process each resolved bgp_session
        if dry_run is True:
            ret.dry_run = True
            result = {"create": [], "exists": []}
        else:
            result = {"created": [], "exists": []}

        payloads = []

        job.event("building BGP session create payloads")
        for bgp_session in bgp_sessions:
            bgp_session_device = bgp_session.get("device")
            bgp_session_local_address = bgp_session.get("local_address")
            bgp_session_remote_address = bgp_session.get("remote_address")
            bgp_session_local_as = bgp_session.get("local_as")
            bgp_session_remote_as = bgp_session.get("remote_as")
            remote_device_name = bgp_session.get("remote_device_name")

            # Determine session name
            sname = bgp_session.get("name")
            if not sname:
                try:
                    sname = render_bgp_session_name(
                        name_template, bgp_session, lookup_cache
                    )
                except Exception as exc:
                    msg = (
                        f"failed to render name_template '{name_template}' for session "
                        f"'{bgp_session.get('name')}' on '{bgp_session_device}': {exc}"
                    )
                    job.event(msg, severity="ERROR")
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")
                    continue
                bgp_session["name"] = sname

            # Idempotency check (step 6i)
            if sname in existing_session_names:
                result["exists"].append(sname)
                continue

            # Dry run — report name and move on (step 6j)
            if dry_run is True:
                result["create"].append(sname)
                continue

            # --- Full resolution (non-dry-run) ---

            # Resolve ASNs from asn_source if not supplied (steps 6b / 6c)
            if asn_source and not bgp_session_local_as:
                dev_data = (all_device_names.get(bgp_session_device) or {}).get(
                    "data", {}
                )
                bgp_session_local_as = resolve_asn_from_source(dev_data, asn_source, nb)
                if not bgp_session_local_as:
                    msg = f"could not resolve local AS for '{sname}' via asn_source"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue

            if asn_source and not bgp_session_remote_as:
                if not remote_device_name:
                    msg = (
                        f"cannot resolve remote AS for '{sname}': remote device not "
                        f"identified and remote_as not provided"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue
                remote_dev_data = (all_device_names.get(remote_device_name) or {}).get(
                    "data", {}
                )
                bgp_session_remote_as = resolve_asn_from_source(
                    remote_dev_data, asn_source, nb
                )
                if not bgp_session_remote_as:
                    msg = f"could not resolve remote AS for '{sname}' via asn_source"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue

            # Resolve IP IDs and ASN IDs (steps 6d / 6e)
            local_ip_id = resolve_ip(
                bgp_session_local_address, nb, job, ret, self.name, lookup_cache
            )
            remote_ip_id = resolve_ip(
                bgp_session_remote_address, nb, job, ret, self.name, lookup_cache
            )
            local_as_id = resolve_asn(
                bgp_session_local_as, nb, rir_id, job, ret, self.name, lookup_cache
            )
            remote_as_id = resolve_asn(
                bgp_session_remote_as, nb, rir_id, job, ret, self.name, lookup_cache
            )

            resolution_errors = []
            if not local_ip_id:
                resolution_errors.append(f"local IP '{bgp_session_local_address}'")
            if not remote_ip_id:
                resolution_errors.append(f"remote IP '{bgp_session_remote_address}'")
            if not local_as_id:
                resolution_errors.append(f"local ASN '{bgp_session_local_as}'")
            if not remote_as_id:
                resolution_errors.append(f"remote ASN '{bgp_session_remote_as}'")
            if resolution_errors:
                msg = f"skipping '{sname}': could not resolve {', '.join(resolution_errors)}"
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue

            # Resolve device ID and site ID (step 6f)
            dev_info = all_device_names.get(bgp_session_device)
            if not dev_info:
                msg = (
                    f"device '{bgp_session_device}' not found in NetBox, "
                    f"skipping '{sname}'"
                )
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue

            device_id = dev_info["id"]
            site_id = dev_info["site_id"]
            addr_family = get_addr_family(bgp_session_local_address)

            payload = {
                "name": sname,
                "description": bgp_session.get("description") or "",
                "device": device_id,
                "local_address": local_ip_id,
                "local_as": local_as_id,
                "remote_address": remote_ip_id,
                "remote_as": remote_as_id,
                "status": bgp_session.get("status", "active"),
                "site": site_id,
            }

            # Optional fields (step 6h)
            payload.update(
                resolve_bgp_session_payload_fields(
                    {
                        k: bgp_session[k]
                        for k in (
                            "vrf",
                            "peer_group",
                            "import_policies",
                            "export_policies",
                            "prefix_list_in",
                            "prefix_list_out",
                        )
                        if bgp_session.get(k)
                    },
                    nb,
                    rir_id,
                    job,
                    ret,
                    self.name,
                    addr_family,
                    lookup_cache=lookup_cache,
                    vrf_custom_field=vrf_custom_field,
                )
            )

            payloads.append(payload)
        if dry_run is True:
            job.event(
                f"dry-run: {len(result['create'])} BGP session(s) would be created, "
                f"{len(result['exists'])} already exist"
            )
            ret.result = result
            job.event("BGP session create task complete")
            return ret
        job.event(
            f"prepared {len(payloads)} BGP session create payload(s), "
            f"{len(result['exists'])} already exist"
        )

        # Bulk create (step 7)
        if payloads:
            job.event(f"creating {len(payloads)} BGP session(s)")
            try:
                nb.plugins.bgp.session.create(payloads)
                result["created"].extend(p["name"] for p in payloads)
                msg = f"created {len(payloads)} BGP session(s)"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
            except Exception as e:
                msg = f"failed to create BGP sessions: {e}"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                log.error(f"{self.name} - {msg}")
        else:
            job.event("no BGP sessions to create")

        ret.result = result
        job.event("BGP session create task complete")
        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=UpdateBgpPeeringInput,
        output=UpdateBgpPeeringResult,
        mcp={
            "annotations": {
                "title": "Update BGP Peering",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def update_bgp_peering(
        self,
        job: Job,
        # single-session mode
        name: Union[None, str] = None,
        description: Union[None, str] = None,
        status: Union[None, str] = None,
        local_address: Union[None, str] = None,
        remote_address: Union[None, str] = None,
        local_as: Union[None, int] = None,
        remote_as: Union[None, int] = None,
        vrf: Union[None, str] = None,
        peer_group: Union[None, str] = None,
        import_policies: Union[None, list] = None,
        export_policies: Union[None, list] = None,
        prefix_list_in: Union[None, str] = None,
        prefix_list_out: Union[None, str] = None,
        # bulk mode
        bulk_update: Union[None, list] = None,
        # shared
        rir: Union[None, str] = None,
        message: Union[None, str] = None,
        branch: Union[None, str] = None,
        dry_run: bool = False,
        instance: Union[None, str] = None,
        vrf_custom_field: str = "vrf",
        lookup_cache: Union[None, dict] = None,
    ) -> Result:
        """
        Update one or many existing BGP sessions in NetBox.

        Supports single-session mode (``name`` plus field kwargs) and bulk mode
        (``bulk_update`` list of dicts).  Only non-None fields are updated.
        Idempotency is enforced: sessions with no effective changes are reported in
        ``in_sync`` and no write is performed.

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            name (str, optional): Existing session name. Required in single-session mode.
            description (str, optional): New description value.
            status (str, optional): New status value.
            local_address (str, optional): New local IP address string.
            remote_address (str, optional): New remote IP address string.
            local_as (str, optional): New local AS number string.
            remote_as (str, optional): New remote AS number string.
            vrf (str, optional): New VRF name.
            peer_group (str, optional): New peer group name.
            import_policies (list, optional): New list of import routing-policy names.
            export_policies (list, optional): New list of export routing-policy names.
            prefix_list_in (str, optional): Inbound prefix-list name.
            prefix_list_out (str, optional): Outbound prefix-list name.
            bulk_update (list, optional): List of session update dicts for bulk mode.
            rir (str, optional): RIR name used when auto-creating ASNs.
            message (str, optional): Changelog message recorded on every NetBox write.
            branch (str, optional): NetBox branching plugin branch name.
            dry_run (bool): When ``True`` return diff without writing.
            vrf_custom_field (str): Name of the BGP session custom field that stores
                the VRF object reference.  The custom field must be of type Object in
                NetBox pointing to the VRF content-type.  The value is always a single
                VRF object reference read from and written into
                ``custom_fields[vrf_custom_field]``.  Default ``'vrf'`` means
                ``custom_fields['vrf']``.

        Returns:
            Normal run::

                {"updated": ["name1", ...], "in_sync": ["name2", ...]}

            Dry run::

                {
                    "update": [{"name": "name1", "diff": {...}}, ...],
                    "in_sync": ["name2", ...],
                }
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:update_bgp_peering",
            result={},
            resources=[instance],
        )

        # Validate BGP plugin
        job.event(f"validating NetBox BGP plugin for '{instance}'")
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            msg = f"'{instance}' NetBox instance has no BGP plugin installed"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        nb = self._get_pynetbox(instance, branch=branch)

        if message:
            job.event("setting NetBox changelog message for BGP session update")
            nb.http_session.headers["X-Changelog-Message"] = message

        lookup_cache = lookup_cache if lookup_cache is not None else {}

        # Validate VRF custom field and RIR
        job.event("validating BGP session VRF custom field and RIR")
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )
        rir_id = _resolve_rir_id(rir, nb, job, self.name, lookup_cache)

        # Build list of sessions to update
        if bulk_update is not None:
            bgp_sessions = bulk_update
        else:
            _single_fields = (
                "description",
                "status",
                "local_address",
                "remote_address",
                "local_as",
                "remote_as",
                "vrf",
                "peer_group",
                "import_policies",
                "export_policies",
                "prefix_list_in",
                "prefix_list_out",
            )
            bgp_session = {
                k: v
                for k, v in locals().items()
                if k in _single_fields and v is not None
            }
            bgp_sessions = [{"name": name, **bgp_session}]
        job.event(
            f"preparing {len(bgp_sessions)} BGP session update request(s), dry_run={dry_run}"
        )

        result = {"updated": [], "in_sync": []}
        if dry_run is True:
            ret.dry_run = True
            result = {"update": [], "in_sync": []}

        # Fetch all existing sessions in a single batch call
        session_names = [s["name"] for s in bgp_sessions]
        job.event(f"fetching {len(session_names)} BGP session(s) from NetBox")
        nb_sessions_raw = self.bulk_filter(
            nb.plugins.bgp.session,
            "name",
            session_names,
            fields="id,name,description,status,local_address,remote_address,local_as,remote_as,custom_fields,peer_group,import_policies,export_policies,prefix_list_in,prefix_list_out",
        )
        normalised_nb = {
            s.name: normalise_nb_bgp_session(dict(s), vrf_custom_field=vrf_custom_field)
            for s in nb_sessions_raw
        }
        job.event(f"retrieved {len(normalised_nb)} BGP session(s) from NetBox")

        # Build updates dictionary by session name
        job.event("normalising BGP session update data")
        normalised_updates = {}
        for bgp_session in bgp_sessions:
            sname = bgp_session["name"]
            # Report sessions not found in NetBox
            if sname not in normalised_nb:
                msg = f"BGP session '{sname}' not found in NetBox, skipping update"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
            else:
                # Normalise policies to list
                if isinstance(bgp_session.get("import_policies"), str):
                    bgp_session["import_policies"] = [bgp_session["import_policies"]]
                if isinstance(bgp_session.get("export_policies"), str):
                    bgp_session["export_policies"] = [bgp_session["export_policies"]]
                normalised_updates[sname] = {
                    **bgp_session,
                    "import_policies": sorted(bgp_session.get("import_policies") or []),
                    "export_policies": sorted(bgp_session.get("export_policies") or []),
                }

        # Compare complete dictionaries using make_diff; classify in_sync vs changed
        job.event("calculating BGP session update diff")
        sessions_diff = self.make_diff(
            {"_": normalised_updates},
            {"_": normalised_nb},
        )["_"]

        changed_snames = set(sessions_diff["update"].keys())
        result["in_sync"].extend(sessions_diff["in_sync"])
        job.event(
            f"BGP session update diff complete: {len(changed_snames)} update, "
            f"{len(sessions_diff['in_sync'])} in sync"
        )

        if dry_run is True:
            job.event(
                "dry-run requested, returning BGP session update diff without changes"
            )
            result["update"] = [
                {"name": sname, "diff": changes}
                for sname, changes in sessions_diff["update"].items()
            ]
            ret.result = result
            ret.dry_run = True
            job.event("BGP session update task complete")
            return ret

        # Build update payloads — iterate over diff to get only changed fields per session
        job.event("building BGP session update payloads")
        update_payloads = []
        for sname, field_changes in sessions_diff["update"].items():
            nb_session = normalised_nb[sname]
            addr_family = get_addr_family(nb_session["local_address"] or "0.0.0.0")
            payload = {"id": nb_session["id"]}
            payload.update(
                resolve_bgp_session_payload_fields(
                    {f: c["new_value"] for f, c in field_changes.items()},
                    nb,
                    rir_id,
                    job,
                    ret,
                    self.name,
                    addr_family,
                    lookup_cache=lookup_cache,
                    vrf_custom_field=vrf_custom_field,
                )
            )
            update_payloads.append(payload)
        job.event(f"prepared {len(update_payloads)} BGP session update payload(s)")

        # Bulk update in a single pynetbox call
        if update_payloads:
            job.event(f"updating {len(update_payloads)} BGP session(s)")
            try:
                nb.plugins.bgp.session.update(update_payloads)
                result["updated"].extend(changed_snames)
                msg = f"updated {len(update_payloads)} BGP session(s)"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
            except Exception as e:
                msg = f"failed to bulk update BGP sessions: {e}"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                log.error(f"{self.name} - {msg}")
        else:
            job.event("no BGP sessions to update")

        ret.result = result
        job.event("BGP session update task complete")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncBgpPeeringsInput,
        output=SyncBgpPeeringsResult,
        mcp={
            "annotations": {
                "title": "Sync BGP Peerings",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        status: str = "active",
        dry_run: bool = False,
        process_deletions: bool = False,
        timeout: int = 60,
        branch: str = None,
        rir: str = None,
        message: str = None,
        name_template: str = "{{device}}_{{name}}",
        filter_by_remote_as: Union[None, List[int]] = None,
        filter_by_peer_group: Union[None, list] = None,
        filter_by_description: Union[None, str] = None,
        ignore_peer_ranges: Union[None, list] = None,
        vrf_custom_field: str = "vrf",
        **kwargs: object,
    ) -> Result:
        """
        Synchronize BGP sessions between live devices and NetBox.

        Collects BGP session data from devices via Nornir ``parse_ttp`` with
        ``get="bgp_neighbors"``, compares against existing NetBox BGP sessions and
        creates, updates, or (optionally) deletes sessions in NetBox accordingly.

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            devices (list, optional): List of device names to process.
            status (str): Status to assign to created/updated sessions when not ``established`` on device.
            dry_run (bool): If True, return diff report without writing to NetBox.
            process_deletions (bool): If True, delete NetBox sessions not found on device.
            timeout (int): Timeout in seconds for Nornir ``parse_ttp`` job.
            branch (str, optional): NetBox branching plugin branch name.
            rir (str, optional): RIR name to use when creating new ASNs in NetBox (e.g. ``RFC 1918``, ``ARIN``).
            message (str, optional): Changelog message recorded in NetBox for all create, update, and delete operations.
            name_template (str): Jinja2 template string for BGP session names written to NetBox.
                The template context includes the following values:

                - ``device`` — NetBox device object, rendered as device name by default
                - ``remote_device`` — NetBox remote device object resolved via remote_address or None
                - ``name`` — parsed session name - ``{vrf}_{remote_address}`` by default
                - ``description`` — session description
                - ``local_address`` — local IP address string (e.g. ``10.0.0.1``)
                - ``local_as`` — local AS number string (e.g. ``65100``)
                - ``remote_address`` — remote IP address string
                - ``remote_as`` — remote AS number string
                - ``vrf`` — VRF name or ``None``
                - ``state`` — device-reported state (e.g. ``established``)
                - ``peer_group`` — peer group name or ``None``

                Default: ``"{{device}}_{{name}}"``.
            filter_by_remote_as (list of int, optional): Only include sessions whose remote AS number
                matches one of the provided integer values. Applied to both NetBox and live device sessions.
            filter_by_peer_group (list, optional): Only include sessions whose peer group name matches
                one of the provided values. Applied to both NetBox and live device sessions.
            filter_by_description (str, optional): Only include sessions whose description matches
                this glob pattern (e.g. ``'*uplink*'``). Applied to both NetBox and live device sessions.
            ignore_peer_ranges (list, optional): provide prefixes to ignore BGP peers
            vrf_custom_field (str): Name of the BGP session custom field that stores
                the VRF object reference.  The custom field must be of type Object in
                NetBox pointing to the VRF content-type.  The value is always a single
                VRF object reference read from and written into
                ``custom_fields[vrf_custom_field]``.  Default ``'vrf'`` means
                ``custom_fields['vrf']``.
            **kwargs: Nornir host filters (e.g. ``FC``, ``FL``, ``FB``).

        Returns:
            Normal run result keyed by device name::

                {
                    "<device>": {
                        "created": ["<session_name>", ...],
                        "updated": ["<session_name>", ...],
                        "deleted": ["<session_name>", ...],
                        "in_sync": ["<session_name>", ...],
                    }
                }

            Dry-run result keyed by device name::

                {
                    "<device>": {
                        "create": ["<session_name>", ...],
                        "delete": ["<session_name>", ...],
                        "update": {"<session_name>": {"<field>": {"old_value": ..., "new_value": ...}, ...}, ...},
                        "in_sync": ["<session_name>", ...],
                    }
                }
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:sync_bgp_peerings",
            result={},
            resources=[instance],
        )

        # Normalised session dicts keyed by device name -> session name -> session field values
        normalised_nb = (
            {}
        )  # NetBox data: device name -> session name -> normalised field values
        normalised_live = (
            {}
        )  # Live data:   device name -> session name -> normalised field values
        lookup_cache: dict = {}
        # handle ranges
        ignore_peer_ranges = ignore_peer_ranges or [
            "127.0.0.0/8",
            "224.0.0.0/24",
            "fe80::/10",
            "ff02::/16",
        ]
        ignore_peer_nets = [
            ipaddress.ip_network(str(pfx), strict=False) for pfx in ignore_peer_ranges
        ]

        # Validate BGP plugin
        job.event(f"validating NetBox BGP plugin for '{instance}'")
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            msg = f"'{instance}' NetBox instance has no BGP plugin installed"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        # Validate VRF custom field
        job.event("validating BGP session VRF custom field")
        nb = self._get_pynetbox(instance)
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )

        # Source additional devices from Nornir filters
        if kwargs:
            job.event("resolving devices from Nornir filters")
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)
            job.event(
                f"resolved {len(nornir_hosts)} device(s) from Nornir filters, "
                f"{len(devices)} total device(s) selected"
            )

        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Sync BGP peerings: processing {len(devices)} device(s) in '{instance}'"
        )
        job.event(
            f"syncing BGP peerings for {len(devices)} device(s) in '{instance}', dry_run={dry_run}"
        )

        # Fetch existing NetBox BGP sessions
        job.event(f"fetching BGP session data from NetBox for {len(devices)} device(s)")
        nb_sessions_result = self.get_bgp_peerings(
            job=job, instance=instance, devices=devices, cache="refresh"
        )
        if nb_sessions_result.errors:
            job.event("failed to fetch BGP session data from NetBox", severity="ERROR")
            ret.errors.extend(nb_sessions_result.errors)
            ret.failed = True
            return ret

        # Fetch live BGP data from devices via Nornir parse_ttp
        job.event(
            f"fetching BGP session data from {len(devices)} device(s) via Nornir parse_ttp"
        )
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_neighbors", "FL": devices},
            workers="all",
            timeout=timeout,
        )

        # Build NetBox BGP sessions normalised dicts per device
        job.event("normalising NetBox BGP session data")
        for device_name in devices:
            # Normalise NetBox sessions for this device
            normalised_nb[device_name] = {}
            for sname, nb_session in nb_sessions_result.result.get(
                device_name, {}
            ).items():
                try:
                    normalised = normalise_nb_bgp_session(
                        nb_session, vrf_custom_field=vrf_custom_field
                    )
                except Exception as e:
                    log.warning(
                        f"{self.name} - failed to normalise NetBox session '{sname}' for '{device_name}': {e}"
                    )
                    continue
                if not bgp_session_matches_filters(
                    normalised,
                    filter_by_remote_as=filter_by_remote_as,
                    filter_by_peer_group=filter_by_peer_group,
                    filter_by_description=filter_by_description,
                    ignore_peer_nets=ignore_peer_nets,
                ):
                    continue
                normalised_nb[device_name][sname] = normalised
        nb_session_count = sum(len(sessions) for sessions in normalised_nb.values())
        job.event(
            f"normalised {nb_session_count} NetBox BGP session(s) after applying filters"
        )

        # pre-seed lookup cache from fetched NetBox sessions and all parsed live
        # sessions before rendering live session names.
        sessions_for_cache = []
        for device_name, sessions in normalised_nb.items():
            for session_data in sessions.values():
                sessions_for_cache.append({"device": device_name, **session_data})
        for wdata in parse_data.values():
            if wdata.get("failed"):
                continue
            for device_name, host_sessions in wdata.get("result", {}).items():
                for s in host_sessions:
                    sessions_for_cache.append(
                        {
                            "device": device_name,
                            "local_address": s.get("local_address"),
                            "local_as": s["local_as"],
                            "remote_address": s["remote_address"],
                            "remote_as": s["remote_as"],
                            "vrf": s.get("vrf"),
                        }
                    )
        if sessions_for_cache:
            job.event(
                f"pre-seeding BGP lookup cache from {len(sessions_for_cache)} NetBox/live session(s)"
            )
            preseed_bgp_lookup_cache(
                nb, sessions_for_cache, lookup_cache, job, self.bulk_filter, self.name
            )

        # Normalize live parse data per device
        job.event("normalising live BGP session data")
        for wname, wdata in parse_data.items():
            if wdata.get("failed"):
                msg = f"{wname} - failed to parse BGP session data from devices"
                log.warning(msg)
                job.event(msg, severity="WARNING")
                continue
            for device_name, host_sessions in (wdata.get("result") or {}).items():
                normalised_live.setdefault(device_name, {})
                for s in host_sessions:
                    parsed_name = s.get("name")
                    description = s.get("description") or ""
                    local_address = s.get("local_address")
                    local_as = s["local_as"]
                    remote_address = s["remote_address"]
                    remote_as = s["remote_as"]
                    peer_group = s.get("peer_group")
                    session_data = {
                        "device": device_name,
                        "name": parsed_name,
                        "description": description,
                        "local_address": local_address,
                        "local_as": local_as,
                        "remote_address": remote_address,
                        "remote_as": remote_as,
                        "vrf": s.get("vrf"),
                        "status": (
                            "active" if s.get("state") == "established" else status
                        ),
                        "peer_group": peer_group,
                        "import_policies": s.get("import_policies"),
                        "export_policies": s.get("export_policies"),
                        "prefix_list_in": s.get("prefix_list_in"),
                        "prefix_list_out": s.get("prefix_list_out"),
                    }
                    # attempt to resolve local ip if empty
                    if not local_address:
                        local_address = resolve_local_ip_via_peer(
                            device_name, remote_address, nb
                        )
                        if not local_address:
                            msg = (
                                f"{parsed_name or remote_address or 'unknown'} "
                                "- skipping, no local ip in parsed data, failed to resolve using peer ip"
                            )
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                            continue
                        session_data["local_address"] = local_address
                        msg = (
                            f"{parsed_name or remote_address} - resolved local ip "
                            f"'{local_address}' using peer ip"
                        )
                        log.info(msg)
                        job.event(msg)
                    try:
                        session_name = render_bgp_session_name(
                            name_template, session_data, lookup_cache
                        )
                    except Exception as exc:
                        msg = (
                            f"failed to render name_template '{name_template}' for session "
                            f"'{parsed_name}' on '{device_name}': {exc}"
                        )
                        ret.errors.append(msg)
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - {msg}")
                        continue
                    if not bgp_session_matches_filters(
                        session_data,
                        filter_by_remote_as=filter_by_remote_as,
                        filter_by_peer_group=filter_by_peer_group,
                        filter_by_description=filter_by_description,
                        ignore_peer_nets=ignore_peer_nets,
                    ):
                        continue
                    session_data["name"] = session_name
                    session_data.pop("device", None)
                    normalised_live[device_name][session_name] = session_data
        live_session_count = sum(len(sessions) for sessions in normalised_live.values())
        job.event(
            f"normalised {live_session_count} live BGP session(s) after applying filters"
        )

        # Single diff on the full normalised datasets
        job.event("calculating BGP session sync diff")
        full_diff = self.make_diff(normalised_live, normalised_nb)
        create_count = sum(len(actions["create"]) for actions in full_diff.values())
        update_count = sum(len(actions["update"]) for actions in full_diff.values())
        delete_count = sum(len(actions["delete"]) for actions in full_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in full_diff.values())
        job.event(
            "BGP session sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{delete_count} delete, {in_sync_count} in sync"
        )

        # Return dry-run results per device
        if dry_run is True:
            job.event(
                "dry-run requested, returning BGP session sync diff without changes"
            )
            ret.result = full_diff
            ret.dry_run = True
            return ret
        else:
            ret.diff = full_diff

        # Per-device result tracking
        device_results = {
            device_name: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for device_name, actions in full_diff.items()
        }

        # Build bulk_create list from full_diff — split pipe-separated policies to lists
        job.event("preparing BGP session create payloads")
        bulk_create = []
        for device_name, actions in full_diff.items():
            for sname in actions["create"]:
                session_data = normalised_live[device_name][sname]
                bulk_create.append(
                    {
                        "name": sname,
                        "device": device_name,
                        "description": session_data.get("description") or "",
                        "local_address": session_data.get("local_address"),
                        "local_as": session_data.get("local_as"),
                        "remote_address": session_data.get("remote_address"),
                        "remote_as": session_data.get("remote_as"),
                        "vrf": session_data.get("vrf"),
                        "status": session_data.get("status", "active"),
                        "peer_group": session_data.get("peer_group"),
                        "import_policies": session_data.get("import_policies"),
                        "export_policies": session_data.get("export_policies"),
                        "prefix_list_in": session_data.get("prefix_list_in"),
                        "prefix_list_out": session_data.get("prefix_list_out"),
                    }
                )
        job.event(f"prepared {len(bulk_create)} BGP session create payload(s)")

        # Build bulk_update list from full_diff
        job.event("preparing BGP session update payloads")
        bulk_update = []
        for device_name, actions in full_diff.items():
            for sname, field_changes in actions["update"].items():
                entry = {"name": sname}
                for field, change in field_changes.items():
                    new_value = change["new_value"]
                    if field in ("import_policies", "export_policies"):
                        entry[field] = new_value if new_value is not None else []
                    elif field in ("prefix_list_in", "prefix_list_out"):
                        entry[field] = new_value if new_value else None
                    else:
                        entry[field] = new_value
                bulk_update.append(entry)
        job.event(f"prepared {len(bulk_update)} BGP session update payload(s)")

        # Delegate writes to create_bgp_peering and update_bgp_peering
        if bulk_create:
            job.event(f"creating {len(bulk_create)} BGP session(s) from sync diff")
            create_result = self.create_bgp_peering(
                job=job,
                instance=instance,
                bulk_create=bulk_create,
                rir=rir,
                message=message,
                branch=branch,
                create_reverse=False,
                vrf_custom_field=vrf_custom_field,
                lookup_cache=lookup_cache,
            )
            ret.errors.extend(create_result.errors)
            created_names = create_result.result.get("created", [])
            for device_name, actions in full_diff.items():
                for sname in actions["create"]:
                    if sname in created_names:
                        device_results[device_name]["created"].append(sname)
        else:
            job.event("no BGP sessions to create")

        if bulk_update:
            job.event(f"updating {len(bulk_update)} BGP session(s) from sync diff")
            update_result = self.update_bgp_peering(
                job=job,
                instance=instance,
                bulk_update=bulk_update,
                rir=rir,
                message=message,
                branch=branch,
                vrf_custom_field=vrf_custom_field,
                lookup_cache=lookup_cache,
            )
            ret.errors.extend(update_result.errors)
            updated_names = set(update_result.result.get("updated", []))
            for device_name, actions in full_diff.items():
                for sname in actions["update"]:
                    if sname in updated_names:
                        device_results[device_name]["updated"].append(sname)
        else:
            job.event("no BGP sessions to update")

        # Deletion — batch-fetch all candidate sessions then delete individually
        if process_deletions:
            job.event("processing BGP session deletions")
            nb = self._get_pynetbox(instance, branch=branch)
            if message:
                nb.http_session.headers["X-Changelog-Message"] = message
            # Map session name → device name for all sessions to delete across devices
            all_deletions: Dict[str, str] = {}
            for device_name, actions in full_diff.items():
                for sname in actions["delete"]:
                    all_deletions[sname] = device_name
            if all_deletions:
                job.event(f"fetching {len(all_deletions)} BGP session(s) to delete")
                sessions_to_delete = self.bulk_filter(
                    nb.plugins.bgp.session,
                    "name",
                    list(all_deletions),
                    fields="id,name",
                )
                for session in sessions_to_delete:
                    device_name = all_deletions[session.name]
                    try:
                        session.delete()
                        device_results[device_name]["deleted"].append(session.name)
                        msg = (
                            f"deleted BGP session '{session.name}' for '{device_name}'"
                        )
                        job.event(msg)
                        log.info(f"{self.name} - {msg}")
                    except Exception as e:
                        msg = f"failed to delete BGP session '{session.name}' for '{device_name}': {e}"
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")
            else:
                job.event("no BGP sessions to delete")
        elif delete_count:
            job.event(
                f"skipping {delete_count} BGP session deletion(s), process_deletions=False"
            )
        else:
            job.event("no BGP sessions to delete")

        ret.result = device_results
        job.event("BGP peerings sync complete")

        return ret
