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
    """Return the union of device names reported by NetBox and Nornir."""
    context = CollectionContext(config=config)
    sources: dict[str, set[str]] = {}
    errors: list[TopologyCollectionError] = []

    netbox_filter: dict[str, Any] = {"name__iregex": ".*"}
    if config.sites:
        netbox_filter["site"] = config.sites
    netbox_result = await _submit_job(
        client,
        context,
        "netbox",
        "get_devices",
        workers=config.netbox_workers,
        kwargs={"filters": [netbox_filter]},
        timeout=config.request_timeout,
    )
    payloads, job_errors = _worker_payloads(netbox_result, "inventory")
    errors.extend(job_errors)
    for payload in payloads:
        if isinstance(payload, Mapping):
            for name in payload:
                sources.setdefault(str(name), set()).add("netbox")

    nornir_result = await _submit_job(
        client,
        context,
        "nornir",
        "get_nornir_hosts",
        workers=config.nornir_workers,
        kwargs={},
        timeout=config.request_timeout,
    )
    payloads, job_errors = _worker_payloads(nornir_result, "inventory")
    errors.extend(job_errors)
    for payload in payloads:
        if isinstance(payload, list):
            for name in payload:
                sources.setdefault(str(name), set()).add("nornir")

    options = [
        TopologyDeviceOption(name=name, sources=sorted(device_sources))
        for name, device_sources in sorted(
            sources.items(), key=lambda item: item[0].casefold()
        )
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
    """Collect intended physical topology and device metadata from NetBox."""

    name = "inventory"

    def __init__(self, refresh_interval: int = 300) -> None:
        """Set how long inventory data may remain cached."""
        self.refresh_interval = refresh_interval

    async def collect(self, client: Any, context: CollectionContext) -> LayerPatch:
        """Collect NetBox devices and cables as an inventory layer patch."""
        patch = LayerPatch(name=self.name)
        scope: dict[str, Any] = {"device_regex": ".*"}
        if context.devices:
            scope = {"devices": context.devices}
        elif context.config.sites:
            scope = {"sites": context.config.sites}
        result = await _submit_job(
            client,
            context,
            "netbox",
            "get_topology",
            workers=context.config.netbox_workers,
            kwargs=scope,
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
                        attributes={
                            key: value
                            for key, value in node.items()
                            if key not in {"id", "name", "status"}
                        }
                        | {"status": node.get("status")},
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
                        health=_health_from_state(link.get("cable_status")),
                        attributes={
                            key: value
                            for key, value in link.items()
                            if key not in {"source", "target", "src_iface", "dst_iface"}
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
                        layers=[self.name],
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
                        self.name,
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
                            layers=[self.name],
                        )
                    )
                    patch.links.append(
                        TopologyLink(
                            id=link_id,
                            source=local,
                            target=remote,
                            layer=self.name,
                            health="healthy",
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
            _string(peer.get("remote_address"))
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
                    )
                )
                for raw_peer in raw_peers or []:
                    peer = _as_dict(raw_peer)
                    if not isinstance(peer, Mapping):
                        continue
                    remote_ip = _string(peer.get("remote_address"))
                    if not remote_ip:
                        continue
                    remote = context.ip_to_device.get(remote_ip, remote_ip)
                    state = peer.get("state")
                    if state is None:
                        health: TopologyHealth = "unknown"
                    elif str(state).lower() == "established":
                        health = "healthy"
                    else:
                        health = "critical"
                    link_id = _link_id(self.name, str(device), remote, remote_ip, None)
                    if link_id in seen:
                        continue
                    seen.add(link_id)
                    patch.nodes.append(
                        TopologyNode(
                            id=remote,
                            label=remote,
                            kind="device" if remote != remote_ip else "external-peer",
                            health=health,
                            layers=[self.name],
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
                            attributes={
                                key: value
                                for key, value in peer.items()
                                if key not in {"remote_address"}
                            }
                            | {"remote_address": remote_ip, "state": state},
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
    if layers.inventory:
        yield InventoryLayer(config.inventory_refresh_interval)
    if layers.lldp:
        yield LLDPLayer(config.collection_interval)
    if layers.bgp:
        yield BGPLayer(config.collection_interval)
    if layers.interfaces:
        yield InterfacesLayer(config.collection_interval)
