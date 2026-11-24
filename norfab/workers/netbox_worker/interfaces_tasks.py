import fnmatch
import logging
from typing import Any, Union

import yaml
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_exceptions import UnsupportedNetboxVersion
from .netbox_models import (
    CreateDeviceInterfacesInput,
    CreateDeviceInterfacesResult,
    GetInterfacesInput,
    GetInterfacesResult,
    InterfaceMapRule,
    NetboxFastApiArgs,
    SyncActionSummary,
    SyncActionSummaryMap,
    SyncDeviceInterfacesInput,
    SyncDeviceInterfacesResult,
    SyncMacAddressesInput,
    SyncMacAddressesResult,
    UpdateInterfacesDescriptionInput,
    UpdateInterfacesDescriptionResult,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    map_interface_name,
    review_sync_task_result,
    sync_diff_has_changes,
)

log = logging.getLogger(__name__)


INTERFACES_QUERY = """
query InterfacesQuery(
    $devices: [String!]!
    $interfaces: [String!]
    $regex: String
    $ip_addresses: Boolean!
    $inventory_items: Boolean!
    $offset: Int!
    $limit: Int!
) {
    interfaces: interface_list(
        filters: {device: {name: {in_list: $devices}}, name: {in_list: $interfaces, i_regex: $regex}}
        pagination: {offset: $offset, limit: $limit}
    ) {
        id
        name
        device {id name}
        label
        type
        enabled
        description
        mtu
        speed
        duplex
        mode
        parent {id name}
        lag {id name}
        bridge {id name}
        bridge_interfaces {id name}
        member_interfaces {name}
        child_interfaces {
            name
            vrf {name}
            ip_addresses @include(if: $ip_addresses) {...InterfaceIP}
        }
        vrf {id name}
        untagged_vlan {id vid name}
        tagged_vlans {id vid name}
        tags {id name slug}
        custom_fields
        last_updated
        wwn
        mark_connected
        mac_addresses {id mac_address}
        cable {id label type status}
        connected_endpoints {
            ... on InterfaceType {id name label device {id name}}
            ... on FrontPortType {id name device {id name}}
            ... on RearPortType {id name device {id name}}
            ... on ProviderNetworkType {id name}
        }
        ip_addresses @include(if: $ip_addresses) {...InterfaceIP}
    }
    inventory_items: inventory_item_list(
        filters: {
            device: {name: {in_list: $devices}}
            component_type: {app_label: {exact: "dcim"}, model: {exact: "interface"}}
        }
        pagination: {offset: $offset, limit: $limit}
    ) @include(if: $inventory_items) {
        id
        name
        component {... on InterfaceType {id}}
        role {id name}
        manufacturer {id name}
        custom_fields
        label
        description
        tags {id name slug}
        asset_tag
        serial
        part_id
    }
}

fragment InterfaceIP on IPAddressType {
    id
    address
    family {value label}
    vrf {id name}
    status
    role
    dns_name
    description
    custom_fields
    last_updated
    tenant {id name}
    tags {id name slug}
}
"""


INTERFACES_FRESHNESS_QUERY = """
query InterfacesFreshnessQuery(
    $devices: [String!]!
    $interfaces: [String!]
    $regex: String
    $offset: Int!
    $limit: Int!
) {
    interfaces: interface_list(
        filters: {device: {name: {in_list: $devices}}, name: {in_list: $interfaces, i_regex: $regex}}
        pagination: {offset: $offset, limit: $limit}
    ) {
        name
        device {name}
        last_updated
    }
}
"""


def _empty_interface_connection_context(interface: object) -> dict:
    """Return template context fields for an interface with no connection data."""
    raw_interface_type = getattr(interface, "type", None)
    if isinstance(raw_interface_type, dict):
        interface_type = raw_interface_type.get("value")
    elif isinstance(raw_interface_type, str):
        interface_type = raw_interface_type
    else:
        interface_type = getattr(raw_interface_type, "value", None)
    if interface_type not in ("virtual", "lag"):
        interface_type = "interface"

    return {
        "breakout": False,
        "remote_device": None,
        "remote_device_status": None,
        "remote_interface": None,
        "remote_interface_label": None,
        "remote_termination_type": None,
        "termination_type": interface_type,
        "remote_mac_addresses": [],
        "cable": {
            "type": None,
            "status": None,
            "tenant": None,
            "label": None,
            "tags": [],
            "custom_fields": {},
            "peer_termination_type": None,
            "peer_device": None,
            "peer_interface": None,
        },
    }


def make_interfaces_brief(result: dict) -> dict:
    """
    Strip full interface data down to essential fields for MCP/LLM context window optimisation.

    Returned per-interface keys: id, name, description, type (value string), enabled,
    ip_addresses (id + address), connected_endpoints (device_name, device_id, id, name),
    custom_fields, vrf.
    """
    brief_result = {}
    for device_name, interfaces in result.items():
        brief_result[device_name] = {}
        for intf_name, intf in (interfaces or {}).items():
            intf_type = intf.get("type")
            if isinstance(intf_type, dict):
                intf_type = intf_type.get("value")

            vrf = None
            if isinstance(intf.get("vrf"), dict):
                vrf = {
                    "id": intf["vrf"]["id"],
                    "name": intf["vrf"]["name"],
                }

            brief_result[device_name][intf_name] = {
                "id": intf.get("id"),
                "name": intf.get("name"),
                "description": intf.get("description"),
                "type": intf_type,
                "enabled": intf.get("enabled"),
                "ip_addresses": [
                    {
                        "id": ip.get("id"),
                        "address": ip.get("address"),
                        "family": ip.get("family", {}).get("label"),
                    }
                    for ip in (intf.get("ip_addresses") or [])
                ],
                "connected_endpoints": [
                    {
                        "device_name": (
                            ep.get("device", {}).get("name")
                            if isinstance(ep.get("device"), dict)
                            else None
                        ),
                        "device_id": (
                            ep.get("device", {}).get("id")
                            if isinstance(ep.get("device"), dict)
                            else None
                        ),
                        "id": ep.get("id"),
                        "name": ep.get("name"),
                    }
                    for ep in (intf.get("connected_endpoints") or [])
                ],
                "custom_fields": intf.get("custom_fields"),
                "vrf": vrf,
            }
    return brief_result


def _build_interface_payload(
    desired: dict,
    changed_fields: set[str],
    object_cache: dict,
    device_name: str,
    intf_name: str,
) -> dict:
    """Build a NetBox interface API payload from desired state and changed fields."""
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
        payload["parent"] = (
            object_cache.get(("interface", device_name, parent_name))
            if parent_name
            else None
        )

    if "lag" in changed_fields:
        lag_name = desired["lag"]
        payload["lag"] = (
            object_cache.get(("interface", device_name, lag_name)) if lag_name else None
        )

    payload["device"] = object_cache[("device", device_name)]
    return payload


class NetboxInterfacesTasks:

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=GetInterfacesInput,
        output=GetInterfacesResult,
        mcp={
            "annotations": {
                "title": "Get Interfaces",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
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
        brief: bool = False,
        raise_on_empty: bool = True,
    ) -> Result:
        """Retrieve device interfaces from NetBox using GraphQL.

        Args:
            job: NorFab job for progress events.
            instance: NetBox instance. Defaults to the worker's default instance.
            devices: Device names to retrieve interfaces for.
            interface_list: Interface names to match.
            interface_regex: Regular expression to match interface names.
            ip_addresses: Include assigned IP addresses.
            inventory_items: Include inventory items assigned to interfaces.
            dry_run: Return the interface filters without querying NetBox.
            cache: Use the configured default, check freshness with True, bypass
                with False, refetch with "refresh", or skip timestamp checks with "force".
            branch: NetBox branch name. Branch reads bypass the cache.
            brief: Return only the brief interface fields.
            raise_on_empty: Raise an error when no interfaces match.

        Returns:
            Result with interfaces keyed by device and interface name, or the
            filter parameters for a dry run.

        Raises:
            UnsupportedNetboxVersion: The instance does not support this GraphQL query.
            Exception: The query fails or no interfaces match and raise_on_empty is set.
        """
        instance = instance or self.default_instance
        devices = devices or []
        cache = self.cache_use if cache is None else cache
        if branch is not None:
            cache = False

        ret = Result(
            task=f"{self.name}:get_interfaces",
            result={device: {} for device in devices},
            resources=[instance],
        )
        if dry_run:
            filter_params = {}
            if devices:
                filter_params["device"] = devices
            if interface_list:
                filter_params["name"] = interface_list
            if interface_regex:
                filter_params["name__regex"] = interface_regex
            ret.result = {"filter_params": filter_params}
            ret.dry_run = True
            return ret

        if self.nb_version[instance] < self.compatible_ge_v4:
            raise UnsupportedNetboxVersion(
                f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                f"minimum required version is {self.compatible_ge_v4}"
            )
        variables = {
            "devices": devices,
            "interfaces": interface_list or None,
            "regex": interface_regex or None,
        }
        cache_keys = {
            device: f"get_interfaces::graphql::{instance}::{device}::{ip_addresses}::{inventory_items}"
            for device in devices
        }
        devices_to_fetch = devices
        if devices and cache in (True, "force"):
            job.event("checking interface cache")
            freshness = self.netbox_graphql(
                job=job,
                instance=instance,
                query=INTERFACES_FRESHNESS_QUERY,
                variables=variables,
            )
            freshness.raise_for_status(
                f"{self.name} - interface freshness query failed"
            )
            timestamps = {}
            for interface in freshness.result.get("interfaces", []):
                device = interface["device"]["name"]
                if device in ret.result:
                    timestamps.setdefault(device, {})[interface["name"]] = interface[
                        "last_updated"
                    ]

            self.cache.expire()
            devices_to_fetch = []
            for device, interfaces in timestamps.items():
                cached = self.cache.get(cache_keys[device], {})
                if all(
                    name in cached
                    and (cache == "force" or cached[name]["last_updated"] == timestamp)
                    for name, timestamp in interfaces.items()
                ):
                    ret.result[device] = {name: cached[name] for name in interfaces}
                else:
                    devices_to_fetch.append(device)

        if devices_to_fetch:
            job.event(f"fetching interfaces for {len(devices_to_fetch)} device(s)")
            response = self.netbox_graphql(
                job=job,
                instance=instance,
                branch=branch,
                query=INTERFACES_QUERY,
                variables={
                    **variables,
                    "devices": devices_to_fetch,
                    "ip_addresses": ip_addresses,
                    "inventory_items": inventory_items,
                },
            )
            response.raise_for_status(f"{self.name} - interface query failed")

            items_by_interface = {}
            for item in response.result.get("inventory_items", []):
                component = item.pop("component")
                if component and component.get("id"):
                    items_by_interface.setdefault(int(component["id"]), []).append(item)

            for interface in response.result.get("interfaces", []):
                device = interface["device"]["name"]
                if device not in ret.result:
                    continue
                interface["id"] = int(interface["id"])
                for field in ("type", "mode", "duplex"):
                    if interface[field]:
                        interface[field] = {"value": interface[field]}
                interface["member_interfaces"] = [
                    member["name"] for member in interface["member_interfaces"]
                ]
                interface.setdefault("ip_addresses", [])
                for ip in interface["ip_addresses"]:
                    ip["id"] = int(ip["id"])
                for child in interface["child_interfaces"]:
                    child["vrf"] = child["vrf"]["name"] if child["vrf"] else None
                    child.setdefault("ip_addresses", [])
                    for ip in child["ip_addresses"]:
                        ip["id"] = int(ip["id"])
                interface["inventory_items"] = items_by_interface.get(
                    interface["id"], []
                )
                ret.result[device][interface["name"]] = interface

            if cache is not False:
                for device in devices_to_fetch:
                    self.cache.set(
                        cache_keys[device], ret.result[device], expire=self.cache_ttl
                    )

        if raise_on_empty and not any(ret.result.values()):
            raise Exception(
                f"{self.name} - no interfaces data returned by '{instance}' "
                f"for devices {', '.join(devices)}"
            )
        if brief:
            ret.result = make_interfaces_brief(ret.result)
        return ret

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateDeviceInterfacesInput,
        output=CreateDeviceInterfacesResult,
        mcp={
            "annotations": {
                "title": "Create Device Interfaces",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
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
        nb = self._get_pynetbox(instance, branch=branch, job=job)
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
                intf.name
                for intf in self.bulk_filter(nb.dcim.interfaces, device=device_name)
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
                if dry_run is True:
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
        output=UpdateInterfacesDescriptionResult,
        mcp={
            "annotations": {
                "title": "Update Interface Descriptions",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
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
        timeout: int = 600,
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
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        update_action = "would update" if dry_run else "updating"
        apply_action = "would apply" if dry_run else "applying"
        log.info(
            f"{self.name} - Update interfaces description: "
            f"{update_action.capitalize()} descriptions for "
            f"{len(devices)} device(s) in '{instance}'"
        )

        job.event(
            f"{update_action} interface descriptions for "
            f"{len(devices)} device(s), dry_run={dry_run}"
        )

        if description_template:
            job.event("rendering interface descriptions from interface data")
            # get list of all interface connections
            nb_connections = self.get_connections(
                job=job,
                devices=devices,
                interfaces=interfaces,
                interface_regex=interface_regex,
                instance=instance,
                branch=branch,
            )
            if nb_connections.errors:
                ret.errors.extend(nb_connections.errors)
                ret.failed = nb_connections.failed
                return ret

            # Fetch NetBox interfaces as well so virtual/disconnected interfaces
            # absent from get_connections still receive template-rendered descriptions.
            interface_filter = {"device": devices}
            if interfaces:
                interface_filter["name"] = interfaces
            if interface_regex:
                interface_filter["name__regex"] = interface_regex
            try:
                nb_interfaces = self.bulk_filter(nb.dcim.interfaces, **interface_filter)
            except Exception as exc:
                msg = f"failed to fetch interfaces for description update: {exc}"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                ret.failed = True
                return ret
            nb_interfaces_by_device = {}
            for nb_interface in nb_interfaces:
                nb_interfaces_by_device.setdefault(nb_interface.device.name, {})[
                    nb_interface.name
                ] = nb_interface

            # produce interface description and update it
            for device in devices:
                device_connections = nb_connections.result.get(device, {})
                device_interfaces = nb_interfaces_by_device.get(device, {})
                interface_names = sorted(
                    set(device_connections).union(device_interfaces)
                )
                if interfaces:
                    interface_names = [
                        interface
                        for interface in interface_names
                        if interface in interfaces
                    ]
                ret.result.setdefault(device, {})
                job.event(
                    f"processing {len(interface_names)} interface(s) for '{device}'"
                )
                nb_device = nb.dcim.devices.get(name=device)
                for interface in interface_names:
                    job.event(f"{device}:{interface} {update_action} description")
                    connection = device_connections.get(interface)
                    nb_interface = device_interfaces.get(interface)
                    if connection is None:
                        if not nb_interface:
                            continue
                        connection = _empty_interface_connection_context(nb_interface)
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
                    nb_interface = nb_interface or api_endpoint.get(
                        device=device, name=interface
                    )
                    if not nb_interface:
                        continue
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
                f"{apply_action} {len(descriptions)} description(s) "
                f"to {len(devices)} device(s)"
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

        updated_count = sum(len(interfaces) for interfaces in ret.result.values())
        if dry_run is True:
            changed_count = sum(
                1
                for interfaces in ret.result.values()
                for diff in interfaces.values()
                if diff["-"] != diff["+"]
            )
            job.event(
                f"dry-run: would update {updated_count} interface description(s), "
                f"would change {changed_count}"
            )
        else:
            job.event(f"updated {updated_count} interface description(s)")
        job.event("interface description update task complete")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncDeviceInterfacesInput,
        output=SyncDeviceInterfacesResult,
        mcp={
            "annotations": {
                "title": "Sync Device Interfaces",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_device_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        process_deletions: bool = False,
        branch: str = None,
        interface_map: Union[None, str, list] = None,
        filter_by_name: Union[None, str] = None,
        filter_by_description: Union[None, str] = None,
        update_type: bool = True,
        preserve_description: Union[None, bool] = None,
        batch_size: int = 1000,
        batch_fallback: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Synchronize device interface configuration from live devices into NetBox using a
        normalized state model and DeepDiff-based reconciliation.

        The task follows a four-step pipeline:

        1. **Fetch**: Pull current interface state from NetBox (source of truth).
        2. **Collect live state**: Run Nornir ``parse_ttp`` interface configuration
           and status jobs against devices. Configuration is authoritative, while
           status fills missing MTU, duplex, and speed values. Existing NetBox MTU
           and speed values are preserved when live values are ``None`` or ``0``.
        3. **Diff**: Compare normalized NetBox state against normalized live state using
           DeepDiff to classify each interface as ``create``, ``update``, ``delete``, or
           ``in_sync``.
        4. **Reconcile**: Apply changes to NetBox in a safe order — LAG interfaces
           first, then parent interfaces, then child (sub)interfaces, then updates,
           and finally deletions (only when ``process_deletions=True``).

        **Prerequisites**

        - Device must exist in Netbox

        **Limitations**

        - Interface sync does not handle IP addresses
        - Clearing interface mode also clears untagged and tagged VLAN assignments
        - Interface sync does not handle MAC addresses
        - Sync interfaces uses device running configuration as the primary source;
          operational state only fills missing MTU, duplex, and speed values

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
            with_approval (bool, optional): Preview changes, ask for review, then apply them.
            timeout (int, optional): Timeout in seconds for the Nornir parse_ttp job.
            devices (list, optional): List of device names to sync.
            process_deletions (bool, optional): If True, delete interfaces present in
                NetBox but absent in live data. Defaults to False (safe by default).
            branch (str, optional): NetBox branch name to use. The branching plugin
                must be installed. The branch is created automatically if it does
                not exist.
            interface_map: Ordered interface rename rules, or an ``nf://`` YAML
                file containing them. Rules match by device name glob, device
                type model glob, and a literal live interface name substring.
                The first matching rule wins.
            filter_by_name (str, optional): Glob pattern to restrict which interfaces
                are included by name, e.g. ``'Loopback*'`` or ``'Eth*'``.
            filter_by_description (str, optional): Glob pattern to restrict which
                interfaces are included by description, e.g. ``'uplink*'``.
            preserve_description (bool, optional): Description preservation policy.
                ``None`` preserves NetBox text when the live description is empty,
                ``True`` always preserves NetBox text, and ``False`` always uses
                live text.
            batch_size (int, optional): Maximum interfaces in each NetBox bulk
                create, update, or delete request. Defaults to 1000.
            batch_fallback (bool, optional): Retry failed create and update batches
                one interface at a time, reporting errors and continuing with the
                next bulk batch. Defaults to False. Deletions are unaffected.
            update_type (bool): Safely update existing interface types. Updates are
                allowed from ``other`` to ``virtual``, ``bridge``, or ``lag``, and
                between those logical types. Specific physical types are protected,
                and transitions to ``other`` are ignored. Set to False to disable
                all type updates. New interfaces can use any parsed type regardless
                of this setting. Defaults to True.
            **kwargs: Additional Nornir host filter keyword arguments passed to
                ``parse_ttp`` (e.g. ``FL``, ``FC``, ``FB``).

        Returns:
            dict: Per-device action summary. Structure depends on ``dry_run``; see
                above. Diff details are available in ``res["diff"]`` for non
                dry-run mode.
        """
        devices = list(devices or [])
        if self.is_url(interface_map):
            interface_map = TypeAdapter(list[InterfaceMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(interface_map, raise_on_fail=True)) or []
            )
        interface_map = [
            rule.model_dump() if hasattr(rule, "model_dump") else dict(rule)
            for rule in interface_map or []
        ]
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_device_interfaces",
            result=SyncActionSummaryMap().model_dump(),
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        log.info(
            f"{self.name} - Sync device interfaces: Processing {len(devices)} device(s) in '{instance}'"
        )

        # Source additional hosts from Nornir filters.
        if kwargs:
            job.event("resolving devices from Nornir filters")
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            devices.extend(nornir_hosts)
            job.event(
                f"resolved {len(nornir_hosts)} device(s) from Nornir filters, "
                f"{len(set(devices))} total device(s) selected"
            )
        devices = sorted(set(devices))

        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        job.event(f"syncing interfaces for {len(devices)} devices, dry_run={dry_run}")

        # filter out devices not define in Netbox
        job.event(f"validating {len(devices)} device(s) exist in NetBox")
        nb_devices_data = {
            d.name: {
                "id": d.id,
                "device_type": d.device_type.model,
            }
            for d in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,device_type",
            )
        }
        object_cache = {
            ("device", device_name): data["id"]
            for device_name, data in nb_devices_data.items()
        }
        for device_name in devices:
            if device_name not in nb_devices_data:
                msg = f"{device_name} - device not found in NetBox"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices_data]
        if not devices:
            job.event(
                "no valid NetBox devices remain after validation", severity="ERROR"
            )
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} device(s) in NetBox")
        # Gather the current NetBox interface state.
        job.event("fetching current interface data from NetBox")
        nb_interfaces_result = self.get_interfaces(
            job=job,
            instance=instance,
            branch=branch,
            devices=devices,
            ip_addresses=False,
            cache="refresh",
            raise_on_empty=False,
        )
        if nb_interfaces_result.errors:
            job.event("failed to fetch NetBox interface data", severity="ERROR")
            ret.errors.extend(nb_interfaces_result.errors)
            ret.failed = True
            return ret

        # Normalize NetBox interface data per device.
        job.event("normalising NetBox interface data")
        normalised_nb_all: dict = {}
        for device_name, interfaces in nb_interfaces_result.result.items():
            normalised_nb_all[device_name] = {}
            for intf_name, data in (interfaces or {}).items():
                object_cache[("interface", device_name, intf_name)] = data["id"]
                if filter_by_name and not fnmatch.fnmatch(intf_name, filter_by_name):
                    continue
                if filter_by_description and not fnmatch.fnmatch(
                    str(data.get("description") or ""), filter_by_description
                ):
                    continue
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
                normalised_nb_all[device_name][intf_name] = {
                    "type": data["type"]["value"],
                    "enabled": bool(data.get("enabled", True)),
                    "parent": parent_name,
                    "lag": lag,
                    "mtu": data.get("mtu"),
                    "speed": data.get("speed"),
                    "duplex": (
                        data["duplex"].get("value")
                        if isinstance(data.get("duplex"), dict)
                        else data.get("duplex")
                    ),
                    "description": str(data.get("description") or ""),
                    "mode": (data.get("mode") or {}).get("value"),
                }
        nb_interface_count = sum(len(v) for v in normalised_nb_all.values())
        job.event(
            f"normalised {nb_interface_count} NetBox interface(s) after applying filters"
        )

        # Gather live source of truth from Nornir parse_ttp.
        job.event(f"retrieving live interfaces for {len(devices)} devices")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "interfaces", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        job.event(f"retrieving live interface status for {len(devices)} devices")
        parse_status_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "interfaces_status", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        interface_status = {}
        for wname, wdata in parse_status_data.items():
            resources_failed = wdata.get("resources_failed") or []
            if resources_failed:
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                msg = (
                    f"{wname} failed to fetch interface status data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
            if wdata.get("failed"):
                msg = f"{wname} - failed to parse interface status data from devices"
                log.warning(msg)
                job.event(msg, severity="WARNING")
                continue
            for device_name, host_interfaces in wdata["result"].items():
                device_status = interface_status.setdefault(device_name, {})
                for data in host_interfaces or []:
                    if data.get("name"):
                        device_status[data["name"]] = data

        # Normalize live interface data per device.
        job.event("normalising live interface data")
        normalised_live_all = {}
        for wname, wdata in parse_data.items():
            resources_failed = wdata.get("resources_failed") or []
            if resources_failed:
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                msg = (
                    f"{wname} failed to fetch interface data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
            if wdata.get("failed"):
                msg = f"{wname} - failed to parse interface data from devices"
                log.warning(msg)
                job.event(msg, severity="WARNING")
                continue
            for device_name, host_interfaces in wdata["result"].items():
                normalised_live_all.setdefault(device_name, {})
                for data in host_interfaces or []:
                    status = interface_status.get(device_name, {}).get(
                        data.get("name"), {}
                    )
                    mapped_names = {
                        field: data.get(field) for field in ("name", "parent", "lag")
                    }
                    for field, live_name in mapped_names.items():
                        mapped_names[field] = map_interface_name(
                            live_name,
                            interface_map,
                            device_name,
                            nb_devices_data[device_name]["device_type"],
                        )
                    intf_name = mapped_names["name"]
                    if filter_by_name and not fnmatch.fnmatch(
                        intf_name, filter_by_name
                    ):
                        continue
                    if filter_by_description and not fnmatch.fnmatch(
                        str(data.get("description") or ""), filter_by_description
                    ):
                        continue

                    normalised_live_all[device_name][intf_name] = {
                        "type": data["type"],
                        "enabled": bool(
                            data.get("enabled", data.get("is_enabled", True))
                        ),
                        "parent": mapped_names["parent"],
                        "lag": mapped_names["lag"],
                        "mtu": data.get("mtu"),
                        "speed": data.get("speed"),
                        "duplex": data.get("duplex"),
                        "description": str(data.get("description") or ""),
                        "mode": data.get("mode"),
                    }
                    interface = normalised_live_all[device_name][intf_name]
                    status_mtu = status.get("mtu")
                    if interface["mtu"] is None and status_mtu and status_mtu > 0:
                        interface["mtu"] = status_mtu
                    status_speed = status.get("speed_bps")
                    if interface["speed"] is None and status_speed and status_speed > 0:
                        interface["speed"] = status_speed // 1_000
                    if interface["duplex"] is None:
                        interface["duplex"] = status.get("duplex")
                    # Preserve existing NetBox values when live data has no usable value.
                    nb_interface = normalised_nb_all.get(device_name, {}).get(intf_name)
                    if nb_interface:
                        interface["description"] = apply_description_policy(
                            interface["description"],
                            nb_interface["description"],
                            preserve_description,
                        )
                        for field in ("mtu", "speed"):
                            if interface[field] in (None, 0) and nb_interface[field]:
                                interface[field] = nb_interface[field]
        live_interface_count = sum(len(v) for v in normalised_live_all.values())
        job.event(
            f"normalised {live_interface_count} live interface(s) after applying filters"
        )

        # remove devices that returned no parsing results
        for device_name in devices:
            if device_name not in normalised_live_all:
                msg = f"{device_name} - parsing returned no interfaces data, skipping device"
                log.error(msg)
                job.event(msg, severity="ERROR")
                normalised_nb_all.pop(device_name)
        if not normalised_nb_all:
            job.event(
                "no interface parsing results collected for devices", severity="ERROR"
            )
            ret.failed = True
            ret.errors.append("no interfaces parsing results collected for devices")
            return ret

        # Single diff on the full normalised datasets
        job.event("calculating interface sync diff")
        full_diff = self.make_diff(normalised_live_all, normalised_nb_all)

        # Apply the existing-interface type update policy. Interface creation is
        # intentionally unrestricted and continues to use any parsed type.
        for dev_name, dev_diff in full_diff.items():
            for intf_name in list(dev_diff["update"].keys()):
                intf_updates = dev_diff["update"][intf_name]
                type_change = intf_updates.get("type")
                if type_change:
                    old_type = type_change["old_value"]
                    new_type = type_change["new_value"]
                    safe_type_transition = old_type in (
                        "other",
                        "virtual",
                        "bridge",
                        "lag",
                    ) and new_type in ("virtual", "bridge", "lag")

                    # Remove all existing-interface type changes when disabled.
                    if update_type is False:
                        intf_updates.pop("type")

                    # NetBox does not allow cabled interfaces to become virtual.
                    elif new_type == "virtual" and nb_interfaces_result.result[
                        dev_name
                    ][intf_name].get("cable"):
                        intf_updates.pop("type")
                        msg = (
                            f"{dev_name}:{intf_name} - cannot transition interface "
                            f"type from {old_type} to virtual while a cable is connected"
                        )
                        ret.errors.append(msg)
                        log.error(msg)
                        job.event(msg, severity="ERROR")

                    # Protect physical types and never transition to ``other``.
                    elif safe_type_transition is False:
                        intf_updates.pop("type")
                        job.event(
                            f"skipping unsafe interface type transition for "
                            f"{dev_name}:{intf_name}: {old_type} -> {new_type}",
                            severity="WARNING",
                        )
                    # Do not assign a parsed parent when NetBox keeps a non-virtual type.
                    if old_type != "virtual" and "type" not in intf_updates:
                        intf_updates.pop("parent", None)
                # remove interface from updates if nothing remains to update
                if not intf_updates:
                    dev_diff["update"].pop(intf_name)
                    dev_diff["in_sync"].append(intf_name)
            dev_diff["in_sync"].sort()
        create_count = sum(len(actions["create"]) for actions in full_diff.values())
        update_count = sum(len(actions["update"]) for actions in full_diff.values())
        delete_count = sum(len(actions["delete"]) for actions in full_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in full_diff.values())
        job.event(
            "interface sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{delete_count} delete, {in_sync_count} in sync"
        )

        ret.result = {
            device_name: SyncActionSummary(in_sync=actions["in_sync"]).model_dump()
            for device_name, actions in full_diff.items()
        }
        ret.diff = full_diff
        if dry_run:
            job.event(
                "dry-run requested, returning interface sync diff without changes"
            )
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if not sync_diff_has_changes(full_diff):
            job.event("no interface sync changes required")
            return ret
        if with_approval and not review_sync_task_result(
            job, "interface sync", full_diff
        ):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret
        device_names_by_id = {
            data["id"]: device_name for device_name, data in nb_devices_data.items()
        }
        # create LAG interfaces
        job.event("preparing LAG interface create payloads")
        bulk_create_lag_interfaces = []
        for device_name, actions in full_diff.items():
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if desired["type"] == "lag":
                    payload = _build_interface_payload(
                        desired=desired,
                        changed_fields={
                            k for k in desired.keys() if desired[k] is not None
                        },
                        object_cache=object_cache,
                        device_name=device_name,
                        intf_name=intf_name,
                    )
                    bulk_create_lag_interfaces.append(payload)
        job.event(
            f"prepared {len(bulk_create_lag_interfaces)} LAG interface create payload(s)"
        )
        if bulk_create_lag_interfaces:
            created_lag_count = 0
            job.event("creating LAG interfaces")
            total_batches = (
                len(bulk_create_lag_interfaces) + batch_size - 1
            ) // batch_size
            for batch_start in range(0, len(bulk_create_lag_interfaces), batch_size):
                batch = bulk_create_lag_interfaces[
                    batch_start : batch_start + batch_size
                ]
                batch_number = batch_start // batch_size + 1
                msg = f"creating LAG interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_interfaces = nb.dcim.interfaces.create(batch)
                except Exception as exc:
                    msg = f"failed to create LAG interface batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    if not batch_fallback:
                        ret.failed = True
                        return ret
                    msg = f"retrying LAG interface batch {batch_number}/{total_batches} one interface at a time"
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    created_interfaces = []
                    for payload in batch:
                        device_name = device_names_by_id[payload["device"]]
                        try:
                            interface = nb.dcim.interfaces.create(payload)
                        except Exception as item_exc:
                            msg = f"failed to create {device_name}:{payload['name']}: {item_exc}"
                            ret.errors.append(msg)
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                        else:
                            created_interfaces.append(interface)
                            msg = (
                                f"created {device_name}:{interface.name} using fallback"
                            )
                            log.info(msg)
                            job.event(msg)
                    msg = f"completed LAG interface batch {batch_number}/{total_batches} fallback: {len(created_interfaces)} succeeded, {len(batch) - len(created_interfaces)} failed"
                    log.info(msg)
                    job.event(msg)
                for interface in created_interfaces:
                    device_name = interface.device.name
                    object_cache[("interface", device_name, interface.name)] = (
                        interface.id
                    )
                    ret.result[device_name]["created"].append(interface.name)
                    created_lag_count += 1
            job.event(f"created {created_lag_count} LAG interface(s)")
        else:
            job.event("no LAG interfaces to create")

        # create parent interfaces associating with LAG if required
        job.event("preparing non-child/main interface create payloads")
        bulk_create_parent_interfaces = []
        for device_name, actions in full_diff.items():
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if not desired["parent"] and desired["type"] != "lag":
                    payload = _build_interface_payload(
                        desired=desired,
                        changed_fields={
                            k for k in desired.keys() if desired[k] is not None
                        },
                        object_cache=object_cache,
                        device_name=device_name,
                        intf_name=intf_name,
                    )
                    bulk_create_parent_interfaces.append(payload)
        job.event(
            f"prepared {len(bulk_create_parent_interfaces)} non-child/main interface create payload(s)"
        )
        if bulk_create_parent_interfaces:
            created_parent_count = 0
            job.event("creating non-child/main interfaces")
            total_batches = (
                len(bulk_create_parent_interfaces) + batch_size - 1
            ) // batch_size
            for batch_start in range(0, len(bulk_create_parent_interfaces), batch_size):
                batch = bulk_create_parent_interfaces[
                    batch_start : batch_start + batch_size
                ]
                batch_number = batch_start // batch_size + 1
                msg = f"creating non-child/main interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_interfaces = nb.dcim.interfaces.create(batch)
                except Exception as exc:
                    msg = f"failed to create non-child/main interface batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    if not batch_fallback:
                        ret.failed = True
                        return ret
                    msg = f"retrying non-child/main interface batch {batch_number}/{total_batches} one interface at a time"
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    created_interfaces = []
                    for payload in batch:
                        device_name = device_names_by_id[payload["device"]]
                        try:
                            interface = nb.dcim.interfaces.create(payload)
                        except Exception as item_exc:
                            msg = f"failed to create {device_name}:{payload['name']}: {item_exc}"
                            ret.errors.append(msg)
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                        else:
                            created_interfaces.append(interface)
                            msg = (
                                f"created {device_name}:{interface.name} using fallback"
                            )
                            log.info(msg)
                            job.event(msg)
                    msg = f"completed non-child/main interface batch {batch_number}/{total_batches} fallback: {len(created_interfaces)} succeeded, {len(batch) - len(created_interfaces)} failed"
                    log.info(msg)
                    job.event(msg)
                for interface in created_interfaces:
                    device_name = interface.device.name
                    object_cache[("interface", device_name, interface.name)] = (
                        interface.id
                    )
                    ret.result[device_name]["created"].append(interface.name)
                    created_parent_count += 1
            job.event(f"created {created_parent_count} non-child/main interface(s)")
        else:
            job.event("no non-child/main interfaces to create")

        # create child interfaces associating with parent interfaces
        job.event("preparing child interface create payloads")
        bulk_create_child_interfaces = []
        for device_name, actions in full_diff.items():
            for intf_name in actions["create"]:
                desired = normalised_live_all[device_name][intf_name]
                if desired["parent"]:
                    payload = _build_interface_payload(
                        desired=desired,
                        changed_fields={
                            k for k in desired.keys() if desired[k] is not None
                        },
                        object_cache=object_cache,
                        device_name=device_name,
                        intf_name=intf_name,
                    )
                    bulk_create_child_interfaces.append(payload)
        job.event(
            f"prepared {len(bulk_create_child_interfaces)} child interface create payload(s)"
        )
        if bulk_create_child_interfaces:
            created_child_count = 0
            job.event("creating child interfaces")
            total_batches = (
                len(bulk_create_child_interfaces) + batch_size - 1
            ) // batch_size
            for batch_start in range(0, len(bulk_create_child_interfaces), batch_size):
                batch = bulk_create_child_interfaces[
                    batch_start : batch_start + batch_size
                ]
                batch_number = batch_start // batch_size + 1
                msg = f"creating child interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_interfaces = nb.dcim.interfaces.create(batch)
                except Exception as exc:
                    msg = f"failed to create child interface batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    if not batch_fallback:
                        ret.failed = True
                        return ret
                    msg = f"retrying child interface batch {batch_number}/{total_batches} one interface at a time"
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    created_interfaces = []
                    for payload in batch:
                        device_name = device_names_by_id[payload["device"]]
                        try:
                            interface = nb.dcim.interfaces.create(payload)
                        except Exception as item_exc:
                            msg = f"failed to create {device_name}:{payload['name']}: {item_exc}"
                            ret.errors.append(msg)
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                        else:
                            created_interfaces.append(interface)
                            msg = (
                                f"created {device_name}:{interface.name} using fallback"
                            )
                            log.info(msg)
                            job.event(msg)
                    msg = f"completed child interface batch {batch_number}/{total_batches} fallback: {len(created_interfaces)} succeeded, {len(batch) - len(created_interfaces)} failed"
                    log.info(msg)
                    job.event(msg)
                for interface in created_interfaces:
                    device_name = interface.device.name
                    object_cache[("interface", device_name, interface.name)] = (
                        interface.id
                    )
                    ret.result[device_name]["created"].append(interface.name)
                    created_child_count += 1
            job.event(f"created {created_child_count} child interface(s)")
        else:
            job.event("no child interfaces to create")

        # Build bulk_update_interfaces list from full_diff
        job.event("preparing interface update payloads")
        bulk_update_interfaces = {}
        for device_name, actions in full_diff.items():
            for intf_name, field_changes in actions["update"].items():
                desired = normalised_live_all[device_name][intf_name]
                payload = _build_interface_payload(
                    desired=desired,
                    changed_fields=set(field_changes.keys()),
                    object_cache=object_cache,
                    device_name=device_name,
                    intf_name=intf_name,
                )
                # Clear VLAN assignments in the same request when removing interface mode.
                if "mode" in field_changes and desired["mode"] is None:
                    payload["untagged_vlan"] = None
                    payload["tagged_vlans"] = []
                payload["id"] = object_cache[("interface", device_name, intf_name)]
                bulk_update_interfaces[(device_name, intf_name)] = payload
        job.event(f"prepared {len(bulk_update_interfaces)} interface update payload(s)")
        if bulk_update_interfaces:
            updated_count = 0
            job.event(f"updating {len(bulk_update_interfaces)} interface(s)")
            update_items = list(bulk_update_interfaces.items())
            total_batches = (len(update_items) + batch_size - 1) // batch_size
            for batch_start in range(0, len(update_items), batch_size):
                batch = update_items[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"updating interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.dcim.interfaces.update([payload for _, payload in batch])
                except Exception as exc:
                    msg = f"failed to update interface batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    if not batch_fallback:
                        ret.failed = True
                        return ret
                    msg = f"retrying interface update batch {batch_number}/{total_batches} one interface at a time"
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    updated_items = []
                    for (device_name, intf_name), payload in batch:
                        try:
                            nb.dcim.interfaces.update([payload])
                        except Exception as item_exc:
                            msg = f"failed to update {device_name}:{intf_name}: {item_exc}"
                            ret.errors.append(msg)
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                        else:
                            updated_items.append(((device_name, intf_name), payload))
                            msg = f"updated {device_name}:{intf_name} using fallback"
                            log.info(msg)
                            job.event(msg)
                    msg = f"completed interface update batch {batch_number}/{total_batches} fallback: {len(updated_items)} succeeded, {len(batch) - len(updated_items)} failed"
                    log.info(msg)
                    job.event(msg)
                    batch = updated_items
                for (device_name, intf_name), _ in batch:
                    ret.result[device_name]["updated"].append(intf_name)
                    updated_count += 1
            job.event(f"updated {updated_count} interface(s)")
        else:
            job.event("no interfaces to update")

        # Build bulk_delete_interfaces payload from full_diff
        bulk_delete_interfaces = {}  # keyed by intf id, values intf names
        if process_deletions:
            job.event("processing interface deletions")
            for device_name, actions in full_diff.items():
                # delete children before parents to avoid constraint errors
                ordered_deletes = sorted(
                    actions["delete"], key=lambda x: (x.count("."), x), reverse=True
                )
                for intf_name in ordered_deletes:
                    intf_id = object_cache[("interface", device_name, intf_name)]
                    bulk_delete_interfaces[intf_id] = {
                        "device": device_name,
                        "interface": intf_name,
                    }
            job.event(
                f"prepared {len(bulk_delete_interfaces)} interface delete payload(s)"
            )
        elif delete_count:
            job.event(
                f"skipping {delete_count} interface deletion(s), process_deletions=False"
            )
        if bulk_delete_interfaces:
            job.event(f"deleting {len(bulk_delete_interfaces)} interface(s)")
            delete_items = list(bulk_delete_interfaces.items())
            total_batches = (len(delete_items) + batch_size - 1) // batch_size
            for batch_start in range(0, len(delete_items), batch_size):
                batch = delete_items[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"deleting interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.dcim.interfaces.delete([intf_id for intf_id, _ in batch])
                except Exception as exc:
                    msg = f"failed to delete interface batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    ret.failed = True
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    return ret
                for _, intf_data in batch:
                    device_name = intf_data["device"]
                    intf_name = intf_data["interface"]
                    ret.result[device_name]["deleted"].append(intf_name)
            job.event(f"deleted {len(bulk_delete_interfaces)} interface(s)")
        elif process_deletions:
            job.event("no interfaces to delete")

        job.event("interface sync complete")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncMacAddressesInput,
        output=SyncMacAddressesResult,
        mcp={
            "annotations": {
                "title": "Sync MAC Addresses",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_mac_addresses(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: str = None,
        filter_by_name: Union[None, str] = None,
        filter_by_description: Union[None, str] = None,
        filter_by_mac: Union[None, str] = None,
        batch_size: int = 1000,
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
            with_approval (bool, optional): Preview changes, ask for review, then apply them.
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
            result=SyncActionSummaryMap().model_dump(),
            resources=[instance],
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        log.info(
            f"{self.name} - Sync MAC addresses: Processing {len(devices)} device(s) in '{instance}'"
        )

        # source additional hosts from Nornir filters
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

        job.event(
            f"syncing MAC addresses for {len(devices)} devices, dry_run={dry_run}"
        )

        # filter out devices not defined in NetBox
        job.event(f"validating {len(devices)} device(s) exist in NetBox")
        nb_devices_data = {
            d.name: {"id": d.id, "name": d.name}
            for d in self.bulk_filter(nb.dcim.devices, name=devices, fields="id,name")
        }
        for d in list(devices):
            if d not in nb_devices_data:
                msg = f"{d} - device not found in Netbox"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                devices.remove(d)
        if not devices:
            job.event(
                "no valid NetBox devices remain after validation", severity="ERROR"
            )
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} device(s) in NetBox")

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
        job.event("collecting live MAC address candidates")
        all_mac_live: dict = {}  # {mac: {"device": ..., "interface": ...}}
        for wname, wdata in parse_data.items():
            resources_failed = wdata.get("resources_failed") or []
            if resources_failed:
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                msg = (
                    f"{wname} failed to fetch interface data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
            if wdata.get("failed"):
                msg = f"{wname} - failed to parse interface data from devices"
                log.warning(msg)
                job.event(msg, severity="WARNING")
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
            job.event("no MAC addresses found in live data")
            return ret
        job.event(f"collected {len(all_mac_live)} live MAC address candidate(s)")

        # fetch interfaces data from NetBox to resolve interface IDs
        job.event("fetching NetBox interfaces to resolve MAC assignments")
        nb_interfaces_result = self.get_interfaces(
            job=job,
            instance=instance,
            branch=branch,
            devices=devices,
            ip_addresses=False,
            cache="refresh",
        )
        if nb_interfaces_result.errors:
            job.event(
                "failed to fetch NetBox interfaces for MAC sync", severity="ERROR"
            )
            ret.errors.extend(nb_interfaces_result.errors)
            ret.failed = True
            return ret

        # fetch existing MAC address objects from NetBox
        # NetBox allows duplicate MAC entries; prefer assigned entries over
        # unassigned ones so that a conflicting assignment is not silently
        # overwritten by a later unassigned copy during dict construction.
        job.event(
            f"fetching {len(all_mac_live)} matching MAC address object(s) from NetBox"
        )
        nb_macs: dict = {}
        for _m in self.bulk_filter(
            nb.dcim.mac_addresses,
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
        job.event(
            f"retrieved {len(nb_macs)} matching MAC address object(s) from NetBox"
        )

        # per-device result tracking
        device_results = {
            device_name: SyncActionSummary().model_dump() for device_name in devices
        }
        ret.result = device_results

        bulk_update_mac = []
        bulk_create_mac = []

        # process and compare live MACs versus NetBox MACs
        job.event("calculating MAC address sync actions")
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
                if dry_run is True:
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
                if dry_run is True:
                    device_results[device_name]["created"].append(mac)
                else:
                    bulk_create_mac.append(
                        {
                            "mac_address": mac,
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id": nb_raw[intf_name]["id"],
                        }
                    )

        job.event(
            f"MAC address sync actions: {len(bulk_create_mac)} create, "
            f"{len(bulk_update_mac)} update"
        )

        if dry_run is True:
            job.event(
                "dry-run requested, returning MAC address sync plan without changes"
            )
            ret.dry_run = True
            return ret
        if not bulk_create_mac and not bulk_update_mac:
            job.event("no MAC address sync changes required")
            return ret
        if with_approval:
            mac_preview_result = {
                device_name: {
                    "created": list(device_result["created"]),
                    "updated": list(device_result["updated"]),
                    "in_sync": list(device_result["in_sync"]),
                }
                for device_name, device_result in device_results.items()
            }
            for m in bulk_create_mac:
                device_name = all_mac_live[m["mac_address"]]["device"]
                mac_preview_result[device_name]["created"].append(m["mac_address"])
            for m in bulk_update_mac:
                device_name = all_mac_live[m["mac_address"]]["device"]
                mac_preview_result[device_name]["updated"].append(m["mac_address"])
            # request confirmation from user
            if not review_sync_task_result(job, "MAC address sync", mac_preview_result):
                ret.status = "skipped"
                ret.result = mac_preview_result
                ret.dry_run = True
                ret.messages.append("review declined; changes were not applied")
                return ret
        if bulk_create_mac:
            job.event(f"creating {len(bulk_create_mac)} MAC address(es)")
            total_batches = (len(bulk_create_mac) + batch_size - 1) // batch_size
            for batch_start in range(0, len(bulk_create_mac), batch_size):
                batch = bulk_create_mac[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"creating MAC address batch {batch_number}/{total_batches} ({len(batch)} address(es))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.dcim.mac_addresses.create(batch)
                except Exception as exc:
                    msg = f"failed to create MAC address batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    ret.failed = True
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    return ret
                for item in batch:
                    device_name = all_mac_live[item["mac_address"]]["device"]
                    device_results[device_name]["created"].append(item["mac_address"])
            job.event(f"created {len(bulk_create_mac)} MAC addresses")
        else:
            job.event("no MAC addresses to create")
        if bulk_update_mac:
            job.event(f"updating {len(bulk_update_mac)} MAC address(es)")
            total_batches = (len(bulk_update_mac) + batch_size - 1) // batch_size
            for batch_start in range(0, len(bulk_update_mac), batch_size):
                batch = bulk_update_mac[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"updating MAC address batch {batch_number}/{total_batches} ({len(batch)} address(es))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.dcim.mac_addresses.update(batch)
                except Exception as exc:
                    msg = f"failed to update MAC address batch {batch_number}/{total_batches}: {exc}"
                    ret.errors.append(msg)
                    ret.failed = True
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    return ret
                for item in batch:
                    device_name = all_mac_live[item["mac_address"]]["device"]
                    device_results[device_name]["updated"].append(item["mac_address"])
            job.event(f"updated {len(bulk_update_mac)} MAC addresses")
        else:
            job.event("no MAC addresses to update")

        job.event("MAC address sync complete")
        return ret
