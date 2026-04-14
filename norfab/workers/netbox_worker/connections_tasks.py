import json
import logging
import concurrent.futures
from typing import Any, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
                    name, device {name, status}, 
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
                        name, device {name, status}, 
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
                    name, device {name, status}, child_interfaces {name mac_addresses {mac_address}}, 
                    lag {name child_interfaces {name mac_addresses {mac_address}}}, 
                    mac_addresses {mac_address}
                }
            }
        }
        connected_endpoints {
            __typename
            ... on ProviderNetworkType {name}
            ... on InterfaceType {
                name, device {name, status}, 
                child_interfaces {name mac_addresses {mac_address}}, 
                lag {name child_interfaces {name mac_addresses {mac_address}}}, 
                mac_addresses {mac_address}
            }
        }
        link_peers {
            __typename
            ... on InterfaceType {name device {name, status}}
            ... on FrontPortType {name device {name, status}}
            ... on RearPortType {name device {name, status}}
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
            ... on ConsoleServerPortType {name device {name, status}}
        }
        link_peers {
            __typename
            ... on ConsoleServerPortType {name device {name, status}}
            ... on FrontPortType {name device {name, status}}
            ... on RearPortType {name device {name, status}}
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
            ... on ConsolePortType {name device {name, status}}
        }
        link_peers {
            __typename
            ... on ConsolePortType {name device {name, status}}
            ... on FrontPortType {name device {name, status}}
            ... on RearPortType {name device {name, status}}
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
            ... on PowerPortType {name device {name, status}}
        }
        link_peers {
            __typename
            ... on PowerPortType {name device {name, status}}
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
    def graphql_fetch_page(
        self,
        session: requests.Session,
        nb_url: str,
        ssl_verify: bool,
        query: str,
        variables: dict,
    ) -> dict[str, Any]:
        """Execute a single paginated GraphQL POST request and return the ``data`` payload.

        Designed to be called concurrently from multiple threads sharing the same session.

        Args:
            session: Shared :class:`requests.Session` with auth headers pre-configured.
            nb_url: Base URL of the NetBox instance (e.g. ``https://netbox.example.com``).
            ssl_verify: Whether to verify TLS certificates.
            query: GraphQL query string.
            variables: Variable mapping sent with the query (must include ``offset`` and ``limit``).

        Returns:
            The ``data`` section of the GraphQL JSON response.

        Raises:
            requests.HTTPError: If the HTTP response status indicates an error.
            RuntimeError: If the GraphQL response body contains an ``errors`` field.
        """
        response = session.post(
            url=f"{nb_url}/graphql/",
            json={"query": query, "variables": variables},
            verify=ssl_verify,
            timeout=(self.netbox_connect_timeout, self.netbox_read_timeout),
        )
        response.raise_for_status()
        response_payload = response.json()
        if response_payload.get("errors"):
            raise RuntimeError(
                f"{self.name} - GraphQL query returned errors: {response_payload['errors']}"
            )
        return response_payload.get("data", {})

    def netbox_graphql(
        self,
        job: Job,
        instance: str,
        query: str,
        variables: Union[None, dict] = None,
        dry_run: bool = False,
        offset: int = 0,
        limit: int = 50,
        max_workers: int = 8
    ) -> Result:
        """
        Execute a paginated GraphQL query against a NetBox instance, fetching all pages in parallel.

        Pages are fetched in parallel batches of up to ``max_workers`` concurrent requests.
        Results across all pages are merged into a single ``aggregated_data`` dict where list
        fields are extended and scalar fields are overwritten.

        Args:
            job: NorFab job context.
            instance: Name of the NetBox instance to query.
            query: GraphQL query string. Must accept ``$offset: Int!`` and ``$limit: Int!``
                variables to support automatic pagination.
            variables: Optional extra GraphQL variables forwarded verbatim to the GraphQL query.
            dry_run: When ``True``, return the request parameters without executing any HTTP calls.
            offset: Starting pagination offset (number of records to skip before the first page).
            limit: Number of records per page fetched from NetBox.
            max_workers: Maximum number of concurrent page-fetch threads per iteration.

        Returns:
            :class:`Result` whose ``result`` field holds the merged GraphQL ``data`` dict.
            On failure ``failed`` is ``True`` and ``errors`` lists the exception messages.
        """
        nb_params = self._get_instance_params(instance)
        ret = Result(task=f"{self.name}:graphql", resources=[instance])

        if dry_run:
            ret.dry_run = True
            ret.result = {
                "url": f"{nb_params['url']}/graphql/",
                "data": json.dumps({"query": query, "variables": variables or {}}),
                "verify": nb_params.get("ssl_verify", True),
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token ...{nb_params['token'][-6:]}",
                },
            }
            return ret

        # configure session with retry back-off for transient server errors
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"POST"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {nb_params['token']}",
        })

        try:
            aggregated_data: dict[str, Any] = {}
            ssl_verify = nb_params.get("ssl_verify", True)
            nb_url = nb_params["url"]

            # paginate through all results, fetching max_workers pages per iteration
            while True:
                batch_offsets = [offset + (i * limit) for i in range(max_workers)]
                pages: list[tuple[int, dict[str, Any]]] = []

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures: dict[concurrent.futures.Future, int] = {
                        pool.submit(
                            self.graphql_fetch_page,
                            session,
                            nb_url,
                            ssl_verify,
                            query,
                            {**variables, "offset": page_offset, "limit": limit},
                        ): page_offset
                        for page_offset in batch_offsets
                    }
                    for future in concurrent.futures.as_completed(futures):
                        page_offset = futures[future]
                        try:
                            pages.append((page_offset, future.result()))
                        except Exception as exc:
                            error_msg = f"Failed to fetch page at offset {page_offset}: {exc}"
                            log.error(f"{self.name} - {error_msg}")
                            ret.errors.append(error_msg)
                            ret.failed = True

                # stop immediately if any page fetch failed — results would be incomplete
                if ret.failed:
                    break

                any_data_returned = False
                has_full_page = False

                # merge pages in offset order to maintain consistent result ordering
                for _, data in sorted(pages, key=lambda item: item[0]):
                    page_sizes: list[int] = []
                    for key, value in data.items():
                        if isinstance(value, list):
                            if value:
                                any_data_returned = True
                            aggregated_data.setdefault(key, [])
                            aggregated_data[key].extend(value)
                            page_sizes.append(len(value))
                        else:
                            aggregated_data[key] = value
                    # a full page means there may be more data to fetch
                    if page_sizes and any(size == limit for size in page_sizes):
                        has_full_page = True

                # stop when no data was returned or no page was fully filled
                if not any_data_returned or not has_full_page:
                    break

                offset += max_workers * limit

            if not ret.failed:
                ret.result = aggregated_data
        finally:
            session.close()

        return ret

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
                if (
                    port["type"] != "virtual"
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
                connection["remote_device"] = endpoint["device"]["name"]
                connection["remote_device_status"] = endpoint["device"]["status"]
                remote_termination_type = endpoint["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")
                # collect virtual interfaces facing provider
                if remote_termination_type == "providernetwork":
                    connection["provider"] = endpoint["name"]
                # find matching remote virtual interface for LAG subif
                elif "." in interface_name and parent["type"] == "lag":
                    if endpoint["lag"]:
                        subif_id = interface_name.split(".")[1]
                        for remote_child in endpoint["lag"]["child_interfaces"]:
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
                            connection["remote_interface"] = endpoint["lag"]["name"]
                            connection["remote_termination_type"] = "lag"
                    # no remote lag found, associate child interface with remote interface
                    else:
                        connection["remote_interface"] = endpoint["name"]
                # find matching remote virtual interface for physical interface subif
                elif "." in interface_name:
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
                    connection["termination_type"] = "interface"
                    connection["remote_device"] = endpoint["device"]["name"]
                    connection["remote_device_status"] = endpoint["device"]["status"]
                    for member in port["member_interfaces"]:
                        for endpoint in member["connected_endpoints"]:
                            connection["remote_interface"].append(endpoint["name"])
                # add lag interface connection to results
                ret.result[device_name][interface_name] = connection

        log.info(
            f"{self.name} - get_connections: completed with connection data for {len(ret.result)} device(s)"
        )
        job.event(f"retrieved connections for {len(ret.result)} device(s)")

        return ret
