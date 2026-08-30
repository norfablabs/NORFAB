"""Monitoring application composition for the shared NFWeb runtime."""

from typing import Any

from norfab.clients.nfweb.monitoring.collector import MonitoringCollector
from norfab.clients.nfweb.monitoring.config import MonitoringConfig
from norfab.clients.nfweb.monitoring.web import (
    MonitoringBroadcaster,
    monitoring_routes,
)


class MonitoringApplication:
    """Own monitoring collection, in-memory history, and browser routes."""

    name = "monitoring"

    def __init__(
        self,
        collector: MonitoringCollector,
        broadcaster: MonitoringBroadcaster,
    ) -> None:
        self.collector = collector
        self.broadcaster = broadcaster

    @classmethod
    def create(cls, client: Any, config: MonitoringConfig) -> "MonitoringApplication":
        """Build the monitoring application from runtime-owned dependencies."""
        broadcaster = MonitoringBroadcaster()
        collector = MonitoringCollector(client, config, broadcaster.publish)
        return cls(collector, broadcaster)

    def routes(self) -> list[Any]:
        return monitoring_routes(self.collector, self.broadcaster)

    def health(self) -> dict[str, Any]:
        return self.collector.health()

    async def start(self) -> None:
        await self.collector.start()

    async def stop(self) -> None:
        await self.collector.stop()
