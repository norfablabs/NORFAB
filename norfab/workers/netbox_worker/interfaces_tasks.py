import fnmatch
import ipaddress
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from norfab.core.worker import Job, Task
from norfab.models import Result
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import NetboxCommonArgs, NetboxFastApiArgs

log = logging.getLogger(__name__)


class InterfaceTypeEnum(str, Enum):
    virtual = "virtual"
    other = "other"
    bridge = "bridge"
    lag = "lag"


class CreateDeviceInterfacesInput(
    NetboxCommonArgs, 
    use_enum_values=True,
    populate_by_name=True # ignore aliases
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
    interface_type: InterfaceTypeEnum = Field(
        "other",
        description="Type of interface to create",
        alias="interface-type",
    )
    description: Union[None, StrictStr] = Field(
        None, description="Interface description"
    )
    speed: StrictInt = Field(None, description="Interface speed in Kbit/s")
    mtu: StrictInt = Field(None, description="Maximum transmission unit size in bytes")


class BulkUpdateInterfaceItem(NetboxCommonArgs, use_enum_values=True):
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
    parent: Union[None, StrictStr] = Field(None, description="Parent interface name")
    lag: Union[None, StrictStr] = Field(None, description="LAG interface name")
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
    vrf: Union[None, StrictStr] = Field(None, description="VRF name")


class UpdateInterfacesInput(
    NetboxCommonArgs, 
    use_enum_values=True, 
    populate_by_name=True # ignore aliases
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
    parent: Union[None, StrictStr] = Field(
        None,
        description="Parent interface name",
    )
    lag: Union[None, StrictStr] = Field(
        None,
        description="LAG interface name",
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
    vrf: Union[None, StrictStr] = Field(
        None,
        description="VRF name",
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
                raise ValueError(
                    "Either 'bulk_update' or 'devices' is required."
                )
            if not self.name:
                raise ValueError("Single-interface mode requires 'name'.")
        return self


class UpdateInterfacesDescriptionInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
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


class GetInterfacesInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True # ignore aliases
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
        False,
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


class SyncDeviceInterfacesInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True # ignore aliases
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


def _normalize_mac(mac: Union[None, str]) -> Union[None, str]:
    if not mac:
        return None
    mac_text = str(mac).strip().lower()
    if mac_text in {"", "none", "null"}:
        return None
    return mac_text


def _normalize_cidr(address: Union[None, str]) -> Union[None, str]:
    if not address:
        return None
    try:
        return str(ipaddress.ip_interface(str(address)).with_prefixlen)
    except Exception:
        return str(address).strip()

def _normalize_mode(value: Any) -> Union[None, str]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("value")
    text = str(value).strip().lower()
    return text or None

def _build_interface_payload(
    desired: dict,
    changed_fields: set,
    name_to_id: dict,
    device_id: Union[None, int] = None,
) -> dict:
    payload = {}

    field_mapping = {
        "type": "type",
        "enabled": "enabled",
        "mtu": "mtu",
        "mac_address": "mac_address",
        "speed": "speed",
        "duplex": "duplex",
        "description": "description",
        "mode": "mode",
        "untagged_vlan": "untagged_vlan",
        "tagged_vlans": "tagged_vlans",
        "qinq_svlan": "qinq_svlan",
    }
    for source_key, target_key in field_mapping.items():
        if source_key in changed_fields:
            payload[target_key] = desired.get(source_key)

    if "parent" in changed_fields:
        parent_name = desired.get("parent")
        payload["parent"] = name_to_id.get(parent_name) if parent_name else None

    if "lag" in changed_fields:
        lag_name = desired.get("lag")
        payload["lag"] = name_to_id.get(lag_name) if lag_name else None

    if device_id is not None:
        payload.setdefault("device", device_id)
    return payload


def _normalize_nb_interfaces_per_device(
    nb_raw_by_device: dict,
    filter_by_name: Union[None, str] = None,
    filter_by_description: Union[None, str] = None,
) -> dict:
    """Normalize raw NetBox interface data into a comparable dict.

    Returns a dict keyed by device name -> interface name -> normalised fields.
    Includes MAC address list, IPv4/IPv6 addresses, and all core interface fields.
    Used by :func:`sync_device_interfaces` and the bulk path of :func:`update_interfaces`.
    """
    normalised: dict = {}
    for device_name, interfaces in nb_raw_by_device.items():
        normalised[device_name] = {}
        for intf_name, data in (interfaces or {}).items():
            if filter_by_name and not fnmatch.fnmatch(intf_name, filter_by_name):
                continue
            if filter_by_description and not fnmatch.fnmatch(
                str(data.get("description") or ""), filter_by_description
            ):
                continue
            tagged_vlans = sorted(
                v.get("vid")
                for v in (data.get("tagged_vlans") or [])
                if isinstance(v, dict) and v.get("vid") is not None
            )
            macs = sorted(
                mac
                for mac in (
                    _normalize_mac((m or {}).get("mac_address"))
                    for m in (data.get("mac_addresses") or [])
                )
                if mac
            )
            ipv4_addresses = []
            ipv6_addresses = []
            for ip in data.get("ip_addresses") or []:
                cidr = ip["address"]
                if ip["family"]["value"] == 4:
                    ipv4_addresses.append(cidr)
                else:
                    ipv6_addresses.append(cidr)
            parent_name = (
                data["parent"].get("name") if isinstance(data.get("parent"), dict) else None
            )
            lag_id = (
                data["lag"].get("id") if isinstance(data.get("lag"), dict) else None
            )
            vrf_name = (
                data["vrf"].get("name") if isinstance(data.get("vrf"), dict) else None
            )
            normalised[device_name][intf_name] = {
                "name": intf_name,
                "type": (
                    data["type"]["value"]
                    if isinstance(data.get("type"), dict)
                    else data.get("type")
                ),
                "enabled": bool(data.get("enabled", True)),
                "parent": parent_name,
                "lag": lag_id,
                "mtu": data.get("mtu"),
                "mac_address": macs,
                "speed": data.get("speed"),
                "duplex": data.get("duplex"),
                "description": str(data.get("description") or ""),
                "mode": _normalize_mode(data.get("mode")),
                "untagged_vlan": (
                    (data.get("untagged_vlan") or {}).get("vid")
                    if isinstance(data.get("untagged_vlan"), dict)
                    else data.get("untagged_vlan")
                ),
                "tagged_vlans": tagged_vlans,
                "qinq_svlan": (
                    (data.get("qinq_svlan") or {}).get("vid")
                    if isinstance(data.get("qinq_svlan"), dict)
                    else data.get("qinq_svlan")
                ),
                "vrf": vrf_name,
                "ipv4_addresses": ipv4_addresses,
                "ipv6_addresses": ipv6_addresses,
            }
    return normalised


class NetboxInterfacesTasks:

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=GetInterfacesInput,
    )
    def get_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        interface_list: Union[None, list] = None,
        interface_regex: Union[None, str] = None,
        ip_addresses: bool = False,
        inventory_items: bool = False,
        dry_run: bool = False,
        cache: Union[None, bool, str] = None,
        branch: Union[None, str] = None,
    ) -> Result:
        """
        Retrieve device interfaces from Netbox using Pynetbox REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve interfaces for.
            interface_list (list, optional): List of interface names to retrieve.
            interface_regex (str, optional): Regex pattern to match interfaces by name.
            ip_addresses (bool, optional): If True, retrieves interface IPs. Defaults to False.
            inventory_items (bool, optional): If True, retrieves interface inventory items. Defaults to False.
            dry_run (bool, optional): If True, only return REST filter params, do not run. Defaults to False.
            cache: ``True`` - use cache if up to date; ``False`` - skip cache;
                ``"refresh"`` - fetch and overwrite cache; ``"force"`` - use cache without staleness check

        Returns:
            dict: Dictionary keyed by device name with interface details.

        This task performs no filtering of data returned by `pynetbox.dcim.interfaces.filter`,
        as a result use netbox REST API explorer to understand resulting data structure, REST
        API browser available at `http://<netbox url>/api/dcim/interfaces/`. In addition
        use nfcli to explore interfaces data:

        ```
        nf#netbox get interfaces devices fceos4 interface-list eth201 | kv

        netbox-worker-1.1.fceos4.eth201.display: eth201
        netbox-worker-1.1.fceos4.eth201.device.name: fceos4
        ...
        ```

        Can also pipe results through `json`, `yaml`, `nested` or `pprint`  formatters to output
        results in  certain format.
        """
        instance = instance or self.default_instance
        nb = self._get_pynetbox(instance, branch=branch)
        devices = devices or []
        cache = self.cache_use if cache is None else cache
        log.info(
            f"{self.name} - Get interfaces: Fetching interfaces for {len(devices)} device(s) from '{instance}'"
        )
        ret = Result(
            task=f"{self.name}:get_interfaces_pynetbox",
            result={d: {} for d in devices},
            resources=[instance],
        )
        filter_params = {}
        all_interfaces = []
        children_by_parent_id = {}  # parent_id -> [child intf, ...]
        member_intf_by_lag_id = {}  # lag_id    -> [member intf, ...]
        ip_by_intf_id = {}
        inv_by_intf_id = {}
        last_updated_by_device = {}

        # build REST filter params
        if devices:
            filter_params["device"] = devices
        if interface_list:
            filter_params["name"] = interface_list
        if interface_regex:
            filter_params["name__regex"] = interface_regex

        if dry_run:
            ret.result = {"filter_params": filter_params}
            return ret

        job.event(f"retrieving interfaces for {len(devices)} device(s)")

        devices_to_fetch = list(devices)

        if cache == True or cache == "force":
            job.event(f"checking cache for {len(devices)} device(s)")
            # quick REST call to get current last_updated for all matching interfaces
            result = nb.dcim.interfaces.filter(
                **filter_params, fields="name,last_updated,device"
            )
            # build per-device last_updated map
            for intf in result:
                last_updated_by_device.setdefault(intf.device.name, {})[
                    intf.name
                ] = intf.last_updated

            self.cache.expire()  # remove expired items from cache
            devices_to_fetch = []
            for device_name, intf_last_updated in last_updated_by_device.items():
                device_cache_key = f"get_interfaces::{device_name}"
                if device_cache_key in self.cache and (
                    cache == "force"
                    or all(
                        self.cache[device_cache_key]
                        .get(intf_name, {})
                        .get("last_updated")
                        == lu
                        for intf_name, lu in intf_last_updated.items()
                    )
                ):
                    # serve requested interfaces from cache
                    for intf_name in intf_last_updated.keys():
                        ret.result[device_name][intf_name] = self.cache[
                            device_cache_key
                        ][intf_name]
                    job.event(
                        f"serving '{device_name}' interfaces from cache ({len(intf_last_updated)} interface(s))"
                    )
                else:
                    devices_to_fetch.append(device_name)
                    job.event(
                        f"'{device_name}' cache miss or stale, fetching fresh data"
                    )
        elif cache == False or cache == "refresh":
            pass  # fetch all devices fresh

        # build fetch filter params restricted to devices needing fresh data
        if devices and cache in (True, "force"):
            fetch_filter_params = {**filter_params, "device": devices_to_fetch}
        else:
            fetch_filter_params = filter_params

        # fetch all matching interfaces in one call
        if devices_to_fetch:
            job.event(
                f"fetching interfaces from NetBox for {len(devices_to_fetch)} device(s)"
            )
            all_interfaces = list(nb.dcim.interfaces.filter(**fetch_filter_params))
            job.event(f"retrieved {len(all_interfaces)} interface(s) from NetBox")

        if not all_interfaces and not any(ret.result.get(d) for d in devices):
            raise Exception(
                f"{self.name} - no interfaces data returned by '{instance}' "
                f"for devices {', '.join(devices)}"
            )

        # build relationship lookup maps from fetched data
        for intf in all_interfaces:
            if intf.parent:
                children_by_parent_id.setdefault(intf.parent.id, []).append(intf)
            if intf.lag:
                member_intf_by_lag_id.setdefault(intf.lag.id, []).append(intf)

        # fetch IP addresses if requested (one bulk call keyed by assigned_object_id)
        if ip_addresses and devices_to_fetch:
            job.event(f"fetching IP addresses for {len(devices_to_fetch)} device(s)")
            for ip in nb.ipam.ip_addresses.filter(device=devices_to_fetch):
                if (
                    ip.assigned_object_id
                    and ip.assigned_object_type == "dcim.interface"
                ):
                    ip_by_intf_id.setdefault(ip.assigned_object_id, []).append(dict(ip))

        # fetch inventory items if requested (one bulk call keyed by component_id)
        if inventory_items and devices_to_fetch:
            job.event(f"fetching inventory items for {len(devices_to_fetch)} device(s)")
            for item in nb.dcim.inventory_items.filter(device=devices_to_fetch):
                if item.component_id and item.component_type == "dcim.interface":
                    inv_by_intf_id.setdefault(item.component_id, []).append(dict(item))

        # transform pynetbox records into result dict keyed by device / interface name
        for intf in all_interfaces:
            device_name = intf.device.name
            if device_name not in ret.result:  # Netbox issue #16299
                continue

            intf_data = dict(intf)
            # add extra fields
            intf_data["child_interfaces"] = [
                {
                    "name": c.name,
                    "vrf": c.vrf.name if c.vrf else None,
                    "ip_addresses": ip_by_intf_id.get(c.id, []),
                }
                for c in children_by_parent_id.get(intf.id, [])
            ]
            intf_data["member_interfaces"] = [
                m.name for m in member_intf_by_lag_id.get(intf.id, [])
            ]
            intf_data["ip_addresses"] = ip_by_intf_id.get(intf.id, [])
            intf_data["inventory_items"] = inv_by_intf_id.get(intf.id, [])
            ret.result[device_name][intf.name] = intf_data

        # cache freshly fetched interfaces per device
        if cache != False:
            job.event(f"caching interfaces data for {len(devices_to_fetch)} device(s)")
            for device_name in devices_to_fetch:
                if device_name in ret.result:
                    cache_key = f"get_interfaces::{device_name}"
                    self.cache.set(
                        cache_key,
                        ret.result[device_name],
                        expire=self.cache_ttl,
                    )

        return ret

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateDeviceInterfacesInput,
    )
    def create_device_interfaces(
        self,
        job: Job,
        devices: list,
        interface_name: Union[None, list, str] = None,
        interfaces_data: Union[None, list] = None,
        interface_type: str = "other",
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: str = None,
        **kwargs: dict,
    ) -> Result:
        """
        Create interfaces for one or more devices in NetBox. This task creates interfaces in bulk and only
        if interfaces does not exist in Netbox.

        Args:
            job (Job): The job object containing execution context and metadata.
            devices (list): List of device names or device objects to create interfaces for.
            interface_name (Union[list, str]): Name(s) of the interface(s) to create. Can be a single
                interface name as a string or multiple names as a list. Alphanumeric ranges are
                supported for bulk creation:

                - Ethernet[1-3] -> Ethernet1, Ethernet2, Ethernet3
                - [ge,xe]-0/0/[0-9] -> ge-0/0/0, ..., xe-0/0/0 etc.

            interface_type (str, optional): Type of interface (e.g., "other", "virtual", "lag",
                "1000base-t"). Defaults to "other".
            instance (Union[None, str], optional): NetBox instance identifier to use. If None,
                uses the default instance. Defaults to None.
            dry_run (bool, optional): If True, simulates the operation without making actual changes.
                Defaults to False.
            branch (str, optional): NetBox branch to use for the operation. Defaults to None.
            kwargs (dict, optional): Any additional interface attributes
            interfaces_data (list, optional): List of per-interface payload dictionaries.
                Each dictionary supports all NetBox interface create fields and must
                include ``name``. This is used for true bulk create with heterogeneous
                interface attributes.

        Returns:
            Result: Result object containing the task name, execution results, and affected resources.
                The result dictionary contains status and details of interface creation operations.
        """
        instance = instance or self.default_instance
        result = {}
        kwargs = kwargs or {}
        ret = Result(
            task=f"{self.name}:create_device_interfaces",
            result=result,
            resources=[instance],
        )
        nb = self._get_pynetbox(instance, branch=branch)
        log.info(
            f"{self.name} - Create device interfaces: Creating interfaces for {len(devices)} device(s) in '{instance}'"
        )

        payloads_by_name = {}
        if interfaces_data:
            for item in interfaces_data:
                payloads_by_name[str(item["name"])] = dict(item)
            all_interface_names = sorted(payloads_by_name.keys())
            job.event(
                f"received {len(all_interface_names)} interface create payload(s)"
            )
        else:
            # Normalize interface_name to a list and expand patterns
            interface_names = [interface_name] if isinstance(interface_name, str) else (interface_name or [])
            all_interface_names = []
            for name_pattern in interface_names:
                all_interface_names.extend(expand_alphanumeric_range(name_pattern))
            job.event(
                f"expanded interface names to {len(all_interface_names)} interface(s)"
            )

        # Process each device
        for device_name in devices:
            result[device_name] = {
                "created": [],
                "skipped": [],
            }

            nb_device = nb.dcim.devices.get(name=device_name)
            if not nb_device:
                msg = f"device '{device_name}' not found in NetBox"
                ret.errors.append(msg)
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")
                continue

            existing_interface_names = {
                intf.name for intf in nb.dcim.interfaces.filter(device=device_name)
            }
            interfaces_to_create = []

            for intf_name in all_interface_names:
                if intf_name in existing_interface_names:
                    result[device_name]["skipped"].append(intf_name)
                    job.event(f"skipping '{intf_name}' on '{device_name}' - already exists")
                    continue
                if payloads_by_name:
                    intf_data = {"device": nb_device.id, **payloads_by_name[intf_name]}
                    intf_data.setdefault("type", interface_type)
                else:
                    intf_data = {"device": nb_device.id, "name": intf_name, "type": interface_type, **kwargs}
                interfaces_to_create.append(intf_data)
                result[device_name]["created"].append(intf_name)

            if interfaces_to_create:
                if dry_run:
                    job.event(f"dry-run, would create {len(interfaces_to_create)} interface(s) on '{device_name}'")
                else:
                    try:
                        nb.dcim.interfaces.create(interfaces_to_create)
                        msg = f"created {len(interfaces_to_create)} interface(s) on '{device_name}'"
                        job.event(msg)
                        log.info(f"{self.name} - {msg}")
                    except Exception as e:
                        msg = f"failed to create interfaces on '{device_name}': {e}"
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")
                        job.event(msg, severity="ERROR")

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=UpdateInterfacesInput,
    )
    def update_interfaces(
        self,
        job: Job,
        devices: Union[None, list] = None,
        # single-interface mode
        name: Union[None, str] = None,
        type: Union[None, str] = None,
        enabled: Union[None, bool] = None,
        parent: Union[None, str] = None,
        lag: Union[None, str] = None,
        mtu: Union[None, int] = None,
        mac_address: Union[None, str] = None,
        speed: Union[None, int] = None,
        duplex: Union[None, str] = None,
        description: Union[None, str] = None,
        mode: Union[None, str] = None,
        untagged_vlan: Union[None, int] = None,
        tagged_vlans: Union[None, list] = None,
        vrf: Union[None, str] = None,
        # bulk mode
        bulk_update: Union[None, list] = None,
        # shared
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: Union[None, str] = None,
    ) -> Result:
        """Update NetBox interfaces for one or more devices.

        Supports selective field updates with idempotency: interfaces with no
        effective changes are reported in ``in_sync`` and no write is performed.

        Each item in ``bulk_update`` must include ``device`` and ``name`` to
        identify the interface, plus any subset of the supported update fields.
        Optional ``id`` can be provided as a NetBox interface ID hint.

        Interface IDs are resolved automatically from NetBox when not supplied.
        ``vrf`` is accepted as a VRF name and resolved to its NetBox object ID.
        ``parent`` and ``lag`` are accepted as interface names and resolved to
        their NetBox interface IDs.

        Args:
            job: NorFab Job object containing execution metadata.
            devices: List of device names whose interfaces to update.
            bulk_update: List of interface update dicts for bulk mode; each must include ``device`` and ``name``.
            instance: NetBox instance name. Defaults to worker default instance.
            dry_run: If True, return diff without writing.
            branch: Optional NetBox branch name.

        Returns:
            Normal run or dry-run — result keyed by device name::

                {
                    "<device>": {
                        "updated": ["intf1", ...],
                        "in_sync": ["intf2", ...],
                    }
                }
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:update_interfaces",
            result={},
            resources=[instance],
        )
        nb = self._get_pynetbox(instance, branch=branch)

        if bulk_update:
            intf_updates = bulk_update
        else:
            _single_fields = (
                "type",
                "enabled",
                "parent",
                "lag",
                "mtu",
                "mac_address",
                "speed",
                "duplex",
                "description",
                "mode",
                "untagged_vlan",
                "tagged_vlans",
                "vrf",
                "name",
            )
            single_update = {
                k: v
                for k, v in locals().items()
                if k in _single_fields and v is not None
            }
            intf_updates = [{"device": d, **single_update} for d in devices]

        log.info(
            f"{self.name} - Update interfaces: Processing {len(intf_updates)} update(s)"
        )

        # resolve interface IDs and construct update payloads
        update_payloads = {}
        for intf in intf_updates:
            name = intf.pop("name")
            device = intf.pop("device")
            ret.result.setdefault(device, {"update": [], "in_sync": []})
            if not intf.get("id"):
                nb_intf = nb.dcim.interfaces.get(name=name, device=device)
                if not nb_intf:
                    msg = f"{device}:{name} - no such interface in '{instance}' Netbox"
                    log.error(msg)
                    ret.errors.append(msg)
                    continue
                intf["id"] = nb_intf.id                    
            update_payloads[(device, name)] = intf

        # push the updates
        if update_payloads:
            try:
                if dry_run:
                    for k in update_payloads.keys():
                        dev_name, intf_name = k
                        ret.result[dev_name]["update"].append(intf_name)
                else:
                    nb.dcim.interfaces.update(list(update_payloads.values()))
                    for k in update_payloads.keys():
                        dev_name, intf_name = k
                        ret.result[dev_name]["updated"].append(intf_name)
                job.event(f"updated {len(update_payloads)} interface(s)")
                log.info(
                    f"{self.name} - Updated {len(update_payloads)} interface(s) in '{instance}' Netbox"
                )
            except Exception as exc:
                msg = f"failed to bulk update interfaces: {exc}"
                ret.errors.append(msg)
                log.error(f"{self.name} - {msg}")
                job.event(msg, severity="ERROR")
                ret.failed = True

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=UpdateInterfacesDescriptionInput,
    )
    def update_interfaces_description(
        self,
        job: Job,
        devices: list,
        description_template: str = None,
        descriptions: dict = None,
        interfaces: Union[None, list] = None,
        interface_regex: Union[None, str] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        timeout: int = 60,
        branch: str = None,
    ) -> Result:
        """
        Updates the description of interfaces for specified devices in NetBox.

        This method retrieves interface connections for the given devices, renders
        new descriptions using a Jinja2 template, and updates the interface descriptions
        in NetBox accordingly.

        Only interfaces, console ports and console server ports supported.

        Jinja2 environment receives these context variables for description template rendering:

        - device - pynetbox `dcim.device` object
        - interface - pynetbox object - `dcim/interface`, `dcip.consoleport`,
            `dcim.consoleserverport` - depending on what kind of interface is that.
        - remote_device - string
        - remote_interface - string
        - termination_type - string
        - cable - dictionary of directly attached cable attributes:
            - type
            - status
            - tenant - dictionary of `{name: tenant_name}`
            - label
            - tags - list of `{name: tag_name}` dictionaries
            - custom_fields - dictionary with custom fields data
            - peer_termination_type
            - peer_device
            - peer_interface

        Args:
            job (Job): The job context for logging and event handling.
            devices (list): List of device names to update interfaces for.
            description_template (str): Jinja2 template string for the interface description.
                Can reference remote template using `nf://path/to/template.txt`.
            descriptions (dict): Dictionary keyed by interface names with values being interface
                description strings
            interfaces (Union[None, list], optional): Specific interfaces to update.
            interface_regex (Union[None, str], optional): Regex pattern to filter interfaces.
            instance (Union[None, str], optional): NetBox instance identifier.
            dry_run (bool, optional): If True, performs a dry run without saving changes.
            timeout (int, optional): Timeout for NetBox API requests.
            branch (str, optional): Branch name for NetBox instance.

        Returns:
            Result: An object containing the outcome of the update operation, including
                before and after descriptions.
        """
        result = {}
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:update_interfaces_description",
            result=result,
            resources=[instance],
        )
        nb = self._get_pynetbox(instance, branch=branch)
        log.info(
            f"{self.name} - Update interfaces description: Updating descriptions for {len(devices)} device(s) in '{instance}'"
        )

        job.event(f"updating interface descriptions for {len(devices)} device(s)")

        if description_template:
            # get list of all interfaces connections
            nb_connections = self.get_connections(
                job=job,
                devices=devices,
                interface_regex=interface_regex,
                instance=instance,
            )
            # produce interfaces description and update it
            while nb_connections.result:
                device, device_connections = nb_connections.result.popitem()
                ret.result.setdefault(device, {})
                job.event(
                    f"processing {len(device_connections)} interface(s) for '{device}'"
                )
                for interface, connection in device_connections.items():
                    job.event(f"{device}:{interface} updating description")
                    if connection["termination_type"] == "consoleport":
                        api_endpoint = nb.dcim.console_ports
                    elif connection["termination_type"] == "consoleserverport":
                        api_endpoint = nb.dcim.console_server_ports
                    elif connection["termination_type"] == "powerport":
                        api_endpoint = nb.dcim.power_ports
                    elif connection["termination_type"] == "poweroutlet":
                        api_endpoint = nb.dcim.power_outlets
                    else:
                        api_endpoint = nb.dcim.interfaces
                    nb_interface = api_endpoint.get(device=device, name=interface)
                    nb_device = nb.dcim.devices.get(name=device)
                    rendered_description = self.jinja2_render_templates(
                        templates=[description_template],
                        context={
                            "device": nb_device,
                            "interface": nb_interface,
                            **connection,
                        },
                    )
                    rendered_description = str(rendered_description).strip()
                    ret.result[device][interface] = {
                        "-": str(nb_interface.description),
                        "+": rendered_description,
                    }
                    nb_interface.description = rendered_description
                    if dry_run is False:
                        nb_interface.save()
        if descriptions:
            job.event(
                f"applying {len(descriptions)} description(s) to {len(devices)} device(s)"
            )
            for device in devices:
                ret.result.setdefault(device, {})
                for interface, description in descriptions.items():
                    nb_interface = nb.dcim.interfaces.get(name=interface, device=device)
                    if nb_interface:
                        ret.result[device][interface] = {
                            "-": str(nb_interface.description),
                            "+": description,
                        }
                        nb_interface.description = description
                        if dry_run is False:
                            nb_interface.save()
        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncDeviceInterfacesInput,
    )
    def sync_device_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        timeout: int = 60,
        devices: Union[None, list] = None,
        process_deletions: bool = False,
        branch: str = None,
        filter_by_name: Union[None, str] = None,
        filter_by_description: Union[None, str] = None,
        **kwargs: Any,
    ) -> Result:
        """
        Synchronize device interfaces with NetBox using normalized state,
        DeepDiff-based reconciliation, and deterministic action planning.

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): The Netbox instance name to use.
            dry_run (bool, optional): If True, no changes will be made to Netbox.
            timeout (int, optional): The timeout for the Nornir parse_ttp job.
            devices (list, optional): List of devices to update.
            process_deletions (bool, optional): If True, delete interfaces missing in live state.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            filter_by_name (str, optional): Glob pattern to filter interfaces by name before syncing,
                e.g. ``'eth*'``. Only matching interfaces are included in the sync.
            filter_by_description (str, optional): Glob pattern to filter interfaces by description
                before syncing, e.g. ``'uplink*'``. Only matching interfaces are included.
            **kwargs: Additional Nornir host filter keyword arguments (e.g. FL, FC, FB).

        Returns:
            dict: Per-device action summary with interfaces, mac_addresses, and ip_addresses
                create/update/delete actions and in_sync interfaces.
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_device_interfaces",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        nb = self._get_pynetbox(instance, branch=branch)
        log.info(
            f"{self.name} - Sync device interfaces: Processing {len(devices)} device(s) in '{instance}'"
        )

        # Source additional hosts from Nornir filters.
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        job.event(f"syncing {len(devices)} devices")

        # filter out devices not define in Netbox
        nb_devices_data = {
            d.name: {"id": d.id} 
            for d in nb.dcim.devices.filter(name=devices, fields="id,name")
        }
        for d in list(devices):
            if d not in nb_devices_data:
                msg = f"{d} - device not found in Netbox"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                devices.remove(d)

        # Gather NetBox source of truth with interface IP/MAC details.
        nb_interfaces_result = self.get_interfaces(
            job=job,
            instance=instance,
            branch=branch,
            devices=devices,
            ip_addresses=True,
            cache="refresh"
        )
        if nb_interfaces_result.errors:
            ret.errors.extend(nb_interfaces_result.errors)
            ret.failed = True
            return ret

        # Gather live source of truth from Nornir parse_ttp.
        job.event(f"retrieving live interfaces for {len(devices)} devices")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "interfaces", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        
        # Normalize NetBox interface data per device.
        normalised_nb_all = _normalize_nb_interfaces_per_device(
            nb_interfaces_result.result,
            filter_by_name=filter_by_name,
            filter_by_description=filter_by_description,
        )

        # Normalize live interface data per device.
        normalised_live_all = {}
        for wname, wdata in parse_data.items():
            if wdata.get("failed"):
                log.warning(f"{wname} - failed to parse devices")
                continue
            for device_name, host_interfaces in wdata["result"].items():
                normalised_live_all.setdefault(device_name, {})
                for data in host_interfaces or []:
                    intf_name = data["name"]
                    if filter_by_name and not fnmatch.fnmatch(intf_name, filter_by_name):
                        continue
                    if filter_by_description and not fnmatch.fnmatch(
                        str(data.get("description") or ""), filter_by_description
                    ):
                        continue
                    raw_macs = data.get("mac_address")
                    if isinstance(raw_macs, list):
                        macs = [_normalize_mac(i) for i in raw_macs]
                    else:
                        mac = _normalize_mac(raw_macs)
                        macs = [mac] if mac else []
                    normalised_live_all[device_name][intf_name] = {
                        "name": intf_name,
                        "type": data["type"],
                        "enabled": bool(data.get("enabled", data.get("is_enabled", True))),
                        "parent": data.get("parent"),
                        "lag": data.get("lag"),
                        "mtu": data.get("mtu"),
                        "mac_address": macs,
                        "speed": data.get("speed"),
                        "duplex": data.get("duplex"),
                        "description": str(data.get("description") or ""),
                        "mode": _normalize_mode(data.get("mode")),
                        "untagged_vlan": data.get("untagged_vlan"),
                        "tagged_vlans": data.get("tagged_vlans") or [],
                        "qinq_svlan": data.get("qinq_svlan"),
                        "vrf": data.get("vrf"),
                        "ipv4_addresses": data.get("ipv4_addresses") or [],
                        "ipv6_addresses": data.get("ipv6_addresses") or [],
                    }

        # Single diff on the full normalised datasets
        full_diff = self.make_diff(normalised_live_all, normalised_nb_all)

        if dry_run:
            ret.result = full_diff
            return ret

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

        # Build bulk_create_interfaces list from full_diff
        bulk_create_interfaces = []
        for device_name, actions in full_diff.items():
            # make sure to create parent interfaces first
            ordered_creates = sorted(actions["create"], key=lambda x: (x.count("."), x))
            for intf_name in ordered_creates:
                desired = normalised_live_all[device_name][intf_name]
                payload = {
                    "name": intf_name,
                    "type": desired.get("type") or "other",
                    "description": desired.get("description") or "",
                    "enabled": desired.get("enabled", True),
                }
                if desired.get("mtu") is not None:
                    payload["mtu"] = desired["mtu"]
                if desired.get("speed") is not None:
                    payload["speed"] = desired["speed"]
                bulk_create_interfaces.append(payload)

        # Build bulk_update_interfaces list from full_diff
        bulk_update_interfaces = []
        for device_name, actions in full_diff.items():
            nb_raw = nb_interfaces_result.result[device_name]
            nb_device = nb_devices_data[device_name]
            name_to_id = {name: (nb_raw.get(name) or {}).get("id") for name in nb_raw}
            for intf_name, field_changes in actions["update"].items():
                desired = normalised_live_all[device_name][intf_name]
                intf_id = nb_raw[intf_name]["id"]
                payload = _build_interface_payload(
                    desired=desired,
                    changed_fields=set(field_changes.keys()),
                    device_id=nb_device["id"],
                    name_to_id=name_to_id,
                )
                payload["id"] = intf_id
                payload["device"] = device_name
                payload["name"] = intf_name
                bulk_update_interfaces.append(payload)

        # Build bulk_delete_interfaces payload from full_diff
        bulk_delete_interfaces = {} # keyed by intf id, values intf names
        if process_deletions:
            for device_name, actions in full_diff.items():
                nb_raw = nb_interfaces_result.result.get(device_name) or {}
                # delete children before parents to avoid constraint errors
                ordered_deletes = sorted(
                    actions["delete"], key=lambda x: (x.count("."), x), reverse=True
                )
                for intf_name in ordered_deletes:
                    intf_id = nb_raw[intf_name]["id"]
                    bulk_delete_interfaces[intf_id] = intf_name

        # Delegate bulk creation to create_device_interfaces
        if bulk_create_interfaces:
            create_result = self.create_device_interfaces(
                job=job,
                devices=[device_name],
                interfaces_data=bulk_create_interfaces,
                instance=instance,
                dry_run=False,
                branch=branch,
            )
            ret.errors.extend(create_result.errors)
            created_names = create_result.result[device_name]["created"]
            for device_name, actions in full_diff.items():
                for intf_name in actions["create"]:
                    if intf_name in created_names:
                        device_results[device_name]["created"].append(intf_name)

        if bulk_update_interfaces:
            update_result = self.update_interfaces(
                job=job,
                bulk_update=bulk_update_interfaces,
                instance=instance,
                dry_run=False,
                branch=branch,
            )
            ret.errors.extend(update_result.errors)
            updated_names = update_result.result[device_name]["update"]
            for device_name, actions in full_diff.items():
                for intf_name in actions["update"]:
                    if intf_name in updated_names:
                        device_results[device_name]["updated"].append(intf_name)

        if bulk_delete_interfaces:
            try:
                nb.dcim.interfaces.delete(list(bulk_delete_interfaces.keys()))
                job.event(f"deleted {len(bulk_delete_interfaces)} interface(s)")
            except Exception as exc:
                msg = f"failed to bulk delete interfaces: {exc}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
            else:
                device_results[device_name]["deleted"] = list(bulk_delete_interfaces.values())

        ret.result = device_results

        return ret

        #     normalised_live = normalised_live_all.get(device_name, {})
        #     normalised_nb = normalised_nb_all.get(device_name, {})
        #     actions = full_diff.get(
        #         device_name,
        #         {"create": [], "update": {}, "delete": [], "in_sync": []},
        #     )
# 
        #     plan = {
        #         "interfaces": {
        #             "create": actions["create"] if create else [],
        #             "update": sorted(list(actions["update"].keys())),
        #             "delete": actions["delete"] if delete else [],
        #         },
        #         "mac_addresses": {"create": [], "update": [], "delete": []},
        #         "ip_addresses": {"create": [], "update": [], "delete": []},
        #         "in_sync": actions["in_sync"],
        #     }
# 
        #     update_payloads = []
        #     name_to_id = {
        #         name: (nb_raw.get(name) or {}).get("id") for name in nb_raw
        #     }
# 
        #     for intf_name, field_changes in actions["update"].items():
        #         desired = normalised_live.get(intf_name)
        #         intf_id = (nb_raw.get(intf_name) or {}).get("id")
        #         if not desired or intf_id is None:
        #             continue
        #         changed_fields = set(field_changes.keys())
        #         payload = _build_interface_payload(
        #             desired=desired,
        #             changed_fields=changed_fields,
        #             device_id=nb_device["id"],
        #             name_to_id=name_to_id,
        #         )
        #         payload["id"] = intf_id
        #         update_payloads.append(payload)
# 
        #     # MAC and IP reconciliation plan.
        #     all_plan_names = sorted(
        #         set(actions["in_sync"])
        #         | set(actions["update"].keys())
        #         | (set(actions["create"]) if create else set())
        #         | (set(actions["delete"]) if delete else set())
        #     )
        #     mac_actions_create = []
        #     mac_actions_update = []
        #     mac_actions_delete = []
        #     ip_actions_create = []
        #     ip_actions_delete = []
# 
        #     for intf_name in all_plan_names:
        #         live_intf = normalised_live.get(intf_name)
        #         nb_intf = normalised_nb.get(intf_name)
# 
        #         live_macs = (live_intf or {}).get("mac_address", [])
        #         nb_mac_entries = (nb_raw.get(intf_name) or {}).get("mac_addresses") or []
        #         nb_macs = sorted(
        #             {
        #                 _normalize_mac((m or {}).get("mac_address"))
        #                 for m in nb_mac_entries
        #                 if _normalize_mac((m or {}).get("mac_address"))
        #             }
        #         )
# 
        #         if live_intf and (
        #             intf_name in actions["update"]
        #             or intf_name in actions["in_sync"]
        #             or intf_name in actions["create"]
        #         ):
        #             if live_macs and not nb_macs:
        #                 plan["mac_addresses"]["create"].append(intf_name)
        #                 mac_actions_create.append(
        #                     {"interface": intf_name, "mac_address": live_macs[0]}
        #                 )
        #             elif live_macs and nb_macs and live_macs[0] != nb_macs[0]:
        #                 first_nb_mac = (nb_mac_entries or [{}])[0]
        #                 if first_nb_mac.get("id"):
        #                     plan["mac_addresses"]["update"].append(intf_name)
        #                     mac_actions_update.append(
        #                         {
        #                             "id": int(first_nb_mac["id"]),
        #                             "mac_address": live_macs[0],
        #                             "interface": intf_name,
        #                         }
        #                     )
        #             if delete and not live_macs and nb_macs:
        #                 plan["mac_addresses"]["delete"].append(intf_name)
        #                 for mac_entry in nb_mac_entries:
        #                     if mac_entry.get("id"):
        #                         mac_actions_delete.append(
        #                             {
        #                                 "id": int(mac_entry["id"]),
        #                                 "interface": intf_name,
        #                             }
        #                         )
# 
        #         live_ips = sorted(
        #             set((live_intf or {}).get("ipv4_addresses", []))
        #             | set((live_intf or {}).get("ipv6_addresses", []))
        #         )
        #         nb_ip_entries = (nb_raw.get(intf_name) or {}).get("ip_addresses") or []
        #         nb_ips = sorted(
        #             {
        #                 _normalize_cidr((ip_entry or {}).get("address"))
        #                 for ip_entry in nb_ip_entries
        #                 if _normalize_cidr((ip_entry or {}).get("address"))
        #             }
        #         )
# 
        #         if live_intf and (
        #             intf_name in actions["update"]
        #             or intf_name in actions["in_sync"]
        #             or intf_name in actions["create"]
        #         ):
        #             for ip_cidr in sorted(set(live_ips) - set(nb_ips)):
        #                 plan["ip_addresses"]["create"].append(f"{intf_name}:{ip_cidr}")
        #                 ip_actions_create.append(
        #                     {"interface": intf_name, "address": ip_cidr}
        #                 )
# 
        #         if delete:
        #             for ip_entry in nb_ip_entries:
        #                 ip_cidr = _normalize_cidr((ip_entry or {}).get("address"))
        #                 if not ip_cidr:
        #                     continue
        #                 if ip_cidr not in live_ips:
        #                     plan["ip_addresses"]["delete"].append(
        #                         f"{intf_name}:{ip_cidr}"
        #                     )
        #                     if ip_entry.get("id"):
        #                         ip_actions_delete.append(
        #                             {
        #                                 "id": int(ip_entry["id"]),
        #                                 "interface": intf_name,
        #                                 "address": ip_cidr,
        #                             }
        #                         )
# 
        #     # Dry-run returns planned actions and diffs only.
        #     if dry_run:
        #         ret.result[device_name] = plan
        #         if branch is not None:
        #             ret.result[device_name]["branch"] = branch
        #         continue
# 
        #     # 1) interface create
        #     if create and plan["interfaces"]["create"]:
        #         ordered_creates = sorted(
        #             plan["interfaces"]["create"], key=lambda x: (x.count("."), x)
        #         )
        #         create_payloads = []
        #         for intf_name in ordered_creates:
        #             desired = normalised_live[intf_name]
        #             payload = {
        #                 "name": intf_name,
        #                 "type": desired.get("type") or "other",
        #                 "description": desired.get("description") or "",
        #                 "enabled": desired.get("enabled", True),
        #             }
        #             if desired.get("mtu") is not None:
        #                 payload["mtu"] = desired["mtu"]
        #             if desired.get("speed") is not None:
        #                 payload["speed"] = desired["speed"]
        #             create_payloads.append(payload)
# 
        #         try:
        #             create_ret = self.create_device_interfaces(
        #                 job=job,
        #                 devices=[device_name],
        #                 interfaces_data=create_payloads,
        #                 instance=instance,
        #                 dry_run=False,
        #                 branch=branch,
        #             )
        #             if create_ret.errors:
        #                 ret.errors.extend(create_ret.errors)
        #         except Exception as exc:
        #             msg = f"failed to bulk create interfaces on '{device_name}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #         # Refresh only created interfaces to resolve NetBox IDs for MAC/IP steps.
        #         try:
        #             refreshed = self.get_interfaces(
        #                 job=job,
        #                 instance=instance,
        #                 devices=[device_name],
        #                 interface_list=plan["interfaces"]["create"],
        #                 ip_addresses=True,
        #                 cache="refresh",
        #                 branch=branch,
        #             ).result.get(device_name, {})
        #             for created_name, created_data in refreshed.items():
        #                 nb_raw[created_name] = created_data
        #                 name_to_id[created_name] = created_data.get("id")
        #         except Exception as exc:
        #             msg = f"failed to refresh created interfaces on '{device_name}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #     # 2) interface update
        #     if update_payloads:
        #         try:
        #             update_ret = self.update_interfaces(
        #                 job=job,
        #                 interfaces=update_payloads,
        #                 instance=instance,
        #                 dry_run=False,
        #                 branch=branch,
        #             )
        #             if update_ret.errors:
        #                 ret.errors.extend(update_ret.errors)
        #         except Exception as exc:
        #             msg = f"failed to update interfaces on '{device_name}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #     # 3) MAC create/update/delete
        #     mac_create_payloads = []
        #     for action in mac_actions_create:
        #         intf_id = name_to_id.get(action["interface"])
        #         if intf_id:
        #             mac_create_payloads.append(
        #                 {
        #                     "mac_address": action["mac_address"],
        #                     "assigned_object_type": "dcim.interface",
        #                     "assigned_object_id": intf_id,
        #                 }
        #             )
        #     if mac_create_payloads:
        #         try:
        #             nb.dcim.mac_addresses.create(mac_create_payloads)
        #         except Exception as exc:
        #             msg = f"failed to create MAC addresses on '{device_name}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #     if mac_actions_update:
        #         try:
        #             nb.dcim.mac_addresses.update(
        #                 [{"id": a["id"], "mac_address": a["mac_address"]} for a in mac_actions_update]
        #             )
        #         except Exception as exc:
        #             msg = f"failed to update MAC addresses on '{device_name}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #     if delete and mac_actions_delete:
        #         for action in mac_actions_delete:
        #             try:
        #                 mac_obj = nb.dcim.mac_addresses.get(id=action["id"])
        #                 if mac_obj:
        #                     mac_obj.delete()
        #             except Exception as exc:
        #                 msg = f"failed to delete MAC id '{action['id']}' on '{device_name}': {exc}"
        #                 ret.errors.append(msg)
        #                 log.error(msg)
        #                 job.event(msg, severity="ERROR")
# 
        #     # 4) IP create/delete
        #     for action in ip_actions_create:
        #         intf_id = name_to_id.get(action["interface"])
        #         if not intf_id:
        #             continue
        #         try:
        #             existing = list(nb.ipam.ip_addresses.filter(address=action["address"]))
        #             if existing:
        #                 ip_obj = existing[0]
        #                 ip_obj.assigned_object_type = "dcim.interface"
        #                 ip_obj.assigned_object_id = intf_id
        #                 ip_obj.status = "active"
        #                 ip_obj.save()
        #             else:
        #                 nb.ipam.ip_addresses.create(
        #                     {
        #                         "address": action["address"],
        #                         "assigned_object_type": "dcim.interface",
        #                         "assigned_object_id": intf_id,
        #                         "status": "active",
        #                     }
        #                 )
        #         except Exception as exc:
        #             msg = f"failed to create IP '{action['address']}' on '{device_name}:{action['interface']}': {exc}"
        #             ret.errors.append(msg)
        #             log.error(msg)
        #             job.event(msg, severity="ERROR")
# 
        #     if delete and ip_actions_delete:
        #         for action in ip_actions_delete:
        #             try:
        #                 ip_obj = nb.ipam.ip_addresses.get(id=action["id"])
        #                 if ip_obj:
        #                     ip_obj.delete()
        #             except Exception as exc:
        #                 msg = f"failed to delete IP id '{action['id']}' on '{device_name}:{action['interface']}': {exc}"
        #                 ret.errors.append(msg)
        #                 log.error(msg)
        #                 job.event(msg, severity="ERROR")
# 
        #     # 5) interface delete
        #     if delete and plan["interfaces"]["delete"]:
        #         ordered_deletes = sorted(
        #             plan["interfaces"]["delete"], key=lambda x: (x.count("."), x), reverse=True
        #         )
        #         for intf_name in ordered_deletes:
        #             intf_id = name_to_id.get(intf_name)
        #             if not intf_id:
        #                 continue
        #             try:
        #                 intf_obj = nb.dcim.interfaces.get(id=intf_id)
        #                 if intf_obj:
        #                     intf_obj.delete()
        #                     job.event(f"deleted interface '{intf_name}' on '{device_name}'")
        #             except Exception as exc:
        #                 msg = f"failed to delete interface '{intf_name}' on '{device_name}': {exc}"
        #                 ret.errors.append(msg)
        #                 log.error(msg)
        #                 job.event(msg, severity="ERROR")
# 
        #     ret.result[device_name] = plan
        #     if branch is not None:
        #         ret.result[device_name]["branch"] = branch

        return ret
