import ipaddress
import logging
from typing import Any, Union

from norfab.core.exceptions import UnsupportedServiceError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_exceptions import NetboxAllocationError
from .netbox_models import NetboxFastApiArgs

log = logging.getLogger(__name__)

def resolve_ip_role(ip: str, intf_name: str, anycast_ranges: Union[None, str, list]):
    if anycast_ranges and isinstance(anycast_ranges, str):
        anycast_ranges = [anycast_ranges]

    # check if IP is part of anycast ranges
    if anycast_ranges:
        ip_addr = ipaddress.ip_interface(str(ip)).ip
        anycast_nets = []
        for pfx in anycast_ranges:
            # strict=False allows host/mask entries such as 192.0.2.1/24.
            anycast_nets.append(ipaddress.ip_network(str(pfx), strict=False))
        if any(ip_addr in net for net in anycast_nets):
            return "anycast"

    # check if interface is a loopback
    if any(intf_name.lower().startswith(k) for k in ["loopback", "lo"]):
        return "loopback"

    return None

def make_prefix_from_ip(address: Union[None, str]) -> Union[None, str]:
    try:
        return str(ipaddress.ip_interface(str(address)).network)
    except Exception:
        return None
        
class NetboxIpTasks:

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def create_ip(
        self,
        job: Job,
        prefix: Union[str, dict],
        device: Union[None, str] = None,
        interface: Union[None, str] = None,
        description: Union[None, str] = None,
        vrf: Union[None, str] = None,
        tags: Union[None, list] = None,
        dns_name: Union[None, str] = None,
        tenant: Union[None, str] = None,
        comments: Union[None, str] = None,
        role: Union[None, str] = None,
        status: Union[None, str] = None,
        is_primary: Union[None, bool] = None,
        instance: Union[None, str] = None,
        dry_run: Union[None, bool] = False,
        branch: Union[None, str] = None,
        mask_len: Union[None, int] = None,
        create_peer_ip: Union[None, bool] = True,
    ) -> Result:
        """
        Allocate the next available IP address from a given subnet.

        This task finds or creates an IP address in NetBox, updates its metadata,
        optionally links it to a device/interface, and supports a dry run mode for
        previewing changes.

        Args:
            prefix (str): The prefix from which to allocate the IP address, could be:

                - IPv4 prefix string e.g. 10.0.0.0/24
                - IPv6 prefix string e.g. 2001::/64
                - Prefix description string to filter by
                - Dictionary with prefix filters to feed `pynetbox` get method
                    e.g. `{"prefix": "10.0.0.0/24", "site": "foo", "role": "bar"}`, 
                    site and role referred to by slugs not by their names.

            description (str, optional): A description for the allocated IP address.
            device (str, optional): The device associated with the IP address.
            interface (str, optional): The interface associated with the IP address.
            vrf (str, optional): The VRF (Virtual Routing and Forwarding) instance.
            tags (list, optional): A list of tags to associate with the IP address.
            dns_name (str, optional): The DNS name for the IP address.
            tenant (str, optional): The tenant associated with the IP address.
            comments (str, optional): Additional comments for the IP address.
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, do not actually allocate the IP address.
            branch (str, optional): Branch name to use, need to have branching plugin
                installed, automatically creates branch if it does not exist in Netbox.
            mask_len (int, optional): mask length to use for IP address on creation or to
                update existing IP address. On new IP address creation will create child
                subnet of `mask_len` within parent `prefix`, new subnet not created for
                existing IP addresses. `mask_len` argument ignored on dry run and ip allocated
                from parent prefix directly.
            create_peer_ip (bool, optional): If True creates IP address for link peer -
                remote device interface connected to requested device and interface

        Returns:
            dict: A dictionary containing the result of the IP allocation.

        Tasks execution follow these steps:

        1. Tries to find an existing IP in NetBox matching the device/interface/description.
            If found, uses it; otherwise, proceeds to create a new IP.

        2. If prefix is a string, determines if it's an IP network or a description.
            Builds a filter dictionary for NetBox queries, optionally including VRF.

        3. Queries NetBox for the prefix using the constructed filter.

        4. If dry_run is True, fetches the next available IP but doesn't create it.

        5. If not a dry run, creates the next available IP in the prefix.

        6. Updates IP attributes (description, VRF, tenant, DNS name, comments, role, tags)
            if provided and different from current values. Handles interface assignment and
            can set the IP as primary for the device.

        7. If changes were made and not a dry run, saves the IP and device updates to NetBox.
        """
        instance = instance or self.default_instance
        log.info(
            f"{self.name} - Create IP: Allocating IP from '{prefix}' for '{device}:{interface}' in '{instance}' Netbox"
        )
        ret = Result(task=f"{self.name}:create_ip", result={}, resources=[instance])
        tags = tags or []
        has_changes = False
        nb_ip = None
        nb_device = None
        create_peer_ip_data = {}
        nb = self._get_pynetbox(instance, branch=branch)

        # source parent prefix from Netbox
        if isinstance(prefix, str):
            # try converting prefix to network, if fails prefix is not an IP network
            try:
                _ = ipaddress.ip_network(prefix)
                is_network = True
            except Exception:
                is_network = False
            if is_network is True and vrf:
                prefix = {"prefix": prefix, "vrf__name": vrf}
            elif is_network is True:
                prefix = {"prefix": prefix}
            elif is_network is False and vrf:
                prefix = {"description": prefix, "vrf__name": vrf}
            elif is_network is False:
                prefix = {"description": prefix}
        nb_prefix = nb.ipam.prefixes.get(**prefix)
        if not nb_prefix:
            raise NetboxAllocationError(
                f"Unable to source parent prefix from Netbox - {prefix}"
            )
        parent_prefix_len = int(str(nb_prefix).split("/")[1])

        # try to source existing IP from netbox
        if device and interface and description:
            nb_ip = nb.ipam.ip_addresses.get(
                device=device,
                interface=interface,
                description=description,
                parent=str(nb_prefix),
            )
        elif device and interface:
            nb_ip = nb.ipam.ip_addresses.get(
                device=device, interface=interface, parent=str(nb_prefix)
            )
        elif description:
            nb_ip = nb.ipam.ip_addresses.get(
                description=description, parent=str(nb_prefix)
            )

        # create new IP address
        if not nb_ip:
            # check if interface has link peer that has IP within parent prefix
            if device and interface:
                connection = self.get_connections(
                    job=job,
                    devices=[device],
                    interface_regex=interface,
                    instance=instance,
                )
                if interface in connection.result[device]:
                    peer = connection.result[device][interface]
                    # do not process breakout cables
                    if isinstance(peer["remote_interface"], list):
                        peer["remote_interface"] = None
                    # try to source peer ip subnet
                    nb_peer_ip = None
                    if peer["remote_device"] and peer["remote_interface"]:
                        nb_peer_ip = nb.ipam.ip_addresses.get(
                            device=peer["remote_device"],
                            interface=peer["remote_interface"],
                            parent=str(nb_prefix),
                        )
                    # try to source peer ip subnet
                    nb_peer_prefix = None
                    if nb_peer_ip:
                        peer_ip = ipaddress.ip_interface(nb_peer_ip.address)
                        nb_peer_prefix = nb.ipam.prefixes.get(
                            prefix=str(peer_ip.network),
                            vrf__name=vrf,
                        )
                    elif create_peer_ip and peer["remote_interface"]:
                        create_peer_ip_data = {
                            "device": peer["remote_device"],
                            "interface": peer["remote_interface"],
                            "vrf": vrf,
                            "branch": branch,
                            "tenant": tenant,
                            "dry_run": dry_run,
                            "tags": tags,
                            "status": status,
                            "create_peer_ip": False,
                            "instance": instance,
                        }
                    # use peer subnet to create IP address
                    if nb_peer_prefix:
                        nb_prefix = nb_peer_prefix
                        mask_len = None  # cancel subnet creation
                        job.event(
                            f"using link peer '{peer['remote_device']}:{peer['remote_interface']}' "
                            f"prefix '{nb_peer_prefix}' to create IP address"
                        )
            # if mask_len provided create new subnet
            if mask_len and not dry_run and mask_len != parent_prefix_len:
                if mask_len < parent_prefix_len:
                    raise ValueError(
                        f"Mask length '{mask_len}' must be longer then '{parent_prefix_len}' prefix length"
                    )
                prefix_status = status
                if prefix_status not in ["active", "reserved", "deprecated"]:
                    prefix_status = None
                child_subnet = self.create_prefix(
                    job=job,
                    parent=str(nb_prefix),
                    prefixlen=mask_len,
                    vrf=vrf,
                    tags=tags,
                    tenant=tenant,
                    status=prefix_status,
                    instance=instance,
                    branch=branch,
                )
                prefix = {"prefix": child_subnet.result["prefix"]}
                if vrf:
                    prefix["vrf__name"] = vrf
                nb_prefix = nb.ipam.prefixes.get(**prefix)

                if not nb_prefix:
                    raise NetboxAllocationError(
                        f"Unable to source child prefix of mask length "
                        f"'{mask_len}' from '{prefix}' parent prefix"
                    )
            # execute dry run on new IP
            if dry_run is True:
                nb_ip = nb_prefix.available_ips.list()[0]
                ret.status = "unchanged"
                ret.dry_run = True
                ret.result = {
                    "address": str(nb_ip),
                    "description": description,
                    "vrf": vrf,
                    "device": device,
                    "interface": interface,
                }
                # add branch to results
                if branch is not None:
                    ret.result["branch"] = branch
                return ret
            # create new IP
            else:
                nb_ip = nb_prefix.available_ips.create()
                job.event(
                    f"created '{nb_ip}' IP address for '{device}:{interface}' within '{nb_prefix}' prefix"
                )
            ret.status = "created"
        else:
            job.event(f"using existing IP address {nb_ip}")
            ret.status = "updated"

        # update IP address parameters
        if description and description != nb_ip.description:
            nb_ip.description = description
            has_changes = True
        if vrf and vrf != nb_ip.vrf:
            nb_ip.vrf = {"name": vrf}
            has_changes = True
        if tenant and tenant != nb_ip.tenant:
            nb_ip.tenant = {"name": tenant}
            has_changes = True
        if dns_name and dns_name != nb_ip.dns_name:
            nb_ip.dns_name = dns_name
            has_changes = True
        if comments and comments != nb_ip.comments:
            nb_ip.comments = comments
            has_changes = True
        if role and role != nb_ip.role:
            nb_ip.role = role
            has_changes = True
        if tags and not any(t in nb_ip.tags for t in tags):
            for t in tags:
                if t not in nb_ip.tags:
                    nb_ip.tags.append({"name": t})
                    has_changes = True
        if device and interface:
            nb_interface = nb.dcim.interfaces.get(device=device, name=interface)
            if not nb_interface:
                raise NetboxAllocationError(
                    f"Unable to source '{device}:{interface}' interface from Netbox"
                )
            if (
                hasattr(nb_ip, "assigned_object")
                and nb_ip.assigned_object != nb_interface.id
            ):
                nb_ip.assigned_object_id = nb_interface.id
                nb_ip.assigned_object_type = "dcim.interface"
                if is_primary is not None:
                    nb_device = nb.dcim.devices.get(name=device)
                    nb_device.primary_ip4 = nb_ip.id
                has_changes = True
        if mask_len and not str(nb_ip).endswith(f"/{mask_len}"):
            address = str(nb_ip).split("/")[0]
            nb_ip.address = f"{address}/{mask_len}"
            has_changes = True

        # save IP address into Netbox
        if dry_run:
            ret.status = "unchanged"
            ret.dry_run = True
        elif has_changes:
            nb_ip.save()
            job.event(f"updated '{str(nb_ip)}' IP address parameters")
            # make IP primary for device
            if is_primary is True and nb_device:
                nb_device.save()
        else:
            ret.status = "unchanged"

        # form and return results
        ret.result = {
            "address": str(nb_ip),
            "description": str(nb_ip.description),
            "vrf": str(nb_ip.vrf) if not vrf else nb_ip.vrf["name"],
            "device": device,
            "interface": interface,
        }
        # add branch to results
        if branch is not None:
            ret.result["branch"] = branch

        # create IP address for peer
        if create_peer_ip and create_peer_ip_data:
            job.event(
                f"creating IP address for link peer '{create_peer_ip_data['device']}:{create_peer_ip_data['interface']}'"
            )
            peer_ip = self.create_ip(
                **create_peer_ip_data, prefix=str(nb_prefix), job=job
            )
            if peer_ip.failed == False:
                ret.result["peer"] = peer_ip.result

        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def create_ip_bulk(
        self,
        job: Job,
        prefix: Union[str, dict],
        devices: list[str] = None,
        interface_list: list[str] = None,
        interface_regex: str = None,
        instance: Union[None, str] = None,
        **kwargs: object,
    ) -> Result:
        """
        Bulk assigns IP addresses to interfaces of specified devices.

        Args:
            job (Job): The job instance used for logging and tracking the task.
            prefix (Union[str, dict]): The IP prefix or a dictionary containing prefix details.
            devices (list[str], optional): A list of device names to process. Defaults to None.
            interface_list (list[str], optional): A list of specific interfaces to target. Defaults to None.
            interface_regex (str, optional): A regex pattern to match interfaces. Defaults to None.
            instance (Union[None, str], optional): The instance name to use. Defaults to None.
            kwargs (dict, optional): Additional arguments to pass to the `create_ip` method calls.

        Returns:
            Result: A Result object containing the task details, results, and resources.

        Notes:
            - If both `interface_list` and `interface_regex` are provided, `interface_list` takes precedence.
            - The `prefix` parameter can be a string representing the prefix or a dictionary with additional details.
        """
        instance = instance or self.default_instance
        log.info(
            f"{self.name} - Create IP bulk: Assigning IPs for {len(devices or [])} device(s) from '{instance}' Netbox"
        )
        ret = Result(
            task=f"{self.name}:create_ip_bulk", result={}, resources=[instance]
        )

        # get list of all interfaces
        interfaces = self.get_interfaces(
            job=job,
            devices=devices,
            interface_list=interface_list,
            interface_regex=interface_regex,
            instance=instance,
        )

        # iterate over interfaces and assign IP addresses
        for device, device_interfaces in interfaces.result.items():
            ret.result[device] = {}
            for interface in sorted(device_interfaces.keys()):
                create_ip = self.create_ip(
                    job=job,
                    device=device,
                    interface=interface,
                    instance=instance,
                    prefix=prefix,
                    **kwargs,
                )
                ret.result[device][interface] = create_ip.result

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def sync_device_ip_old(
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
        Update the IP addresses of devices in Netbox.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): The Netbox instance name to use.
            dry_run (bool, optional): If True, no changes will be made.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces_ip getter

            timeout (int, optional): The timeout for the operation.
            devices (list, optional): The list of devices to update.
            create (bool, optional): If True, new IP addresses will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_device_ip", result=result, resources=[instance]
        )
        nb = self._get_pynetbox(instance, branch=branch)
        log.info(
            f"{self.name} - Sync device IP: Syncing IP addresses for {len(devices)} device(s) from '{instance}' Netbox"
        )

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces_ip"
                data = self.client.run_job(
                    "nornir",
                    "parse_napalm",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} Get interfaces IP failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        updated, created = {}, {}
                        result[host] = {
                            "sync_ip_dry_run" if dry_run else "sync_ip": updated,
                            "created_ip_dry_run" if dry_run else "created_ip": created,
                        }
                        if branch is not None:
                            result[host]["branch"] = branch
                        interfaces = host_data["napalm_get"]["get_interfaces_ip"]
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        nb_interfaces = nb.dcim.interfaces.filter(
                            device_id=nb_device.id
                        )
                        # update interface IP addresses
                        for nb_interface in nb_interfaces:
                            if nb_interface.name not in interfaces:
                                continue
                            interface = interfaces.pop(nb_interface.name)
                            # merge v6 into v4 addresses to save code repetition
                            ips = {
                                **interface.get("ipv4", {}),
                                **interface.get("ipv6", {}),
                            }
                            # update/create IP addresses
                            for ip, ip_data in ips.items():
                                prefix_length = ip_data["prefix_length"]
                                # get IP address info from Netbox
                                nb_ip = nb.ipam.ip_addresses.filter(
                                    address=f"{ip}/{prefix_length}"
                                )
                                if len(nb_ip) > 1:
                                    log.warning(
                                        f"{host} Got multiple {ip}/{prefix_length} IP addresses from Netbox, "
                                        f"NorFab Netbox Service only supports handling of non-duplicate IPs."
                                    )
                                    continue
                                # decide what to do
                                if not nb_ip and create is False:
                                    continue
                                elif not nb_ip and create is True:
                                    if dry_run is not True:
                                        try:
                                            nb_ip = nb.ipam.ip_addresses.create(
                                                address=f"{ip}/{prefix_length}"
                                            )
                                        except Exception as e:
                                            msg = f"{host} failed to create {ip}/{prefix_length}, error: {e}"
                                            log.error(msg)
                                            job.event(msg, resource=instance)
                                            continue
                                        nb_ip.assigned_object_type = "dcim.interface"
                                        nb_ip.assigned_object_id = nb_interface.id
                                        nb_ip.status = "active"
                                        nb_ip.save()
                                    created[f"{ip}/{prefix_length}"] = nb_interface.name
                                    job.event(
                                        f"{host} created IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )
                                elif nb_ip:
                                    nb_ip = list(nb_ip)[0]
                                    if dry_run is not True:
                                        nb_ip.assigned_object_type = "dcim.interface"
                                        nb_ip.assigned_object_id = nb_interface.id
                                        nb_ip.status = "active"
                                        nb_ip.save()
                                    updated[nb_ip.address] = nb_interface.name
                                    job.event(
                                        f"{host} updated IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )

        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret


    def sync_device_ip(self):
        device_results = {
            device_name: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for device_name, actions in full_diff.items()
        }

        # process IP and Prefixes
        bulk_update_ip = {} # {(device, intf, ip): {ip data}}
        bulk_create_ip = {} # {(device, intf, ip): {ip data}}
        bulk_create_prefixes = []
        bulk_update_prefixes = []
        # collect all discovered IP addresses and prefixes
        all_ip_live = [] 
        all_prefixes_live = []
        for device_name, interfaces in normalised_live_all.items():
            nb_device = nb_devices_data[device_name]
            nb_raw = nb_interfaces_result.result[device_name]
            for intf_name, intf_data in interfaces.items():
                for ip in (intf_data.get("ipv4_addresses") or []) + (intf_data.get("ipv6_addresses") or []):
                    description = f"{device_name} {intf_name}"
                    vrf = resolve_vrf(intf_data["vrf"], nb, job, ret, self.name)
                    if vrf:
                        description += f", VRF {vrf}"
                    all_ip_live.append(
                        {
                            "device": device_name,
                            "interface": intf_name,
                            "address": ip,
                            "vrf": vrf,
                            "role": resolve_ip_role(ip, intf_name, anycast_ranges),
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id": nb_raw[intf_name]["id"],
                            # "description": description
                        }
                    )
                    all_prefixes_live.append(
                        {
                            "prefix": make_prefix_from_ip(ip),
                            "vrf": vrf,
                            "site": nb_device["site_id"],
                        }
                    )
        # fetch existing IP addresses and prefixes from Netbox
        nb_ips = [
            {
                "id": ip.id,
                "address": ip.address,
                "vrf": ip.vrf.id if ip.vrf else None,
                "role": str(ip.role).lower(),
                "assigned_object_id": ip.assigned_object.id if ip.assigned_object else None,
                "device": ip.assigned_object.device.name if ip.assigned_object else None,
                "interface": ip.assigned_object.name if ip.assigned_object else None,
            }
            for ip in nb.ipam.ip_addresses.filter(
                address=[i["address"] for i in all_ip_live], 
                fields="id,address,vrf,role,assigned_object"
            )
        ]
        nb_prefixes = [
            {
                "id": pfx.id,
                "prefix": pfx.prefix,
                "vrf": pfx.vrf.id if pfx.vrf else None,
                "scope_type": pfx.scope_type,
                "scope_id": pfx.scope_id,
            }
            for pfx in nb.ipam.prefixes.filter(
                prefix=[p["prefix"] for p in all_prefixes_live], 
                fields="id,prefix,vrf,scope_id,scope_type"
            )
        ]
        # process IP addresses
        for ip_live in all_ip_live:
            device_name = ip_live.pop("device")
            intf_name = ip_live.pop("interface")
            key = (device_name, intf_name, ip_live["address"])
            # find existing Netbox IPs of same value
            matching_nb_ips = [i for i in nb_ips if i["address"] == ip_live["address"]]
            # no existing IP found, create it
            if not matching_nb_ips:
                bulk_create_ip[key] = ip_live
                continue
            # check if existing IP already assigned to same interface
            for nb_ip in matching_nb_ips:
                if nb_ip["assigned_object_id"]:
                    # ip already assigned to same interface, update it
                    if nb_ip["assigned_object_id"] == ip_live["assigned_object_id"]:
                        # check if vrf or role need an update
                        if any(nb_ip[k] != ip_live[k] for k in ["role", "vrf"] if ip_live[k]):
                            ip_live["id"] = nb_ip["id"]
                            bulk_update_ip[key] = ip_live
                        break
            # no IP assigned to same interface
            else:
                for nb_ip in matching_nb_ips:
                    # existing NB IP already assigned to an interface
                    if nb_ip["assigned_object_id"]:
                        nb_ip_resolved_role = resolve_ip_role(nb_ip["address"], nb_ip["interface"], anycast_ranges) or nb_ip["role"]
                        # add existign IP to updates if needed
                        if nb_ip["role"] != nb_ip_resolved_role:
                            nb_ip_key = (nb_ip["device"], nb_ip["interface"], nb_ip['address'])
                            bulk_update_ip[nb_ip_key] = {
                                "id": nb_ip["id"],
                                "role": nb_ip_resolved_role
                            }
                        # create anycast ip if existing and discovered IPs are anycast
                        if nb_ip_resolved_role == ip_live["role"] == "anycast":
                            bulk_create_ip[key] = ip_live
                            break
                        # check if existing ip role did not resolve to anycast
                        if nb_ip_resolved_role != "anycast":
                            msg = (
                                f"Duplicate non anycast ip found, {device_name}:{intf_name}->{ip_live['address']}, "
                                f"overlaps with {nb_ip['device']}:{nb_ip['interface']}->{nb_ip['address']}"
                            )
                            log.error(msg)
                            ret.errors.append(msg)
                            job.event(msg, severity="ERROR")
                            break

                    # ip exists but not assigned to an interface - update it
                    else:
                        ip_live["id"] = nb_ip["id"]
                        bulk_update_ip[key] = ip_live
        # update first, since existing IPs might change role to Anycast
        if bulk_update_ip:
            try:
                nb.ipam.ip_addresses.update(list(bulk_update_ip.values()))
                job.event(f"updated {len(bulk_update_ip)} IP addresses")
                for key in bulk_update_ip:
                    device_name = key[0]
                    ip_address = key[2]
                    # updates might contain existing IPs that changed the role
                    device_results.setdefault(device_name, {"ip_addresses": {"updated": []}})
                    device_results[device_name]["ip_addresses"]["updated"].append(ip_address)
            except Exception as e:
                msg = f"failed to bulk update IP addresses: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
        # create new IPs next
        if bulk_create_ip:
            try:
                nb.ipam.ip_addresses.create(list(bulk_create_ip.values()))
                job.event(f"created {len(bulk_create_ip)} IP addresses")
                for key in bulk_create_ip:
                    device_name = key[0]
                    ip_address = key[2]
                    device_results[device_name]["ip_addresses"]["created"].append(ip_address)
            except Exception as e:
                msg = f"failed to bulk create IP addresses: {e}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
        
        # process prefixes

        return ret
