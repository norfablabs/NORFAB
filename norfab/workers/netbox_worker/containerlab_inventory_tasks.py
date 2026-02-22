import ipaddress
import logging
import re

from typing import Union
from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs
from .netbox_exceptions import UnsupportedNetboxVersion

log = logging.getLogger(__name__)


class NetboxContainerlabInventoryTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_containerlab_inventory(
        self,
        job: Job,
        lab_name: str = None,
        tenant: Union[None, str] = None,
        filters: Union[None, list] = None,
        devices: Union[None, list] = None,
        instance: Union[None, str] = None,
        image: Union[None, str] = None,
        ipv4_subnet: str = "172.100.100.0/24",
        ports: tuple = (12000, 15000),
        ports_map: Union[None, dict] = None,
        cache: Union[bool, str] = False,
    ) -> Result:
        """
        Retrieve and construct Containerlab inventory from NetBox data.

        Containerlab node details must be defined under device configuration
        context `norfab.containerlab` path, for example:

        ```
        {
            "norfab": {
                "containerlab": {
                    "kind": "ceos",
                    "image": "ceos:latest",
                    "mgmt-ipv4": "172.100.100.10/24",
                    "ports": [
                        {10000: 22},
                        {10001: 830}
                    ],

                    ... any other node parameters ...

                    "interfaces_rename": [
                        {
                            "find": "eth",
                            "replace": "Eth",
                            "use_regex": false
                        }
                    ]
                }
            }
        }
        ```

        For complete list of parameters refer to
        [Containerlab nodes definition](https://containerlab.dev/manual/nodes/).

        Special handling given to these parameters:

        - `lab_name` - if not provided uses `tenant` argument value as a lab name
        - `kind` - uses device platform field value by default
        - `image` - uses `image` value if provided, otherwise uses `{kind}:latest`
        - `interfaces_rename` - a list of one or more interface renaming instructions,
            each item must have `find` and `replace` defined, optional `use_regex`
            flag specifies whether to use regex based pattern substitution.

        To retrieve topology data from Netbox at least one of these arguments must be provided
        to identify a set of devices to include into Containerlab topology:

        - `tenant` - topology constructed using all devices and links that belong to this tenant
        - `devices` - creates topology only using devices in the lists
        - `filters` - list of device filters to retrieve from Netbox and add to topology

        If multiple of above arguments provided, resulting lab topology is a sum of all
        devices matched.

        Args:
            job: NorFab Job object containing relevant metadata
            lab_name (str, Mandatory): Name of containerlab to construct inventory for.
            tenant (str, optional): Construct topology using given tenant's devices
            filters (list, optional): List of filters to apply when retrieving devices from NetBox.
            devices (list, optional): List of specific devices to retrieve from NetBox.
            instance (str, optional): NetBox instance to use.
            image (str, optional): Default containerlab image to use,
            ipv4_subnet (str, Optional): Management subnet to use to IP number nodes
                starting with 2nd IP in the subnet, in assumption that 1st IP is a default gateway.
            ports (tuple, Optional): Ports range to use for nodes.
            ports_map (dict, Optional): dictionary keyed by node name with list of ports maps to use,
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: Containerlab inventory dictionary containing lab topology data
        """
        devices = devices or []
        filters = filters or []
        nodes, links = {}, []
        ports_map = ports_map or {}
        endpts_done = []  # to deduplicate links
        instance = instance or self.default_instance
        # handle lab name and tenant name with filters
        if lab_name is None and tenant:
            lab_name = tenant
        # add tenant filters
        if tenant:
            filters = filters or [{}]
            for filter in filters:
                if self.nb_version[instance] >= (4, 4, 0):
                    filter["tenant"] = f'{{name: {{exact: "{tenant}"}}}}'
                else:
                    raise UnsupportedNetboxVersion(
                        f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )

        # construct inventory
        inventory = {
            "name": lab_name,
            "topology": {"nodes": nodes, "links": links},
            "mgmt": {"ipv4-subnet": ipv4_subnet, "network": f"br-{lab_name}"},
        }
        ret = Result(
            task=f"{self.name}:get_containerlab_inventory",
            result=inventory,
            resources=[instance],
        )
        mgmt_net = ipaddress.ip_network(ipv4_subnet)
        available_ips = list(mgmt_net.hosts())[1:]

        # run checks
        if not available_ips:
            raise ValueError(f"Need IPs to allocate, but '{ipv4_subnet}' given")
        if ports:
            available_ports = list(range(ports[0], ports[1]))
        else:
            raise ValueError(f"Need ports to allocate, but '{ports}' given")

        # check Netbox status
        netbox_status = self.get_netbox_status(job=job, instance=instance)
        if netbox_status.result[instance]["status"] is False:
            ret.failed = True
            ret.messages = [f"Netbox status is no good: {netbox_status}"]
            return ret

        # retrieve devices data
        log.debug(
            f"Fetching devices from {instance} Netbox instance, devices '{devices}', filters '{filters}'"
        )
        job.event("Fetching devices data from Netbox")
        nb_devices = self.get_devices(
            job=job,
            filters=filters,
            devices=devices,
            instance=instance,
            cache=cache,
        )

        # form Containerlab nodes inventory
        for device_name, device in nb_devices.result.items():
            node = device["config_context"].get("norfab", {}).get("containerlab", {})
            # populate node parameters
            if not node.get("kind"):
                if device["platform"]:
                    node["kind"] = device["platform"]["name"]
                else:
                    msg = (
                        f"{device_name} - has no 'kind' of 'platform' defined, skipping"
                    )
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    continue
            if not node.get("image"):
                if image:
                    node["image"] = image
                else:
                    node["image"] = f"{node['kind']}:latest"
            if not node.get("mgmt-ipv4"):
                if available_ips:
                    node["mgmt-ipv4"] = f"{available_ips.pop(0)}"
                else:
                    raise RuntimeError("Run out of IP addresses to allocate")
            if not node.get("ports"):
                node["ports"] = []
                # use ports map
                if ports_map.get(device_name):
                    node["ports"] = ports_map[device_name]
                # allocate next-available ports
                else:
                    for port in [
                        "22/tcp",
                        "23/tcp",
                        "80/tcp",
                        "161/udp",
                        "443/tcp",
                        "830/tcp",
                        "8080/tcp",
                    ]:
                        if available_ports:
                            node["ports"].append(f"{available_ports.pop(0)}:{port}")
                        else:
                            raise RuntimeError(
                                "Run out of TCP / UDP ports to allocate."
                            )

            # save node content
            nodes[device_name] = node
            job.event(f"Node added {device_name}")

        # return if no nodes found for provided parameters
        if not nodes:
            msg = f"{self.name} - no devices found in Netbox"
            log.error(msg)
            ret.failed = True
            ret.messages = [
                f"{self.name} - no devices found in Netbox, "
                f"devices - '{devices}', filters - '{filters}'"
            ]
            ret.errors = [msg]
            return ret

        job.event("Fetching connections data from Netbox")

        # query interface connections data from netbox
        nb_connections = self.get_connections(
            job=job, devices=list(nodes), instance=instance, cache=cache
        )
        # save connections data to links inventory
        while nb_connections.result:
            device, device_connections = nb_connections.result.popitem()
            for interface, connection in device_connections.items():
                # skip non ethernet links
                if connection.get("termination_type") != "interface":
                    continue
                # skip orphaned links
                if not connection.get("remote_interface"):
                    continue
                # skip connections to devices that are not part of lab
                if connection["remote_device"] not in nodes:
                    continue
                endpoints = []
                link = {
                    "type": "veth",
                    "endpoints": endpoints,
                }
                # add A node
                endpoints.append(
                    {
                        "node": device,
                        "interface": interface,
                    }
                )
                # add B node
                endpoints.append({"node": connection["remote_device"]})
                if connection.get("breakout") is True:
                    endpoints[-1]["interface"] = connection["remote_interface"][0]
                else:
                    endpoints[-1]["interface"] = connection["remote_interface"]
                # save the link
                a_end = (
                    endpoints[0]["node"],
                    endpoints[0]["interface"],
                )
                b_end = (
                    endpoints[1]["node"],
                    endpoints[1]["interface"],
                )
                if a_end not in endpts_done and b_end not in endpts_done:
                    endpts_done.append(a_end)
                    endpts_done.append(b_end)
                    links.append(link)
                    job.event(
                        f"Link added {endpoints[0]['node']}:{endpoints[0]['interface']}"
                        f" - {endpoints[1]['node']}:{endpoints[1]['interface']}"
                    )

        # query circuits connections data from netbox
        nb_circuits = self.get_circuits(
            job=job, devices=list(nodes), instance=instance, cache=cache
        )
        # save circuits data to hosts' inventory
        while nb_circuits.result:
            device, device_circuits = nb_circuits.result.popitem()
            for cid, circuit in device_circuits.items():
                # skip circuits not connected to devices
                if not circuit.get("remote_interface"):
                    continue
                # skip circuits to devices that are not part of lab
                if circuit["remote_device"] not in nodes:
                    continue
                endpoints = []
                link = {
                    "type": "veth",
                    "endpoints": endpoints,
                }
                # add A node
                endpoints.append(
                    {
                        "node": device,
                        "interface": circuit["interface"],
                    }
                )
                # add B node
                endpoints.append(
                    {
                        "node": circuit["remote_device"],
                        "interface": circuit["remote_interface"],
                    }
                )
                # save the link
                a_end = (
                    endpoints[0]["node"],
                    endpoints[0]["interface"],
                )
                b_end = (
                    endpoints[1]["node"],
                    endpoints[1]["interface"],
                )
                if a_end not in endpts_done and b_end not in endpts_done:
                    endpts_done.append(a_end)
                    endpts_done.append(b_end)
                    links.append(link)
                    job.event(
                        f"Link added {endpoints[0]['node']}:{endpoints[0]['interface']}"
                        f" - {endpoints[1]['node']}:{endpoints[1]['interface']}"
                    )

        # rename links' interfaces
        for node_name, node_data in nodes.items():
            interfaces_rename = node_data.pop("interfaces_rename", [])
            if interfaces_rename:
                job.event(f"Renaming {node_name} interfaces")
            for item in interfaces_rename:
                if not item.get("find") or not item.get("replace"):
                    log.error(
                        f"{self.name} - interface rename need to have"
                        f" 'find' and 'replace' defined, skipping: {item}"
                    )
                    continue
                pattern = item["find"]
                replace = item["replace"]
                use_regex = item.get("use_regex", False)
                # go over links one by one and rename interfaces
                for link in links:
                    for endpoint in link["endpoints"]:
                        if endpoint["node"] != node_name:
                            continue
                        if use_regex:
                            renamed = re.sub(
                                pattern,
                                replace,
                                endpoint["interface"],
                            )
                        else:
                            renamed = endpoint["interface"].replace(pattern, replace)
                        if endpoint["interface"] != renamed:
                            msg = f"{node_name} interface {endpoint['interface']} renamed to {renamed}"
                            log.debug(msg)
                            job.event(msg)
                            endpoint["interface"] = renamed

        return ret
