import fnmatch
import ipaddress
import logging
from enum import Enum
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, model_validator, StrictBool

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import NetboxCommonArgs, NetboxFastApiArgs
from .netbox_worker_utilities import resolve_vrf, resolve_ip

log = logging.getLogger(__name__)


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
) -> Union[int, None]:
    """Resolve or create an ASN, return its NetBox ID or None."""
    if not asn_str:
        return None
    try:
        asn_int = int(asn_str)
    except (ValueError, TypeError):
        return None
    existing = list(nb.ipam.asns.filter(asn=asn_int))
    if existing:
        return existing[0].id
    if not rir_id:
        msg = f"cannot create ASN '{asn_str}': no RIR provided, use 'rir' parameter"
        job.event(msg, severity="WARNING")
        log.warning(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None
    try:
        new_asn = nb.ipam.asns.create(asn=asn_int, rir=rir_id)
        msg = f"created ASN '{asn_str}' in NetBox IPAM"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_asn.id
    except Exception as e:
        msg = f"failed to create ASN '{asn_str}': {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
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


def resolve_asn_from_source(
    device_data: Dict[str, Any], asn_source: Union[str, Dict[str, Any]], nb: Any
) -> Union[None, str]:
    """
    Resolve an ASN from device data or a NetBox IPAM query.

    asn_source can be:

    - str  — dot-separated path through device_data dict/list
    - dict — kwargs passed to nb.ipam.asn.get(**asn_source); uses asn_obj.asn
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
        "local_address": (
            nb_session["local_address"]["address"].split("/")[0]
            if nb_session.get("local_address")
            else None
        ),
        "local_as": (
            nb_session["local_as"]["asn"] if nb_session.get("local_as") else None
        ),
        "remote_address": (
            nb_session["remote_address"]["address"].split("/")[0]
            if nb_session.get("remote_address")
            else None
        ),
        "remote_as": (
            nb_session["remote_as"]["asn"] if nb_session.get("remote_as") else None
        ),
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


def resolve_bgp_session_payload_fields(
    fields: dict,
    nb: Any,
    rir_id: Union[None, int],
    job: Job,
    ret: Result,
    worker_name: str,
    addr_family: str,
    _lookup_cache: Union[None, dict] = None,
    vrf_custom_field: str = "vrf",
) -> dict:
    """Resolve BGP session field name/value pairs to a partial NetBox API payload dict.

    Accepts a flat ``{field: desired_value}`` mapping and resolves each value to the
    corresponding NetBox object ID.  Returns a partial payload dict ready to be merged
    into a create or update payload.

    ``import_policies`` / ``export_policies`` values may be either a list of policy
    names or a pipe-separated string; both forms are handled.

    ``_lookup_cache`` is an optional dict shared across multiple calls within the same
    task invocation to avoid redundant NetBox lookups for VRF / peer group / routing
    policy / prefix list objects.
    """
    if _lookup_cache is None:
        _lookup_cache = {}
    payload = {}
    for field, value in fields.items():
        if field in ("local_address", "remote_address"):
            ip_id = resolve_ip(value, nb, job, ret, worker_name)
            if ip_id:
                payload[field] = ip_id
        elif field in ("local_as", "remote_as"):
            asn_id = resolve_asn(value, nb, rir_id, job, ret, worker_name)
            if asn_id:
                payload[field] = asn_id
        elif field in ("description", "status"):
            payload[field] = value
        elif field == "vrf":
            if not vrf_custom_field:
                pass
            elif value:
                cache_key = ("vrf", value)
                if cache_key not in _lookup_cache:
                    _lookup_cache[cache_key] = resolve_vrf(
                        value, nb, job, ret, worker_name
                    )
                vrf_id = _lookup_cache[cache_key]
                payload.setdefault("custom_fields", {})[vrf_custom_field] = vrf_id
            else:
                payload.setdefault("custom_fields", {})[vrf_custom_field] = None
        elif field == "peer_group":
            if value:
                cache_key = ("peer_group", value)
                if cache_key not in _lookup_cache:
                    _lookup_cache[cache_key] = resolve_peer_group(
                        value, nb, job, ret, worker_name
                    )
                payload["peer_group"] = _lookup_cache[cache_key]
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
                if cache_key not in _lookup_cache:
                    _lookup_cache[cache_key] = resolve_route_policy(
                        p_name, nb, job, ret, worker_name
                    )
                if _lookup_cache[cache_key]:
                    ids.append(_lookup_cache[cache_key])
            payload[field] = ids
        elif field in ("prefix_list_in", "prefix_list_out"):
            if value:
                cache_key = ("prefix_list", value, addr_family)
                if cache_key not in _lookup_cache:
                    _lookup_cache[cache_key] = resolve_prefix_list(
                        value, nb, job, ret, worker_name, family=addr_family
                    )
                payload[field] = _lookup_cache[cache_key]
            else:
                payload[field] = None
    return payload


def _resolve_rir_id(
    rir: Union[None, str], nb: Any, job: Job, worker_name: str
) -> Union[None, int]:
    """Resolve RIR name to its NetBox ID; log a warning when not found."""
    if not rir:
        return None
    rir_obj = nb.ipam.rirs.get(name=rir)
    if rir_obj:
        return rir_obj.id
    msg = f"RIR '{rir}' not found in NetBox, ASN creation will fail if needed"
    job.event(msg, severity="WARNING")
    log.warning(f"{worker_name} - {msg}")
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


class BgpSessionStatusEnum(str, Enum):
    active = "active"
    planned = "planned"
    maintenance = "maintenance"
    offline = "offline"
    decommissioned = "decommissioned"


class SyncBgpPeeringsInput(NetboxCommonArgs, use_enum_values=True):
    devices: Union[None, List] = Field(
        None,
        description="List of device names to create BGP peerings for",
    )
    status: BgpSessionStatusEnum = Field(
        "active",
        description="Status to set on created/updated BGP sessions",
    )
    process_deletions: bool = Field(
        False,
        description="Delete BGP sessions present in NetBox but not found on the device",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    rir: Union[None, str] = Field(
        None,
        description="RIR name to use when creating new ASNs in NetBox (e.g. 'RFC 1918', 'ARIN')",
    )
    message: Union[None, str] = Field(
        None,
        description="Changelog message to record in NetBox for all create, update, and delete operations",
    )
    name_template: str = Field(
        "{device}_{name}",
        description=("Template f-string for BGP session names in NetBox. "),
        examples=[
            "Available variables: device, name, "
            "description, local_address, local_as, remote_address, remote_as, "
            "vrf, state, peer_group."
        ],
    )
    filter_by_remote_as: Union[None, List[int]] = Field(
        None,
        description="Only sync sessions whose remote AS number matches one of the provided integer values",
    )
    filter_by_peer_group: Union[None, List[str]] = Field(
        None,
        description="Only sync sessions whose peer group name matches one of the provided values",
    )
    filter_by_description: Union[None, str] = Field(
        None,
        description="Only sync sessions whose description matches this glob pattern (e.g. '*uplink*')",
    )
    vrf_custom_field: Union[StrictBool, StrictStr] = Field(
        "vrf",
        description="BGP session Object-type custom field name used to store VRF reference.",
        examples=[
            "Object-type custom field in NetBox pointing to the VRF content-type. "
            "The value is always a single VRF object reference read from and written to "
            "custom_fields[vrf_custom_field]. Default 'vrf' means custom_fields['vrf']."
        ],
    )


class BgpSessionCommonFields(BaseModel):
    """Common BGP session fields shared by bulk create and bulk update entry models."""

    name: StrictStr = Field(..., description="BGP session name")
    description: Union[None, StrictStr] = Field(None, description="Session description")
    status: Union[None, BgpSessionStatusEnum] = Field(
        None, description="Session status"
    )
    local_address: Union[None, StrictStr] = Field(None, description="Local IP address")
    remote_address: Union[None, StrictStr] = Field(
        None, description="Remote IP address"
    )
    local_as: Union[None, StrictInt] = Field(None, description="Local ASN")
    remote_as: Union[None, StrictInt] = Field(None, description="Remote ASN")
    vrf: Union[None, StrictStr] = Field(None, description="VRF name")
    peer_group: Union[None, StrictStr] = Field(None, description="Peer group name")
    import_policies: Union[None, List[StrictStr]] = Field(
        None, description="Import routing policies"
    )
    export_policies: Union[None, List[StrictStr]] = Field(
        None, description="Export routing policies"
    )
    prefix_list_in: Union[None, StrictStr] = Field(
        None, description="Inbound prefix list"
    )
    prefix_list_out: Union[None, StrictStr] = Field(
        None, description="Outbound prefix list"
    )


class BgpSessionBulkCreateFields(BgpSessionCommonFields):
    """Fields for a single BGP session entry used in bulk_create."""

    device: StrictStr = Field(..., description="Local device name")
    local_interface: Union[None, StrictStr] = Field(
        None, description="Local interface name or bracket-range pattern"
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> "BgpSessionBulkCreateFields":
        if self.local_interface:
            return self
        if self.local_address and self.remote_address:
            return self
        raise ValueError(
            "Bulk session entries require device and either local_interface or both local_address and remote_address."
        )


class CreateBgpPeeringInput(NetboxCommonArgs, use_enum_values=True):
    """Input model for create_bgp_peering task."""

    name: Union[None, StrictStr] = Field(None, description="Session name")
    device: Union[None, StrictStr] = Field(None, description="Local device name")
    local_address: Union[None, StrictStr] = Field(None, description="Local IP address")
    remote_address: Union[None, StrictStr] = Field(
        None, description="Remote IP address"
    )
    local_as: Union[None, StrictInt] = Field(None, description="Local ASN")
    remote_as: Union[None, StrictInt] = Field(None, description="Remote ASN")
    status: BgpSessionStatusEnum = Field("active", description="Session status")
    description: Union[None, StrictStr] = Field(None, description="Session description")
    vrf: Union[None, StrictStr] = Field(None, description="VRF name")
    peer_group: Union[None, StrictStr] = Field(None, description="Peer group name")
    import_policies: Union[None, List[StrictStr]] = Field(
        None, description="Import routing policies"
    )
    export_policies: Union[None, List[StrictStr]] = Field(
        None, description="Export routing policies"
    )
    prefix_list_in: Union[None, StrictStr] = Field(
        None, description="Inbound prefix list"
    )
    prefix_list_out: Union[None, StrictStr] = Field(
        None, description="Outbound prefix list"
    )
    local_interface: Union[None, StrictStr] = Field(
        None,
        description="Local interface name or bracket-range pattern to resolve local_address from IPAM.",
    )
    asn_source: Union[None, StrictStr, Dict[StrictStr, Any]] = Field(
        None,
        description=(
            "Dot-path string through device data e.g. 'custom_fields.asn' or dictionary for ASN filter query"
        ),
    )
    name_template: Union[None, StrictStr] = Field(
        None,
        description=("Template string for BGP session names."),
        examples=[
            "Available variables: device, local_address, remote_address. "
            "Default: '{device}_{vrf}_{remote_address}'."
        ],
    )
    create_reverse: bool = Field(
        True,
        description=(
            "When True, also create a reverse BGP session on the remote device "
            "with local and remote IPs/ASNs swapped."
        ),
    )
    bulk_create: Union[None, List[BgpSessionBulkCreateFields]] = Field(
        None,
        description="List of BGP session objects to create in bulk.",
    )
    rir: Union[None, StrictStr] = Field(
        None,
        description="RIR name used when auto-creating ASNs in NetBox (e.g. 'RFC 1918', 'ARIN').",
    )
    message: Union[None, StrictStr] = Field(
        None,
        description="Changelog message recorded on every NetBox write.",
    )
    vrf_custom_field: Union[StrictBool, StrictStr] = Field(
        "vrf",
        description="BGP session Object-type custom field name used to store VRF reference.",
        examples=[
            "Object-type custom field in NetBox pointing to the VRF content-type. "
            "The value is always a single VRF object reference read from and written to "
            "custom_fields[vrf_custom_field]. Default 'vrf' means custom_fields['vrf']."
        ],
    )

    @model_validator(mode="before")
    @classmethod
    def validate_single_or_bulk_pre(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        bulk_create = values.get("bulk_create")
        if bulk_create is None:
            if not values.get("device"):
                raise ValueError("Single-session mode requires 'device'.")
            if not values.get("local_address") and not values.get("local_interface"):
                raise ValueError(
                    "Single-session mode requires either 'local_address' or 'local_interface'."
                )
        return values


class UpdateBgpPeeringInput(NetboxCommonArgs, use_enum_values=True):
    """Input model for update_bgp_peering task."""

    # --- Single-session mode ---
    name: Union[None, StrictStr] = Field(
        None,
        description="Existing session name to update.",
    )
    description: Union[None, StrictStr] = Field(None, description="Description")
    status: Union[None, BgpSessionStatusEnum] = Field(None, description="Status value")
    local_address: Union[None, StrictStr] = Field(None, description="Local IP address")
    remote_address: Union[None, StrictStr] = Field(
        None, description="Remote IP address"
    )
    local_as: Union[None, StrictInt] = Field(None, description="Local ASN")
    remote_as: Union[None, StrictInt] = Field(None, description="Remote ASN")
    vrf: Union[None, StrictStr] = Field(None, description="VRF name")
    peer_group: Union[None, StrictStr] = Field(None, description="Peer group name")
    import_policies: Union[None, List[StrictStr]] = Field(
        None, description="Import routing policies"
    )
    export_policies: Union[None, List[StrictStr]] = Field(
        None, description="Export routing policies"
    )
    prefix_list_in: Union[None, StrictStr] = Field(
        None, description="Inbound prefix list"
    )
    prefix_list_out: Union[None, StrictStr] = Field(
        None, description="Outbound prefix list"
    )

    # --- Bulk mode ---
    bulk_update: Union[None, List[BgpSessionCommonFields]] = Field(
        None,
        description="List of BGP sessions to update in bulk.",
    )

    # --- Shared resolution options ---
    rir: Union[None, StrictStr] = Field(
        None, description="RIR name used when auto-creating ASNs in NetBox"
    )
    message: Union[None, StrictStr] = Field(
        None, description="Changelog message recorded on every NetBox write"
    )
    vrf_custom_field: Union[StrictBool, StrictStr] = Field(
        "vrf",
        description="BGP session Object-type custom field name used to store VRF reference.",
        examples=[
            "Object-type custom field in NetBox pointing to the VRF content-type. "
            "The value is always a single VRF object reference read from and written to "
            "custom_fields[vrf_custom_field]. Default 'vrf' means custom_fields['vrf']."
        ],
    )

    @model_validator(mode="after")
    def validate_single_or_bulk(self) -> "UpdateBgpPeeringInput":
        if self.bulk_update is None and self.name is None:
            raise ValueError(
                "Either 'name' (single-session mode) or 'bulk_update' (bulk mode) is required."
            )
        return self


class NetboxBgpPeeringsTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve device BGP peerings from Netbox using REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve BGP peerings for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - refresh: Ignore data in cache and replace it with data fetched from Netbox.
                - force: Use data in cache without checking if it is up to date.

        Returns:
            dict: Dictionary keyed by device name with BGP peerings details.

        Example return data for single bgp peering - same data as returned by Netbox built-in REST
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
            f"{self.name} - Get BGP peerings: Fetching BGP peerings for {len(devices)} device(s) from '{instance}' Netbox"
        )
        cache = self.cache_use if cache is None else cache
        ret = Result(
            task=f"{self.name}:get_bgp_peerings",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # Check if BGP plugin is installed
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(f"{instance} Netbox instance has no BGP Plugin installed")
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
            # Skip devices not found in Netbox
            if device_name not in devices_result.result:
                msg = f"Device '{device_name}' not found in Netbox"
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

            # Find new sessions in Netbox not in cache
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
                for session in nb.plugins.bgp.session.filter(id=session_ids_to_fetch):
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
        name_template: Union[None, str] = "{device}_{vrf}_{remote_address}",
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
                dict of kwargs for ``nb.ipam.asn.get`` for automatic ASN resolution.
            name_template (str, optional): Format string for session names. Default
                ``'{device}_{vrf}_{remote_address}'``.
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
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(
                f"'{instance}' NetBox instance has no BGP plugin installed"
            )
            ret.failed = True
            return ret

        nb = self._get_pynetbox(instance, branch=branch)

        if message:
            nb.http_session.headers["X-Changelog-Message"] = message

        # Validate VRF custom field and RIR
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )
        rir_id = _resolve_rir_id(rir, nb, job, self.name)

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

        # Step 5a: Resolve interfaces, IPs, and discover remote devices for every
        # bgp_session in one pass.  Range expansion turns one bgp_session into many when a bracket
        # pattern is used in local_interface.
        resolved_bgp_sessions = []
        # dict keyed by device name; values populated with {id, site_id, data} after batch fetch
        all_device_names = {}

        for bgp_session in bgp_sessions:
            bgp_session_device = bgp_session["device"]
            bgp_session_local_interface = bgp_session.get("local_interface")

            if bgp_session_local_interface:
                # Expand bracket-range pattern e.g. "Ethernet[1-4]/1.101"
                intf_names = expand_alphanumeric_range(bgp_session_local_interface)

                # Batch fetch interfaces and their IPs in two calls instead of 2N
                intf_by_name = {
                    i.name: i
                    for i in nb.dcim.interfaces.filter(
                        device=bgp_session_device, name=intf_names, fields="id,name"
                    )
                }
                found_intf_ids = [i.id for i in intf_by_name.values()]
                ips_by_intf_id: Dict[int, list] = {}
                if found_intf_ids:
                    for _ip in nb.ipam.ip_addresses.filter(
                        interface_id=found_intf_ids,
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
                    remote_device_name = None

                    if not bgp_session_remote_address:
                        peer_ip = get_p2p_peer_ip(ip_cidr)
                        if peer_ip:
                            bgp_session_remote_address = peer_ip
                            peer_ip_list = list(
                                nb.ipam.ip_addresses.filter(address=peer_ip)
                            )
                            if peer_ip_list and peer_ip_list[0].assigned_object:
                                obj = peer_ip_list[0].assigned_object
                                if hasattr(obj, "device") and obj.device:
                                    remote_device_name = obj.device.name
                                    all_device_names.setdefault(
                                        remote_device_name, None
                                    )

                    new_bgp_session = dict(bgp_session)
                    new_bgp_session["device"] = bgp_session_device
                    new_bgp_session["local_address"] = local_addr
                    new_bgp_session["remote_address"] = bgp_session_remote_address
                    new_bgp_session["remote_device_name"] = remote_device_name

                    if not new_bgp_session.get("name"):
                        try:
                            new_bgp_session["name"] = name_template.format(
                                **new_bgp_session,
                            )
                        except Exception as exc:
                            msg = (
                                f"name_template '{name_template}' failed for session "
                                f"'{new_bgp_session.get('name')}' on '{bgp_session_device}': {exc}"
                            )
                            ret.errors.append(msg)
                            log.error(f"{self.name} - {msg}")
                            continue

                    all_device_names.setdefault(bgp_session_device, None)
                    resolved_bgp_sessions.append(new_bgp_session)

                    # Build mirror (reverse) session at resolution time if remote device identified
                    if create_reverse and remote_device_name:
                        mirror_session = dict(bgp_session)
                        mirror_session["device"] = remote_device_name
                        mirror_session["local_address"] = bgp_session_remote_address
                        mirror_session["remote_address"] = local_addr
                        mirror_session["local_as"] = bgp_session.get("remote_as")
                        mirror_session["remote_as"] = bgp_session.get("local_as")
                        mirror_session["remote_device_name"] = bgp_session_device
                        mirror_session["local_interface"] = None
                        mirror_session["name"] = None
                        try:
                            mirror_session["name"] = name_template.format(
                                **mirror_session,
                            )
                        except Exception as exc:
                            msg = (
                                f"name_template '{name_template}' failed for mirror session "
                                f"on '{remote_device_name}': {exc}"
                            )
                            ret.errors.append(msg)
                            log.error(f"{self.name} - {msg}")
                        else:
                            resolved_bgp_sessions.append(mirror_session)
            else:
                bgp_session_copy = dict(bgp_session)
                bgp_session_copy["remote_device_name"] = None
                if bgp_session_device:
                    all_device_names.setdefault(bgp_session_device, None)
                resolved_bgp_sessions.append(bgp_session_copy)

        # Step 5b: Pre-fetch device data for all collected device names (single API call)
        if all_device_names:
            try:
                for dev_obj in nb.dcim.devices.filter(name=list(all_device_names)):
                    all_device_names[dev_obj.name] = {
                        "id": dev_obj.id,
                        "site_id": dev_obj.site.id if dev_obj.site else None,
                        "data": dict(dev_obj),
                    }
            except Exception as exc:
                log.warning(
                    f"{self.name} - could not pre-fetch device data for "
                    f"{list(all_device_names)}: {exc}"
                )

        # Step 5c: Pre-fetch existing sessions for idempotency (single API call)
        existing_session_names = set()
        if all_device_names:
            try:
                existing = nb.plugins.bgp.session.filter(
                    device=list(all_device_names), fields="name,id"
                )
                existing_session_names = {s.name for s in existing}
            except Exception as exc:
                log.warning(
                    f"{self.name} - could not pre-fetch BGP sessions for "
                    f"{list(all_device_names)}: {exc}; will check per-session"
                )

        # Step 6: Process each resolved bgp_session
        if dry_run:
            result = {"create": [], "exists": []}
        else:
            result = {"created": [], "exists": []}

        _lookup_cache: dict = {}
        payloads = []

        for bgp_session in resolved_bgp_sessions:
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
                    sname = name_template.format(
                        **bgp_session,
                    )
                except Exception as exc:
                    msg = (
                        f"name_template '{name_template}' failed for session "
                        f"'{bgp_session.get('name')}' on '{bgp_session_device}': {exc}"
                    )
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")
                    continue

            # Idempotency check (step 6i)
            if sname in existing_session_names:
                result["exists"].append(sname)
                continue

            # Dry run — report name and move on (step 6j)
            if dry_run:
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
            local_ip_id = resolve_ip(bgp_session_local_address, nb, job, ret, self.name)
            remote_ip_id = resolve_ip(
                bgp_session_remote_address, nb, job, ret, self.name
            )
            local_as_id = resolve_asn(
                bgp_session_local_as, nb, rir_id, job, ret, self.name
            )
            remote_as_id = resolve_asn(
                bgp_session_remote_as, nb, rir_id, job, ret, self.name
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
                    _lookup_cache=_lookup_cache,
                    vrf_custom_field=vrf_custom_field,
                )
            )

            payloads.append(payload)

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
                job.event(msg)
                ret.errors.append(msg)
                log.error(f"{self.name} - {msg}")

        ret.result = result
        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=UpdateBgpPeeringInput,
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
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(
                f"'{instance}' NetBox instance has no BGP plugin installed"
            )
            ret.failed = True
            return ret

        nb = self._get_pynetbox(instance, branch=branch)

        if message:
            nb.http_session.headers["X-Changelog-Message"] = message

        # Validate VRF custom field and RIR
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )
        rir_id = _resolve_rir_id(rir, nb, job, self.name)

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

        result = {"updated": [], "in_sync": []}
        if dry_run:
            result = {"update": [], "in_sync": []}

        # Fetch all existing sessions in a single batch call
        session_names = [s["name"] for s in bgp_sessions]
        nb_sessions_raw = list(
            nb.plugins.bgp.session.filter(
                name=session_names,
                fields="id,name,description,status,local_address,remote_address,local_as,remote_as,custom_fields,peer_group,import_policies,export_policies,prefix_list_in,prefix_list_out",
            )
        )
        normalised_nb = {
            s.name: normalise_nb_bgp_session(dict(s), vrf_custom_field=vrf_custom_field)
            for s in nb_sessions_raw
        }

        # Build updates dictionary by session name
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
        sessions_diff = self.make_diff(
            {"_": normalised_updates},
            {"_": normalised_nb},
        )["_"]

        changed_snames = set(sessions_diff["update"].keys())
        result["in_sync"].extend(sessions_diff["in_sync"])

        if dry_run:
            result["update"] = [
                {"name": sname, "diff": changes}
                for sname, changes in sessions_diff["update"].items()
            ]
            ret.result = result
            return ret

        # Build update payloads — iterate over diff to get only changed fields per session
        _lookup_cache: dict = {}
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
                    _lookup_cache=_lookup_cache,
                    vrf_custom_field=vrf_custom_field,
                )
            )
            update_payloads.append(payload)

        # Bulk update in a single pynetbox call
        if update_payloads:
            try:
                nb.plugins.bgp.session.update(update_payloads)
                result["updated"].extend(changed_snames)
                msg = f"updated {len(update_payloads)} BGP session(s)"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
            except Exception as e:
                msg = f"failed to bulk update BGP sessions: {e}"
                ret.errors.append(msg)
                log.error(f"{self.name} - {msg}")

        ret.result = result
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncBgpPeeringsInput,
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
        name_template: str = "{device}_{name}",
        filter_by_remote_as: Union[None, List[int]] = None,
        filter_by_peer_group: Union[None, list] = None,
        filter_by_description: Union[None, str] = None,
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
            name_template (str): Template string for BGP session names written to NetBox. Formatted with the
                following keyword arguments from parsing results:

                - ``device`` — device name (e.g. ``ceos-leaf-1``)
                - ``name`` — parsed session name - ``{vrf}_{remote_address}`` by default
                - ``description`` — session description
                - ``local_address`` — local IP address string (e.g. ``10.0.0.1``)
                - ``local_as`` — local AS number string (e.g. ``65100``)
                - ``remote_address`` — remote IP address string
                - ``remote_as`` — remote AS number string
                - ``vrf`` — VRF name or ``None``
                - ``state`` — device-reported state (e.g. ``established``)
                - ``peer_group`` — peer group name or ``None``

                Default: ``"{device}_{name}"``.
            filter_by_remote_as (list of int, optional): Only include sessions whose remote AS number
                matches one of the provided integer values. Applied to both NetBox and live device sessions.
            filter_by_peer_group (list, optional): Only include sessions whose peer group name matches
                one of the provided values. Applied to both NetBox and live device sessions.
            filter_by_description (str, optional): Only include sessions whose description matches
                this glob pattern (e.g. ``'*uplink*'``). Applied to both NetBox and live device sessions.
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

        # Validate BGP plugin
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(
                f"'{instance}' NetBox instance has no BGP plugin installed"
            )
            ret.failed = True
            return ret

        # Validate VRF custom field
        nb = self._get_pynetbox(instance)
        vrf_custom_field = _resolve_vrf_custom_field(
            vrf_custom_field, nb, job, self.name
        )

        # Source additional devices from Nornir filters
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Sync BGP peerings: processing {len(devices)} device(s) in '{instance}'"
        )

        # Fetch existing NetBox BGP sessions
        job.event(f"fetching BGP session data from Netbox for {len(devices)} device(s)")
        nb_sessions_result = self.get_bgp_peerings(
            job=job, instance=instance, devices=devices, cache="refresh"
        )
        if nb_sessions_result.errors:
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

        # Build Netbox BGP sessions normalised dicts per device
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
                if filter_by_remote_as:
                    if (normalised.get("remote_as") or 0) not in filter_by_remote_as:
                        continue
                if (
                    filter_by_peer_group
                    and normalised.get("peer_group") not in filter_by_peer_group
                ):
                    continue
                if filter_by_description and not fnmatch.fnmatch(
                    normalised.get("description") or "", filter_by_description
                ):
                    continue
                normalised_nb[device_name][sname] = normalised

        # Normalize live parse data per device
        for wname, wdata in parse_data.items():
            if wdata.get("failed"):
                log.warning(f"{wname} - failed to parse devices")
                continue
            for device_name, host_sessions in wdata.get("result", {}).items():
                normalised_live.setdefault(device_name, {})
                for s in host_sessions:
                    try:
                        session_name = name_template.format(device=device_name, **s)
                    except Exception as exc:
                        msg = (
                            f"name_template '{name_template}' failed for session "
                            f"'{s.get('name')}' on '{device_name}': {exc}"
                        )
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")
                        continue
                    remote_as_val = s.get("remote_as")
                    peer_group_val = s.get("peer_group")
                    description_val = s.get("description") or ""
                    if filter_by_remote_as:
                        if (remote_as_val or 0) not in filter_by_remote_as:
                            continue
                    if (
                        filter_by_peer_group
                        and peer_group_val not in filter_by_peer_group
                    ):
                        continue
                    if filter_by_description and not fnmatch.fnmatch(
                        description_val, filter_by_description
                    ):
                        continue
                    # attempt to resolve local ip if empty
                    local_address = s.get("local_address")
                    remote_address = s.get("remote_address")
                    if not local_address and remote_address:
                        local_address = resolve_local_ip_via_peer(
                            device_name, remote_address, nb
                        )
                        if not local_address:
                            msg = f"{session_name} - skipping, no local ip in parsed data, failed to resolve using peer ip"
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                            continue
                        msg = f"{session_name} - resolved local ip '{local_address}' using peer ip"
                        log.info(msg)
                        job.event(msg)
                    normalised_live[device_name][session_name] = {
                        "name": session_name,
                        "description": description_val,
                        "local_address": local_address,
                        "local_as": s.get("local_as"),
                        "remote_address": remote_address,
                        "remote_as": remote_as_val,
                        "vrf": s.get("vrf"),
                        "status": (
                            "active" if s.get("state") == "established" else status
                        ),
                        "peer_group": peer_group_val,
                        "import_policies": s.get("import_policies"),
                        "export_policies": s.get("export_policies"),
                        "prefix_list_in": s.get("prefix_list_in"),
                        "prefix_list_out": s.get("prefix_list_out"),
                    }

        # Single diff on the full normalised datasets
        full_diff = self.make_diff(normalised_live, normalised_nb)

        # Return dry-run results per device
        if dry_run:
            ret.result = full_diff
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

        # Build bulk_update list from full_diff
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

        # Delegate writes to create_bgp_peering and update_bgp_peering
        if bulk_create:
            create_result = self.create_bgp_peering(
                job=job,
                instance=instance,
                bulk_create=bulk_create,
                rir=rir,
                message=message,
                branch=branch,
                create_reverse=False,
                vrf_custom_field=vrf_custom_field,
            )
            ret.errors.extend(create_result.errors)
            created_names = create_result.result.get("created", [])
            for device_name, actions in full_diff.items():
                for sname in actions["create"]:
                    if sname in created_names:
                        device_results[device_name]["created"].append(sname)

        if bulk_update:
            update_result = self.update_bgp_peering(
                job=job,
                instance=instance,
                bulk_update=bulk_update,
                rir=rir,
                message=message,
                branch=branch,
                vrf_custom_field=vrf_custom_field,
            )
            ret.errors.extend(update_result.errors)
            updated_names = set(update_result.result.get("updated", []))
            for device_name, actions in full_diff.items():
                for sname in actions["update"]:
                    if sname in updated_names:
                        device_results[device_name]["updated"].append(sname)

        # Deletion — batch-fetch all candidate sessions then delete individually
        if process_deletions:
            nb = self._get_pynetbox(instance, branch=branch)
            if message:
                nb.http_session.headers["X-Changelog-Message"] = message
            # Map session name → device name for all sessions to delete across devices
            all_deletions: Dict[str, str] = {}
            for device_name, actions in full_diff.items():
                for sname in actions["delete"]:
                    all_deletions[sname] = device_name
            if all_deletions:
                sessions_to_delete = list(
                    nb.plugins.bgp.session.filter(name=list(all_deletions))
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

        ret.result = device_results

        return ret
