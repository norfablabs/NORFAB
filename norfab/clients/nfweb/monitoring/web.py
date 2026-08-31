"""Tornado routes and WebSocket publication for NFWeb monitoring."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import tornado.websocket

from norfab.clients.nfweb.monitoring.collector import MonitoringCollector
from norfab.clients.nfweb.monitoring.models import MonitoringSnapshot
from norfab.clients.nfweb.server import NFWebJSONHandler, _json

log = logging.getLogger(__name__)


class MonitoringBroadcaster:
    """Publish monitoring samples to connected browsers."""

    def __init__(self) -> None:
        self.connections: set[MonitoringWebSocket] = set()

    async def publish(self, snapshot: MonitoringSnapshot) -> None:
        """Send a completed monitoring sample to every browser."""
        message = _json({"type": "snapshot", "data": snapshot}).decode("utf-8")
        for connection in tuple(self.connections):
            try:
                await connection.write_message(message)
            except Exception:
                self.connections.discard(connection)
                log.warning("Removed failed NFWeb monitoring WebSocket")


class MonitoringSnapshotHandler(NFWebJSONHandler):
    def initialize(self, monitoring_collector: MonitoringCollector) -> None:
        self.monitoring_collector = monitoring_collector

    def get(self) -> None:
        """Return the latest sample."""
        if self.monitoring_collector.latest is None:
            self.write_json({"error": "monitoring data is not available"}, status=503)
            return
        self.write_json(self.monitoring_collector.latest)


class MonitoringHistoryHandler(MonitoringSnapshotHandler):
    def get(self) -> None:
        """Return the bounded in-memory sample history."""
        self.write_json(list(self.monitoring_collector.history))


class MonitoringRefreshHandler(MonitoringSnapshotHandler):
    async def post(self) -> None:
        """Collect and return one fresh sample."""
        if self.monitoring_collector.collecting:
            self.write_json(
                {"error": "monitoring collection is already in progress"}, status=409
            )
            return
        snapshot = await self.monitoring_collector.collect()
        if snapshot is None:
            self.write_json({"error": "monitoring collection failed"}, status=500)
            return
        self.write_json(snapshot)


class MonitoringWorkerDatabaseHandler(MonitoringSnapshotHandler):
    async def get(self, worker_name: str) -> None:
        """Return recent job database statistics for one selected worker."""
        try:
            statistics = await asyncio.to_thread(
                self.monitoring_collector.worker_database_stats,
                worker_name,
            )
        except LookupError as exc:
            self.write_json({"error": str(exc)}, status=404)
            return
        except Exception as exc:
            log.warning("Worker job database statistics unavailable: %s", exc)
            self.write_json({"error": str(exc)}, status=502)
            return
        self.write_json(statistics)


class MonitoringWebSocket(tornado.websocket.WebSocketHandler):
    """Push live monitoring samples to connected browsers."""

    def initialize(
        self,
        monitoring_collector: MonitoringCollector,
        monitoring_broadcaster: MonitoringBroadcaster,
    ) -> None:
        self.monitoring_collector = monitoring_collector
        self.monitoring_broadcaster = monitoring_broadcaster

    def check_origin(self, _origin: str) -> bool:
        return True

    async def open(self) -> None:
        self.monitoring_broadcaster.connections.add(self)
        if self.monitoring_collector.latest is not None:
            await self.write_message(
                _json(
                    {"type": "snapshot", "data": self.monitoring_collector.latest}
                ).decode("utf-8")
            )

    def on_close(self) -> None:
        self.monitoring_broadcaster.connections.discard(self)


def monitoring_routes(
    monitoring_collector: MonitoringCollector,
    monitoring_broadcaster: MonitoringBroadcaster,
) -> list[Any]:
    """Return all routes owned by the monitoring application."""
    dependencies = {"monitoring_collector": monitoring_collector}
    return [
        (
            r"/api/v1/monitoring/snapshot",
            MonitoringSnapshotHandler,
            dependencies,
        ),
        (
            r"/api/v1/monitoring/history",
            MonitoringHistoryHandler,
            dependencies,
        ),
        (
            r"/api/v1/monitoring/refresh",
            MonitoringRefreshHandler,
            dependencies,
        ),
        (
            r"/api/v1/monitoring/workers/([^/]+)/database",
            MonitoringWorkerDatabaseHandler,
            dependencies,
        ),
        (
            r"/api/v1/monitoring/stream",
            MonitoringWebSocket,
            {
                "monitoring_collector": monitoring_collector,
                "monitoring_broadcaster": monitoring_broadcaster,
            },
        ),
    ]
