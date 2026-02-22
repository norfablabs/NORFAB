import logging

import copy

from typing import Union, Any
from norfab.core.worker import Task, Job
from norfab.models import Result
from .netbox_models import NetboxFastApiArgs
from .netbox_exceptions import UnsupportedNetboxVersion
from norfab.core.exceptions import UnsupportedServiceError

log = logging.getLogger(__name__)


class NetboxInterfacesTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_interfaces_graphql(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        interface_list: Union[None, list] = None,
        interface_regex: Union[None, str] = None,
        ip_addresses: bool = False,
        inventory_items: bool = False,
        dry_run: bool = False,
        cache: Union[bool, str] = None,
        branch: str = None,
    ) -> Result:
        """
        Retrieve device interfaces from Netbox using GraphQL API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve interfaces for.
            interface_list (list, optional): List of interface names to retrieve.
            interface_regex (str, optional): Regex pattern to match interfaces by name, case insensitive.
            ip_addresses (bool, optional): If True, retrieves interface IPs. Defaults to False.
            inventory_items (bool, optional): If True, retrieves interface inventory items. Defaults to False.
            dry_run (bool, optional): If True, only return query content, do not run it. Defaults to False.

        Returns:
            dict: Dictionary keyed by device name with interface details:

                ```
                nf#netbox get interfaces devices fceos4 interface-regex "eth9.*"
                {
                    "netbox-worker-1.2": {
                        "fceos4": {
                            "eth9": {
                                "bridge": null,
                                "bridge_interfaces": [],
                                "child_interfaces": [],
                                "custom_fields": {},
                                "description": "Interface 9 description",
                                "duplex": null,
                                "enabled": true,
                                "id": "495",
                                "label": "",
                                "last_updated": "2026-01-02T22:49:34.905510+00:00",
                                "mac_addresses": [],
                                "mark_connected": false,
                                "member_interfaces": [],
                                "mode": "tagged",
                                "mtu": 1500,
                                "parent": null,
                                "speed": null,
                                "tagged_vlans": [],
                                "tags": [],
                                "untagged_vlan": null,
                                "vrf": null,
                                "wwn": null
                            }
                        }
                    }
                }
                nf#
                ```
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:get_interfaces",
            result={d: {} for d in devices},
            resources=[instance],
        )

        intf_fields = [
            "name",
            "enabled",
            "description",
            "mtu",
            "parent {name}",
            "mode",
            "untagged_vlan {vid name}",
            "vrf {name}",
            "tagged_vlans {vid name}",
            "tags {name}",
            "custom_fields",
            "last_updated",
            "bridge {name}",
            "bridge_interfaces {name}",
            "member_interfaces {name}",
            "wwn",
            "duplex",
            "speed",
            "id",
            "device {name}",
            "label",
            "mark_connected",
        ]
        intf_fields.append("mac_addresses {mac_address}")

        # add IP addresses to interfaces fields
        if ip_addresses:
            intf_fields.append(
                "ip_addresses {address status role dns_name description custom_fields last_updated tenant {name} tags {name}}"
            )
            intf_fields.append(
                "child_interfaces {name vrf {name} ip_addresses {address status role dns_name description custom_fields last_updated tenant {name} tags {name}}}"
            )
        else:
            intf_fields.append("child_interfaces {name vrf {name}}")

        # form interfaces query dictionary
        dlist = str(devices).replace("'", '"')  # swap quotes
        if self.nb_version[instance] >= (4, 4, 0):
            # add interface name regex filter
            if interface_regex:
                filters = (
                    "{device: {name: {in_list: "
                    + dlist
                    + "}}"
                    + ", name: {i_regex: "
                    + f'"{interface_regex}"'
                    + "}}"
                )
            elif interface_list:
                ilist = str(interface_list).replace("'", '"')  # swap quotes
                filters = (
                    "{device: {name: {in_list: "
                    + dlist
                    + "}}"
                    + ", name: {in_list: "
                    + ilist
                    + "}}"
                )
            else:
                filters = "{device: {name: {in_list: " + dlist + "}}}"
        else:
            raise UnsupportedNetboxVersion(
                f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                f"minimum required version is {self.compatible_ge_v4}"
            )

        queries = {
            "interfaces": {
                "obj": "interface_list",
                "filters": filters,
                "fields": intf_fields,
            }
        }

        # add query to retrieve inventory items
        if inventory_items:
            if self.nb_version[instance] >= (4, 4, 0):
                dlist = str(devices).replace("'", '"')  # swap quotes
                inv_filters = (
                    "{device: {name: {in_list: "
                    + dlist
                    + '}}, component_type: {app_label: {exact: "dcim"}}}'
                )
            else:
                raise UnsupportedNetboxVersion(
                    f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                    f"minimum required version is {self.compatible_ge_v4}"
                )
            inv_fields = [
                "name",
                "component {... on InterfaceType {id}}",
                "role {name}",
                "manufacturer {name}",
                "custom_fields",
                "label",
                "description",
                "tags {name}",
                "asset_tag",
                "serial",
                "part_id",
            ]
            queries["inventor_items"] = {
                "obj": "inventory_item_list",
                "filters": inv_filters,
                "fields": inv_fields,
            }

        query_result = self.graphql(
            job=job, instance=instance, queries=queries, dry_run=dry_run
        )

        # return dry run result
        if dry_run:
            return query_result

        interfaces_data = query_result.result

        # exit if no Interfaces returned
        if interfaces_data is None or not interfaces_data.get("interfaces"):
            raise Exception(
                f"{self.name} - no interfaces data in '{interfaces_data}' returned by '{instance}' "
                f"for devices {', '.join(devices)}"
            )

        # process query results
        interfaces_list = interfaces_data.pop("interfaces")

        # process inventory items
        if inventory_items:
            inventory_items_list = interfaces_data.pop("inventor_items")
            # transform inventory items list to a dictionary keyed by intf_id
            inventory_items_dict = {}
            while inventory_items_list:
                inv_item = inventory_items_list.pop()
                # skip inventory items that does not assigned to components
                if inv_item.get("component") is None:
                    continue
                intf_id = str(inv_item.pop("component").pop("id"))
                inventory_items_dict.setdefault(intf_id, [])
                inventory_items_dict[intf_id].append(inv_item)
            # iterate over interfaces and add inventory items
            for intf in interfaces_list:
                intf["inventory_items"] = inventory_items_dict.pop(intf["id"], [])

        # transform interfaces list to dictionary keyed by device and interfaces names
        while interfaces_list:
            intf = interfaces_list.pop()
            device_name = intf.pop("device").pop("name")
            intf_name = intf.pop("name")
            if device_name in ret.result:  # Netbox issue #16299
                ret.result[device_name][intf_name] = intf

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
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
        cache: Union[bool, str] = None,
        branch: str = None,
    ) -> Result:
        """
        Retrieve device interfaces from Netbox using pynetbox REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve interfaces for.
            interface_list (list, optional): List of interface names to retrieve.
            interface_regex (str, optional): Regex pattern to match interfaces by name.
            ip_addresses (bool, optional): If True, retrieves interface IPs. Defaults to False.
            inventory_items (bool, optional): If True, retrieves interface inventory items. Defaults to False.
            dry_run (bool, optional): If True, only return REST filter params, do not run. Defaults to False.

        Returns:
            dict: Dictionary keyed by device name with interface details.
        """
        instance = instance or self.default_instance
        nb = self._get_pynetbox(instance, branch=branch)
        devices = devices or []
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

        # build REST filter params
        if devices:
            filter_params["device__in"] = devices
        if interface_list:
            filter_params["name"] = interface_list
        if interface_regex:
            filter_params["name__regex"] = interface_regex

        if dry_run:
            ret.result = {"filter_params": filter_params}
            return ret

        # fetch all matching interfaces in one call
        all_interfaces = list(nb.dcim.interfaces.filter(**filter_params))

        if not all_interfaces:
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
        if ip_addresses:
            for ip in nb.ipam.ip_addresses.filter(device__in=devices):
                if (
                    ip.assigned_object_id
                    and ip.assigned_object_type == "dcim.interface"
                ):
                    ip_by_intf_id.setdefault(ip.assigned_object_id, []).append(dict(ip))

        # fetch inventory items if requested (one bulk call keyed by component_id)
        if inventory_items:
            for item in nb.dcim.inventory_items.filter(device__in=devices):
                if item.component_id and item.component_type == "dcim.interface":
                    inv_by_intf_id.setdefault(item.component_id, []).append(dict(item))

        # transform pynetbox records into result dict keyed by device / interface name
        for intf in all_interfaces:
            device_name = intf.device.name if intf.device else None
            if device_name not in ret.result:  # Netbox issue #16299
                continue

            children = children_by_parent_id.get(intf.id, [])

            if ip_addresses:
                child_interfaces = [
                    {
                        "name": c.name,
                        "vrf": {"name": c.vrf.name} if c.vrf else None,
                        "ip_addresses": ip_by_intf_id.get(c.id, []),
                    }
                    for c in children
                ]
                intf_ip_addresses = ip_by_intf_id.get(intf.id, [])
            else:
                child_interfaces = [
                    {
                        "name": c.name,
                        "vrf": {"name": c.vrf.name} if c.vrf else None,
                    }
                    for c in children
                ]
                intf_ip_addresses = []

            intf_data = dict(intf)
            # normalize fields to match get_interfaces (GraphQL) output format
            intf_data["id"] = str(intf.id)
            intf_data["mode"] = intf.mode.value if intf.mode else None
            intf_data["duplex"] = intf.duplex.value if intf.duplex else None
            intf_data["child_interfaces"] = child_interfaces
            intf_data["member_interfaces"] = [
                {"name": m.name} for m in member_intf_by_lag_id.get(intf.id, [])
            ]
            if ip_addresses:
                intf_data["ip_addresses"] = intf_ip_addresses
            if inventory_items:
                intf_data["inventory_items"] = inv_by_intf_id.get(intf.id, [])

            ret.result[device_name][intf.name] = intf_data

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def create_device_interfaces(
        self,
        job: Job,
        devices: list,
        interface_name: Union[list, str],
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

        # Normalize interface_name to a list
        if isinstance(interface_name, str):
            interface_names = [interface_name]
        else:
            interface_names = interface_name

        # Expand all interface name patterns
        all_interface_names = []
        for name_pattern in interface_names:
            all_interface_names.extend(self.expand_alphanumeric_range(name_pattern))

        job.event(
            f"Expanded interface names to {len(all_interface_names)} interface(s)"
        )

        # Process each device
        for device_name in devices:
            result[device_name] = {
                "created": [],
                "skipped": [],
            }

            try:
                # Get device from NetBox
                nb_device = nb.dcim.devices.get(name=device_name)
                if not nb_device:
                    msg = f"Device '{device_name}' not found in NetBox"
                    ret.errors.append(msg)
                    job.event(msg)
                    continue

                # Get existing interfaces for this device
                existing_interfaces = nb.dcim.interfaces.filter(device=device_name)
                existing_interface_names = {intf.name for intf in existing_interfaces}

                # Prepare interfaces to create
                interfaces_to_create = []

                for intf_name in all_interface_names:
                    if intf_name in existing_interface_names:
                        result[device_name]["skipped"].append(intf_name)
                        continue

                    # Build interface data
                    intf_data = {
                        "device": nb_device.id,
                        "name": intf_name,
                        "type": interface_type,
                        **kwargs,
                    }

                    interfaces_to_create.append(intf_data)
                    result[device_name]["created"].append(intf_name)

                # Create interfaces in bulk if not dry_run
                if interfaces_to_create and not dry_run:
                    try:
                        nb.dcim.interfaces.create(interfaces_to_create)
                        msg = f"Created {len(interfaces_to_create)} interface(s) on device '{device_name}'"
                        job.event(msg)
                    except Exception as e:
                        msg = f"Failed to create interfaces on device '{device_name}': {e}"
                        ret.errors.append(msg)
                        log.error(msg)
                elif interfaces_to_create and dry_run:
                    msg = f"[DRY RUN] Would create {len(interfaces_to_create)} interface(s) on device '{device_name}'"
                    job.event(msg)

            except Exception as e:
                msg = f"Error processing device '{device_name}': {e}"
                ret.errors.append(msg)
                log.error(msg)

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
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

        if description_template:
            # get list of all interfaces connections
            nb_connections = self.get_connections(
                job=job,
                devices=devices,
                interface_regex=interface_regex,
                instance=instance,
                include_virtual=True,
                cables=True,
            )
            # produce interfaces description and update it
            while nb_connections.result:
                device, device_connections = nb_connections.result.popitem()
                ret.result.setdefault(device, {})
                for interface, connection in device_connections.items():
                    job.event(f"{device}:{interface} updating description")
                    if connection["termination_type"] == "consoleport":
                        nb_interface = nb.dcim.console_ports.get(
                            device=device, name=interface
                        )
                    elif connection["termination_type"] == "consoleserverport":
                        nb_interface = nb.dcim.console_server_ports.get(
                            device=device, name=interface
                        )
                    elif connection["termination_type"] == "powerport":
                        nb_interface = nb.dcim.power_ports.get(
                            device=device, name=interface
                        )
                    elif connection["termination_type"] == "poweroutlet":
                        nb_interface = nb.dcim.power_outlets.get(
                            device=device, name=interface
                        )
                    else:
                        nb_interface = nb.dcim.interfaces.get(
                            device=device, name=interface
                        )
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
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def sync_device_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: Union[None, list] = None,
        create: bool = True,
        batch_size: int = 10,
        branch: str = None,
        **kwargs: Any,
    ) -> Result:
        """
        Update or create device interfaces in Netbox using devices interfaces
        data sourced via Nornir service `parse` task using NAPALM getter.

        Interface parameters updated:

        - interface name
        - interface description
        - mtu
        - mac address
        - admin status
        - speed

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): The Netbox instance name to use.
            dry_run (bool, optional): If True, no changes will be made to Netbox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces getter

            timeout (int, optional): The timeout for the job.
            devices (list, optional): List of devices to update.
            create (bool, optional): If True, new interfaces will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments to pass to the datasource job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
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
        kwargs["add_details"] = True

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
                devices = list(set(devices))
                job.event(f"syncing {len(devices)} devices")

            # fetch devices interfaces data from Netbox
            nb_interfaces_data = self.get_interfaces(
                job=job,
                instance=instance,
                devices=copy.copy(devices),
                cache="refresh",
            ).result

            # fetch devices data from Netbox
            nb_devices_data = self.get_devices(
                job=job,
                instance=instance,
                devices=copy.copy(devices),
            ).result

            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces"
                job.event(
                    f"retrieving interfaces for devices {', '.join(kwargs['FL'])}"
                )
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )

                # Collect interfaces to update and create in bulk
                interfaces_to_update = []
                interfaces_to_create = []
                mac_addresses_to_create = []

                for worker, results in data.items():
                    if results["failed"]:
                        msg = f"{worker} get_interfaces failed, errors: {'; '.join(results['errors'])}"
                        ret.errors.append(msg)
                        log.error(msg)
                        continue

                    for host, host_data in results["result"].items():
                        if host_data["napalm_get"]["failed"]:
                            msg = f"{host} interfaces update failed: '{host_data['napalm_get']['exception']}'"
                            ret.errors.append(msg)
                            log.error(msg)
                            continue

                        nb_interfaces = nb_interfaces_data.get(host, {})
                        if not nb_interfaces:
                            msg = f"'{host}' has no interfaces in Netbox, skipping"
                            ret.errors.append(msg)
                            log.warning(msg)
                            continue

                        # Get device ID for creating new interfaces
                        nb_device = nb_devices_data.get(host)
                        if not nb_device:
                            msg = f"'{host}' does not exist in Netbox"
                            ret.errors.append(msg)
                            log.error(msg)
                            continue

                        interfaces = host_data["napalm_get"]["result"]["get_interfaces"]

                        sync_key = "sync_device_interfaces"
                        create_key = "created_device_interfaces"
                        if dry_run:
                            sync_key = "sync_device_interfaces_dry_run"
                            create_key = "created_device_interfaces_dry_run"
                        ret.result[host] = {
                            sync_key: {},
                            create_key: {},
                        }
                        if branch is not None:
                            ret.result[host]["branch"] = branch

                        # Process network device interfaces
                        for intf_name, interface_data in interfaces.items():
                            if intf_name in nb_interfaces:
                                # Interface exists - prepare update
                                nb_intf = nb_interfaces[intf_name]

                                # Build desired state
                                desired_state = {
                                    "description": interface_data.get(
                                        "description", ""
                                    ),
                                    "enabled": interface_data.get("is_enabled", True),
                                }
                                if 10000 > interface_data.get("mtu", 0) > 0:
                                    desired_state["mtu"] = interface_data["mtu"]
                                if interface_data.get("speed", 0) > 0:
                                    desired_state["speed"] = (
                                        interface_data["speed"] * 1000
                                    )

                                # Build current state
                                current_state = {
                                    "description": nb_intf.get("description", ""),
                                    "enabled": nb_intf.get("enabled", True),
                                }
                                if nb_intf.get("mtu"):
                                    current_state["mtu"] = nb_intf["mtu"]
                                if nb_intf.get("speed"):
                                    current_state["speed"] = nb_intf["speed"]

                                # Compare and get fields that need updating
                                updates, diff = self.compare_netbox_object_state(
                                    desired_state=desired_state,
                                    current_state=current_state,
                                )

                                # Only update if there are changes
                                if updates:
                                    updates["id"] = int(nb_intf["id"])
                                    interfaces_to_update.append(updates)
                                    ret.diff.setdefault(host, {})[intf_name] = diff

                                ret.result[host][sync_key][intf_name] = (
                                    updates if updates else "Interface in sync"
                                )

                                mac_address = (
                                    interface_data.get("mac_address", "")
                                    .strip()
                                    .lower()
                                )
                                if mac_address and mac_address not in ["none", ""]:
                                    # Check if MAC already exists
                                    for nb_mac in nb_intf.get("mac_addresses") or []:
                                        if (
                                            nb_mac.get("mac_address", "").lower()
                                            == mac_address
                                        ):
                                            break
                                    else:
                                        # Prepare MAC address for creation
                                        mac_addresses_to_create.append(
                                            {
                                                "mac_address": mac_address,
                                                "assigned_object_type": "dcim.interface",
                                                "assigned_object_id": int(
                                                    nb_intf["id"]
                                                ),
                                            }
                                        )
                            elif create:
                                # Interface doesn't exist - prepare creation
                                new_intf = {
                                    "name": intf_name,
                                    "device": int(nb_device["id"]),
                                    "type": "other",
                                    "description": interface_data.get(
                                        "description", ""
                                    ),
                                    "enabled": interface_data.get("is_enabled", True),
                                }
                                if 10000 > interface_data.get("mtu", 0) > 0:
                                    new_intf["mtu"] = interface_data["mtu"]
                                if interface_data.get("speed", 0) > 0:
                                    new_intf["speed"] = interface_data["speed"] * 1000

                                mac_address = (
                                    interface_data.get("mac_address", "")
                                    .strip()
                                    .lower()
                                )
                                if mac_address and mac_address not in ["none", ""]:
                                    mac_addresses_to_create.append(
                                        {
                                            "mac_address": mac_address,
                                            "assigned_object_type": "dcim.interface",
                                            "assigned_object_id": int(nb_intf["id"]),
                                        }
                                    )

                                interfaces_to_create.append(new_intf)
                                ret.result[host][create_key][intf_name] = new_intf

                # Perform bulk updates and creations
                if interfaces_to_update and not dry_run:
                    try:
                        nb.dcim.interfaces.update(interfaces_to_update)
                        job.event(
                            f"Bulk updated {len(interfaces_to_update)} interfaces"
                        )
                    except Exception as e:
                        msg = f"Bulk interface update failed: {e}"
                        ret.errors.append(msg)
                        log.error(msg)

                if interfaces_to_create and not dry_run:
                    try:
                        _ = nb.dcim.interfaces.create(interfaces_to_create)
                        job.event(
                            f"Bulk created {len(interfaces_to_create)} interfaces"
                        )
                    except Exception as e:
                        msg = f"Bulk interface creation failed: {e}"
                        ret.errors.append(msg)
                        log.error(msg)

                # Bulk create MAC addresses
                if mac_addresses_to_create and not dry_run:
                    try:
                        nb.dcim.mac_addresses.create(mac_addresses_to_create)
                        job.event(
                            f"Bulk created {len(mac_addresses_to_create)} MAC addresses"
                        )
                    except Exception as e:
                        msg = f"Bulk MAC address creation failed: {e}"
                        ret.errors.append(msg)
                        log.error(msg)

        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret
