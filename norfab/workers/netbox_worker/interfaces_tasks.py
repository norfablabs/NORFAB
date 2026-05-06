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
from .netbox_worker_utilities import resolve_vrf, resolve_ip

log = logging.getLogger(__name__)


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


def _build_interface_payload(
    job: object,
    desired: dict,
    ret: Result,
    worker_name: str,
    changed_fields: set,
    name_to_id: dict,
    device: Union[None, dict] = None,
    intf_name: str = None,
    nb: object = None,
    _lookup_cache: Union[None, dict] = None,
) -> dict:
    """Build a NetBox interface API payload from desired state and changed fields.

    ``_lookup_cache`` is an optional dict shared across multiple calls within the
    same task invocation to avoid redundant NetBox lookups for VLAN and VRF objects.
    Keyed by ``("vlan", vid, site_id)``, ``("vlan_global", vid)``, or ``("vrf", name)``.
    """  # noqa: D205
    if _lookup_cache is None:
        _lookup_cache = {}

    payload = {
        k: desired.get(k)
        for k in (
            "type",
            "enabled",
            "mtu",
            "speed",
            "duplex",
            "description",
            "mode",
        )
        if k in changed_fields
    }
    payload["name"] = intf_name

    if "parent" in changed_fields:
        parent_name = desired["parent"]
        payload["parent"] = name_to_id.get(parent_name) if parent_name else None

    if "lag" in changed_fields:
        lag_name = desired["lag"]
        payload["lag"] = name_to_id.get(lag_name) if lag_name else None

    if "untagged_vlan" in changed_fields:
        vid = desired["untagged_vlan"]
        site_key = ("vlan", vid, device["site_id"])
        global_key = ("vlan_global", vid)
        if site_key not in _lookup_cache:
            nb_vlan = list(nb.ipam.vlans.filter(vid=vid, site_id=device["site_id"]))
            _lookup_cache[site_key] = nb_vlan[0].id if nb_vlan else None
            if _lookup_cache[site_key] is None:
                nb_vlan = list(nb.ipam.vlans.filter(vid=vid))
                _lookup_cache[global_key] = nb_vlan[0].id if nb_vlan else None
        vlan_id = _lookup_cache[site_key] or _lookup_cache.get(global_key)
        if vlan_id:
            payload["untagged_vlan"] = vlan_id
        else:
            log.warning(
                f"{device['name']}:{intf_name} untagged vlan "
                f"'{vid}' does not exist in Netbox"
            )

    if "qinq_svlan" in changed_fields:
        vid = desired["qinq_svlan"]
        site_key = ("vlan", vid, device["site_id"])
        global_key = ("vlan_global", vid)
        if site_key not in _lookup_cache:
            nb_vlan = list(nb.ipam.vlans.filter(vid=vid, site_id=device["site_id"]))
            _lookup_cache[site_key] = nb_vlan[0].id if nb_vlan else None
            if _lookup_cache[site_key] is None:
                nb_vlan = list(nb.ipam.vlans.filter(vid=vid))
                _lookup_cache[global_key] = nb_vlan[0].id if nb_vlan else None
        vlan_id = _lookup_cache[site_key] or _lookup_cache.get(global_key)
        if vlan_id:
            payload["qinq_svlan"] = vlan_id
        else:
            log.warning(
                f"{device['name']}:{intf_name} qinq svlan "
                f"'{vid}' does not exist in Netbox"
            )

    if "tagged_vlans" in changed_fields:
        payload["tagged_vlans"] = []
        for vid in desired["tagged_vlans"]:
            site_key = ("vlan", vid, device["site_id"])
            global_key = ("vlan_global", vid)
            if site_key not in _lookup_cache:
                nb_vlan = list(nb.ipam.vlans.filter(vid=vid, site_id=device["site_id"]))
                _lookup_cache[site_key] = nb_vlan[0].id if nb_vlan else None
                if _lookup_cache[site_key] is None:
                    nb_vlan = list(nb.ipam.vlans.filter(vid=vid))
                    _lookup_cache[global_key] = nb_vlan[0].id if nb_vlan else None
            vlan_id = _lookup_cache[site_key] or _lookup_cache.get(global_key)
            if vlan_id:
                payload["tagged_vlans"].append(vlan_id)
            else:
                log.warning(
                    f"{device['name']}:{intf_name} tagged vlan "
                    f"'{vid}' does not exist in Netbox"
                )

    if "vrf" in changed_fields:
        vrf_name = desired["vrf"]
        cache_key = ("vrf", vrf_name)
        if cache_key not in _lookup_cache:
            _lookup_cache[cache_key] = resolve_vrf(vrf_name, nb, job, ret, worker_name)
        payload["vrf"] = _lookup_cache[cache_key]

    payload["device"] = device["id"]
    return payload


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
            interface_names = (
                [interface_name]
                if isinstance(interface_name, str)
                else (interface_name or [])
            )
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
                    job.event(
                        f"skipping '{intf_name}' on '{device_name}' - already exists"
                    )
                    continue
                if payloads_by_name:
                    intf_data = {"device": nb_device.id, **payloads_by_name[intf_name]}
                    intf_data.setdefault("type", interface_type)
                else:
                    intf_data = {
                        "device": nb_device.id,
                        "name": intf_name,
                        "type": interface_type,
                        **kwargs,
                    }
                interfaces_to_create.append(intf_data)
                result[device_name]["created"].append(intf_name)

            if interfaces_to_create:
                if dry_run:
                    job.event(
                        f"dry-run, would create {len(interfaces_to_create)} interface(s) on '{device_name}'"
                    )
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
        Synchronize device interface configuration from live devices into NetBox using a
        normalized state model and DeepDiff-based reconciliation.

        The task follows a four-step pipeline:

        1. **Fetch**: Pull current interface state from NetBox (source of truth).
        2. **Collect live state**: Run a Nornir ``parse_ttp`` get interfaces job against
           devices to collect live interface attributes (type, enabled, MTU, VLANs, VRF, etc.).
        3. **Diff**: Compare normalized NetBox state against normalized live state using
           DeepDiff to classify each interface as ``create``, ``update``, ``delete``, or
           ``in_sync``.
        4. **Reconcile**: Apply changes to NetBox in a safe order — LAG interfaces
           first, then parent interfaces, then child (sub)interfaces, then updates,
           and finally deletions (only when ``process_deletions=True``).

        **Side-Effects**

        - Sync interfaces task creates VRFs if they do not exist in Netbox

        **Prerequisites**

        - VLANs must exist in Netbox otherwise sync will fail to associate vlans with interfaces
        - Device must exist in Netbox

        **Limitations**

        - Sync interfaces task does not handles IP Addresses
        - Sync interfaces task does not handles MAC Addresses
        - Sync interfaces uses devices running configuration to pull interfaces data, interfaces
          operational state data not used

        **Dry-run mode** (``dry_run=True``): returns the raw diff plan without making
        any changes. Result is keyed by device name::

        ```
        {
            "<device>": {
                "create": ["Loopback99", ...],
                "update": {"Ethernet1": {"description": {"old_value": "x", "new_value": "y"}}},
                "delete": ["StrayIface"],
                "in_sync": ["Loopback0", ...]
            }
        }
        ```

        **Live-run mode** (``dry_run=False``, default): applies changes and returns a summary
        of what was done, keyed by device name::

        ```
        {
            "<device>": {
                "created": ["Loopback99"],
                "updated": ["Ethernet1"],
                "deleted": ["StrayIface"],
                "in_sync": ["Loopback0", ...]
            }
        }
        ```

        In non dry-run mode ``res["diff"]`` contains difference detail
        for interfaces that were (or would be) created/updated/deleted.

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): The NetBox instance name to use.
            dry_run (bool, optional): If True, no changes will be made to NetBox.
            timeout (int, optional): Timeout in seconds for the Nornir parse_ttp job.
            devices (list, optional): List of device names to sync.
            process_deletions (bool, optional): If True, delete interfaces present in
                NetBox but absent in live data. Defaults to False (safe by default).
            branch (str, optional): NetBox branch name to use. The branching plugin
                must be installed. The branch is created automatically if it does
                not exist.
            filter_by_name (str, optional): Glob pattern to restrict which interfaces
                are included by name, e.g. ``'Loopback*'`` or ``'Eth*'``.
            filter_by_description (str, optional): Glob pattern to restrict which
                interfaces are included by description, e.g. ``'uplink*'``.
            **kwargs: Additional Nornir host filter keyword arguments passed to
                ``parse_ttp`` (e.g. ``FL``, ``FC``, ``FB``).

        Returns:
            dict: Per-device action summary. Structure depends on ``dry_run``; see
                above. Diff details are available in ``res["diff"]`` for non
                dry-run mode.
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
            d.name: {"id": d.id, "site_id": d.site.id, "name": d.name}
            for d in nb.dcim.devices.filter(name=devices, fields="id,name,site")
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
            ip_addresses=False,
            cache="refresh",
        )
        if nb_interfaces_result.errors:
            ret.errors.extend(nb_interfaces_result.errors)
            ret.failed = True
            return ret

        # Normalize NetBox interface data per device.
        normalised_nb_all: dict = {}
        for device_name, interfaces in nb_interfaces_result.result.items():
            normalised_nb_all[device_name] = {}
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
                parent_name = (
                    data["parent"].get("name")
                    if isinstance(data.get("parent"), dict)
                    else None
                )
                lag = (
                    data["lag"].get("name")
                    if isinstance(data.get("lag"), dict)
                    else None
                )
                vrf_name = (
                    data["vrf"].get("name")
                    if isinstance(data.get("vrf"), dict)
                    else None
                )
                normalised_nb_all[device_name][intf_name] = {
                    "name": intf_name,
                    "type": (
                        data["type"]["value"]
                        if isinstance(data.get("type"), dict)
                        else data.get("type")
                    ),
                    "enabled": bool(data.get("enabled", True)),
                    "parent": parent_name,
                    "lag": lag,
                    "mtu": data.get("mtu"),
                    "speed": data.get("speed"),
                    "duplex": data.get("duplex"),
                    "description": str(data.get("description") or ""),
                    "mode": (data.get("mode") or {}).get("value"),
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
                }

        # Gather live source of truth from Nornir parse_ttp.
        job.event(f"retrieving live interfaces for {len(devices)} devices")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "interfaces", "FL": devices},
            workers="all",
            timeout=timeout,
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
                    if filter_by_name and not fnmatch.fnmatch(
                        intf_name, filter_by_name
                    ):
                        continue
                    if filter_by_description and not fnmatch.fnmatch(
                        str(data.get("description") or ""), filter_by_description
                    ):
                        continue
                    normalised_live_all[device_name][intf_name] = {
                        "name": intf_name,
                        "type": data["type"],
                        "enabled": bool(
                            data.get("enabled", data.get("is_enabled", True))
                        ),
                        "parent": data.get("parent"),
                        "lag": data.get("lag"),
                        "mtu": data.get("mtu"),
                        "speed": data.get("speed"),
                        "duplex": data.get("duplex"),
                        "description": str(data.get("description") or ""),
                        "mode": data.get("mode"),
                        "untagged_vlan": data.get("untagged_vlan"),
                        "tagged_vlans": data.get("tagged_vlans") or [],
                        "qinq_svlan": data.get("qinq_svlan"),
                        "vrf": data.get("vrf"),
                    }

        # Single diff on the full normalised datasets
        full_diff = self.make_diff(normalised_live_all, normalised_nb_all)

        if dry_run:
            ret.result = full_diff
            return ret
        else:
            ret.diff = full_diff

        # Shared lookup cache for VLAN and VRF objects — avoids redundant NetBox
        # API calls when the same VID or VRF name appears across multiple interfaces.
        _lookup_cache: dict = {}

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
        ret.result = device_results

        # create LAG interfaces
        bulk_create_lag_interfaces = []
        for device_name, actions in full_diff.items():
            nb_device = nb_devices_data[device_name]
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if desired["type"] == "lag":
                    payload = _build_interface_payload(
                        job=job,
                        ret=ret,
                        worker_name=self.name,
                        desired=desired,
                        changed_fields=[
                            k for k in desired.keys() if desired[k] is not None
                        ],
                        device=nb_device,
                        name_to_id={},
                        intf_name=intf_name,
                        nb=nb,
                        _lookup_cache=_lookup_cache,
                    )
                    bulk_create_lag_interfaces.append(payload)
        if bulk_create_lag_interfaces:
            job.event(f"creating LAG interfaces")
            try:
                nb.dcim.interfaces.create(bulk_create_lag_interfaces)
                job.event(f"created {len(bulk_create_lag_interfaces)} LAG interface(s)")
                for device_name, device_data in nb_devices_data.items():
                    for intf in bulk_create_lag_interfaces:
                        if intf["device"] == device_data["id"]:
                            device_results[device_name]["created"].append(intf["name"])
            except Exception as e:
                msg = f"failed to bulk create LAG interfaces: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                return ret

        # re-fetch interface IDs after creating LAG interfaces
        nb_intf_ids = {}
        for intf in nb.dcim.interfaces.filter(device=devices, fields="id,name,device"):
            nb_intf_ids.setdefault(intf.device.name, {})[intf.name] = intf.id

        # create parent interfaces associating with LAG if required
        bulk_create_parent_interfaces = []
        for device_name, actions in full_diff.items():
            name_to_id = nb_intf_ids[device_name]
            nb_device = nb_devices_data[device_name]
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if not desired["parent"] and desired["type"] != "lag":
                    payload = _build_interface_payload(
                        job=job,
                        ret=ret,
                        worker_name=self.name,
                        desired=desired,
                        changed_fields=[
                            k for k in desired.keys() if desired[k] is not None
                        ],
                        device=nb_device,
                        name_to_id=name_to_id,
                        intf_name=intf_name,
                        nb=nb,
                        _lookup_cache=_lookup_cache,
                    )
                    bulk_create_parent_interfaces.append(payload)
        if bulk_create_parent_interfaces:
            job.event(f"creating non-child/main interfaces")
            try:
                nb.dcim.interfaces.create(bulk_create_parent_interfaces)
                job.event(
                    f"created {len(bulk_create_parent_interfaces)} non-child/main interface(s)"
                )
                for device_name, device_data in nb_devices_data.items():
                    for intf in bulk_create_parent_interfaces:
                        if intf["device"] == device_data["id"]:
                            device_results[device_name]["created"].append(intf["name"])
            except Exception as e:
                msg = f"failed to bulk create non-child/main interfaces: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                return ret

        # re-fetch interface IDs after creating parent interfaces
        nb_intf_ids = {}
        for intf in nb.dcim.interfaces.filter(device=devices, fields="id,name,device"):
            nb_intf_ids.setdefault(intf.device.name, {})[intf.name] = intf.id

        # create child interfaces associating with parent interfaces
        bulk_create_child_interfaces = []
        for device_name, actions in full_diff.items():
            name_to_id = nb_intf_ids[device_name]
            nb_device = nb_devices_data[device_name]
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if desired["parent"]:
                    payload = _build_interface_payload(
                        job=job,
                        ret=ret,
                        worker_name=self.name,
                        desired=desired,
                        changed_fields=[
                            k for k in desired.keys() if desired[k] is not None
                        ],
                        device=nb_device,
                        name_to_id=name_to_id,
                        intf_name=intf_name,
                        nb=nb,
                        _lookup_cache=_lookup_cache,
                    )
                    bulk_create_child_interfaces.append(payload)
        if bulk_create_child_interfaces:
            job.event(f"creating child interfaces")
            try:
                nb.dcim.interfaces.create(bulk_create_child_interfaces)
                job.event(
                    f"created {len(bulk_create_child_interfaces)} child interface(s)"
                )
                for device_name, device_data in nb_devices_data.items():
                    for intf in bulk_create_child_interfaces:
                        if intf["device"] == device_data["id"]:
                            device_results[device_name]["created"].append(intf["name"])
            except Exception as e:
                msg = f"failed to bulk create child interfaces: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                return ret

        # Build bulk_update_interfaces list from full_diff
        bulk_update_interfaces = {}
        for device_name, actions in full_diff.items():
            nb_device = nb_devices_data[device_name]
            name_to_id = nb_intf_ids[device_name]
            for intf_name, field_changes in actions["update"].items():
                desired = normalised_live_all[device_name][intf_name]
                intf_id = nb_intf_ids[device_name][intf_name]
                payload = _build_interface_payload(
                    job=job,
                    ret=ret,
                    worker_name=self.name,
                    desired=desired,
                    changed_fields=set(field_changes.keys()),
                    device=nb_device,
                    name_to_id=name_to_id,
                    intf_name=intf_name,
                    nb=nb,
                    _lookup_cache=_lookup_cache,
                )
                payload["id"] = intf_id
                bulk_update_interfaces[(device_name, intf_name)] = payload
        if bulk_update_interfaces:
            try:
                nb.dcim.interfaces.update(list(bulk_update_interfaces.values()))
                job.event(f"updated {len(bulk_update_interfaces)} interface(s)")
                for k in bulk_update_interfaces.keys():
                    device_name, intf_name = k
                    device_results[device_name]["updated"].append(intf_name)
            except Exception as e:
                msg = f"failed to bulk update interfaces: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                return ret

        # Build bulk_delete_interfaces payload from full_diff
        bulk_delete_interfaces = {}  # keyed by intf id, values intf names
        if process_deletions:
            job.event(f"processing interface deletions")
            for device_name, actions in full_diff.items():
                # delete children before parents to avoid constraint errors
                ordered_deletes = sorted(
                    actions["delete"], key=lambda x: (x.count("."), x), reverse=True
                )
                for intf_name in ordered_deletes:
                    intf_id = nb_intf_ids[device_name][intf_name]
                    bulk_delete_interfaces[intf_id] = {
                        "device": device_name,
                        "interface": intf_name,
                    }
        if bulk_delete_interfaces:
            try:
                nb.dcim.interfaces.delete(list(bulk_delete_interfaces.keys()))
                job.event(f"deleted {len(bulk_delete_interfaces)} interface(s)")
                for intf_data in bulk_delete_interfaces.values():
                    device_name = intf_data["device"]
                    intf_name = intf_data["interface"]
                    device_results[device_name]["deleted"].append(intf_name)
            except Exception as exc:
                msg = f"failed to bulk delete interfaces: {exc}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncMacAddressesInput,
    )
    def sync_mac_addresses(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        timeout: int = 60,
        devices: Union[None, list] = None,
        branch: str = None,
        filter_by_name: Union[None, str] = None,
        filter_by_description: Union[None, str] = None,
        filter_by_mac: Union[None, str] = None,
        **kwargs: Any,
    ) -> Result:
        """
        Synchronize MAC addresses from live devices into NetBox.

        The task follows a three-step pipeline:

        1. **Collect live state**: Run a Nornir ``parse_ttp`` get interfaces job against
           devices to collect live MAC addresses per interface.
        2. **Fetch NetBox state**: Retrieve existing MAC address objects from NetBox.
        3. **Reconcile**: Create new MAC address objects or update existing unassigned
           ones to point at the correct interface.

        **Dry-run mode** (``dry_run=True``): returns the reconciliation plan without
        making any changes. Result is keyed by device name::

        ```
        {
            "<device>": {
                "created": ["aa:bb:cc:dd:ee:01", ...],
                "updated": ["aa:bb:cc:dd:ee:02", ...],
                "in_sync": ["aa:bb:cc:dd:ee:03", ...]
            }
        }
        ```

        **Live-run mode** (``dry_run=False``, default): applies changes and returns
        the same structure showing what was done.

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): The NetBox instance name to use.
            dry_run (bool, optional): If True, no changes will be made to NetBox.
            timeout (int, optional): Timeout in seconds for the Nornir parse_ttp job.
            devices (list, optional): List of device names to sync.
            branch (str, optional): NetBox branch name to use.
            filter_by_name (str, optional): Glob pattern to restrict which interfaces
                are included by name, e.g. ``'Loopback*'`` or ``'Eth*'``.
            filter_by_description (str, optional): Glob pattern to restrict which
                interfaces are included by description, e.g. ``'uplink*'``.
            filter_by_mac (str, optional): Glob pattern to restrict which MAC addresses
                are included, e.g. ``'aa:bb:*'``.
            **kwargs: Additional Nornir host filter keyword arguments passed to
                ``parse_ttp`` (e.g. ``FL``, ``FC``, ``FB``).

        Returns:
            Result: Per-device action summary with ``created``, ``updated``, and
                ``in_sync`` MAC address lists.
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_mac_addresses",
            result={},
            resources=[instance],
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch)
        log.info(
            f"{self.name} - Sync MAC addresses: Processing {len(devices)} device(s) in '{instance}'"
        )

        # source additional hosts from Nornir filters
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        job.event(f"syncing MAC addresses for {len(devices)} devices")

        # filter out devices not defined in NetBox
        nb_devices_data = {
            d.name: {"id": d.id, "name": d.name}
            for d in nb.dcim.devices.filter(name=devices, fields="id,name")
        }
        for d in list(devices):
            if d not in nb_devices_data:
                msg = f"{d} - device not found in Netbox"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                devices.remove(d)
        if not devices:
            ret.failed = True
            return ret

        # gather live interface data from Nornir parse_ttp
        job.event(f"retrieving live interfaces for {len(devices)} devices")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "interfaces", "FL": devices},
            workers="all",
            timeout=timeout,
        )

        # collect all discovered MAC addresses applying interface and MAC filters
        all_mac_live: dict = {}  # {mac: {"device": ..., "interface": ...}}
        for wname, wdata in parse_data.items():
            if wdata.get("failed"):
                log.warning(f"{wname} - failed to parse devices")
                continue
            for device_name, host_interfaces in wdata["result"].items():
                for data in host_interfaces:
                    intf_name = data["name"]
                    intf_description = data["description"]
                    mac = data["mac_address"]
                    if not mac:
                        continue
                    if filter_by_name and not fnmatch.fnmatch(
                        intf_name, filter_by_name
                    ):
                        continue
                    if (
                        filter_by_description
                        and intf_description
                        and not fnmatch.fnmatch(intf_description, filter_by_description)
                    ):
                        continue
                    if filter_by_mac and not fnmatch.fnmatch(mac, filter_by_mac):
                        continue
                    all_mac_live[mac] = {
                        "device": device_name,
                        "interface": intf_name,
                    }

        if not all_mac_live:
            log.info(
                f"{self.name} - Sync MAC addresses: no MAC addresses found in live data"
            )
            return ret

        # fetch interfaces data from NetBox to resolve interface IDs
        nb_interfaces_result = self.get_interfaces(
            job=job,
            instance=instance,
            branch=branch,
            devices=devices,
            ip_addresses=False,
            cache="refresh",
        )
        if nb_interfaces_result.errors:
            ret.errors.extend(nb_interfaces_result.errors)
            ret.failed = True
            return ret

        # fetch existing MAC address objects from NetBox
        # NetBox allows duplicate MAC entries; prefer assigned entries over
        # unassigned ones so that a conflicting assignment is not silently
        # overwritten by a later unassigned copy during dict construction.
        nb_macs: dict = {}
        for _m in nb.dcim.mac_addresses.filter(
            mac_address=list(all_mac_live.keys()),
            fields="id,mac_address,assigned_object",
        ):
            _mac = _m.mac_address.lower()
            _entry = {
                "id": _m.id,
                "device": (
                    _m.assigned_object.device.name if _m.assigned_object else None
                ),
                "interface": _m.assigned_object.name if _m.assigned_object else None,
            }
            # keep the entry if we haven't seen this MAC yet, or if the new
            # entry is assigned (has an interface) and the stored one is not
            if _mac not in nb_macs or (
                _entry["interface"] is not None and nb_macs[_mac]["interface"] is None
            ):
                nb_macs[_mac] = _entry

        # per-device result tracking
        device_results = {
            device_name: {
                "created": [],
                "updated": [],
                "in_sync": [],
            }
            for device_name in devices
        }
        ret.result = device_results

        bulk_update_mac = []
        bulk_create_mac = []

        # process and compare live MACs versus NetBox MACs
        for mac, mac_data in all_mac_live.items():
            device_name = mac_data["device"]
            intf_name = mac_data["interface"]
            nb_raw = nb_interfaces_result.result.get(device_name, {})
            if intf_name not in nb_raw:
                msg = f"{device_name}:{intf_name} - interface not found in NetBox, skipping MAC {mac}"
                log.warning(msg)
                continue
            # MAC already assigned to a different interface
            if (
                nb_macs.get(mac, {}).get("interface")
                and nb_macs[mac]["interface"] != intf_name
            ):
                exist_intf = nb_macs[mac]["interface"]
                exist_device = nb_macs[mac]["device"]
                msg = (
                    f"{device_name}:{intf_name} - {mac} already assigned to "
                    f"a different interface {exist_device}:{exist_intf}"
                )
                log.error(msg)
                ret.errors.append(msg)
                job.event(msg, severity="ERROR")
                continue
            # MAC already assigned to correct interface
            elif mac in nb_macs and nb_macs[mac]["interface"] == intf_name:
                device_results[device_name]["in_sync"].append(mac)
            # update existing MAC if it is not associated with any interface
            elif mac in nb_macs and nb_macs[mac]["interface"] is None:
                if dry_run:
                    device_results[device_name]["updated"].append(mac)
                else:
                    bulk_update_mac.append(
                        {
                            "id": nb_macs[mac]["id"],
                            "mac_address": mac,
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id": nb_raw[intf_name]["id"],
                        }
                    )
            # create new MAC address entry
            else:
                if dry_run:
                    device_results[device_name]["created"].append(mac)
                else:
                    bulk_create_mac.append(
                        {
                            "mac_address": mac,
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id": nb_raw[intf_name]["id"],
                        }
                    )

        if dry_run:
            return ret

        if bulk_create_mac:
            try:
                nb.dcim.mac_addresses.create(bulk_create_mac)
                job.event(f"created {len(bulk_create_mac)} MAC addresses")
                for m in bulk_create_mac:
                    device_name = all_mac_live[m["mac_address"]]["device"]
                    device_results[device_name]["created"].append(m["mac_address"])
            except Exception as e:
                msg = f"failed to bulk create MAC addresses: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
        if bulk_update_mac:
            try:
                nb.dcim.mac_addresses.update(bulk_update_mac)
                job.event(f"updated {len(bulk_update_mac)} MAC addresses")
                for m in bulk_update_mac:
                    device_name = all_mac_live[m["mac_address"]]["device"]
                    device_results[device_name]["updated"].append(m["mac_address"])
            except Exception as e:
                msg = f"failed to bulk update MAC addresses: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")

        return ret
