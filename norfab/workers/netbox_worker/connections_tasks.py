import logging
from typing import Union

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_exceptions import UnsupportedNetboxVersion
from .netbox_models import NetboxFastApiArgs

log = logging.getLogger(__name__)


CONNECTIONS_QUERY = """
query ConnectionsQuery(
    $devices: [String!]!
    $interface_regex: String!
    $offset: Int!
    $limit: Int!
) {
    interface: interface_list(
        filters: {device: {name: {in_list: $devices}}, name: {i_regex: $interface_regex}}
        pagination: { offset: $offset, limit: $limit }
    ) {
        name
        type
        device {name, status}
        member_interfaces {
            name
            connected_endpoints {
                __typename
                ... on ProviderNetworkType {name}
                ... on InterfaceType {
                    name, label, device {name, status}, 
                    child_interfaces {name mac_addresses {mac_address}}, 
                    lag {name mac_addresses {mac_address} child_interfaces {name mac_addresses {mac_address}}}, 
                    mac_addresses {mac_address}
                }
            }
        }
        parent {
            name
            type
            member_interfaces {
                name
                connected_endpoints {
                    __typename
                    ... on ProviderNetworkType {name}
                    ... on InterfaceType {
                        name, label, device {name, status}, 
                        child_interfaces {name mac_addresses {mac_address}}, 
                        lag {name child_interfaces {name mac_addresses {mac_address}}}, 
                        mac_addresses {mac_address}
                    }
                }
            }
            connected_endpoints {
                __typename
                ... on ProviderNetworkType {name}
                ... on InterfaceType {
                    name, label, device {name, status}, child_interfaces {name mac_addresses {mac_address}}, 
                    lag {name child_interfaces {name mac_addresses {mac_address}}}, 
                    mac_addresses {mac_address}
                }
            }
        }
        connected_endpoints {
            __typename
            ... on ProviderNetworkType {name}
            ... on InterfaceType {
                name, label, device {name, status}, 
                child_interfaces {name mac_addresses {mac_address}}, 
                lag {name child_interfaces {name mac_addresses {mac_address}}}, 
                mac_addresses {mac_address}
            }
        }
        link_peers {
            __typename
            ... on InterfaceType {name label device {name, status}}
            ... on FrontPortType {name label device {name, status}}
            ... on RearPortType {name label device {name, status}}
        }
        cable {
            type
            status
            tenant {name}
            label
            tags {name}
            custom_fields
        }
    }
    consoleport: console_port_list(
        filters: {device: {name: {in_list: $devices}}, name: {i_regex: $interface_regex}}
        pagination: { offset: $offset, limit: $limit }
    ) {
        name
        device {name, status}
        type
        connected_endpoints {
            __typename
            ... on ConsoleServerPortType {name label device {name, status}}
        }
        link_peers {
            __typename
            ... on ConsoleServerPortType {name label device {name, status}}
            ... on FrontPortType {name label device {name, status}}
            ... on RearPortType {name label device {name, status}}
        }
        cable {
            type
            status
            tenant {name}
            label
            tags {name}
            length
            length_unit
            custom_fields
        }
    }
    consoleserverport: console_server_port_list(
        filters: {device: {name: {in_list: $devices}}, name: {i_regex: $interface_regex}}
        pagination: { offset: $offset, limit: $limit }
    ) {
        name
        device {name, status}
        type
        connected_endpoints {
            __typename
            ... on ConsolePortType {name label device {name, status}}
        }
        link_peers {
            __typename
            ... on ConsolePortType {name label device {name, status}}
            ... on FrontPortType {name label device {name, status}}
            ... on RearPortType {name label device {name, status}}
        }
        cable {
            type
            status
            tenant {name}
            label
            tags {name}
            length
            length_unit
            custom_fields
        }
    }
    poweroutlet: power_outlet_list(
        filters: {device: {name: {in_list: $devices}}, name: {i_regex: $interface_regex}}
        pagination: { offset: $offset, limit: $limit }
    ) {
        name
        device {name, status}
        type
        connected_endpoints {
            __typename
            ... on PowerPortType {name label device {name, status}}
        }
        link_peers {
            __typename
            ... on PowerPortType {name label device {name, status}}
        }
        cable {
            type
            status
            tenant {name}
            label
            tags {name}
            length
            length_unit
            custom_fields
        }
    }
}
"""


class NetboxConnectionsTasks:
    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_connections(
        self,
        job: Job,
        devices: list[str],
        interface_regex: Union[None, str] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve interface connection details for specified devices from Netbox.

        This task retrieves these connections:

        - Physical interfaces connections
        - Child/virtual interfaces connections using parent interface connections details
        - Lag interfaces connections using member ports connections details
        - Lag child interfaces connections using member ports connections details
        - Console port and console server ports connections
        - Connections to provider networks for physical, child/virtual and lag interfaces

        This task also fetches MAC addresses for remote interfaces, sub-interfaces, LAG
        and LAG sub-interfaces

        Args:
            job: NorFab Job object containing relevant metadata
            devices (list): List of device names to retrieve connections for.
            instance (str, optional): Netbox instance name for the GraphQL query.
            dry_run (bool, optional): If True, perform a dry run without making actual changes.
            interface_regex (str, optional): Regex pattern to match interfaces, console ports and
                console server ports by name, case insensitive.

        Returns:
            dict: A dictionary containing per-interface connection details for each device:

                ```
                {
                    "netbox-worker-1.2": {
                        "r1": {
                            "eth101": {
                                "breakout": False,
                                "cable": {
                                    "custom_fields": {},
                                    "label": "",
                                    "peer_device": None,
                                    "peer_interface": None,
                                    "peer_termination_type": "circuittermination",
                                    "status": "connected",
                                    "tags": [],
                                    "tenant": None,
                                    "type": "smf"
                                },
                                "remote_device": "fceos4",
                                "remote_device_status": "active",
                                "remote_interface": "eth101",
                                "remote_interface_label": "port101",
                                "remote_termination_type": "interface",
                                "termination_type": "interface",
                                "remote_mac_addresses": [
                                    "00:11:22:33:44:01"
                                ]
                            }
                        }
                    }
                }
                ```

        Raises:
            Exception: If there is an error in the GraphQL query or data retrieval process.
        """
        instance = instance or self.default_instance
        log.info(
            f"{self.name} - Get connections: Fetching connections for {len(devices)} device(s) from '{instance}'"
        )
        job.event(f"fetching connections for {len(devices)} device(s)")
        ret = Result(
            task=f"{self.name}:get_connections",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # query uses inline filters with variables for devices and interface regex
        if not self.nb_version[instance] >= (4, 4, 0):
            raise UnsupportedNetboxVersion(
                f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                f"minimum required version is {self.compatible_ge_v4}"
            )

        variables = {
            "devices": devices,
            "interface_regex": interface_regex or ".*",
            "offset": 0,
            "limit": 50,
        }

        # retrieve full list of ports and process client-side to map connections
        query_result = self.netbox_graphql(
            job=job,
            query=CONNECTIONS_QUERY,
            variables=variables,
            instance=instance,
            dry_run=dry_run,
        )

        # return dry run result
        if dry_run:
            ret.dry_run = True
            ret.result = query_result.result
            return ret

        all_ports = query_result.result
        if not all_ports:
            log.info(
                f"{self.name} - Get connections: No ports returned for {len(devices)} device(s)"
            )
            return ret

        # extract physical interfaces connections
        for port_type, ports in all_ports.items():
            for port in ports:
                # skip ports that have no remote device connected
                endpoints = port["connected_endpoints"]
                if not endpoints or not all(i for i in endpoints):
                    continue

                # extract required parameters
                cable = port.get("cable", {})
                device_name = port["device"]["name"]
                port_name = port["name"]
                link_peers = port["link_peers"]
                remote_termination_type = endpoints[0]["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")

                # form initial connection dictionary
                connection = {
                    "breakout": len(endpoints) > 1,
                    "remote_termination_type": remote_termination_type,
                    "termination_type": port_type,
                    "remote_mac_addresses": sorted(
                        {
                            mac.get("mac_address")
                            for endpoint in endpoints
                            for mac in endpoint.get("mac_addresses") or []
                            if mac.get("mac_address")
                        }
                    ),
                }

                # add remote connection details
                if remote_termination_type == "providernetwork":
                    connection["remote_device"] = None
                    connection["remote_device_status"] = None
                    connection["remote_interface"] = None
                    connection["remote_interface_label"] = None
                    connection["provider"] = endpoints[0]["name"]
                else:
                    remote_interface = endpoints[0]["name"]
                    remote_label = endpoints[0]["label"]
                    if len(endpoints) > 1:
                        remote_interface = [i["name"] for i in endpoints]
                        remote_label = [i["label"] for i in endpoints]
                    connection["remote_interface"] = remote_interface
                    connection["remote_interface_label"] = remote_label
                    connection["remote_device"] = endpoints[0]["device"]["name"]
                    connection["remote_device_status"] = endpoints[0]["device"][
                        "status"
                    ]

                # add cable and its peer details
                if link_peers:
                    peer_termination_type = link_peers[0]["__typename"].lower()
                    peer_termination_type = peer_termination_type.replace("type", "")
                    cable["peer_termination_type"] = peer_termination_type
                    cable["peer_device"] = link_peers[0].get("device", {}).get("name")
                    cable["peer_interface"] = link_peers[0].get("name")
                    if len(link_peers) > 1:  # handle breakout cable
                        cable["peer_interface"] = [i["name"] for i in link_peers]
                connection["cable"] = cable

                # add physical connection to the results
                ret.result[device_name][port_name] = connection

        # extract virtual interfaces connections
        for port_type, ports in all_ports.items():
            for port in ports:
                # add child virtual interfaces connections
                if port["type"] != "virtual" or not port["parent"]:
                    continue
                device_name = port["device"]["name"]
                interface_name = port["name"]
                parent = port["parent"]
                connection = {
                    "remote_device": None,
                    "remote_device_status": None,
                    "remote_interface": None,
                    "remote_termination_type": "virtual",
                    "termination_type": "virtual",
                    "remote_mac_addresses": [],
                }
                # find connection endpoint
                if parent["type"] == "lag":
                    try:
                        endpoint = parent["member_interfaces"][0][
                            "connected_endpoints"
                        ][0]
                    except Exception:
                        continue
                elif parent["connected_endpoints"]:
                    try:
                        endpoint = parent["connected_endpoints"][0]
                    except Exception:
                        continue
                else:
                    log.error(
                        f"{device_name}:{interface_name} Parent has no connected endpoints"
                    )
                    continue
                remote_termination_type = endpoint["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")
                # collect virtual interfaces facing provider
                if remote_termination_type == "providernetwork":
                    connection["provider"] = endpoint["name"]
                    connection["remote_termination_type"] = remote_termination_type
                # find matching remote virtual interface for LAG subif
                elif "." in interface_name and parent["type"] == "lag":
                    connection["remote_device"] = endpoint["device"]["name"]
                    connection["remote_device_status"] = endpoint["device"]["status"]
                    if endpoint["lag"]:
                        subif_id = interface_name.split(".")[1]
                        for remote_child in endpoint["lag"]["child_interfaces"]:
                            if remote_child["name"].endswith(f".{subif_id}"):
                                connection["remote_interface"] = remote_child["name"]
                                connection["remote_mac_addresses"] = sorted(
                                    {
                                        mac.get("mac_address")
                                        for mac in remote_child.get("mac_addresses")
                                        or []
                                        if mac.get("mac_address")
                                    }
                                )
                                break
                        # no matching subinterface found, associate child interface with remote interface
                        else:
                            connection["remote_interface"] = endpoint["lag"]["name"]
                            connection["remote_termination_type"] = "lag"
                    # no remote lag found, associate child interface with remote interface
                    else:
                        connection["remote_interface"] = endpoint["name"]
                        connection["remote_interface_label"] = endpoint["label"]
                # find matching remote virtual interface for physical interface subif
                elif "." in interface_name:
                    connection["remote_device"] = endpoint["device"]["name"]
                    connection["remote_device_status"] = endpoint["device"]["status"]
                    subif_id = interface_name.split(".")[1]
                    for remote_child in endpoint["child_interfaces"]:
                        if remote_child["name"].endswith(f".{subif_id}"):
                            connection["remote_interface"] = remote_child["name"]
                            connection["remote_mac_addresses"] = sorted(
                                {
                                    mac.get("mac_address")
                                    for mac in remote_child.get("mac_addresses") or []
                                    if mac.get("mac_address")
                                }
                            )
                            break
                    # no matching subinterface found, associate child interface with remote interface
                    else:
                        connection["remote_interface"] = endpoint["name"]
                        connection["remote_interface_label"] = endpoint["label"]
                        connection["remote_termination_type"] = remote_termination_type
                # add virtual interface connection to results
                ret.result[device_name][interface_name] = connection

        # extract LAG interfaces connections
        for port_type, ports in all_ports.items():
            for port in ports:
                if port["type"] != "lag":
                    continue
                device_name = port["device"]["name"]
                interface_name = port["name"]
                connection = {
                    "remote_device": None,
                    "remote_device_status": None,
                    "remote_interface": None,
                    "remote_termination_type": "lag",
                    "termination_type": "lag",
                    "remote_mac_addresses": [],
                }
                try:
                    endpoint = port["member_interfaces"][0]["connected_endpoints"][0]
                except Exception:
                    continue
                remote_termination_type = endpoint["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")
                # collect lag interfaces facing provider
                if remote_termination_type == "providernetwork":
                    connection["provider"] = endpoint["name"]
                # find remote lag interface
                elif endpoint["lag"]:
                    connection["remote_interface"] = endpoint["lag"]["name"]
                    connection["remote_device"] = endpoint["device"]["name"]
                    connection["remote_device_status"] = endpoint["device"]["status"]
                    connection["remote_mac_addresses"] = sorted(
                        {
                            mac.get("mac_address")
                            for mac in endpoint["lag"].get("mac_addresses") or []
                            if mac.get("mac_address")
                        }
                    )
                # if no remote lag, collect remote end interfaces
                else:
                    connection["remote_interface"] = []
                    connection["remote_interface_label"] = []
                    connection["termination_type"] = "interface"
                    connection["remote_device"] = endpoint["device"]["name"]
                    connection["remote_device_status"] = endpoint["device"]["status"]
                    for member in port["member_interfaces"]:
                        for endpoint in member["connected_endpoints"]:
                            connection["remote_interface"].append(endpoint["name"])
                            connection["remote_interface_label"].append(
                                endpoint["label"]
                            )
                # add lag interface connection to results
                ret.result[device_name][interface_name] = connection

        log.info(
            f"{self.name} - get_connections: completed with connection data for {len(ret.result)} device(s)"
        )
        job.event(f"retrieved connections for {len(ret.result)} device(s)")

        return ret
