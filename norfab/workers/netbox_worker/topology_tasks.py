import logging
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_exceptions import UnsupportedNetboxVersion
from .netbox_models import NetboxCommonArgs, NetboxFastApiArgs

log = logging.getLogger(__name__)


TOPOLOGY_INTERFACES_QUERY = """
query TopologyInterfacesQuery(
    $devices: [String!]!
    $offset: Int!
    $limit: Int!
) {
    interface: interface_list(
        filters: {
            device: {name: {in_list: $devices}}
        }
        pagination: { offset: $offset, limit: $limit }
    ) {
        name
        type
        speed
        mtu
        tags { name }
        device { name }
        connected_endpoints {
            __typename
            ... on InterfaceType {
                name
                device { name }
            }
        }
        cable {
            type
            status
            label
            tags { name }
        }
    }
}
"""


# --------------------------------------------------------------------------
# INPUT PYDANTIC MODELS
# --------------------------------------------------------------------------


class GetTopologyInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
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


# --------------------------------------------------------------------------
# OUTPUT PYDANTIC MODELS
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# TASK CLASS
# --------------------------------------------------------------------------


def _build_node(dev: Any, color: Union[str, None] = None) -> Dict[str, Any]:
    """Build a topology node dict from a pynetbox device record."""
    return {
        "id": dev.name,
        "name": dev.name,
        "type": dev.platform.slug if dev.platform else None,
        "ip": dev.primary_ip4.address if dev.primary_ip4 else None,
        "status": dev.status.value,
        "role": dev.role.name,
        "site": dev.site.name,
        "tags": [t.name for t in dev.tags] if dev.tags else [],
        "manufacturer": dev.device_type.manufacturer.name,
        "device_type": dev.device_type.model,
        "color": color,
    }


class NetboxTopologyTasks:

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=GetTopologyInput,
        output=GetTopologyResult,
    )
    def get_topology(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        device_contains: Union[None, str] = None,
        device_regex: Union[None, str] = None,
        role: Union[None, list] = None,
        platform: Union[None, list] = None,
        manufacturers: Union[None, list] = None,
        status: Union[None, list] = None,
        sites: Union[None, list] = None,
        dry_run: bool = False,
        branch: Union[None, str] = None,
        timeout: int = 60,
        **kwargs: dict,
    ) -> Result:
        """
        Retrieve network topology from NetBox as a list of nodes and links.

        Fetches device data and physical interface connections to build a topology
        graph suitable for network visualisation tools. Nodes represent devices;
        links represent physical cabled connections between them. Links are
        deduplicated so each cable appears only once.

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): NetBox instance name; uses the default instance
                when omitted.
            devices (list, optional): List of device names to include in the topology.
                When omitted all devices in NetBox are fetched. After building links,
                any remote device connected to a filtered device that is not already
                in the list is automatically fetched and added as an adjacent node so
                every link endpoint always has a corresponding node entry.
            device_contains (str, optional): Case-insensitive substring to filter
                device names by (e.g. ``"spine"`` matches ``spine-1``, ``dc1-spine``).
            device_regex (str, optional): Regex pattern to filter device names by
                (e.g. ``"spine-[0-9]+"``).
            role (list, optional): List of device role slugs to filter by
                (e.g. ``["spine", "leaf"]``).
            platform (list, optional): List of platform slugs to filter by
                (e.g. ``["arista-eos", "cisco-ios"]``).
            manufacturers (list, optional): List of manufacturer slugs to filter by
                (e.g. ``["arista", "cisco"]``).
            status (list, optional): List of device status values to filter by
                (e.g. ``["active", "planned"]``).
            sites (list, optional): List of site slugs to filter by
                (e.g. ``["dc-1", "dc-2"]``).
            dry_run (bool, optional): When True returns GraphQL query parameters
                for both the device and interface queries without executing them.
                Defaults to False.
            branch (str, optional): NetBox branching plugin branch name to use.
            timeout (int, optional): Timeout in seconds for Nornir host resolution
                when Fx filter arguments are used. Defaults to 60.
            **kwargs: Nornir host filter arguments (e.g. ``FC``, ``FL``, ``FB``,
                ``FG``, ``FO``, ``FP``, ``FH``, ``FR``, ``FT``) passed to
                ``get_nornir_hosts`` to resolve additional devices from the Nornir
                inventory. Resolved hosts are merged with the ``devices`` list.

        Returns:
            GetTopologyResult with ``result.nodes`` and ``result.links``:

            **nodes** — one entry per device::

                {
                    "id":           "spine-1",
                    "name":         "spine-1",
                    "type":         "arista_eos",
                    "ip":           "10.0.0.1/32",
                    "status":       "active",
                    "role":         "spine",
                    "site":         "dc-1",
                    "tags":         ["core"],
                    "manufacturer": "Arista",
                    "device_type":  "DCS-7050CX3-32S",
                    "color":        "aa1409"
                }

            **links** — one entry per physical cable::

                {
                    "source":        "spine-1",
                    "target":        "leaf-1",
                    "src_iface":     "Ethernet1",
                    "dst_iface":     "Ethernet49",
                    "type":          "1000base-t",
                    "speed":         1000000,
                    "mtu":           9214,
                    "tags":          [],
                    "cable_type":    "smf",
                    "cable_status":  "connected",
                    "cable_label":   ""
                }

        Raises:
            UnsupportedNetboxVersion: If the NetBox instance version is below 4.4.0.
        """
        instance = instance or self.default_instance
        log.info(
            f"{self.name} - Get topology: Fetching topology for "
            + (f"{len(devices)} device(s)" if devices else "all devices")
            + f" from '{instance}'"
        )
        ret = GetTopologyResult(
            task=f"{self.name}:get_topology",
            result={"nodes": [], "links": []},
            resources=[instance],
        )

        if not self.nb_version[instance] >= (4, 4, 0):
            raise UnsupportedNetboxVersion(
                f"{self.name} - NetBox version {self.nb_version[instance]} is not supported, "
                f"minimum required version is {self.compatible_ge_v4}"
            )

        devices = devices or []

        # resolve additional devices from Nornir Fx filter arguments
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        # build pynetbox REST filter params
        device_filter_params: Dict[str, Any] = {}
        if devices:
            device_filter_params["name"] = devices
        if device_contains:
            device_filter_params["name__ic"] = device_contains
        if device_regex:
            device_filter_params["name__re"] = device_regex
        if role:
            device_filter_params["role"] = role
        if platform:
            device_filter_params["platform"] = platform
        if manufacturers:
            device_filter_params["manufacturer"] = manufacturers
        if status:
            device_filter_params["status"] = status
        if sites:
            device_filter_params["site"] = sites

        if dry_run:
            intf_dry = self.netbox_graphql(
                job=job,
                query=TOPOLOGY_INTERFACES_QUERY,
                variables={"devices": devices or ["*"], "offset": 0, "limit": 50},
                instance=instance,
                dry_run=True,
            )
            ret.dry_run = True
            ret.result = {
                "device_filter": device_filter_params,
                "graphql": intf_dry.result,
            }
            return ret

        nb = self._get_pynetbox(instance, branch=branch)

        # --- step 1: fetch device data for nodes via pynetbox REST ---
        job.event(
            "fetching device data from '{}'".format(instance)
            + (
                f" using {len(device_filter_params)} filter(s)"
                if device_filter_params
                else ""
            )
        )
        all_nb_devices = list(
            nb.dcim.devices.filter(
                **device_filter_params,
                fields="name,platform,primary_ip4,status,role,site,tags,device_type",
            )
        )
        device_names = set()
        role_slugs: set = set()
        for dev in all_nb_devices:
            device_names.add(dev.name)
            if dev.role:
                role_slugs.add(dev.role.slug)

        # fetch role colors
        role_colors: Dict[str, str] = {}
        if role_slugs:
            job.event("fetching role colors for {} role(s)".format(len(role_slugs)))
            for role in nb.dcim.device_roles.filter(slug=list(role_slugs)):
                role_colors[role.slug] = role.color

        for dev in all_nb_devices:
            color = role_colors.get(dev.role.slug) if dev.role else None
            ret.result.nodes.append(_build_node(dev, color=color))

        if not device_names:
            log.info(
                f"{self.name} - Get topology: No devices found, returning empty topology"
            )
            return ret

        # --- step 2: fetch interface connections for links ---
        job.event(f"fetching interface connections for {len(device_names)} device(s)")
        variables = {
            "devices": list(device_names),
            "offset": 0,
            "limit": 50,
        }
        query_result = self.netbox_graphql(
            job=job,
            query=TOPOLOGY_INTERFACES_QUERY,
            variables=variables,
            instance=instance,
            dry_run=False,
        )

        if query_result.failed:
            ret.failed = True
            ret.errors.extend(query_result.errors)
            return ret

        all_interfaces = (
            query_result.result.get("interface", []) if query_result.result else []
        )

        # --- step 3: build deduplicated links ---
        seen_links: set = set()
        for intf in all_interfaces:
            for endpoint in intf.get("connected_endpoints") or []:
                if endpoint.get("__typename") != "InterfaceType":
                    continue

                source = intf["device"]["name"]
                target = endpoint["device"]["name"]
                src_iface = intf["name"]
                dst_iface = endpoint["name"]

                # canonical key ensures (A:eth1->B:eth2) == (B:eth2->A:eth1)
                link_key = tuple(sorted([(source, src_iface), (target, dst_iface)]))
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)

                cable = intf.get("cable") or {}
                intf_type = intf.get("type") or {}
                link = {
                    "source": source,
                    "target": target,
                    "src_iface": src_iface,
                    "dst_iface": dst_iface,
                    "type": intf_type,
                    "speed": intf.get("speed"),
                    "mtu": intf.get("mtu"),
                    "tags": [t["name"] for t in (intf.get("tags") or [])],
                    "cable_type": cable.get("type"),
                    "cable_status": cable.get("status"),
                    "cable_label": cable.get("label"),
                }
                ret.result.links.append(link)

        # --- step 4: add nodes for connected devices not yet in the nodes list ---
        linked_device_names = set()
        for link in ret.result.links:
            linked_device_names.add(link["source"])
            linked_device_names.add(link["target"])
        missing_device_names = linked_device_names - device_names
        if missing_device_names:
            job.event(
                f"fetching data for {len(missing_device_names)} additional connected device(s)"
            )
            extra_nb_devices = list(
                nb.dcim.devices.filter(
                    name=list(missing_device_names),
                    fields="name,platform,primary_ip4,status,role,site,tags,device_type",
                )
            )
            extra_role_slugs = {
                dev.role.slug
                for dev in extra_nb_devices
                if dev.role and dev.role.slug not in role_colors
            }
            if extra_role_slugs:
                for role in nb.dcim.device_roles.filter(slug=list(extra_role_slugs)):
                    role_colors[role.slug] = role.color
            for dev in extra_nb_devices:
                device_names.add(dev.name)
                color = role_colors.get(dev.role.slug) if dev.role else None
                ret.result.nodes.append(_build_node(dev, color=color))

        log.info(
            f"{self.name} - Get topology: Built topology with "
            f"{len(ret.result.nodes)} nodes and {len(ret.result.links)} links"
        )
        return ret
