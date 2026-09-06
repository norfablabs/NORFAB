"""Native NORFAB adapters for the NFWeb topology application."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from norfab.clients.nfweb.topology.config import TopologyConfig
from norfab.clients.nfweb.topology.models import (
    LayerPatch,
    TopologyCollectionError,
    TopologyCollectionEvent,
    TopologyDeviceOption,
    TopologyHealth,
    TopologyLink,
    TopologyNode,
)


@dataclass
class CollectionContext:
    """State shared by adapters during one collection cycle."""

    config: TopologyConfig
    devices: list[str] = field(default_factory=list)
    ip_to_device: dict[str, str] = field(default_factory=dict)
    events: list[TopologyCollectionEvent] = field(default_factory=list)


class TopologyLayerAdapter(Protocol):
    """Protocol implemented by every topology data source."""

    name: str
    refresh_interval: int

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect one graph patch from NORFAB."""


def _as_dict(value: Any) -> Any:
    """Convert Pydantic-like values to dictionaries and leave others unchanged."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def _submit_job(
    client: Any,
    context: CollectionContext,
    service: str,
    task: str,
    *,
    workers: str,
    kwargs: dict[str, Any],
    timeout: int,
) -> Any:
    """Submit one NORFAB job without blocking the NFWeb event loop."""
    future = client.submit_job(
        service=service,
        task=task,
        workers=workers,
        kwargs=kwargs,
        timeout=timeout,
    )
    deadline = asyncio.get_running_loop().time() + timeout
    while not future.done_event.is_set():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(0.05, remaining))
    result = future.result(timeout=0)
    for raw_event in future.events(timeout=0):
        event = _as_dict(raw_event)
        if not isinstance(event, Mapping) or not event.get("message"):
            continue
        context.events.append(
            TopologyCollectionEvent(
                service=service,
                message=str(event["message"]),
                severity=str(event.get("severity") or "INFO"),
                task=str(event["task"]) if event.get("task") else task,
                worker=str(event["worker"]) if event.get("worker") else None,
                status=str(event["status"]) if event.get("status") else None,
                timestamp=(str(event["timestamp"]) if event.get("timestamp") else None),
                resource=event.get("resource"),
            )
        )
    return result


def _worker_payloads(
    result: Any, layer: str
) -> tuple[list[Any], list[TopologyCollectionError]]:
    """Separate successful worker payloads from normalized topology errors."""
    payloads: list[Any] = []
    errors: list[TopologyCollectionError] = []
    if not isinstance(result, Mapping):
        return payloads, [
            TopologyCollectionError(
                layer=layer,
                message="NORFAB returned no worker results",
            )
        ]

    for worker, raw_data in result.items():
        data = _as_dict(raw_data)
        if not isinstance(data, Mapping):
            errors.append(
                TopologyCollectionError(
                    layer=layer,
                    worker=str(worker),
                    message="worker returned an unsupported result",
                )
            )
            continue
        worker_errors = [str(item) for item in (data.get("errors") or [])]
        if data.get("failed") or worker_errors:
            errors.append(
                TopologyCollectionError(
                    layer=layer,
                    worker=str(worker),
                    message="; ".join(worker_errors) or "worker task failed",
                )
            )
        payload = _as_dict(data.get("result"))
        if payload is not None:
            payloads.append(payload)
    return payloads, errors


async def discover_device_options(
    client: Any, config: TopologyConfig
) -> tuple[list[TopologyDeviceOption], list[TopologyCollectionError]]:
    """Return device names reported by Nornir."""
    context = CollectionContext(config=config)
    names: set[str] = set()
    errors: list[TopologyCollectionError] = []

    nornir_result = await _submit_job(
        client,
        context,
        "nornir",
        "get_nornir_hosts",
        workers=config.nornir_workers,
        kwargs={},
        timeout=config.request_timeout,
    )
    payloads, job_errors = _worker_payloads(nornir_result, "topology")
    errors.extend(job_errors)
    for payload in payloads:
        if isinstance(payload, list):
            for name in payload:
                names.add(str(name))

    options = [
        TopologyDeviceOption(name=name, sources=["nornir"])
        for name in sorted(names, key=str.casefold)
    ]
    return options, errors


def _health_from_state(value: Any) -> TopologyHealth:
    """Map a service state value to the shared topology health vocabulary."""
    state = str(value or "").strip().lower()
    if state in {"up", "active", "connected", "established", "ok", "healthy"}:
        return "healthy"
    if state in {"down", "failed", "offline", "disabled"}:
        return "critical"
    if state in {"degraded", "warning", "admin-down", "administratively down"}:
        return "warning"
    return "unknown"


_HEALTH_ORDER: dict[TopologyHealth, int] = {
    "unknown": 0,
    "healthy": 1,
    "warning": 2,
    "critical": 3,
}


def worst_health(*values: TopologyHealth) -> TopologyHealth:
    """Return the most severe health value."""
    return max(values or ("unknown",), key=lambda value: _HEALTH_ORDER[value])


_INTERFACE_PREFIXES = {
    "et": "ethernet",
    "eth": "ethernet",
    "ethernet": "ethernet",
    "fa": "fastethernet",
    "fastethernet": "fastethernet",
    "gi": "gigabitethernet",
    "gig": "gigabitethernet",
    "gigabitethernet": "gigabitethernet",
    "lo": "loopback",
    "loopback": "loopback",
    "mgmt": "management",
    "management": "management",
    "po": "portchannel",
    "portchannel": "portchannel",
    "te": "tengigabitethernet",
    "ten": "tengigabitethernet",
    "tengigabitethernet": "tengigabitethernet",
}


def _device_identity(value: str) -> str:
    """Normalize a device value for case-insensitive endpoint identity."""
    return value.strip().rstrip(".").casefold()


def _interface_identity(value: str | None) -> str:
    """Normalize common interface abbreviations without changing display data."""
    if not value:
        return "?"
    compact = re.sub(r"\s+", "", value).casefold()
    match = re.match(r"([a-z-]+)(.*)", compact)
    if not match:
        return compact
    prefix, suffix = match.groups()
    canonical_prefix = _INTERFACE_PREFIXES.get(prefix.replace("-", ""), prefix)
    return f"{canonical_prefix}{suffix}"


def _known_device(value: str, devices: list[str]) -> str:
    """Resolve reported case or FQDN variants to one selected device name."""
    reported = value.strip().rstrip(".")
    identity = _device_identity(reported)
    exact = [device for device in devices if _device_identity(device) == identity]
    if len(exact) == 1:
        return exact[0]

    short = identity.split(".", 1)[0]
    short_matches = [
        device
        for device in devices
        if _device_identity(device).split(".", 1)[0] == short
    ]
    return short_matches[0] if len(short_matches) == 1 else reported


def _endpoint(device: str, interface: str | None) -> str:
    """Build a normalized identity for one device interface endpoint."""
    return f"{_device_identity(device)}:{_interface_identity(interface)}"


def _link_id(
    layer: str,
    source: str,
    target: str,
    source_interface: str | None = None,
    target_interface: str | None = None,
) -> str:
    """Build a direction-independent link identifier from two endpoints."""
    if layer == "bgp":
        addresses = sorted([_device_identity(source), _device_identity(target)])
        return f"bgp:{addresses[0]}--{addresses[1]}"
    endpoints = sorted(
        [
            _endpoint(source, source_interface),
            _endpoint(target, target_interface),
        ]
    )
    return f"{layer}:{endpoints[0]}--{endpoints[1]}"


def _string(value: Any) -> str:
    """Return an empty string for null values and stringify everything else."""
    return "" if value is None else str(value)


class InventoryLayer:
    """Seed topology from the selected hosts' running Nornir inventory."""

    name = "topology"

    def __init__(self, refresh_interval: int = 300) -> None:
        """Set how long Nornir inventory data may remain cached."""
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect topology-safe host, connection, circuit, and BGP data."""
        patch = LayerPatch(name=self.name)
        if not context.devices:
            return patch
        result = await _submit_job(
            client,
            context,
            "nornir",
            "get_inventory",
            workers=context.config.nornir_workers,
            kwargs={"FL": context.devices},
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)

        inventories: list[Mapping[str, Any]] = []
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            hosts = payload.get("hosts") or {}
            if not isinstance(hosts, Mapping):
                continue
            inventories.append(hosts)
            for raw_name, raw_host in hosts.items():
                host = _as_dict(raw_host)
                if not isinstance(host, Mapping):
                    continue
                name = _known_device(str(raw_name), context.devices)
                data = _as_dict(host.get("data"))
                data = data if isinstance(data, Mapping) else {}
                attributes = {
                    key: host[key]
                    for key in ("hostname", "platform", "groups")
                    if host.get(key) not in (None, "", [])
                }
                attributes.update(
                    {
                        key: data[key]
                        for key in (
                            "role",
                            "site",
                            "status",
                            "manufacturer",
                            "device_type",
                            "tags",
                            "primary_ip",
                        )
                        if data.get(key) not in (None, "", [])
                    }
                )
                patch.nodes.append(
                    TopologyNode(
                        id=name,
                        label=name,
                        health=_health_from_state(data.get("status")),
                        layers=[self.name],
                        origin=["nornir"],
                        attributes=attributes,
                    )
                )
                addresses: list[Any] = [data.get("primary_ip"), host.get("hostname")]
                interfaces = data.get("interfaces") or []
                if isinstance(interfaces, Mapping):
                    interfaces = interfaces.values()
                for raw_interface in interfaces:
                    interface = _as_dict(raw_interface)
                    if not isinstance(interface, Mapping):
                        continue
                    raw_addresses = interface.get("ip_addresses") or []
                    if isinstance(raw_addresses, Mapping):
                        raw_addresses = raw_addresses.values()
                    addresses.extend(raw_addresses)
                known_addresses: list[str] = []
                for raw_address in addresses:
                    address = _as_dict(raw_address)
                    if isinstance(address, Mapping):
                        address = address.get("address") or address.get("display")
                    ip = _string(address).split("/", 1)[0]
                    if ip:
                        context.ip_to_device[ip] = name
                        known_addresses.append(ip)
                if known_addresses:
                    patch.nodes[-1].attributes["addresses"] = sorted(
                        set(known_addresses)
                    )

        for hosts in inventories:
            for raw_name, raw_host in hosts.items():
                host = _as_dict(raw_host)
                if not isinstance(host, Mapping):
                    continue
                name = _known_device(str(raw_name), context.devices)
                data = _as_dict(host.get("data"))
                data = data if isinstance(data, Mapping) else {}
                connections = (
                    data.get("connections") or []
                    if context.config.layers.topology
                    else []
                )
                connection_items = (
                    connections.items()
                    if isinstance(connections, Mapping)
                    else ((None, item) for item in connections)
                )
                for local_interface, raw_link in connection_items:
                    link = _as_dict(raw_link)
                    if not isinstance(link, Mapping):
                        continue
                    source = _known_device(
                        _string(link.get("source") or name), context.devices
                    )
                    target = _known_device(
                        _string(
                            link.get("target")
                            or link.get("remote_device")
                            or link.get("provider")
                        ),
                        context.devices,
                    )
                    if not source or not target:
                        continue
                    source_interface = _string(
                        link.get("source_interface")
                        or link.get("src_iface")
                        or local_interface
                    )
                    target_interface = _string(
                        link.get("target_interface")
                        or link.get("dst_iface")
                        or link.get("remote_interface")
                    )
                    cable = _as_dict(link.get("cable"))
                    cable = cable if isinstance(cable, Mapping) else {}
                    patch.links.append(
                        TopologyLink(
                            id=_link_id(
                                self.name,
                                source,
                                target,
                                source_interface,
                                target_interface,
                            ),
                            source=source,
                            target=target,
                            layer=self.name,
                            health=_health_from_state(
                                link.get("status") or cable.get("status")
                            ),
                            origin=["nornir"],
                            attributes={
                                key: value
                                for key, value in link.items()
                                if key
                                not in {
                                    "source",
                                    "target",
                                    "source_interface",
                                    "target_interface",
                                    "src_iface",
                                    "dst_iface",
                                }
                            }
                            | {
                                "source_interface": source_interface,
                                "target_interface": target_interface,
                            },
                        )
                    )
                circuits = (
                    data.get("circuits") or [] if context.config.layers.topology else []
                )
                circuit_items = (
                    circuits.items()
                    if isinstance(circuits, Mapping)
                    else ((None, item) for item in circuits)
                )
                for circuit_id, raw_circuit in circuit_items:
                    circuit = _as_dict(raw_circuit)
                    if not isinstance(circuit, Mapping):
                        continue
                    source = _known_device(
                        _string(circuit.get("source") or name), context.devices
                    )
                    target = _known_device(
                        _string(
                            circuit.get("target")
                            or circuit.get("remote_device")
                            or circuit.get("provider_network")
                            or circuit.get("provider")
                        ),
                        context.devices,
                    )
                    if not source or not target:
                        continue
                    source_interface = _string(
                        circuit.get("source_interface")
                        or circuit.get("src_iface")
                        or circuit.get("interface")
                    )
                    target_interface = _string(
                        circuit.get("target_interface")
                        or circuit.get("dst_iface")
                        or circuit.get("remote_interface")
                    )
                    patch.links.append(
                        TopologyLink(
                            id=_link_id(
                                self.name,
                                source,
                                target,
                                source_interface,
                                target_interface,
                            ),
                            source=source,
                            target=target,
                            layer=self.name,
                            health=_health_from_state(circuit.get("status")),
                            origin=["nornir"],
                            attributes={
                                key: value
                                for key, value in circuit.items()
                                if key
                                not in {
                                    "source",
                                    "target",
                                    "source_interface",
                                    "target_interface",
                                    "src_iface",
                                    "dst_iface",
                                }
                            }
                            | {
                                "cid": circuit.get("cid") or circuit_id,
                                "source_interface": source_interface,
                                "target_interface": target_interface,
                            },
                        )
                    )
                if not context.config.layers.bgp:
                    continue
                peerings = data.get("bgp_peerings") or []
                peering_items = (
                    peerings.items()
                    if isinstance(peerings, Mapping)
                    else ((None, item) for item in peerings)
                )
                for peering_name, raw_peer in peering_items:
                    peer = _as_dict(raw_peer)
                    if not isinstance(peer, Mapping):
                        continue
                    local_address = _as_dict(peer.get("local_address"))
                    if isinstance(local_address, Mapping):
                        local_address = local_address.get("address")
                    remote_address = _as_dict(peer.get("remote_address"))
                    if isinstance(remote_address, Mapping):
                        remote_address = remote_address.get("address")
                    local_ip = _string(local_address).split("/", 1)[0]
                    remote_ip = _string(remote_address).split("/", 1)[0]
                    if not remote_ip:
                        continue
                    remote = context.ip_to_device.get(remote_ip, remote_ip)
                    peer_group = _as_dict(peer.get("peer_group"))
                    if isinstance(peer_group, Mapping):
                        peer_group = peer_group.get("name") or peer_group.get("display")
                    label = (
                        remote
                        if remote != remote_ip
                        else (
                            f"{peer_group} ({remote_ip})" if peer_group else remote_ip
                        )
                    )
                    health = _health_from_state(peer.get("state"))
                    patch.nodes.append(
                        TopologyNode(
                            id=remote,
                            label=label,
                            health=health,
                            layers=["bgp"],
                            origin=["nornir"],
                            attributes={"ip": remote_ip},
                        )
                    )
                    patch.links.append(
                        TopologyLink(
                            id=_link_id("bgp", local_ip or name, remote_ip),
                            source=name,
                            target=remote,
                            layer="bgp",
                            health=health,
                            origin=["nornir"],
                            attributes={
                                key: peer[key]
                                for key in (
                                    "description",
                                    "local_as",
                                    "remote_as",
                                    "state",
                                )
                                if peer.get(key) is not None
                            }
                            | {
                                "name": peer.get("name") or peering_name,
                                "peer_group": peer_group,
                                "local_address": local_ip,
                                "remote_address": remote_ip,
                            },
                        )
                    )
        return patch


class NetBoxTopologyLayer:
    """Collect desired topology for the selected Nornir hosts from NetBox."""

    name = "topology"

    def __init__(self, refresh_interval: int = 300) -> None:
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        patch = LayerPatch(name=self.name)
        if not context.devices:
            return patch
        result = await _submit_job(
            client,
            context,
            "netbox",
            "get_topology",
            workers=context.config.netbox_workers,
            kwargs={"devices": context.devices},
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            for raw_node in payload.get("nodes") or []:
                node = _as_dict(raw_node)
                if not isinstance(node, Mapping) or not node.get("id"):
                    continue
                node_id = str(node["id"])
                patch.nodes.append(
                    TopologyNode(
                        id=node_id,
                        label=str(node.get("name") or node_id),
                        health=_health_from_state(node.get("status")),
                        layers=[self.name],
                        origin=["netbox"],
                        attributes={
                            key: value
                            for key, value in node.items()
                            if key not in {"id", "name"}
                        },
                    )
                )
            for raw_link in payload.get("links") or []:
                link = _as_dict(raw_link)
                if not isinstance(link, Mapping):
                    continue
                source = _string(link.get("source"))
                target = _string(link.get("target"))
                if not source or not target:
                    continue
                source_interface = _string(
                    link.get("src_iface") or link.get("source_interface")
                )
                target_interface = _string(
                    link.get("dst_iface") or link.get("target_interface")
                )
                patch.links.append(
                    TopologyLink(
                        id=_link_id(
                            self.name,
                            source,
                            target,
                            source_interface,
                            target_interface,
                        ),
                        source=source,
                        target=target,
                        layer=self.name,
                        health=_health_from_state(
                            link.get("cable_status") or link.get("status")
                        ),
                        origin=["netbox"],
                        attributes={
                            key: value
                            for key, value in link.items()
                            if key
                            not in {
                                "source",
                                "target",
                                "src_iface",
                                "dst_iface",
                                "source_interface",
                                "target_interface",
                            }
                        }
                        | {
                            "source_interface": source_interface,
                            "target_interface": target_interface,
                        },
                    )
                )
            break
        return patch


class LLDPLayer:
    """Collect observed physical adjacency from network devices."""

    name = "lldp"

    def __init__(self, refresh_interval: int = 30) -> None:
        """Set how long LLDP observations may remain cached."""
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect LLDP neighbors as discovered nodes and physical links."""
        patch = LayerPatch(name=self.name)
        if not context.devices:
            return patch
        result = await _submit_job(
            client,
            context,
            "nornir",
            "parse_ttp",
            workers=context.config.nornir_workers,
            kwargs={"get": "lldp_neighbors", "FL": context.devices},
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)
        seen: set[str] = set()
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            for device, raw_neighbors in payload.items():
                local = _known_device(str(device), context.devices)
                patch.nodes.append(
                    TopologyNode(
                        id=local,
                        label=local,
                        health="healthy",
                        layers=["topology"],
                        origin=["live-lldp"],
                    )
                )
                for raw_neighbor in raw_neighbors or []:
                    neighbor = _as_dict(raw_neighbor)
                    if not isinstance(neighbor, Mapping):
                        continue
                    reported_remote = _string(neighbor.get("remote_device"))
                    if not reported_remote:
                        continue
                    remote = _known_device(reported_remote, context.devices)
                    source_interface = _string(neighbor.get("interface"))
                    target_interface = _string(neighbor.get("remote_interface"))
                    link_id = _link_id(
                        "topology",
                        local,
                        remote,
                        source_interface,
                        target_interface,
                    )
                    if link_id in seen:
                        continue
                    seen.add(link_id)
                    patch.nodes.append(
                        TopologyNode(
                            id=remote,
                            label=remote,
                            health="healthy",
                            layers=["topology"],
                            origin=["live-lldp"],
                        )
                    )
                    patch.links.append(
                        TopologyLink(
                            id=link_id,
                            source=local,
                            target=remote,
                            layer="topology",
                            health="healthy",
                            origin=["live-lldp"],
                            attributes={
                                "source_interface": source_interface,
                                "target_interface": target_interface,
                            }
                            | {
                                key: neighbor[key]
                                for key in (
                                    "remote_system_description",
                                    "remote_chassi_id",
                                    "remote_interface_description",
                                    "remote_device_management_ip",
                                )
                                if neighbor.get(key) is not None
                            },
                        )
                    )
        return patch


class BGPLayer:
    """Collect BGP sessions and resolve peer addresses through NetBox."""

    name = "bgp"

    def __init__(self, refresh_interval: int = 30) -> None:
        """Set how long BGP observations may remain cached."""
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect BGP peers and resolve known peer addresses to devices."""
        patch = LayerPatch(name=self.name)
        if not context.devices:
            return patch
        result = await _submit_job(
            client,
            context,
            "nornir",
            "parse_ttp",
            workers=context.config.nornir_workers,
            kwargs={"get": "bgp_neighbors", "FL": context.devices},
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)
        peer_ips = {
            _string(peer.get("remote_address")).split("/", 1)[0]
            for payload in payloads
            if isinstance(payload, Mapping)
            for peers in payload.values()
            for peer in (peers or [])
            if isinstance(peer, Mapping) and peer.get("remote_address")
        }
        unresolved = sorted(peer_ips - set(context.ip_to_device))
        if unresolved:
            await self._resolve_peer_addresses(client, context, unresolved, patch)

        seen: set[str] = set()
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            for device, raw_peers in payload.items():
                patch.nodes.append(
                    TopologyNode(
                        id=str(device),
                        label=str(device),
                        health="unknown",
                        layers=[self.name],
                        origin=["nornir"],
                    )
                )
                for raw_peer in raw_peers or []:
                    peer = _as_dict(raw_peer)
                    if not isinstance(peer, Mapping):
                        continue
                    remote_ip = _string(peer.get("remote_address")).split("/", 1)[0]
                    if not remote_ip:
                        continue
                    remote = context.ip_to_device.get(remote_ip, remote_ip)
                    local_ip = _string(peer.get("local_address")).split("/", 1)[0]
                    if not local_ip:
                        local_ip = next(
                            (
                                ip
                                for ip, known_device in context.ip_to_device.items()
                                if _device_identity(known_device)
                                == _device_identity(str(device))
                            ),
                            str(device),
                        )
                    state = peer.get("state")
                    if state is None:
                        health: TopologyHealth = "unknown"
                    elif str(state).lower() == "established":
                        health = "healthy"
                    else:
                        health = "critical"
                    link_id = _link_id(self.name, local_ip, remote_ip)
                    if link_id in seen:
                        continue
                    seen.add(link_id)
                    patch.nodes.append(
                        TopologyNode(
                            id=remote,
                            label=(
                                remote
                                if remote != remote_ip
                                else (
                                    f"{peer.get('peer_group')} ({remote_ip})"
                                    if peer.get("peer_group")
                                    else remote_ip
                                )
                            ),
                            health=health,
                            layers=[self.name],
                            origin=["nornir"],
                            attributes={"ip": remote_ip},
                        )
                    )
                    patch.links.append(
                        TopologyLink(
                            id=link_id,
                            source=str(device),
                            target=remote,
                            layer=self.name,
                            health=health,
                            origin=["nornir"],
                            attributes={
                                key: value
                                for key, value in peer.items()
                                if key not in {"remote_address"}
                            }
                            | {
                                "local_address": local_ip,
                                "remote_address": remote_ip,
                                "state": state,
                            },
                        )
                    )
        return patch

    async def _resolve_peer_addresses(
        self,
        client: Any,
        context: CollectionContext,
        peer_ips: list[str],
        patch: LayerPatch,
    ) -> None:
        """Resolve peer IP addresses through NetBox into the collection context."""
        result = await _submit_job(
            client,
            context,
            "netbox",
            "crud_read",
            workers=context.config.netbox_workers,
            kwargs={
                "object_type": "ipam.ip_addresses",
                "filters": [{"address": peer_ips}],
                "fields": ["assigned_object", "address"],
            },
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            for entry in payload.get("results") or []:
                if not isinstance(entry, Mapping):
                    continue
                ip = _string(entry.get("address")).split("/")[0]
                assigned = entry.get("assigned_object") or {}
                device = (assigned.get("device") or {}).get("name")
                if ip and device:
                    context.ip_to_device[ip] = str(device)


class InterfacesLayer:
    """Collect live interface state used to decorate topology links."""

    name = "interfaces"

    _METRIC_FIELDS = (
        "speed_bps",
        "transitions",
        "errors_in",
        "errors_out",
        "crc_errors",
        "packets_in",
        "packets_out",
        "rate_bps_in",
        "rate_bps_out",
        "input_utilization",
        "output_utilization",
        "rate_pps_in",
        "rate_pps_out",
        "rate_interval",
    )

    _ATTRIBUTE_FIELDS = (
        "description",
        "mtu",
        "mac_address",
        "duplex",
        "status_admin",
        "status_oper",
        "last_cleared",
    )

    def __init__(self, refresh_interval: int = 30) -> None:
        """Set how long interface observations may remain cached."""
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect interface state and metrics used to enrich topology links."""
        patch = LayerPatch(name=self.name)
        if not context.devices:
            return patch
        result = await _submit_job(
            client,
            context,
            "nornir",
            "parse_ttp",
            workers=context.config.nornir_workers,
            kwargs={"get": "interfaces_status", "FL": context.devices},
            timeout=context.config.request_timeout,
        )
        payloads, errors = _worker_payloads(result, self.name)
        patch.errors.extend(errors)
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            for device, raw_interfaces in payload.items():
                local = _known_device(str(device), context.devices)
                for raw_interface in raw_interfaces or []:
                    interface = _as_dict(raw_interface)
                    if not isinstance(interface, Mapping):
                        continue
                    name = _string(interface.get("name"))
                    if not name:
                        continue
                    metrics = {
                        key: interface.get(key)
                        for key in self._METRIC_FIELDS
                        if interface.get(key) is not None
                    }
                    patch.interface_observations[_endpoint(local, name)] = {
                        "health": _health_from_state(interface.get("status_oper")),
                        "attributes": {
                            key: interface.get(key)
                            for key in self._ATTRIBUTE_FIELDS
                            if interface.get(key) is not None
                        },
                        "metrics": metrics,
                    }
        return patch


def enabled_adapters(config: TopologyConfig) -> Iterable[TopologyLayerAdapter]:
    """Create adapters enabled in the inventory, in dependency order."""
    layers = config.layers
    if layers.topology or layers.bgp:
        yield InventoryLayer(config.inventory_refresh_interval)
    if layers.topology:
        yield NetBoxTopologyLayer(config.inventory_refresh_interval)
    if layers.lldp:
        yield LLDPLayer(config.collection_interval)
    if layers.bgp:
        yield BGPLayer(config.collection_interval)
    if layers.interfaces:
        yield InterfacesLayer(config.collection_interval)
