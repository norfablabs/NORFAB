"""Tornado browser boundary for the NFWeb topology application."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import orjson
import tornado.websocket

from norfab.clients.nfweb.server import NFWebJSONHandler, _json, is_loopback_host
from norfab.clients.nfweb.topology.collector import TopologyCollector
from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.models import TopologySnapshot

log = logging.getLogger(__name__)


class TopologySnapshotBroadcaster:
    """Publish completed topology snapshots to connected browsers."""

    def __init__(self) -> None:
        self.connections: set[TopologyWebSocket] = set()

    async def publish(self, snapshot: TopologySnapshot) -> None:
        """Send one snapshot to every currently connected browser."""
        message = _json({"type": "snapshot", "data": snapshot}).decode("utf-8")
        for connection in tuple(self.connections):
            try:
                await connection.write_message(message)
            except Exception:
                self.connections.discard(connection)
                log.warning("Removed failed NFWeb topology WebSocket", exc_info=True)


class TopologyAPIHandler(NFWebJSONHandler):
    """Base class for topology history routes."""

    def initialize(self, topology_history: TopologyHistoryStore) -> None:
        self.topology_history = topology_history


class TopologySnapshotHandler(TopologyAPIHandler):
    def get(self, snapshot_id: str) -> None:
        snapshot = self.topology_history.get(snapshot_id)
        if snapshot is None:
            self.write_json({"error": "topology snapshot was not found"}, status=404)
            return
        self.write_json(snapshot)


class TopologyHistoryHandler(TopologyAPIHandler):
    def initialize(
        self,
        topology_history: TopologyHistoryStore,
        topology_collector: TopologyCollector,
    ) -> None:
        self.topology_history = topology_history
        self.topology_collector = topology_collector

    def get(self) -> None:
        if not self.topology_collector.selected_devices:
            self.write_json([])
            return
        self.write_json(
            self.topology_history.history(self.topology_collector.selected_devices)
        )


class TopologyLogsHandler(TopologyHistoryHandler):
    """Return the bounded persistent log for the active topology scope."""

    def get(self) -> None:
        if not self.topology_collector.selected_devices:
            self.write_json([])
            return
        self.write_json(
            self.topology_history.logs(
                self.topology_collector.selected_devices, limit=300
            )
        )


class TopologyRefreshHandler(NFWebJSONHandler):
    """Trigger one cache-bypassing topology collection."""

    def initialize(self, topology_collector: TopologyCollector) -> None:
        self.topology_collector = topology_collector

    async def post(self) -> None:
        if not self.is_local_post("topology-refresh"):
            self.write_json({"error": "invalid NFWeb request"}, status=403)
            return
        if self.topology_collector.collecting:
            self.write_json(
                {"error": "topology collection is already in progress"}, status=409
            )
            return
        if not self.topology_collector.selected_devices:
            self.write_json(
                {"error": "select at least one device before collecting"}, status=400
            )
            return
        snapshot = await self.topology_collector.collect(force=True)
        if snapshot is None:
            self.write_json(
                {"error": self.topology_collector.last_error or "collection failed"},
                status=500,
            )
            return
        self.write_json(snapshot)


class TopologyDevicesHandler(NFWebJSONHandler):
    """Return the combined NetBox and Nornir device inventory."""

    def initialize(self, topology_collector: TopologyCollector) -> None:
        self.topology_collector = topology_collector

    async def get(self) -> None:
        self.write_json(await self.topology_collector.device_inventory())


class TopologySelectionHandler(NFWebJSONHandler):
    """Apply the topology device scope and collect it when non-empty."""

    def initialize(self, topology_collector: TopologyCollector) -> None:
        self.topology_collector = topology_collector

    async def post(self) -> None:
        if not self.is_local_post("topology-selection"):
            self.write_json({"error": "invalid NFWeb request"}, status=403)
            return
        if self.topology_collector.collecting:
            self.write_json(
                {"error": "topology collection is already in progress"}, status=409
            )
            return
        try:
            body = orjson.loads(self.request.body or b"{}")
            devices = body.get("devices")
            if not isinstance(devices, list) or not all(
                isinstance(device, str) and device for device in devices
            ):
                raise ValueError("devices must be a list of device names")
            snapshot = await self.topology_collector.select_devices(devices)
        except (orjson.JSONDecodeError, AttributeError, ValueError) as exc:
            self.write_json({"error": str(exc)}, status=400)
            return
        self.write_json(
            {
                "selected": self.topology_collector.selected_devices,
                "snapshot": snapshot,
            }
        )


class TopologyWebSocket(tornado.websocket.WebSocketHandler):
    """Push snapshots from the local collector to the local browser."""

    def initialize(
        self,
        topology_broadcaster: TopologySnapshotBroadcaster,
        topology_history: TopologyHistoryStore,
        topology_collector: TopologyCollector,
    ) -> None:
        self.topology_broadcaster = topology_broadcaster
        self.topology_history = topology_history
        self.topology_collector = topology_collector

    def check_origin(self, origin: str) -> bool:
        """Allow only the exact loopback origin that opened this socket."""
        if not origin or not is_loopback_host(self.request.host):
            return False
        parsed = urlparse(origin)
        return (
            parsed.scheme == "http"
            and is_loopback_host(parsed.netloc)
            and parsed.netloc == self.request.host
        )

    async def open(self) -> None:
        self.topology_broadcaster.connections.add(self)
        latest = self.topology_history.latest(self.topology_collector.selected_devices)
        if latest is not None and self.topology_collector.selected_devices:
            await self.write_message(
                _json({"type": "snapshot", "data": latest}).decode("utf-8")
            )

    def on_close(self) -> None:
        self.topology_broadcaster.connections.discard(self)


def topology_routes(
    topology_collector: TopologyCollector,
    topology_history: TopologyHistoryStore,
    topology_broadcaster: TopologySnapshotBroadcaster,
) -> list[Any]:
    """Return all routes owned by the topology application."""
    return [
        (
            r"/api/v1/topology/snapshots/([a-f0-9]+)",
            TopologySnapshotHandler,
            {"topology_history": topology_history},
        ),
        (
            r"/api/v1/topology/history",
            TopologyHistoryHandler,
            {
                "topology_history": topology_history,
                "topology_collector": topology_collector,
            },
        ),
        (
            r"/api/v1/topology/logs",
            TopologyLogsHandler,
            {
                "topology_history": topology_history,
                "topology_collector": topology_collector,
            },
        ),
        (
            r"/api/v1/topology/devices",
            TopologyDevicesHandler,
            {"topology_collector": topology_collector},
        ),
        (
            r"/api/v1/topology/selection",
            TopologySelectionHandler,
            {"topology_collector": topology_collector},
        ),
        (
            r"/api/v1/topology/refresh",
            TopologyRefreshHandler,
            {"topology_collector": topology_collector},
        ),
        (
            r"/api/v1/topology/stream",
            TopologyWebSocket,
            {
                "topology_broadcaster": topology_broadcaster,
                "topology_history": topology_history,
                "topology_collector": topology_collector,
            },
        ),
    ]
