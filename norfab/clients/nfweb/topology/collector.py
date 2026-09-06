"""Topology collection and live snapshot scheduling."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from tornado.ioloop import PeriodicCallback

from norfab.clients.nfweb.topology.config import TopologyConfig
from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.layers import (
    CollectionContext,
    TopologyLayerAdapter,
    _endpoint,
    discover_device_options,
    enabled_adapters,
    worst_health,
)
from norfab.clients.nfweb.topology.models import (
    LayerPatch,
    TopologyCollectionError,
    TopologyDeviceOption,
    TopologyLink,
    TopologyNode,
    TopologySnapshot,
)

log = logging.getLogger(__name__)

SnapshotCallback = Callable[[TopologySnapshot], Awaitable[None] | None]


class TopologyCollector:
    """Collect one shared topology and persist a bounded local history."""

    def __init__(
        self,
        client: Any,
        config: TopologyConfig,
        history: TopologyHistoryStore,
        adapters: list[TopologyLayerAdapter] | None = None,
        on_snapshot: SnapshotCallback | None = None,
    ) -> None:
        """Configure collection state, persistence, and snapshot publication."""
        self.client = client
        self.config = config
        self.history = history
        self.adapters = list(adapters or enabled_adapters(config))
        self.on_snapshot = on_snapshot
        self._periodic: PeriodicCallback | None = None
        self._collection_lock = asyncio.Lock()
        self._active_task: asyncio.Task | None = None
        self._layer_cache: dict[str, tuple[float, LayerPatch]] = {}
        self._device_options_cache: (
            tuple[float, list[TopologyDeviceOption], list[TopologyCollectionError]]
            | None
        ) = None
        self.selected_devices = sorted(set(config.devices))
        self.running = False
        self.last_started_at: datetime | None = None
        self.last_completed_at: datetime | None = None
        self.last_error: str | None = None

    @property
    def collecting(self) -> bool:
        """Return whether a collection cycle currently owns the collector."""
        return self._collection_lock.locked()

    async def start(self) -> None:
        """Start periodic collection and collect an explicitly configured scope."""
        if self.running:
            return
        self.running = True
        self._periodic = PeriodicCallback(
            self.collect,
            self.config.collection_interval * 1000,
        )
        self._periodic.start()
        if self.selected_devices:
            self._active_task = asyncio.create_task(self.collect())

    async def stop(self) -> None:
        """Stop periodic collection and wait for an active cycle."""
        self.running = False
        if self._periodic is not None:
            self._periodic.stop()
        if self._active_task is not None and not self._active_task.done():
            await self._active_task
        async with self._collection_lock:
            pass

    async def collect(self, force: bool = False) -> TopologySnapshot | None:
        """Run one non-overlapping asynchronous collection."""
        if not self.selected_devices:
            return None
        if self._collection_lock.locked():
            log.warning("NFWeb topology collection skipped because a cycle is active")
            return None
        async with self._collection_lock:
            self.last_started_at = datetime.now(timezone.utc)
            try:
                snapshot = await self.collect_once(force)
                self.history.insert(snapshot)
                self.last_completed_at = snapshot.collected_at
                self.last_error = None
                if self.on_snapshot is not None:
                    result = self.on_snapshot(snapshot)
                    if result is not None:
                        await result
                return snapshot
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("NFWeb topology collection failed")
                return None

    async def collect_once(self, force: bool = False) -> TopologySnapshot:
        """Collect and merge every enabled layer through submitted jobs."""
        if not self.selected_devices:
            raise RuntimeError("topology collection requires selected devices")
        started = time.perf_counter()
        context = CollectionContext(
            config=self.config,
            devices=list(self.selected_devices),
        )
        patches: list[LayerPatch] = []
        errors = []

        for adapter in self.adapters:
            cache_key = adapter.__class__.__name__
            cached = self._layer_cache.get(cache_key)
            now = time.monotonic()
            if not force and cached and now - cached[0] < adapter.refresh_interval:
                patch = cached[1]
            else:
                try:
                    patch = await adapter.collect(self.client, context)
                    self._layer_cache[cache_key] = (now, patch)
                except Exception as exc:
                    patch = LayerPatch(
                        name=adapter.name,
                        errors=[
                            TopologyCollectionError(
                                layer=adapter.name,
                                message=str(exc),
                            )
                        ],
                    )
            patches.append(patch)
            errors.extend(patch.errors)
            for node in patch.nodes:
                addresses = node.attributes.get("addresses") or []
                if isinstance(addresses, list):
                    addresses = list(addresses)
                else:
                    addresses = [addresses]
                addresses.append(node.attributes.get("primary_ip"))
                for address in addresses:
                    ip = str(address or "").split("/", 1)[0]
                    if ip:
                        context.ip_to_device[ip] = node.id

        nodes, links = self._merge(patches)
        if errors and (nodes or links):
            status = "partial"
        elif errors:
            status = "failed"
        elif nodes or links:
            status = "complete"
        else:
            status = "empty"
        return TopologySnapshot(
            collected_at=datetime.now(timezone.utc),
            duration_ms=round((time.perf_counter() - started) * 1000),
            status=status,
            devices=list(self.selected_devices),
            layers=list(dict.fromkeys(patch.name for patch in patches)),
            nodes=sorted(nodes.values(), key=lambda node: node.id.casefold()),
            links=sorted(links.values(), key=lambda link: link.id.casefold()),
            errors=errors,
            events=context.events,
        )

    async def device_inventory(self, force: bool = False) -> dict[str, Any]:
        """Return selectable devices discovered from Nornir."""
        cached = self._device_options_cache
        if not force and cached and time.monotonic() - cached[0] < 60:
            options, errors = cached[1], cached[2]
        else:
            options, errors = await discover_device_options(self.client, self.config)
            self._device_options_cache = (time.monotonic(), options, errors)
        return {
            "devices": options,
            "selected": list(self.selected_devices),
            "errors": errors,
        }

    async def select_devices(self, devices: list[str]) -> TopologySnapshot | None:
        """Set the shared topology scope and collect it immediately."""
        inventory = await self.device_inventory()
        available = {option.name for option in inventory["devices"]}
        selected = sorted(set(devices), key=str.casefold)
        unknown = [device for device in selected if device not in available]
        if unknown:
            raise ValueError(f"unknown topology devices: {', '.join(unknown)}")
        self.selected_devices = selected
        self._layer_cache.clear()
        if not selected:
            return None
        return await self.collect(force=True)

    @staticmethod
    def _merge(
        patches: list[LayerPatch],
    ) -> tuple[dict[str, TopologyNode], dict[str, TopologyLink]]:
        """Merge layer patches into de-duplicated nodes and enriched links."""
        nodes: dict[str, TopologyNode] = {}
        links: dict[str, TopologyLink] = {}
        observations: dict[str, dict[str, Any]] = {}

        for patch in patches:
            observations.update(patch.interface_observations)
            for incoming in patch.nodes:
                existing = nodes.get(incoming.id)
                if existing is None:
                    nodes[incoming.id] = incoming.model_copy(deep=True)
                    continue
                existing.health = worst_health(existing.health, incoming.health)
                existing.layers = sorted(set(existing.layers + incoming.layers))
                existing.origin = sorted(set(existing.origin + incoming.origin))
                if "netbox" in incoming.origin or patch.name == "bgp":
                    existing.attributes.update(incoming.attributes)
                else:
                    for key, value in incoming.attributes.items():
                        existing.attributes.setdefault(key, value)
                if existing.label == existing.id and incoming.label != incoming.id:
                    existing.label = incoming.label
            for incoming in patch.links:
                existing = links.get(incoming.id)
                if existing is None:
                    links[incoming.id] = incoming.model_copy(deep=True)
                    continue
                existing.health = worst_health(existing.health, incoming.health)
                existing.origin = sorted(set(existing.origin + incoming.origin))
                attributes = dict(incoming.attributes)
                if (
                    incoming.source == existing.target
                    and incoming.target == existing.source
                ):
                    if incoming.layer == "bgp":
                        for suffix in ("address", "as"):
                            local_value = attributes.pop(f"local_{suffix}", None)
                            remote_value = attributes.pop(f"remote_{suffix}", None)
                            if remote_value is not None:
                                attributes[f"local_{suffix}"] = remote_value
                            if local_value is not None:
                                attributes[f"remote_{suffix}"] = local_value
                    for suffix in {
                        key.removeprefix("source_")
                        for key in attributes
                        if key.startswith("source_")
                    } | {
                        key.removeprefix("target_")
                        for key in attributes
                        if key.startswith("target_")
                    }:
                        source_value = attributes.pop(f"source_{suffix}", None)
                        target_value = attributes.pop(f"target_{suffix}", None)
                        if target_value is not None:
                            attributes[f"source_{suffix}"] = target_value
                        if source_value is not None:
                            attributes[f"target_{suffix}"] = source_value
                if "netbox" in incoming.origin or patch.name == "bgp":
                    existing.attributes.update(attributes)
                else:
                    for key, value in attributes.items():
                        existing.attributes.setdefault(key, value)
                existing.metrics.update(incoming.metrics)

        for link in links.values():
            for side in ("source", "target"):
                device = getattr(link, side)
                interface = link.attributes.get(f"{side}_interface")
                observation = observations.get(_endpoint(device, interface))
                if not observation:
                    continue
                link.health = worst_health(link.health, observation["health"])
                for key, value in observation.get("attributes", {}).items():
                    link.attributes[f"{side}_{key}"] = value
                for key, value in observation.get("metrics", {}).items():
                    link.metrics[f"{side}_{key}"] = value
            for node_id in (link.source, link.target):
                if node_id not in nodes:
                    nodes[node_id] = TopologyNode(
                        id=node_id,
                        label=node_id,
                        health=link.health,
                        layers=[link.layer],
                        origin=list(link.origin),
                    )
        return nodes, links

    def health(self) -> dict[str, Any]:
        """Return safe process and collection status for the local UI."""
        return {
            "status": "ok" if self.last_error is None else "degraded",
            "collector_running": self.running,
            "last_started_at": self.last_started_at,
            "last_completed_at": self.last_completed_at,
            "last_error": self.last_error,
            "snapshot_count": self.history.count(),
            "selected_devices": list(self.selected_devices),
        }
