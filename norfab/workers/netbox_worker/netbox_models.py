import builtins
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Union

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from norfab.models import NorFabClientRunJob, Result

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
    ssl_verify: StrictBool = Field(True, description="Verify SSL vertsor not")


class NetboxConfigModel(BaseModel):
    cache_use: Union[CacheUseEnum, StrictBool] = Field(
        True, description="Use cache or not"
    )
    cache_ttl: StrictInt = Field(True, description="Cache TTL")
    instances: Dict[StrictStr, NetboxInstanceConfig] = Field(
        None, description="Netbox instance config keyed by instance name"
    )


# --------------------------------------------------------------------------
# CORE NETBOX WORKER MODELS
# --------------------------------------------------------------------------


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
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
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


class CreateBgpPeeringInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
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
            if not values.get("local_address") and not values.get("local_interface"):
                raise ValueError(
                    "Single-session mode requires either 'local_address' or 'local_interface'."
                )
        return values


class UpdateBgpPeeringInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
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
    result: dict[StrictStr, Any] = Field(
        {},
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
    interface_regex: Union[None, StrictStr] = Field(
        None,
        description="Regex pattern to match interfaces and ports",
        alias="interface-regex",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to target",
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


class CreateDesignInput(BaseModel, use_enum_values=True, populate_by_name=True):
    design_data: Union[StrictStr, dict[StrictStr, Any]] = Field(
        ...,
        description="NetBox design data as YAML string, URL, or dictionary",
        alias="design-data",
    )
    context: Union[StrictStr, dict[StrictStr, Any]] = Field(
        {},
        description="Template context as YAML string, URL, or dictionary",
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


class CreateDesignResult(Result):
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
    check_interfaces: StrictBool = Field(
        True,
        description="Check interface sync state",
        json_schema_extra={"presence": True},
        alias="check-interfaces",
    )
    check_mac_addresses: StrictBool = Field(
        True,
        description="Check MAC address sync state",
        json_schema_extra={"presence": True},
        alias="check-mac-addresses",
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


class SyncAllInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp jobs",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return diff without writing to NetBox",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    process_deletions: StrictBool = Field(
        False,
        description="Process deletions for inventory, interfaces, and BGP peerings",
        json_schema_extra={"presence": True},
        alias="process-deletions",
    )
    message: Union[None, StrictStr] = Field(
        None,
        description="Changelog message for inventory and BGP operations",
    )
    inventory_create_module_types: StrictBool = Field(
        False,
        description="Create missing module types during inventory sync",
        json_schema_extra={"presence": True},
        alias="inventory-create-module-types",
    )
    inventory_create_module_bays: StrictBool = Field(
        False,
        description="Create missing module bays during inventory sync",
        json_schema_extra={"presence": True},
        alias="inventory-create-module-bays",
    )
    inventory_map: Union[None, StrictStr, InventoryPatternMap] = Field(
        None,
        description="Inventory pattern mappings or nf:// YAML file reference",
        alias="inventory-map",
    )
    inventory_transform: Union[None, StrictStr] = Field(
        None,
        description="nf:// Python inventory transformer file",
        alias="inventory-transform",
    )
    inventory_filter_by_module: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns selecting normalized module type names",
        alias="inventory-filter-by-module",
    )
    inventory_filter_by_slot: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns selecting normalized module bay names",
        alias="inventory-filter-by-slot",
    )
    inventory_ignore_modules: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns excluding normalized module type names",
        alias="inventory-ignore-modules",
    )
    inventory_ignore_slots: Union[None, List[StrictStr]] = Field(
        None,
        description="Glob patterns excluding normalized module bay names",
        alias="inventory-ignore-slots",
    )
    interfaces_filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by name",
        alias="interfaces-filter-by-name",
    )
    interfaces_filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter interfaces by description",
        alias="interfaces-filter-by-description",
    )
    interfaces_update_type: Union[None, StrictBool] = Field(
        False,
        description="Update existing NetBox interface types",
        json_schema_extra={"presence": True},
        alias="interfaces-update-type",
    )
    interfaces_vlan_group: Union[None, StrictStr, StrictInt] = Field(
        None,
        description="VLAN group name, slug, or ID for interface VLAN resolution",
        alias="interfaces-vlan-group",
    )
    mac_filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter MAC sync interfaces by name",
        alias="mac-filter-by-name",
    )
    mac_filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter MAC sync interfaces by description",
        alias="mac-filter-by-description",
    )
    mac_filter_by_mac: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter MAC addresses",
        alias="mac-filter-by-mac",
    )
    ip_anycast_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="IP prefix(es) to classify as anycast",
        alias="ip-anycast-ranges",
    )
    ip_ignore_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="IP prefix(es) to exclude from IP sync",
        alias="ip-ignore-ranges",
    )
    ip_create_prefixes: StrictBool = Field(
        True,
        description="Create missing prefixes during IP sync",
        json_schema_extra={"presence": True},
        alias="ip-create-prefixes",
    )
    ip_filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter IP sync interfaces by name",
        alias="ip-filter-by-name",
    )
    ip_filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter IP sync interfaces by description",
        alias="ip-filter-by-description",
    )
    ip_filter_by_prefix: Union[None, StrictStr] = Field(
        None,
        description="IP prefix to restrict synced IP addresses",
        alias="ip-filter-by-prefix",
    )
    ip_filter_by_ip: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict synced IP addresses",
        alias="ip-filter-by-ip",
    )
    bgp_status: BgpSessionStatusEnum = Field(
        "active",
        description="Status to set on created/updated BGP sessions",
        alias="bgp-status",
    )
    bgp_rir: Union[None, StrictStr] = Field(
        None,
        description="RIR name to use when creating new ASNs",
        alias="bgp-rir",
    )
    bgp_name_template: StrictStr = Field(
        "{{device}}_{{name}}",
        description="Jinja2 template string for BGP session names",
        alias="bgp-name-template",
    )
    bgp_filter_by_remote_as: Union[None, List[int]] = Field(
        None,
        description="Only sync BGP sessions matching remote AS numbers",
        alias="bgp-filter-by-remote-as",
    )
    bgp_filter_by_peer_group: Union[None, List[StrictStr]] = Field(
        None,
        description="Only sync BGP sessions matching peer groups",
        alias="bgp-filter-by-peer-group",
    )
    bgp_filter_by_description: Union[None, StrictStr] = Field(
        None,
        description="Only sync BGP sessions matching description glob",
        alias="bgp-filter-by-description",
    )
    bgp_ignore_peer_ranges: Union[None, List[StrictStr]] = Field(
        None,
        description="Prefix(es) to ignore BGP peers",
        alias="bgp-ignore-peer-ranges",
    )
    bgp_vrf_custom_field: Union[StrictBool, StrictStr] = Field(
        "vrf",
        description="BGP session custom field name used to store VRF reference",
        alias="bgp-vrf-custom-field",
    )


class GetDevicesResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Device data keyed by device name",
    )


class SyncDeviceInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
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
        description="Type of interface to create",
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


class SyncDeviceInterfacesInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True  # ignore aliases
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    process_deletions: StrictBool = Field(
        False,
        description="Delete interfaces present in NetBox but absent in live data",
        json_schema_extra={"presence": True},
        alias="process-deletions",
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
    update_type: Union[None, StrictBool] = Field(
        None,
        description="Update interface types or not",
        alias="update-type",
        json_schema_extra={"presence": True},
    )
    vlan_group: Union[None, StrictStr, StrictInt] = Field(
        None,
        description="VLAN group name, slug, or ID to use when resolving or creating interface VLANs",
        alias="vlan-group",
    )


class SyncMacAddressesInput(
    NetboxCommonArgs, use_enum_values=True, populate_by_name=True
):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync MAC addresses for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
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
    result: dict[StrictStr, Any] = Field(
        {},
        description="Interface sync result keyed by device name",
    )


class SyncMacAddressesResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="MAC address sync result keyed by device name",
    )


# --------------------------------------------------------------------------
# IP TASKS MODELS
# --------------------------------------------------------------------------


class SyncDeviceIpInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox devices to sync IP addresses for",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    anycast_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="IP prefix(es) to classify as anycast role, e.g. '10.3.250.0/24'",
        alias="anycast-ranges",
    )
    ignore_ranges: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Prefix(es) to exclude IP addresses",
        alias="ignore-ranges",
    )
    create_prefixes: StrictBool = Field(
        True,
        description="Create missing IP prefixes in NetBox for each discovered IP address",
        json_schema_extra={"presence": True},
        alias="create-prefixes",
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


class CreateIpInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
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
    create_peer_ip: Union[None, StrictBool] = Field(
        True,
        description="If True, creates an IP address for the link peer interface",
        alias="create-peer-ip",
    )

    @model_validator(mode="after")
    def validate_mask_len_with_peer_ip(self) -> "CreateIpInput":
        if self.mask_len in (32, 128) and self.create_peer_ip is True:
            raise ValueError(
                f"mask_len={self.mask_len} with create_peer_ip=True is invalid: "
                "cannot create a peer IP for a host prefix (/32 or /128)"
            )
        return self


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
    result: dict[StrictStr, Any] = Field(
        {},
        description="IP address sync result keyed by device name",
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
    partial: StrictBool = Field(
        True, description="True=PATCH (partial); False=PUT (full replace)"
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
# PREFIX TASKS MODELS
# --------------------------------------------------------------------------


class PrefixStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    container = "container"
    deprecated = "deprecated"


class CreatePrefixInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
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
