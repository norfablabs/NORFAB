import builtins
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from norfab.models import NorFabClientRunJob, Result
from norfab.utils.text import expand_alphanumeric_range

# --------------------------------------------------------------------------
# NETBOX WORKER CONFIGURATION MODEL
# --------------------------------------------------------------------------


class CacheUseEnum(str, Enum):
    force = "force"
    refresh = "refrresh"


class NetboxInstanceConfig(BaseModel):
    default: StrictBool = Field(
        None, description="Is this default instance of Netbox or not"
    )
    url: StrictStr = Field(None, description="Netbox URL")
    token: StrictStr = Field(None, description="Netbox auth token")
    ssl_verify: StrictBool = Field(True, description="Verify SSL certificates")


class NetboxConfigModel(BaseModel):
    cache_use: Union[CacheUseEnum, StrictBool] = Field(
        True, description="Use cache or not"
    )
    cache_ttl: StrictInt = Field(True, description="Cache TTL")
    netbox_connect_timeout: StrictInt = Field(
        10,
        gt=0,
        description="NetBox API connection timeout in seconds",
    )
    netbox_read_timeout: StrictInt = Field(
        300,
        gt=0,
        description="NetBox API response timeout in seconds",
    )
    netbox_retries: StrictInt = Field(
        3,
        ge=0,
        description="Number of retries for retryable NetBox API requests",
    )
    netbox_retry_backoff: Union[StrictInt, StrictFloat] = Field(
        0.5,
        ge=0,
        description="Backoff factor between NetBox API retries",
    )
    instances: Dict[StrictStr, NetboxInstanceConfig] = Field(
        None, description="Netbox instance config keyed by instance name"
    )


# --------------------------------------------------------------------------
# CORE NETBOX WORKER MODELS
# --------------------------------------------------------------------------


SyncActionIdentifier = Union[StrictStr, StrictInt]


class SyncActionSummary(BaseModel):
    """Actions applied by a synchronization task."""

    created: List[SyncActionIdentifier] = Field(default_factory=list)
    updated: List[SyncActionIdentifier] = Field(default_factory=list)
    deleted: List[SyncActionIdentifier] = Field(default_factory=list)
    in_sync: List[SyncActionIdentifier] = Field(default_factory=list)


class SyncActionSummaryMap(RootModel[Dict[StrictStr, SyncActionSummary]]):
    """Action summaries keyed by device, scope, or resource type."""

    root: Dict[StrictStr, SyncActionSummary] = Field(default_factory=dict)


class NetboxCommonArgs(BaseModel, use_enum_values=True, populate_by_name=True):
    """Model to enlist arguments common across Netbox service tasks"""

    instance: Union[None, StrictStr] = Field(
        None,
        description="Netbox instance name to target",
    )
    dry_run: StrictBool = Field(
        None,
        description="Do not commit to database",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )

    @staticmethod
    def source_instance() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.run_job("netbox", "get_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["result"]["instances"])


class NetboxBulkBatchArgs(BaseModel, use_enum_values=True, populate_by_name=True):
    """Common batch-size control for NetBox bulk write tasks."""

    batch_size: StrictInt = Field(
        1000,
        ge=1,
        description="Number of objects per NetBox bulk request",
        alias="batch-size",
    )


class NetboxFastApiArgs(
    NorFabClientRunJob, use_enum_values=True, populate_by_name=True
):
    """Model to specify arguments for FastAPI REST API endpoints"""

    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )


class NetboxNornirHostsFilters(BaseModel, use_enum_values=True, populate_by_name=True):
    """Nornir Fx host filters accepted by NetBox tasks."""

    FO: Union[None, Dict, List[Dict]] = Field(
        None, title="Filter Object", description="Filter hosts using Filter Object"
    )
    FB: Union[None, List[str], str] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using Glob Patterns",
    )
    FH: Union[None, List[StrictStr], StrictStr] = Field(
        None, title="Filter Hostname", description="Filter hosts by hostname"
    )
    FC: Union[None, List[str], str] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts containment of pattern in name",
    )
    FR: Union[None, List[str], str] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using Regular Expressions",
    )
    FG: Union[None, StrictStr] = Field(
        None, title="Filter Group", description="Filter hosts by group"
    )
    FP: Union[None, List[StrictStr], StrictStr] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP Prefix",
    )
    FL: Union[None, List[StrictStr], StrictStr] = Field(
        None, title="Filter List", description="Filter hosts by names list"
    )
    FM: Union[None, List[StrictStr], StrictStr] = Field(
        None, title="Filter platforM", description="Filter hosts by platform"
    )
    FX: Union[None, List[str], str] = Field(
        None,
        title="Filter eXclude",
        description="Filter hosts excluding them by name",
    )
    FN: Union[None, StrictBool] = Field(
        None,
        title="Filter Negate",
        description="Negate the match",
        json_schema_extra={"presence": True},
    )


# --------------------------------------------------------------------------
# BGP PEERINGS TASKS MODELS
# --------------------------------------------------------------------------


class BgpSessionStatusEnum(str, Enum):
    active = "active"
    planned = "planned"
    maintenance = "maintenance"
    offline = "offline"
    decommissioned = "decommissioned"


class GetBgpPeeringsInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="Device names to retrieve BGP peerings for",
    )
    cache: Union[None, StrictBool, StrictStr] = Field(
        None,
        description="Cache usage mode",
    )


class SyncBgpPeeringsInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, List] = Field(
        None,
        description="List of device names to create BGP peerings for",
    )
    status: BgpSessionStatusEnum = Field(
        "active",
        description="Status to set on created/updated BGP sessions",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    process_deletions: bool = Field(
        False,
        description="Delete BGP sessions present in NetBox but not found on the device",
        alias="process-deletions",
        json_schema_extra={"presence": True},
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
        "{{device}}_{{name}}",
        description=("Jinja2 template string for BGP session names in NetBox. "),
        alias="name-template",
        examples=[
            "Available variables: device, remote_device, name, "
            "description, local_address, local_as, remote_address, remote_as, "
            "vrf, state, peer_group."
        ],
    )
    filter_by_remote_as: Union[None, List[int]] = Field(
        None,
        description="Only sync sessions whose remote AS number matches one of the provided integer values",
        alias="filter-by-remote-as",
    )
    filter_by_peer_group: Union[None, List[str]] = Field(
        None,
        description="Only sync sessions whose peer group name matches one of the provided values",
        alias="filter-by-peer-group",
    )
    filter_by_description: Union[None, str] = Field(
        None,
        description="Only sync sessions whose description matches this glob pattern (e.g. '*uplink*')",
        alias="filter-by-description",
    )
    preserve_description: Union[None, StrictBool] = Field(
        None,
        description=(
            "Preserve existing NetBox descriptions always (true), only when live "
            "text is empty (null), or never (false)"
        ),
        alias="preserve-description",
    )
    ignore_peer_ranges: Union[None, List[str]] = Field(
        None,
        description="Only sync sessions whose peer IP is not within one of provided prefixes",
        alias="ignore-peer-ranges",
    )
    vrf_custom_field: Union[StrictBool, StrictStr] = Field(
        "vrf",
        description="BGP session Object-type custom field name used to store VRF reference.",
        alias="vrf-custom-field",
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
    custom_fields: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="BGP session custom fields"
    )
    tags: Union[None, List[Union[StrictStr, dict]]] = Field(
        None, description="BGP session tags"
    )


class BgpSessionBulkCreateFields(BgpSessionCommonFields):
    """Fields for a single BGP session entry used in bulk_create."""

    name: Union[None, StrictStr] = Field(
        None, description="Session name; derived from name_template when omitted"
    )
    device: StrictStr = Field(..., description="Local device name")
    local_interface: Union[None, StrictStr] = Field(
        None, description="Local interface name or bracket-range pattern"
    )
    local_as_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox ASN filters for the local AS when local_as is omitted"
    )
    remote_as_query: Union[None, Dict[StrictStr, Any]] = Field(
        None,
        description="NetBox ASN filters for the remote AS when remote_as is omitted",
    )
    local_ip_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox IP address filters when local_address is omitted"
    )
    remote_ip_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox IP address filters when remote_address is omitted"
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> "BgpSessionBulkCreateFields":
        if self.local_interface:
            return self
        if (self.local_address or self.local_ip_query) and (
            self.remote_address or self.remote_ip_query
        ):
            return self
        raise ValueError(
            "Bulk session entries require device and either local_interface or local and remote addresses or IP queries."
        )


class CreateBgpPeeringInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
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
    custom_fields: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="BGP session custom fields"
    )
    local_interface: Union[None, StrictStr] = Field(
        None,
        description="Local interface name or bracket-range pattern to resolve local_address from IPAM.",
    )
    local_as_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox ASN filters for the local AS when local_as is omitted"
    )
    remote_as_query: Union[None, Dict[StrictStr, Any]] = Field(
        None,
        description="NetBox ASN filters for the remote AS when remote_as is omitted",
    )
    local_ip_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox IP address filters when local_address is omitted"
    )
    remote_ip_query: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="NetBox IP address filters when remote_address is omitted"
    )
    name_template: Union[None, StrictStr] = Field(
        "{{device}}_{{vrf}}_{{remote_address}}",
        description=("Jinja2 template string for BGP session names."),
        examples=[
            "Available variables: device, remote_device, "
            "local_address, remote_address. Default: '{{device}}_{{vrf}}_{{remote_address}}'."
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
            if not any(
                values.get(field)
                for field in ("local_address", "local_interface", "local_ip_query")
            ):
                raise ValueError(
                    "Single-session mode requires 'local_address', 'local_interface', or 'local_ip_query'."
                )
        return values


class BgpSessionBulkUpdateFields(BgpSessionCommonFields):
    """BGP session update selected by NetBox ID or existing name."""

    name: Union[None, StrictStr] = Field(None, description="Existing session name")
    id: Union[None, StrictInt] = Field(None, description="NetBox session ID")
    new_name: Union[None, StrictStr] = Field(None, description="New session name")

    @model_validator(mode="after")
    def validate_selector(self) -> "BgpSessionBulkUpdateFields":
        if self.id is None and self.name is None:
            raise ValueError("Bulk update requires 'id' or 'name'.")
        return self


class UpdateBgpPeeringInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
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
    tags: Union[None, List[Union[StrictStr, dict]]] = Field(
        None, description="Tags to add"
    )
    custom_fields: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="Custom fields to update"
    )

    # --- Bulk mode ---
    bulk_update: Union[None, List[BgpSessionBulkUpdateFields]] = Field(
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


class GetBgpPeeringsResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="BGP peering data keyed by device name",
    )


class CreateBgpPeeringResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="BGP peering create result data",
    )


class UpdateBgpPeeringResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="BGP peering update result data",
    )


class SyncBgpPeeringsResult(Result):
    result: Union[SyncActionSummaryMap, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="BGP peering sync result keyed by device name",
    )


# --------------------------------------------------------------------------
# BRANCH TASKS MODELS
# --------------------------------------------------------------------------


class DeleteBranchInput(BaseModel, use_enum_values=True, populate_by_name=True):
    branch: Union[None, StrictStr] = Field(
        None,
        description="Branch name to delete",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )


class DeleteBranchResult(Result):
    result: Union[StrictBool, None] = Field(
        None,
        description="True when branch was deleted; None when branch was not found",
    )


# --------------------------------------------------------------------------
# CIRCUITS TASKS MODELS
# --------------------------------------------------------------------------


class GetCircuitsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    devices: list[StrictStr] = Field(
        ...,
        description="Device names to retrieve circuits for",
        alias="device-list",
    )
    cid: Union[None, list[StrictStr]] = Field(
        None,
        description="Circuit identifiers to retrieve",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return query content without running it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cache: Union[None, StrictBool, Literal["refresh", "force"]] = Field(
        None,
        description="Cache usage mode",
    )
    add_interface_details: StrictBool = Field(
        False,
        description="Add interface details to circuit results",
        alias="add-interface-details",
        json_schema_extra={"presence": True},
    )


class GetCircuitsResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Circuit data keyed by device name and circuit ID",
    )


# --------------------------------------------------------------------------
# CONNECTIONS TASKS MODELS
# --------------------------------------------------------------------------


class GetConnectionsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    devices: list[StrictStr] = Field(
        ...,
        description="Device names to retrieve connections for",
    )
    interfaces: Union[None, list[StrictStr]] = Field(
        None,
        description="Interface and port names to retrieve connections for",
    )
    interface_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to match interfaces and ports",
        alias="interface-regex",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return query content without running it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cache: Union[None, StrictBool, Literal["refresh", "force"]] = Field(
        None,
        description="Cache usage mode",
    )


class GetConnectionsResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Connection data keyed by device and interface name",
    )


# --------------------------------------------------------------------------
# CONTAINERLAB INVENTORY TASKS MODELS
# --------------------------------------------------------------------------


class GetContainerlabInventoryInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    lab_name: Union[None, StrictStr] = Field(
        None,
        description="Containerlab lab name",
        alias="lab-name",
    )
    tenant: Union[None, StrictStr] = Field(
        None,
        description="Tenant name to source devices from",
    )
    filters: Union[None, list[dict[StrictStr, Any]]] = Field(
        None,
        description="NetBox device filter dictionaries",
    )
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="Device names to include in the lab",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    image: Union[None, StrictStr] = Field(
        None,
        description="Container image to use for all nodes",
    )
    ipv4_subnet: StrictStr = Field(
        "172.100.100.0/24",
        description="IPv4 management subnet to allocate node addresses from",
        alias="ipv4-subnet",
    )
    ports: tuple[StrictInt, StrictInt] = Field(
        (12000, 15000),
        description="TCP/UDP port allocation range",
    )
    ports_map: Union[None, dict[StrictStr, Any]] = Field(
        None,
        description="Port mappings keyed by node name",
        alias="ports-map",
    )
    cache: Union[StrictBool, Literal["refresh", "force"]] = Field(
        False,
        description="Cache usage mode",
    )


class GetContainerlabInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Containerlab inventory data",
    )


# --------------------------------------------------------------------------
# DESIGN TASKS MODELS
# --------------------------------------------------------------------------


class DesignDocument(BaseModel):
    """Design metadata and supported object collections in one document."""

    model_config = ConfigDict(extra="forbid")

    design_input_schema: Union[str, dict, None] = None
    jinja_functions: dict[str, str] = Field(default={})
    custom_functions: dict[str, str] = Field(default={})
    tenants: list[dict[str, Any]] = Field(default=[])
    regions: list[dict[str, Any]] = Field(default=[])
    manufacturers: list[dict[str, Any]] = Field(default=[])
    platforms: list[dict[str, Any]] = Field(default=[])
    device_types: list[dict[str, Any]] = Field(default=[])
    device_roles: list[dict[str, Any]] = Field(default=[])
    sites: list[dict[str, Any]] = Field(default=[])
    roles: list[dict[str, Any]] = Field(default=[])
    rirs: list[dict[str, Any]] = Field(default=[])
    asn_ranges: list[dict[str, Any]] = Field(default=[])
    asns: list[dict[str, Any]] = Field(default=[])
    vlans: list[dict[str, Any]] = Field(default=[])
    vlan_groups: list[dict[str, Any]] = Field(default=[])
    vrfs: list[dict[str, Any]] = Field(default=[])
    l2vpns: list[dict[str, Any]] = Field(default=[])
    l2vpn_terminations: list[dict[str, Any]] = Field(default=[])
    route_targets: list[dict[str, Any]] = Field(default=[])
    rack_roles: list[dict[str, Any]] = Field(default=[])
    racks: list[dict[str, Any]] = Field(default=[])
    prefixes: list[dict[str, Any]] = Field(default=[])
    devices: list[dict[str, Any]] = Field(default=[])
    interfaces: list[dict[str, Any]] = Field(default=[])
    power_ports: list[dict[str, Any]] = Field(default=[])
    console_ports: list[dict[str, Any]] = Field(default=[])
    power_outlets: list[dict[str, Any]] = Field(default=[])
    console_server_ports: list[dict[str, Any]] = Field(default=[])
    connections: list[dict[str, Any]] = Field(default=[])
    ip_addresses: list[dict[str, Any]] = Field(default=[])
    bgp_communities: list[dict[str, Any]] = Field(default=[])
    routing_policies: list[dict[str, Any]] = Field(default=[])
    peer_groups: list[dict[str, Any]] = Field(default=[])
    bgp_peerings: list[dict[str, Any]] = Field(default=[])
    vrrp_groups: list[dict[str, Any]] = Field(default=[])
    vrrp_group_assignments: list[dict[str, Any]] = Field(default=[])
    primary_ip: list[dict[str, Any]] = Field(default=[])
    config_context: list[dict[str, Any]] = Field(default=[])
    local_context_data: list[dict[str, Any]] = Field(default=[])

    @model_validator(mode="after")
    def validate_design_allocations(self) -> "DesignDocument":
        for record in self.vlan_groups:
            if "custom_function" in record:
                continue
            scope_fields = (
                "rack",
                "location",
                "site",
                "site_group",
                "region",
                "cluster",
                "cluster_group",
            )
            selected = [
                field for field in scope_fields if record.get(field) is not None
            ]
            if "site" in selected and any(
                field in selected for field in ("rack", "location")
            ):
                selected.remove("site")
            if len(selected) > 1:
                raise ValueError(
                    "vlan_groups accepts only one scope; site may qualify rack or location"
                )
            for field in scope_fields:
                if field in record and (
                    not isinstance(record[field], str) or not record[field]
                ):
                    raise ValueError(f"vlan_groups.{field} must be a name string")
        for record in self.config_context:
            if "custom_function" in record:
                continue
            if not isinstance(record.get("name"), str) or not isinstance(
                record.get("data"), dict
            ):
                raise ValueError("config_context requires name and data dictionary")
            if "sites" in record and (
                not isinstance(record["sites"], list)
                or not all(isinstance(name, str) and name for name in record["sites"])
            ):
                raise ValueError("config_context.sites must be a list of site names")
        for record in self.local_context_data:
            if not all(
                isinstance(record.get(field), str) and record[field]
                for field in ("device", "site")
            ):
                raise ValueError("local_context_data requires device and site names")
            if "tenant" in record and not isinstance(record["tenant"], str):
                raise ValueError("local_context_data.tenant must be a name string")
            context = record.get("local_context_data")
            if not isinstance(context, dict):
                raise ValueError("local_context_data must be a dictionary")
            if "custom_function" in context:
                name = context["custom_function"]
                if not isinstance(name, str) or name not in self.custom_functions:
                    raise ValueError(f"unknown custom function: {name}")
                if "netbox" in context or "dry_run" in context or "device" in context:
                    raise ValueError(
                        "device, netbox, and dry_run are supplied by deployment"
                    )
        for record in self.connections:
            if "custom_function" in record:
                continue
            for field in ("a_terminations", "b_terminations"):
                endpoints = record.get(field)
                if not isinstance(endpoints, list) or len(endpoints) != 1:
                    raise ValueError(
                        f"connections.{field} requires one cable termination"
                    )
                endpoint = endpoints[0]
                port_fields = {
                    "interface",
                    "power_port",
                    "power_outlet",
                    "console_port",
                    "console_server_port",
                }
                if (
                    not isinstance(endpoint, dict)
                    or "device" not in endpoint
                    or len(set(endpoint) & port_fields) != 1
                    or len(endpoint) != 2
                    or not all(
                        isinstance(value, str) and value for value in endpoint.values()
                    )
                ):
                    raise ValueError(
                        "connection endpoints require device and one port name"
                    )
            if record["a_terminations"] == record["b_terminations"]:
                raise ValueError("a connection requires two different terminations")
        for collection in ("vrfs", "l2vpns"):
            for record in getattr(self, collection):
                if "custom_function" in record:
                    continue
                for field in ("import_route_targets", "export_route_targets"):
                    if field in record and (
                        not isinstance(record[field], list)
                        or not all(
                            isinstance(value, dict)
                            and isinstance(value.get("name"), str)
                            and value["name"]
                            for value in record[field]
                        )
                    ):
                        raise ValueError(
                            f"{collection}.{field} must be a list of route-target dictionaries with name"
                        )
        attachments = set()
        for record in self.l2vpn_terminations:
            if "custom_function" in record:
                continue
            if not isinstance(record.get("l2vpn"), str) or not record["l2vpn"]:
                raise ValueError("l2vpn_terminations requires an l2vpn name")
            interface = "device" in record or "interface" in record
            vlan = "group" in record or "vid" in record
            if (
                interface == vlan
                or (
                    interface
                    and not all(
                        isinstance(record.get(field), str) and record[field]
                        for field in ("device", "interface")
                    )
                )
                or (
                    vlan
                    and (
                        not isinstance(record.get("group"), str)
                        or not record["group"]
                        or not isinstance(record.get("vid"), int)
                        or isinstance(record["vid"], bool)
                    )
                )
            ):
                raise ValueError(
                    "l2vpn_terminations requires either device and interface or group and vid"
                )
            attachment = (
                ("dcim.interface", record["device"], record["interface"])
                if interface
                else ("ipam.vlan", record["group"], record["vid"])
            )
            if attachment in attachments:
                raise ValueError(f"duplicate l2vpn termination: {attachment}")
            attachments.add(attachment)
        for record in self.peer_groups:
            if "custom_function" not in record and (
                not isinstance(record.get("name"), str) or not record["name"]
            ):
                raise ValueError("peer_groups requires a non-empty name")
        for record in self.bgp_peerings:
            if "custom_function" not in record:
                task_record = dict(record)
                for field in ("import_policies", "export_policies"):
                    if field not in record:
                        continue
                    policies = record[field]
                    if not isinstance(policies, list) or not all(
                        isinstance(policy, dict) and isinstance(policy.get("name"), str)
                        for policy in policies
                    ):
                        raise ValueError(
                            f"bgp_peerings.{field} requires policy dictionaries with name"
                        )
                    task_record[field] = [policy["name"] for policy in policies]
                CreateBgpPeeringInput.model_validate(task_record)
        for collection, fields in {
            "tenants": ["group"],
            "regions": ["parent"],
            "platforms": ["manufacturer"],
            "device_types": ["manufacturer", "default_platform"],
            "sites": ["region", "tenant"],
            "asn_ranges": ["rir"],
            "vrfs": ["tenant"],
            "l2vpns": ["tenant"],
            "route_targets": ["tenant"],
            "racks": ["site", "role", "tenant"],
            "devices": ["site", "role", "platform", "tenant"],
            "prefixes": ["tenant", "role"],
            "ip_addresses": ["tenant"],
            "asns": ["rir", "tenant", "role"],
            "vlans": ["group", "role", "tenant"],
            "interfaces": ["device"],
        }.items():
            for record in getattr(self, collection):
                if "custom_function" in record:
                    continue
                for field in fields:
                    if record.get(field) is not None and not isinstance(
                        record[field], str
                    ):
                        raise ValueError(f"{collection}.{field} must be a name string")
        for record in self.devices:
            if "custom_function" not in record and "device_type" in record:
                reference = record["device_type"]
                if (
                    not isinstance(reference, dict)
                    or set(reference) != {"manufacturer", "model"}
                    or not all(isinstance(value, str) for value in reference.values())
                ):
                    raise ValueError(
                        "device_type requires manufacturer and model strings"
                    )
        for field in type(self).model_fields:
            records = getattr(self, field)
            if not isinstance(records, list):
                continue
            for record in records:
                if "custom_fields" in record:
                    if field in ("config_context", "vrrp_group_assignments"):
                        raise ValueError(f"{field} does not support custom_fields")
                    if not isinstance(record["custom_fields"], dict) or not all(
                        isinstance(key, str) for key in record["custom_fields"]
                    ):
                        raise ValueError(
                            f"{field}.custom_fields must be a dictionary with string keys"
                        )
                if "custom_function" in record:
                    name = record["custom_function"]
                    if not isinstance(name, str) or name not in self.custom_functions:
                        raise ValueError(f"unknown custom function: {name}")
                    if "netbox" in record or "dry_run" in record:
                        raise ValueError(
                            "netbox and dry_run are supplied by deployment"
                        )
        for records, identity, task_name, model in (
            (self.prefixes, "prefix", "create_prefix", CreatePrefixInput),
            (self.ip_addresses, "address", "create_ip", CreateIpInput),
            (self.asns, "asn", "create_asn", CreateBgpAsnInput),
            (self.vlans, "vid", "create_vlan", CreateVlanInput),
        ):
            for record in records:
                if "custom_function" in record:
                    continue
                if (identity in record) == (task_name in record):
                    raise ValueError(
                        f"records require exactly one of {identity} or {task_name}"
                    )
                if task_name in record:
                    if set(record) != {task_name}:
                        raise ValueError(f"task arguments belong inside {task_name}")
                    model.model_validate(record[task_name])
        for record in self.asns:
            if "custom_function" in record:
                continue
            if record.get("sites") is not None and (
                not isinstance(record["sites"], list)
                or not all(isinstance(name, str) and name for name in record["sites"])
            ):
                raise ValueError("asns.sites must be a list of site names")
            if "create_asn" in record:
                arguments = record["create_asn"]
                if not arguments.get("asn_range") or arguments.get("asn") is not None:
                    raise ValueError(
                        "create_asn requires asn_range without an explicit ASN; "
                        "use an unwrapped asn record for a known number"
                    )
        for record in self.ip_addresses:
            if "custom_function" in record:
                continue
            if ("device" in record) != ("interface" in record):
                raise ValueError("IP assignment requires both device and interface")
        for record in self.primary_ip:
            if "custom_function" in record:
                continue
            if not all(record.get(field) for field in ("device", "site", "address")):
                raise ValueError("primary_ip requires device, site, and address")
            if record.get("field", "primary_ip4") not in ("primary_ip4", "primary_ip6"):
                raise ValueError("primary_ip.field must be primary_ip4 or primary_ip6")
        for record in self.vrrp_groups:
            if "custom_function" in record:
                continue
            if not all(field in record for field in ("protocol", "group_id")):
                raise ValueError("vrrp_groups require protocol and group_id")
        for record in self.vrrp_group_assignments:
            if "custom_function" in record:
                continue
            if not all(
                field in record
                for field in ("protocol", "group_id", "device", "interface", "priority")
            ):
                raise ValueError(
                    "vrrp_group_assignments require protocol, group_id, device, interface, and priority"
                )
        for record in self.prefixes:
            if "custom_function" in record or "create_prefix" in record:
                continue
            for field in ("location", "site", "site_group", "region"):
                if field in record and not isinstance(record[field], str):
                    raise ValueError(f"prefixes.{field} must be a name string")
            if isinstance(record.get("vlan"), dict) and set(record["vlan"]) != {
                "group",
                "vid",
            }:
                raise ValueError("prefixes.vlan requires group and vid")
        for record in self.vlans:
            if "custom_function" in record:
                continue
            if "site" in record:
                raise ValueError("vlans.site is not supported; scope the VLAN group")
            if "vid" in record and not record.get("group"):
                raise ValueError("explicit VLANs require a group name")
            if "create_vlan" in record and "site" in record["create_vlan"]:
                raise ValueError("vlans.create_vlan.site is not supported")
            if "create_vlan" in record and record["create_vlan"].get("vid") is not None:
                raise ValueError(
                    "create_vlan is only for next-available allocation; "
                    "use an unwrapped vid record for a known VLAN ID"
                )
        return self


class DesignDeployInput(BaseModel, use_enum_values=True, populate_by_name=True):
    design: Union[StrictStr, dict[StrictStr, Any]] = Field(
        ...,
        description="NetBox design as YAML text, file URL, or parsed dictionary",
    )
    context: Union[StrictStr, dict[StrictStr, Any]] = Field(
        default={},
        description="Template context validated by design_input_schema",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    dry_run: StrictBool = Field(
        False,
        description="Validate design without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )


class DesignDeployResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="NetBox design creation result data",
    )


# --------------------------------------------------------------------------
# DEVICES TASKS MODELS
# --------------------------------------------------------------------------


class GetDevicesInput(BaseModel, use_enum_values=True, populate_by_name=True):
    filters: Union[None, list[dict[StrictStr, Any]]] = Field(
        None,
        description="NetBox device filter dictionaries",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return filters without querying NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="Device names to retrieve",
    )
    cache: Union[None, StrictBool, Literal["refresh", "force"]] = Field(
        None,
        description="Cache usage mode",
    )


class InventoryPatternCondition(
    BaseModel,
    extra="forbid",
    populate_by_name=True,
):
    """Condition used to map a live inventory value to a NetBox name."""

    glob: Union[None, StrictStr] = Field(
        None,
        description="Case-sensitive glob pattern matched against the live value",
    )
    regex: Union[None, StrictStr] = Field(
        None,
        description="Regular expression full-matched against the live value",
    )
    eval_expression: Union[None, StrictStr] = Field(
        None,
        alias="eval",
        description="Trusted Python expression evaluated with the live value in 'value'",
    )

    @model_validator(mode="after")
    def validate_condition(self) -> "InventoryPatternCondition":
        conditions = [self.glob, self.regex, self.eval_expression]
        if sum(value is not None for value in conditions) != 1:
            raise ValueError("exactly one of glob, regex, or eval is required")

        condition = next(value for value in conditions if value is not None)
        if not condition.strip():
            raise ValueError("inventory pattern condition cannot be empty")

        if self.regex is not None:
            try:
                re.compile(self.regex)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern: {exc}") from exc

        if self.eval_expression is not None:
            try:
                compile(self.eval_expression, "<inventory-map>", "eval")
            except SyntaxError as exc:
                raise ValueError(f"invalid eval expression: {exc}") from exc

        return self


InventoryPatternTargets = Dict[
    StrictStr,
    List[InventoryPatternCondition],
]


class InventoryPatternMap(BaseModel, extra="forbid"):
    """Pattern mappings from live inventory names to NetBox object names."""

    module_types: Dict[
        StrictStr,
        InventoryPatternTargets,
    ] = Field(
        default_factory=dict,
        description="Module type mappings keyed by NetBox manufacturer name",
    )
    module_bays: Dict[
        StrictStr,
        Dict[
            StrictStr,
            InventoryPatternTargets,
        ],
    ] = Field(
        default_factory=dict,
        description="Module bay mappings keyed by NetBox manufacturer and device type",
    )

    @model_validator(mode="after")
    def validate_mapping_keys(self) -> "InventoryPatternMap":
        for manufacturer, targets in self.module_types.items():
            if not manufacturer.strip():
                raise ValueError("module type manufacturer name cannot be empty")
            self.validate_targets(targets, "module type")

        for manufacturer, device_types in self.module_bays.items():
            if not manufacturer.strip():
                raise ValueError("module bay manufacturer name cannot be empty")
            for device_type, targets in device_types.items():
                if not device_type.strip():
                    raise ValueError("module bay device type cannot be empty")
                self.validate_targets(targets, "module bay")

        return self

    @staticmethod
    def validate_targets(
        targets: InventoryPatternTargets,
        target_type: str,
    ) -> None:
        for target_name, conditions in targets.items():
            if not target_name.strip():
                raise ValueError(f"{target_type} target name cannot be empty")
            if not conditions:
                raise ValueError(
                    f"{target_type} target '{target_name}' requires conditions"
                )


class DeviceInventoryRecord(BaseModel, extra="forbid"):
    """Parsed live device inventory record."""

    description: Union[None, StrictStr]
    slot: Union[None, StrictStr]
    module: Union[None, StrictStr]
    serial: Union[None, StrictStr]


class DeviceInventoryRecords(RootModel[List[DeviceInventoryRecord]]):
    """List of parsed live device inventory records."""


class SyncDeviceInventoryInput(
    NetboxNornirHostsFilters,
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync inventory for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp inventory job",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    process_deletions: StrictBool = Field(
        False,
        description="Delete NetBox modules present in module bays but absent from live inventory",
        alias="process-deletions",
        json_schema_extra={"presence": True},
    )
    create_module_types: StrictBool = Field(
        False,
        description="Create missing NetBox module types from live inventory model data",
        alias="create-module-types",
        json_schema_extra={"presence": True},
    )
    create_module_bays: StrictBool = Field(
        False,
        description="Create missing NetBox module bays using the live inventory slot names",
        alias="create-module-bays",
        json_schema_extra={"presence": True},
    )
    inventory_parse_template: Union[None, StrictStr] = Field(
        None,
        description="TTP template string or URL used to parse live inventory",
        alias="inventory-parse-template",
    )
    inventory_map: Union[None, StrictStr, InventoryPatternMap] = Field(
        None,
        description="Pattern mappings or nf:// YAML file reference",
        alias="inventory-map",
    )
    inventory_transform: Union[None, StrictStr] = Field(
        None,
        description="nf:// Python transformer file containing a transform function",
        alias="inventory-transform",
    )
    filter_by_module: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns selecting normalized module type names",
        alias="filter-by-module",
    )
    filter_by_slot: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns selecting normalized module bay names",
        alias="filter-by-slot",
    )
    ignore_modules: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns excluding normalized module type names",
        alias="ignore-modules",
    )
    ignore_slots: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns excluding normalized module bay names",
        alias="ignore-slots",
    )
    message: Union[None, StrictStr] = Field(
        None,
        description="Changelog message recorded on NetBox writes",
    )


class CheckDeviceSyncInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox devices to check sync state for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp jobs",
    )
    check_inventory: StrictBool = Field(
        True,
        description="Check device inventory sync state",
        json_schema_extra={"presence": True},
        alias="check-inventory",
    )
    check_interfaces: StrictBool = Field(
        True,
        description="Check interface sync state",
        json_schema_extra={"presence": True},
        alias="check-interfaces",
    )
    check_vrfs: StrictBool = Field(
        True,
        description="Check VRF and interface VRF assignment sync state",
        json_schema_extra={"presence": True},
        alias="check-vrfs",
    )
    check_vlans: StrictBool = Field(
        True,
        description="Check VLAN and interface VLAN assignment sync state",
        json_schema_extra={"presence": True},
        alias="check-vlans",
    )
    check_prefixes: StrictBool = Field(
        True,
        description="Check prefix sync state",
        json_schema_extra={"presence": True},
        alias="check-prefixes",
    )
    check_ip_addresses: StrictBool = Field(
        True,
        description="Check IP address sync state",
        json_schema_extra={"presence": True},
        alias="check-ip-addresses",
    )
    check_bgp_peerings: StrictBool = Field(
        True,
        description="Check BGP peering sync state",
        json_schema_extra={"presence": True},
        alias="check-bgp-peerings",
    )
    check_bgp_communities: StrictBool = Field(
        True,
        description="Check BGP community sync state",
        json_schema_extra={"presence": True},
        alias="check-bgp-communities",
    )
    check_vrrp: StrictBool = Field(
        True,
        description="Check VRRP sync state",
        json_schema_extra={"presence": True},
        alias="check-vrrp",
    )
    ignore_deletions: StrictBool = Field(
        False,
        description="Treat deletion-only differences as in sync",
        json_schema_extra={"presence": True},
        alias="ignore-deletions",
    )
    sync_kwargs: Union[None, StrictStr, Dict] = Field(
        None,
        description=(
            "Per-task sync arguments keyed by sync task name, or an nf:// YAML "
            "file containing them"
        ),
        alias="sync-kwargs",
    )


class SyncAllInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync",
    )
    timeout: StrictInt = Field(
        600,
        description="Timeout in seconds for Nornir parse_ttp jobs",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return diff without writing to NetBox",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview each sync stage and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    sync_kwargs: Union[None, StrictStr, Dict] = Field(
        None,
        description=(
            "Per-task sync arguments keyed by sync task name, or an nf:// YAML "
            "file containing them; use False as a task value to skip that task"
        ),
        alias="sync-kwargs",
    )


class GetDevicesResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Device data keyed by device name",
    )


class SyncDeviceInventoryResult(Result):
    result: Union[SyncActionSummaryMap, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="Device inventory sync result keyed by device name",
    )


class CheckDeviceSyncResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Device sync check summary keyed by device name",
    )


class SyncAllResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Per-device sync results keyed by device name",
    )


# --------------------------------------------------------------------------
# GRAPHQL TASKS MODELS
# --------------------------------------------------------------------------


class NetboxGraphqlInput(BaseModel, use_enum_values=True, populate_by_name=True):
    instance: StrictStr = Field(
        ...,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    query: StrictStr = Field(
        ...,
        description="GraphQL query string to execute",
    )
    variables: Union[None, dict[StrictStr, Any]] = Field(
        None,
        description="GraphQL variables keyed by variable name",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return request payload without executing it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    offset: StrictInt = Field(
        0,
        description="Starting pagination offset in records",
    )
    limit: StrictInt = Field(
        50,
        description="Number of records to fetch per GraphQL page",
    )


class NetboxGraphqlResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Merged GraphQL data payload",
    )


class GraphqlInput(BaseModel, use_enum_values=True, populate_by_name=True):
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return query payload without executing it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    obj: Union[None, StrictStr, dict[StrictStr, Any]] = Field(
        None,
        description="NetBox GraphQL object name or query object",
    )
    filters: Union[None, dict[StrictStr, Any], StrictStr] = Field(
        None,
        description="GraphQL filters as dict or raw filter string",
    )
    fields: Union[None, list[StrictStr]] = Field(
        None,
        description="GraphQL fields to return",
    )
    queries: Union[None, dict[StrictStr, Any]] = Field(
        None,
        description="GraphQL query definitions keyed by alias",
    )
    query_string: Union[None, StrictStr] = Field(
        None,
        description="Complete GraphQL query string to send as is",
        alias="query-string",
    )


class GraphqlResult(Result):
    result: Any = Field(
        {},
        description="GraphQL response payload",
    )


# --------------------------------------------------------------------------
# INTERFACES TASKS MODELS
# --------------------------------------------------------------------------


class InterfaceTypeEnum(str, Enum):
    virtual = "virtual"
    other = "other"
    bridge = "bridge"
    lag = "lag"


class CreateDeviceInterfacesInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True  # ignore aliases
):
    devices: List = Field(
        ...,
        description="List of device names or device objects to create interfaces for",
    )
    interface_name: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="Name(s) of the interface(s) to create",
    )
    interfaces_data: Union[None, List[Dict]] = Field(
        None,
        description="List of per-interface payload dicts, each must include 'name'",
        alias="interfaces-data",
    )
    interface_type: Union[StrictStr, InterfaceTypeEnum] = Field(
        "other",
        description="Interface type value, for example 'other', 'virtual', 'lag', or '1000base-t'",
        alias="interface-type",
    )
    description: Union[None, StrictStr] = Field(
        None, description="Interface description"
    )
    speed: StrictInt = Field(None, description="Interface speed in Kbit/s")
    mtu: StrictInt = Field(None, description="Maximum transmission unit size in bytes")


class BulkUpdateInterfaceItem(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    """A single interface update payload for bulk-update mode."""

    device: StrictStr = Field(
        ...,
        description="Device name the interface belongs to",
    )
    name: StrictStr = Field(
        ...,
        description="Interface name to update",
    )
    id: Union[None, StrictInt] = Field(
        None,
        description="NetBox interface ID; resolved from name when omitted",
    )
    type: Union[None, StrictStr] = Field(None, description="Interface type value")
    enabled: Union[None, StrictBool] = Field(
        None,
        description="Enable or disable the interface",
        json_schema_extra={"presence": True},
    )
    parent: Union[None, StrictInt] = Field(
        None, description="Parent interface ID integer"
    )
    lag: Union[None, StrictInt] = Field(None, description="LAG interface ID integer")
    mtu: Union[None, StrictInt] = Field(None, description="MTU value")
    mac_address: Union[None, StrictStr] = Field(
        None, description="MAC address", alias="mac-address"
    )
    speed: Union[None, StrictInt] = Field(None, description="Speed in Kbit/s")
    duplex: Union[None, StrictStr] = Field(None, description="Duplex setting")
    description: Union[None, StrictStr] = Field(
        None, description="Interface description"
    )
    mode: Union[None, StrictStr] = Field(
        None, description="Interface mode (access, tagged, tagged-all)"
    )
    untagged_vlan: Union[None, StrictInt] = Field(
        None, description="Untagged VLAN VID", alias="untagged-vlan"
    )
    tagged_vlans: Union[None, List[StrictInt]] = Field(
        None, description="List of tagged VLAN VIDs", alias="tagged-vlans"
    )
    vrf: Union[None, StrictInt] = Field(None, description="VRF ID integer")


class UpdateInterfacesInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True  # ignore aliases
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of device names whose interfaces to update in single-interface mode",
    )
    # single-interface mode
    name: Union[None, StrictStr] = Field(
        None,
        description="Interface name to update (single-interface mode)",
    )
    type: Union[None, StrictStr] = Field(
        None,
        description="Interface type value",
    )
    enabled: Union[None, StrictBool] = Field(
        None,
        description="Enable or disable the interface",
        json_schema_extra={"presence": True},
    )
    parent: Union[None, StrictInt] = Field(
        None,
        description="Parent interface ID integer",
    )
    lag: Union[None, StrictInt] = Field(
        None,
        description="LAG interface ID integer",
    )
    mtu: Union[None, StrictInt] = Field(
        None,
        description="MTU value",
    )
    mac_address: Union[None, StrictStr] = Field(
        None,
        description="MAC address",
        alias="mac-address",
    )
    speed: Union[None, StrictInt] = Field(
        None,
        description="Speed in Kbit/s",
    )
    duplex: Union[None, StrictStr] = Field(
        None,
        description="Duplex setting",
    )
    description: Union[None, StrictStr] = Field(
        None,
        description="Interface description",
    )
    mode: Union[None, StrictStr] = Field(
        None,
        description="Interface mode (access, tagged, tagged-all)",
    )
    untagged_vlan: Union[None, StrictInt] = Field(
        None,
        description="Untagged VLAN VID",
        alias="untagged-vlan",
    )
    tagged_vlans: Union[None, List[StrictInt]] = Field(
        None,
        description="List of tagged VLAN VIDs",
        alias="tagged-vlans",
    )
    vrf: Union[None, StrictInt] = Field(
        None,
        description="VRF ID Integer",
    )
    # bulk mode
    bulk_update: Union[None, List[BulkUpdateInterfaceItem]] = Field(
        None,
        description="List of interface update payload dicts; each must include 'device' and 'name' keys. 'id' is optional.",
        alias="bulk-update",
    )

    @model_validator(mode="after")
    def validate_single_or_bulk(self) -> "UpdateInterfacesInput":
        if self.bulk_update is None:
            if not self.devices:
                raise ValueError("Either 'bulk_update' or 'devices' is required.")
            if not self.name:
                raise ValueError("Single-interface mode requires 'name'.")
        return self


class UpdateInterfacesDescriptionInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    devices: List[StrictStr] = Field(
        ...,
        description="List of device names to update interface descriptions for",
    )
    description_template: Union[None, StrictStr] = Field(
        None,
        description="Jinja2 template string for the interface description",
        alias="description-template",
    )
    descriptions: Union[None, Dict[StrictStr, StrictStr]] = Field(
        None,
        description="Dict keyed by interface name with description string values",
    )
    interfaces: Union[None, List[StrictStr]] = Field(
        None,
        description="Specific interface names to update",
    )
    interface_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to filter interfaces by name",
        alias="interface-regex",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for NetBox API requests",
    )


class GetInterfacesInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True  # ignore aliases
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of device names to retrieve interfaces for",
    )
    interface_list: Union[None, List[StrictStr]] = Field(
        None,
        description="List of interface names to retrieve",
        alias="interface-list",
    )
    interface_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to match interfaces by name",
        alias="interface-regex",
    )
    ip_addresses: StrictBool = Field(
        None,
        description="If True, retrieves interface IP addresses",
        alias="ip-addresses",
        json_schema_extra={"presence": True},
    )
    inventory_items: StrictBool = Field(
        False,
        description="If True, retrieves interface inventory items",
        alias="inventory-items",
        json_schema_extra={"presence": True},
    )
    cache: Union[None, StrictBool, StrictStr] = Field(
        None,
        description="Cache control: True - use if up to date; False - skip; 'refresh' - fetch and overwrite; 'force' - use without staleness check",
    )
    brief: StrictBool = Field(
        False,
        description="If True, return stripped-down interface data for MCP/LLM context window optimisation",
        json_schema_extra={"presence": True},
    )
    raise_on_empty: StrictBool = Field(
        True,
        description="Raise an error when no interfaces match the query",
        alias="raise-on-empty",
        json_schema_extra={"presence": True},
    )


# --------------------------------------------------------------------------
# SHARED VLAN MAP MODELS
# --------------------------------------------------------------------------


class VlanMapRule(BaseModel, extra="forbid", populate_by_name=True):
    set_vlan_group: StrictStr = Field(
        ...,
        min_length=1,
        description="Exact NetBox VLAN group name for matching VLANs",
        alias="set-vlan-group",
    )
    match_vlan_ids: Union[None, List[StrictStr]] = Field(
        None,
        description="VLAN IDs or inclusive ranges narrowing the group VID ranges",
        alias="match-vlan-ids",
    )
    vlan_names: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns matched against VLAN names",
        alias="vlan-names",
    )
    match_device_names: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns matched against device names",
        alias="match-device-names",
    )
    match_interface_names: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns matched against interface names",
        alias="match-interface-names",
    )

    @model_validator(mode="after")
    def validate_rule(self) -> "VlanMapRule":
        for vlan_range in self.match_vlan_ids or []:
            values = expand_alphanumeric_range(f"[{vlan_range}]")
            parts = vlan_range.split("-")
            if (
                "[" in vlan_range
                or "]" in vlan_range
                or any(not vlan_id.isdigit() for vlan_id in values)
                or any(not 1 <= int(vlan_id) <= 4094 for vlan_id in values)
                or (
                    len(parts) == 2
                    and all(part.isdigit() for part in parts)
                    and int(parts[0]) > int(parts[1])
                )
            ):
                raise ValueError(f"invalid VLAN ID range '{vlan_range}'")
        for patterns in (
            self.vlan_names,
            self.match_device_names,
            self.match_interface_names,
        ):
            if patterns and any(not pattern.strip() for pattern in patterns):
                raise ValueError("VLAN map glob patterns cannot be empty")
        if not self.set_vlan_group.strip():
            raise ValueError("VLAN group name cannot be empty")
        return self


class InterfaceMapRule(BaseModel, extra="forbid", populate_by_name=True):
    device_name: StrictStr = Field(
        ...,
        min_length=1,
        description="Glob pattern matched against the NetBox device name",
        alias="device-name",
    )
    device_type: StrictStr = Field(
        ...,
        min_length=1,
        description="Glob pattern matched against the NetBox device type model",
        alias="device-type",
    )
    match: StrictStr = Field(
        ...,
        min_length=1,
        description="Literal substring to match in the live interface name",
    )
    replace: StrictStr = Field(
        ...,
        description="Replacement for the matched live interface name substring",
    )


class SyncDeviceInterfacesInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,  # ignore aliases
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    process_deletions: StrictBool = Field(
        False,
        description="Delete interfaces present in NetBox but absent in live data",
        json_schema_extra={"presence": True},
        alias="process-deletions",
    )
    interface_map: Union[None, StrictStr, List[InterfaceMapRule]] = Field(
        None,
        description="Ordered interface name mapping rules or nf:// YAML file reference",
        alias="interface-map",
    )
    filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by name, e.g. 'eth*' or 'Gi0/*'",
        alias="filter-by-name",
    )
    filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by description, e.g. 'uplink*'",
        alias="filter-by-description",
    )
    preserve_description: Union[None, StrictBool] = Field(
        None,
        description=(
            "Preserve existing NetBox descriptions always (true), only when live "
            "text is empty (null), or never (false)"
        ),
        alias="preserve-description",
    )
    update_type: StrictBool = Field(
        True,
        description="Safely update existing NetBox logical interface types",
        alias="update-type",
        json_schema_extra={"presence": True},
    )


class SyncMacAddressesInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync MAC addresses for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by name, e.g. 'eth*' or 'Gi0/*'",
        alias="filter-by-name",
    )
    filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by description, e.g. 'uplink*'",
        alias="filter-by-description",
    )
    filter_by_mac: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter MAC addresses, e.g. 'aa:bb:*'",
        alias="filter-by-mac",
    )


class GetInterfacesResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Interface data keyed by device and interface name",
    )


class CreateDeviceInterfacesResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Created interface data keyed by device name",
    )


class UpdateInterfacesDescriptionResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Interface description update result keyed by device name",
    )


class SyncDeviceInterfacesResult(Result):
    result: Union[SyncActionSummaryMap, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="Interface sync result keyed by device name",
    )


class SyncMacAddressesResult(Result):
    result: Union[SyncActionSummaryMap, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="MAC address sync result keyed by device name",
    )


# --------------------------------------------------------------------------
# IP TASKS MODELS
# --------------------------------------------------------------------------


class SyncDeviceIpInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync IP addresses for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    anycast_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="IP prefix(es) to classify as anycast role, or nf:// YAML file reference",
        alias="anycast-ranges",
    )
    ignore_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Prefix(es) to exclude IP addresses",
        alias="ignore-ranges",
    )
    ignore_vrf: StrictBool = Field(
        True,
        description="Ignore discovered interface VRFs during IP sync",
        alias="ignore-vrf",
    )
    interface_map: Union[None, StrictStr, List[InterfaceMapRule]] = Field(
        None,
        description="Ordered interface name mapping rules or nf:// YAML file reference",
        alias="interface-map",
    )
    filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict which interfaces are included by name, e.g. 'Loopback*' or 'Eth*'",
        alias="filter-by-name",
    )
    filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict which interfaces are included by description, e.g. 'uplink*'",
        alias="filter-by-description",
    )
    filter_by_prefix: Union[None, StrictStr] = Field(
        None,
        description="IP prefix to restrict which IP addresses are included, e.g. '10.0.0.0/8'",
        alias="filter-by-prefix",
    )
    filter_by_ip: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict which IP addresses are included, e.g. '10.0.*'",
        alias="filter-by-ip",
    )


class SyncDevicePrefixesInput(
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to collect prefixes from",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    ignore_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Exclude derived prefixes fully contained in these ranges",
        alias="ignore-ranges",
    )
    ignore_vrf: StrictBool = Field(
        True,
        description="Ignore discovered interface VRFs during prefix sync",
        alias="ignore-vrf",
    )
    ignore_site: StrictBool = Field(
        True,
        description="Ignore device sites during prefix sync",
        alias="ignore-site",
    )
    filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict source interfaces by name",
        alias="filter-by-name",
    )
    filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict source interfaces by description",
        alias="filter-by-description",
    )
    filter_by_prefix: Union[None, StrictStr] = Field(
        None,
        description="IP network containing prefixes to include",
        alias="filter-by-prefix",
    )


class CreateIpInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    vrrp_group: Union[None, StrictStr] = Field(
        None, min_length=1, description="Existing VRRP group name to assign the IP to"
    )

    @model_validator(mode="after")
    def validate_vrrp_group(self) -> "CreateIpInput":
        if self.vrrp_group is not None and (
            self.device is not None
            or self.interface is not None
            or self.is_primary is True
        ):
            raise ValueError(
                "vrrp_group cannot accompany device, interface, or is_primary=True"
            )
        return self

    custom_fields: Union[None, dict[StrictStr, Any]] = Field(
        None, description="Custom-field names and values for the IP address"
    )
    prefix: Union[StrictStr, dict] = Field(
        ...,
        description="Prefix to allocate IP from; IPv4/IPv6 network string, prefix description, or dict with pynetbox filter keys",
    )
    device: Union[None, StrictStr] = Field(
        None,
        description="Device name to associate the IP address with",
    )
    interface: Union[None, StrictStr] = Field(
        None,
        description="Interface name to associate the IP address with",
    )
    description: Union[None, StrictStr] = Field(
        None,
        description="Description for the allocated IP address",
    )
    vrf: Union[None, StrictStr] = Field(
        None,
        description="VRF name for the IP address",
    )
    tags: Union[None, list] = Field(
        None,
        description="List of tags to associate with the IP address",
    )
    dns_name: Union[None, StrictStr] = Field(
        None,
        description="DNS name for the IP address",
        alias="dns-name",
    )
    tenant: Union[None, StrictStr] = Field(
        None,
        description="Tenant name to associate with the IP address",
    )
    comments: Union[None, StrictStr] = Field(
        None,
        description="Additional comments for the IP address",
    )
    role: Union[None, StrictStr] = Field(
        None,
        description="Role for the IP address, e.g. 'loopback', 'anycast'",
    )
    status: Union[None, StrictStr] = Field(
        None,
        description="Status for the IP address, e.g. 'active', 'reserved', 'deprecated'",
    )
    is_primary: Union[None, StrictBool] = Field(
        None,
        description="If True, set the IP address as the primary IP for the device",
        alias="is-primary",
    )
    mask_len: Union[None, StrictInt] = Field(
        None,
        description="Mask length for the IP address; creates a child subnet of this length within the parent prefix",
        alias="mask-len",
    )
    ip_index: Union[None, StrictInt] = Field(
        None,
        ge=1,
        description="One-based index of a usable IP in the selected subnet",
        alias="ip-index",
    )
    create_peer_ip: Union[None, StrictBool] = Field(
        True,
        description="If True, creates an IP address for the link peer interface",
        alias="create-peer-ip",
    )


class CreateIpBulkInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    prefix: Union[StrictStr, dict] = Field(
        ...,
        description="Prefix to allocate IPs from; IPv4/IPv6 network string, prefix description, or dict with pynetbox filter keys",
    )
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of device names to assign IP addresses to",
    )
    interface_list: Union[None, list[StrictStr]] = Field(
        None,
        description="List of specific interface names to target",
        alias="interface-list",
    )
    interface_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to match interface names",
        alias="interface-regex",
    )
    description: Union[None, StrictStr] = Field(
        None,
        description="Description for the allocated IP addresses",
    )
    vrf: Union[None, StrictStr] = Field(
        None,
        description="VRF name for the IP addresses",
    )
    tags: Union[None, list] = Field(
        None,
        description="List of tags to associate with the IP addresses",
    )
    dns_name: Union[None, StrictStr] = Field(
        None,
        description="DNS name for the IP addresses",
        alias="dns-name",
    )
    tenant: Union[None, StrictStr] = Field(
        None,
        description="Tenant name to associate with the IP addresses",
    )
    comments: Union[None, StrictStr] = Field(
        None,
        description="Additional comments for the IP addresses",
    )
    role: Union[None, StrictStr] = Field(
        None,
        description="Role for the IP addresses, e.g. 'loopback', 'anycast'",
    )
    status: Union[None, StrictStr] = Field(
        None,
        description="Status for the IP addresses, e.g. 'active', 'reserved', 'deprecated'",
    )
    is_primary: Union[None, StrictBool] = Field(
        None,
        description="If True, set each IP address as the primary IP for its device",
        alias="is-primary",
    )
    mask_len: Union[None, StrictInt] = Field(
        None,
        description="Mask length for the IP addresses; creates a child subnet of this length within the parent prefix",
        alias="mask-len",
    )
    create_peer_ip: Union[None, StrictBool] = Field(
        True,
        description="If True, creates an IP address for the link peer interface",
        alias="create-peer-ip",
    )


class CreateIpResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Allocated IP address result data",
    )


class CreateIpBulkResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Bulk IP allocation result data",
    )


class SyncDeviceIpResult(Result):
    result: Union[SyncActionSummaryMap, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="IP address sync result keyed by device name",
    )


class SyncDevicePrefixesResult(Result):
    result: Union[SyncActionSummary, dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummary,
        description="Global prefix synchronization action lists",
    )


# --------------------------------------------------------------------------
# NETBOX CRUD MODELS
# --------------------------------------------------------------------------


class CrudListObjectsArgs(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    app_filter: Union[None, StrictStr, List[StrictStr]] = Field(
        None,
        description="Filter by NetBox app label or labels",
        alias="app-filter",
        examples=["dcim", ["dcim", "ipam"]],
    )
    include_metadata: StrictBool = Field(
        True,
        description="Include path, methods, schema name, and description in results",
        alias="include-metadata",
        json_schema_extra={"presence": True},
    )


class CrudSearchArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    query: StrictStr = Field(..., description="Search term")
    object_types: Union[None, List[StrictStr]] = Field(
        None,
        description="List of app.resource object types to search",
        alias="object-types",
        examples=[["dcim.devices", "ipam.prefixes"]],
    )
    fields: Union[None, List[StrictStr]] = Field(
        None, description="Specific fields to return; ignored when brief=True"
    )
    brief: StrictBool = Field(False, description="Return brief representation")
    limit: StrictInt = Field(
        10, ge=1, le=100, description="Max results per object type"
    )


class CrudReadArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    object_type: StrictStr = Field(
        ...,
        description="NetBox object type in app.resource format",
        alias="object-type",
        examples=["dcim.devices"],
    )
    object_id: Union[None, StrictInt, List[StrictInt]] = Field(
        None,
        description="Object ID or IDs to retrieve; ignores filters when set",
        alias="object-id",
    )
    filters: Union[None, Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        None, description="Filter dict(s)"
    )
    fields: Union[None, List[StrictStr]] = Field(
        None, description="Specific fields to return; ignored when brief=True"
    )
    brief: StrictBool = Field(False, description="Return brief representation")
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")
    ordering: Union[None, StrictStr, List[StrictStr]] = Field(
        None,
        description="Ordering field or fields; prefix with '-' for descending",
        examples=["name", ["-name", "id"]],
    )


class CrudCreateArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    object_type: StrictStr = Field(
        ...,
        description="NetBox object type in app.resource format",
        alias="object-type",
        examples=["dcim.interfaces"],
    )
    data: Union[Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        ..., description="Object data; dict for single, list for bulk"
    )
    dry_run: StrictBool = Field(False, description="Preview without creating")


class CrudUpdateArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    object_type: StrictStr = Field(
        ...,
        description="NetBox object type in app.resource format",
        alias="object-type",
    )
    data: Union[Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        ..., description="Object data; each item must contain 'id'"
    )
    dry_run: StrictBool = Field(False, description="Compute diffs without updating")


class CrudDeleteArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    object_type: StrictStr = Field(
        ...,
        description="NetBox object type in app.resource format",
        alias="object-type",
    )
    object_id: Union[StrictInt, List[StrictInt]] = Field(
        ...,
        description="Object ID or IDs to delete",
        alias="object-id",
    )
    dry_run: StrictBool = Field(False, description="Preview without deleting")


class CrudChangelogArgs(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    filters: Union[None, Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        None, description="Filter dict(s)"
    )
    fields: Union[None, List[StrictStr]] = Field(
        None, description="Specific fields to return"
    )
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")


class CrudListObjectsResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="NetBox object types keyed by app name",
    )


class CrudSearchResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Search results keyed by object type",
    )


class CrudReadResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Read result with count and object list",
    )


class CrudCreateResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Create result with object count and payloads",
    )


class CrudUpdateResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Update result with object count and payloads",
    )


class CrudDeleteResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Delete result with object count and IDs",
    )


class CrudChangelogResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Changelog result with count and entries",
    )


# --------------------------------------------------------------------------
# NETBOX WORKER MODELS
# --------------------------------------------------------------------------


class GetInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="NetBox worker inventory data",
    )


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="NetBox worker package and service versions",
    )


class GetNetboxStatusInput(BaseModel, use_enum_values=True, populate_by_name=True):
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )


class GetNetboxStatusResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="NetBox status data keyed by instance name",
    )


class GetCompatibilityInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetCompatibilityResult(Result):
    result: dict[StrictStr, Union[StrictBool, None]] = Field(
        {},
        description="NetBox compatibility state keyed by instance name",
    )


class CacheListInput(BaseModel, use_enum_values=True, populate_by_name=True):
    keys: StrictStr = Field(
        "*",
        description="Glob pattern to match cache keys",
    )
    details: StrictBool = Field(
        False,
        description="Return cache key age and expiry details",
        json_schema_extra={"presence": True},
    )


class CacheListResult(Result):
    result: list[Any] = Field(
        [],
        description="Cache keys or cache key details",
    )


class CacheClearInput(BaseModel, use_enum_values=True, populate_by_name=True):
    key: Union[None, StrictStr] = Field(
        None,
        description="Cache key to remove",
    )
    keys: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern of cache keys to remove",
    )


class CacheClearResult(Result):
    result: Union[list[StrictStr], StrictStr] = Field(
        [],
        description="Removed cache keys or no-op message",
    )


class CacheGetInput(BaseModel, use_enum_values=True, populate_by_name=True):
    key: Union[None, StrictStr] = Field(
        None,
        description="Cache key to retrieve",
    )
    keys: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern of cache keys to retrieve",
    )
    raise_missing: StrictBool = Field(
        False,
        description="Raise an error when requested cache key is missing",
        alias="raise-missing",
        json_schema_extra={"presence": True},
    )


class CacheGetResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Cache values keyed by cache key",
    )


class RestInput(BaseModel, use_enum_values=True, populate_by_name=True):
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    method: StrictStr = Field(
        "get",
        description="HTTP method to use",
    )
    api: StrictStr = Field(
        "",
        description="NetBox API path under /api",
    )


class RestResult(Result):
    result: Any = Field(
        {},
        description="NetBox REST API response payload",
    )


# --------------------------------------------------------------------------
# NORNIR INVENTORY TASKS MODELS
# --------------------------------------------------------------------------


class GetNornirInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    filters: Union[None, list[dict[StrictStr, Any]]] = Field(
        None,
        description="NetBox device filter dictionaries",
    )
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="Device names to include in inventory",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
    )
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )
    interfaces: Union[dict[StrictStr, Any], StrictBool] = Field(
        False,
        description="Include interface data or provide interface task kwargs",
    )
    connections: Union[dict[StrictStr, Any], StrictBool] = Field(
        False,
        description="Include connection data or provide connection task kwargs",
    )
    circuits: Union[dict[StrictStr, Any], StrictBool] = Field(
        False,
        description="Include circuit data or provide circuit task kwargs",
    )
    nbdata: StrictBool = Field(
        True,
        description="Include NetBox device data in host data",
        json_schema_extra={"presence": True},
    )
    bgp_peerings: Union[dict[StrictStr, Any], StrictBool] = Field(
        False,
        description="Include BGP peering data or provide BGP task kwargs",
        alias="bgp-peerings",
    )
    primary_ip: StrictStr = Field(
        "ip4",
        description="Primary IP family to use for hostname",
        alias="primary-ip",
    )
    cache: Union[None, StrictBool, Literal["refresh", "force"]] = Field(
        None,
        description="Cache usage mode",
    )


class GetNornirInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Nornir inventory data",
    )


# --------------------------------------------------------------------------
# VLAN TASK MODELS
# --------------------------------------------------------------------------


class CreateVlanGroupInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    name: StrictStr = Field(..., min_length=1, description="VLAN group name")
    site: StrictStr = Field(..., min_length=1, description="Site scope name")
    vid_ranges: List[List[StrictInt]] = Field(
        ..., description="Inclusive VLAN ID ranges"
    )


class CreateVlanGroupResult(Result):
    result: Dict[StrictStr, Any] = Field({}, description="VLAN group data")


class CreateVlanInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    vlan_group: StrictStr = Field(
        ...,
        min_length=1,
        description="VLAN group name to allocate or create the VLAN in",
        alias="vlan-group",
    )
    name: StrictStr = Field(..., min_length=1, description="VLAN name")
    vid: Union[None, StrictInt] = Field(
        None, ge=1, le=4094, description="Explicit VLAN ID; allocate when omitted"
    )
    status: StrictStr = Field("active", description="VLAN status")
    description: Union[None, StrictStr] = Field(None, description="VLAN description")
    tenant: Union[None, StrictStr] = Field(None, description="Tenant name")
    role: Union[None, StrictStr] = Field(None, description="IPAM role name")
    tags: Union[None, List[StrictStr]] = Field(None, description="VLAN tags")
    custom_fields: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="VLAN custom fields"
    )


class CreateVlanResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {}, description="Created, updated, existing, or proposed VLAN"
    )


class SyncVlansInput(
    NetboxNornirHostsFilters,
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the VLAN diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect VLANs from",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for Nornir host resolution and VLAN parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview VLAN changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    vlan_group: Union[None, StrictStr] = Field(
        None,
        min_length=1,
        description="Exact group name for live VLANs not matched by vlan-map",
        alias="vlan-group",
    )
    vlan_map: Union[None, StrictStr, List[VlanMapRule]] = Field(
        None,
        description="Ordered VLAN and interface membership mapping rules or nf:// YAML file reference",
        alias="vlan-map",
    )
    interface_map: Union[None, StrictStr, List[InterfaceMapRule]] = Field(
        None,
        description="Interface name mapping rules shared with interface sync",
        alias="interface-map",
    )
    require_vlan_group: StrictBool = Field(
        False,
        description="Require every live VLAN to resolve to a VLAN group",
        alias="require-vlan-group",
        json_schema_extra={"presence": True},
    )
    filter_by_vlan_ids: Union[None, List[StrictStr]] = Field(
        None,
        description="VLAN IDs or inclusive ranges to reconcile",
        alias="vlan-ids",
        examples=[["100", "200-299"]],
    )
    preserve_description: Union[None, StrictBool] = Field(
        None,
        description=(
            "Preserve existing NetBox descriptions always (true), only when live "
            "text is empty (null), or never (false)"
        ),
        alias="preserve-description",
    )

    @model_validator(mode="after")
    def validate_sync_vlans(self) -> "SyncVlansInput":
        for vlan_range in self.filter_by_vlan_ids or []:
            values = expand_alphanumeric_range(f"[{vlan_range}]")
            parts = vlan_range.split("-")
            if (
                "[" in vlan_range
                or "]" in vlan_range
                or any(not vlan_id.isdigit() for vlan_id in values)
                or any(not 1 <= int(vlan_id) <= 4094 for vlan_id in values)
                or (
                    len(parts) == 2
                    and all(part.isdigit() for part in parts)
                    and int(parts[0]) > int(parts[1])
                )
            ):
                raise ValueError(f"invalid VLAN ID range '{vlan_range}'")
        return self


class SyncVlansResultPayload(BaseModel):
    """Applied VLAN and related interface synchronization actions."""

    vlans: Dict[StrictStr, SyncActionSummary] = Field(default_factory=dict)
    interfaces: Dict[StrictStr, SyncActionSummary] = Field(default_factory=dict)


class SyncVlansResult(Result):
    result: Union[SyncVlansResultPayload, Dict[StrictStr, Any]] = Field(
        default_factory=SyncVlansResultPayload,
        description="VLAN actions by NetBox scope and interface actions by device",
    )


# --------------------------------------------------------------------------
# FHRP TASK MODELS
# --------------------------------------------------------------------------


class SyncVrrpInput(
    NetboxNornirHostsFilters,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the VRRP diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect VRRP state from",
    )
    name_template: StrictStr = Field(
        "{{ device.name }}_{{ interface }}_VRRP{{ group_id }}",
        min_length=1,
        max_length=500,
        description=(
            "Inline Jinja2 template or nf:// path used to render NetBox FHRP "
            "group names"
        ),
        alias="name-template",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for Nornir host resolution and VRRP parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview VRRP changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )


class SyncVrrpResult(Result):
    result: Union[SyncActionSummaryMap, Dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="VRRP sync actions keyed by NetBox device name",
    )


# --------------------------------------------------------------------------
# VRF TASK MODELS
# --------------------------------------------------------------------------


class SyncVrfsInput(
    NetboxNornirHostsFilters,
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the VRF diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect VRFs from",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for Nornir host resolution and VRF parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview VRF changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    device_custom_field: StrictStr = Field(
        "devices",
        min_length=1,
        description="VRF custom field that stores associated NetBox devices",
        alias="device-custom-field",
    )
    rpl_import_ipv4: StrictStr = Field(
        "rpl_import_ipv4",
        min_length=1,
        description="VRF custom field for IPv4 import routing policies",
        alias="rpl-import-ipv4",
    )
    rpl_import_ipv6: StrictStr = Field(
        "rpl_import_ipv6",
        min_length=1,
        description="VRF custom field for IPv6 import routing policies",
        alias="rpl-import-ipv6",
    )
    rpl_export_ipv4: StrictStr = Field(
        "rpl_export_ipv4",
        min_length=1,
        description="VRF custom field for IPv4 export routing policies",
        alias="rpl-export-ipv4",
    )
    rpl_export_ipv6: StrictStr = Field(
        "rpl_export_ipv6",
        min_length=1,
        description="VRF custom field for IPv6 export routing policies",
        alias="rpl-export-ipv6",
    )
    preserve_description: Union[None, StrictBool] = Field(
        None,
        description=(
            "Preserve existing NetBox descriptions always (true), only when live "
            "text is empty (null), or never (false)"
        ),
        alias="preserve-description",
    )
    interface_map: Union[None, StrictStr, List[InterfaceMapRule]] = Field(
        None,
        description="Ordered interface name mapping rules or nf:// YAML file reference",
        alias="interface-map",
    )


class SyncVrfsResultPayload(BaseModel):
    """Applied VRF synchronization actions."""

    vrfs: SyncActionSummary = Field(default_factory=SyncActionSummary)
    route_targets: SyncActionSummary = Field(default_factory=SyncActionSummary)
    routing_policies: SyncActionSummary = Field(default_factory=SyncActionSummary)
    interfaces: Dict[StrictStr, SyncActionSummary] = Field(default_factory=dict)


class SyncVrfsResult(Result):
    result: Union[SyncVrfsResultPayload, Dict[StrictStr, Any]] = Field(
        default_factory=SyncVrfsResultPayload,
        description=(
            "Applied VRF, route-target, routing-policy, and interface assignment "
            "actions, or an untyped dry-run diff"
        ),
    )


# --------------------------------------------------------------------------
# BGP ASN TASK MODELS
# --------------------------------------------------------------------------


class CreateBgpAsnInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    asn_range: Union[None, StrictStr] = Field(
        None,
        min_length=1,
        description="ASN range name to allocate the next available ASN from",
        alias="asn-range",
    )
    sites: Union[None, List[StrictStr]] = Field(
        None, description="Sites to assign the ASN to"
    )
    role: Union[None, StrictStr] = Field(None, description="IPAM role name")
    asn: Union[None, StrictInt] = Field(
        None, ge=1, le=4294967295, description="Explicit ASN; allocate when omitted"
    )
    rir: Union[None, StrictStr] = Field(
        None, description="RIR name required when creating an explicit ASN"
    )
    description: Union[None, StrictStr] = Field(None, description="ASN description")
    tenant: Union[None, StrictStr] = Field(None, description="Tenant name")
    tags: Union[None, List[StrictStr]] = Field(None, description="ASN tags")
    custom_fields: Union[None, Dict[StrictStr, Any]] = Field(
        None, description="ASN custom fields"
    )

    @model_validator(mode="before")
    @classmethod
    def reject_singular_site(cls, values: Any) -> Any:
        if isinstance(values, dict) and "site" in values:
            raise ValueError("site is not supported; use sites")
        return values

    @model_validator(mode="after")
    def validate_asn_source(self) -> "CreateBgpAsnInput":
        if self.asn is None and self.asn_range is None:
            raise ValueError("Either asn or asn-range must be provided")
        if self.asn is not None and self.asn_range is None and self.rir is None:
            raise ValueError("rir is required when creating an explicit ASN")
        return self


class CreateBgpAsnResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {}, description="Created, updated, existing, or proposed ASN"
    )


class SyncBgpAsnInput(
    NetboxNornirHostsFilters,
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the BGP ASN diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect BGP ASNs from",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for host resolution and BGP ASN parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview BGP ASN changes before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    rir: Union[None, StrictStr] = Field(
        None,
        description="NetBox RIR name required to create missing ASNs",
    )
    device_custom_field: StrictStr = Field(
        "devices",
        min_length=1,
        description="ASN custom field that stores associated NetBox devices",
        alias="device-custom-field",
    )
    ignore_asn_by_range: Union[None, List[StrictStr]] = Field(
        None,
        description="ASN values or numerical ranges to exclude from synchronization",
        alias="ignore-asn-by-range",
        examples=[["65000", "65100-65200"]],
    )
    preserve_description: StrictBool = Field(
        True,
        description="Keep existing NetBox ASN descriptions unchanged",
        alias="preserve-description",
    )


class SyncBgpAsnResult(Result):
    result: Union[SyncActionSummaryMap, Dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="BGP ASN synchronization actions keyed by global scope",
    )


# --------------------------------------------------------------------------
# BGP COMMUNITY TASK MODELS
# --------------------------------------------------------------------------


class SyncBgpCommunityInput(
    NetboxNornirHostsFilters,
    NetboxBulkBatchArgs,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the BGP community diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect BGP communities from",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for host resolution and community parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview BGP community changes before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    community_name_field: Union[StrictBool, StrictStr] = Field(
        "community_name",
        description="Optional custom field used to store live community-set names",
        alias="community-name-field",
    )
    device_custom_field: StrictStr = Field(
        "devices",
        min_length=1,
        description="Community custom field that stores associated NetBox devices",
        alias="device-custom-field",
    )


class SyncBgpCommunityResult(Result):
    result: Union[SyncActionSummaryMap, Dict[StrictStr, Any]] = Field(
        default_factory=SyncActionSummaryMap,
        description="BGP community synchronization actions keyed by NetBox model",
    )


# --------------------------------------------------------------------------
# PREFIX TASKS MODELS
# --------------------------------------------------------------------------


class PrefixStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    container = "container"
    deprecated = "deprecated"


class CreatePrefixInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    vlan: Union[None, StrictInt] = Field(
        None, ge=1, le=4094, description="VLAN VID; requires vlan_group"
    )
    vlan_group: Union[None, StrictStr] = Field(
        None, min_length=1, description="Existing VLAN group name; requires vlan"
    )
    custom_fields: Union[None, dict[StrictStr, Any]] = Field(
        None, description="Custom-field names and values for the prefix"
    )
    parent: Union[StrictStr, dict] = Field(
        ...,
        description="Parent prefix to allocate new prefix from",
    )
    description: Union[None, StrictStr] = Field(
        None, description="Description for new prefix"
    )
    prefixlen: StrictInt = Field(30, description="The prefix length of the new prefix")
    vrf: Union[None, StrictStr] = Field(
        None, description="Name of the VRF to associate with the prefix"
    )
    tags: Union[None, StrictStr, list[StrictStr]] = Field(
        None, description="List of tags to assign to the prefix"
    )
    tenant: Union[None, StrictStr] = Field(
        None, description="Name of the tenant to associate with the prefix"
    )
    comments: Union[None, StrictStr] = Field(
        None, description="Comments for the prefix"
    )
    role: Union[None, StrictStr] = Field(
        None, description="Role to assign to the prefix"
    )
    site: Union[None, StrictStr] = Field(
        None, description="Name of the site to associate with the prefix"
    )
    status: Union[None, PrefixStatusEnum] = Field(
        None, description="Status of the prefix"
    )

    @model_validator(mode="after")
    def validate_vlan_group(self) -> "CreatePrefixInput":
        if (self.vlan is None) != (self.vlan_group is None):
            raise ValueError("vlan and vlan_group must be supplied together")
        return self


class CreatePrefixResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Created or updated prefix data",
    )


# --------------------------------------------------------------------------
# TOPOLOGY TASKS MODELS
# --------------------------------------------------------------------------


class GetTopologyInput(
    NetboxNornirHostsFilters,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of device names to include in the topology; fetches all devices when omitted",
    )
    device_contains: Union[None, StrictStr] = Field(
        None,
        description="Case-insensitive substring to filter device names by",
        alias="device-contains",
    )
    device_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to filter device names by",
        alias="device-regex",
    )
    role: Union[None, List[StrictStr]] = Field(
        None,
        description="List of device role slugs to filter by",
    )
    platform: Union[None, List[StrictStr]] = Field(
        None,
        description="List of platform slugs to filter by",
    )
    manufacturers: Union[None, List[StrictStr]] = Field(
        None,
        description="List of manufacturer slugs to filter by",
    )
    status: Union[None, List[StrictStr]] = Field(
        None,
        description="List of device status values to filter by (e.g. 'active', 'planned')",
    )
    sites: Union[None, List[StrictStr]] = Field(
        None,
        description="List of site slugs to filter by",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir host resolution when Fx filters are used",
    )

    @model_validator(mode="after")
    def check_at_least_one_filter(self) -> "GetTopologyInput":
        has_device_filter = any(
            f is not None
            for f in (
                self.devices,
                self.device_contains,
                self.device_regex,
                self.role,
                self.platform,
                self.manufacturers,
                self.status,
                self.sites,
            )
        )
        has_fx_filter = any(
            f is not None
            for f in (
                self.FC,
                self.FL,
                self.FB,
                self.FG,
                self.FO,
                self.FP,
                self.FH,
                self.FR,
                self.FM,
                self.FX,
            )
        )
        if not has_device_filter and not has_fx_filter:
            raise ValueError(
                "at least one filter must be provided: 'devices', 'device_contains', "
                "'device_regex', 'role', 'platform', 'manufacturers', 'status', 'sites', "
                "or a Nornir Fx filter argument (FC, FL, FB, FG, FO, FP, FH, FR, FM, FX)"
            )
        return self


class GetTopologyResultPayload(BaseModel):
    nodes: List[Dict[str, Any]] = Field(
        None, description="List of topology nodes (devices)"
    )
    links: List[Dict[str, Any]] = Field(
        None, description="List of topology links (connections)"
    )


class GetTopologyResult(Result):
    result: Union[GetTopologyResultPayload, Dict, None] = Field(
        None,
        description="Topology data containing nodes (devices) and links (connections)",
    )
