import logging

from typing import Union
from norfab.core.worker import Task, Job
from norfab.models import Result
from .netbox_models import NetboxFastApiArgs
from .netbox_exceptions import UnsupportedNetboxVersion

log = logging.getLogger(__name__)


class NetboxConnectionsTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_connections(
        self,
        job: Job,
        devices: list[str],
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cables: bool = False,
        cache: Union[bool, str] = None,
        include_virtual: bool = True,
        interface_regex: Union[None, str] = None,
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

        Args:
            job: NorFab Job object containing relevant metadata
            devices (list): List of device names to retrieve connections for.
            instance (str, optional): Netbox instance name for the GraphQL query.
            dry_run (bool, optional): If True, perform a dry run without making actual changes.
            cables (bool, optional): if True includes interfaces' directly attached cables and peers details
            include_virtual (bool, optional): if True include connections for virtual and LAG interfaces
            interface_regex (str, optional): Regex pattern to match interfaces, console ports and
                console server ports by name, case insensitive.

        Returns:
            dict: A dictionary containing connection details for each device:

                ```
                {
                    "netbox-worker-1.2": {
                        "r1": {
                            "Console": {
                                "breakout": false,
                                "remote_device": "termserv1",
                                "remote_device_status": "active",
                                "remote_interface": "ConsoleServerPort1",
                                "remote_termination_type": "consoleserverport",
                                "termination_type": "consoleport"
                            },
                            "eth1": {
                                "breakout": false,
                                "remote_device": "r2",
                                "remote_device_status": "active",
                                "remote_interface": "eth8",
                                "remote_termination_type": "interface",
                                "termination_type": "interface"
                            }
                        }
                    }
                }
                ```

        Raises:
            Exception: If there is an error in the GraphQL query or data retrieval process.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:get_connections",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # form lists of fields to request from netbox
        cable_fields = """
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
        """
        interfaces_fields = [
            "name",
            "type",
            "device {name, status}",
            """
            member_interfaces {
              name
              connected_endpoints {
                __typename
                ... on ProviderNetworkType {name}
                ... on InterfaceType {name, device {name, status}, child_interfaces {name}, lag {name child_interfaces {name}}}
              }
            }
            """,
            """
            parent {
              name
              type
              member_interfaces {
                name
                connected_endpoints {
                  __typename
                  ... on ProviderNetworkType {name}
                  ... on InterfaceType {name, device {name, status}, child_interfaces {name}, lag {name child_interfaces {name}}}
                }
              }
              connected_endpoints {
                __typename
                ... on ProviderNetworkType {name}
                ... on InterfaceType {name, device {name, status}, child_interfaces {name}, lag {name child_interfaces {name}}}
              }
            }
            """,
            """
            connected_endpoints {
                __typename 
                ... on ProviderNetworkType {name}
                ... on InterfaceType {name, device {name, status}, child_interfaces {name}, lag {name child_interfaces {name}}}
            }
            """,
            """
            link_peers {
                __typename
                ... on InterfaceType {name device {name, status}}
                ... on FrontPortType {name device {name, status}}
                ... on RearPortType {name device {name, status}}
            }
            """,
        ]
        console_ports_fields = [
            "name",
            "device {name, status}",
            "type",
            """connected_endpoints {
              __typename 
              ... on ConsoleServerPortType {name device {name, status}}
            }""",
            """link_peers {
              __typename
              ... on ConsoleServerPortType {name device {name, status}}
              ... on FrontPortType {name device {name, status}}
              ... on RearPortType {name device {name, status}}
            }""",
        ]
        console_server_ports_fields = [
            "name",
            "device {name, status}",
            "type",
            """connected_endpoints {
              __typename 
              ... on ConsolePortType {name device {name, status}}
            }""",
            """link_peers {
              __typename
              ... on ConsolePortType {name device {name, status}}
              ... on FrontPortType {name device {name, status}}
              ... on RearPortType {name device {name, status}}
            }""",
        ]
        power_outlet_fields = [
            "name",
            "device {name, status}",
            "type",
            """connected_endpoints {
              __typename 
              ... on PowerPortType {name device {name, status}}
            }""",
            """link_peers {
              __typename
              ... on PowerPortType {name device {name, status}}
            }""",
        ]

        # check if need to include cables info
        if cables is True:
            interfaces_fields.append(cable_fields)
            console_ports_fields.append(cable_fields)
            console_server_ports_fields.append(cable_fields)
            power_outlet_fields.append(cable_fields)

        # form query dictionary with aliases to get data from Netbox
        dlist = str(devices).replace("'", '"')  # swap quotes
        if self.nb_version[instance] >= (4, 4, 0):
            if interface_regex:
                filters = (
                    "{device: {name: {in_list: "
                    + dlist
                    + "}}, "
                    + "name: {i_regex: "
                    + f'"{interface_regex}"'
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
            "interface": {
                "obj": "interface_list",
                "filters": filters,
                "fields": interfaces_fields,
            },
            "consoleport": {
                "obj": "console_port_list",
                "filters": filters,
                "fields": console_ports_fields,
            },
            "consoleserverport": {
                "obj": "console_server_port_list",
                "filters": filters,
                "fields": console_server_ports_fields,
            },
            "poweroutlet": {
                "obj": "power_outlet_list",
                "filters": filters,
                "fields": power_outlet_fields,
            },
        }

        # retrieve full list of devices interface with all cables
        query_result = self.graphql(
            job=job, queries=queries, instance=instance, dry_run=dry_run
        )

        # return dry run result
        if dry_run:
            return query_result

        all_ports = query_result.result
        if not all_ports:
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
                }

                # add remote connection details
                if remote_termination_type == "providernetwork":
                    connection["remote_device"] = None
                    connection["remote_device_status"] = None
                    connection["remote_interface"] = None
                    connection["provider"] = endpoints[0]["name"]
                else:
                    remote_interface = endpoints[0]["name"]
                    if len(endpoints) > 1:
                        remote_interface = list(sorted([i["name"] for i in endpoints]))
                    connection["remote_interface"] = remote_interface
                    connection["remote_device"] = endpoints[0]["device"]["name"]
                    connection["remote_device_status"] = endpoints[0]["device"][
                        "status"
                    ]

                # add cable and its peer details
                if cables:
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
                if (
                    not include_virtual
                    or port["type"] != "virtual"
                    or not port["parent"]
                ):
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
                        f"{device_name}:{interface_name} parent has no connected endpoints"
                    )
                    continue
                connection["remote_device"] = endpoint["device"]["name"]
                connection["remote_device_status"] = endpoint["device"]["status"]
                remote_termination_type = endpoint["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")
                # collect virtual interfaces facing provider
                if remote_termination_type == "providernetwork":
                    connection["provider"] = endpoint["name"]
                # find matching remote virtual interface for LAG subif
                elif "." in interface_name and parent["type"] == "lag":
                    subif_id = interface_name.split(".")[1]
                    for remote_child in endpoint["lag"]["child_interfaces"]:
                        if remote_child["name"].endswith(f".{subif_id}"):
                            connection["remote_interface"] = remote_child["name"]
                            break
                    # no matching subinterface found, associate child interface with remote interface
                    else:
                        connection["remote_interface"] = endpoint["lag"]["name"]
                        connection["remote_termination_type"] = "lag"
                # find matching remote virtual interface for physical interface subif
                elif "." in interface_name:
                    subif_id = interface_name.split(".")[1]
                    for remote_child in endpoint["child_interfaces"]:
                        if remote_child["name"].endswith(f".{subif_id}"):
                            connection["remote_interface"] = remote_child["name"]
                            break
                    # no matching subinterface found, associate child interface with remote interface
                    else:
                        connection["remote_interface"] = endpoint["name"]
                        connection["remote_termination_type"] = remote_termination_type
                # add virtual interface connection to results
                ret.result[device_name][interface_name] = connection

        # extract LAG interfaces connections
        for port_type, ports in all_ports.items():
            for port in ports:
                if not include_virtual or port["type"] != "lag":
                    continue
                device_name = port["device"]["name"]
                interface_name = port["name"]
                connection = {
                    "remote_device": None,
                    "remote_device_status": None,
                    "remote_interface": None,
                    "remote_termination_type": "lag",
                    "termination_type": "lag",
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
                # add lag interface connection to results
                ret.result[device_name][interface_name] = connection

        return ret
