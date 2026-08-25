"""Topology application composition for the shared NFWeb runtime."""

from pathlib import Path
from typing import Any

from norfab.clients.nfweb.topology.collector import TopologyCollector
from norfab.clients.nfweb.topology.config import TopologyConfig
from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.web import (
    TopologySnapshotBroadcaster,
    topology_routes,
)


class TopologyApplication:
    """Own topology collection, storage, publication, and browser routes."""

    name = "topology"

    def __init__(
        self,
        collector: TopologyCollector,
        history: TopologyHistoryStore,
        broadcaster: TopologySnapshotBroadcaster,
    ) -> None:
        self.collector = collector
        self.history = history
        self.broadcaster = broadcaster

    @classmethod
    def create(
        cls,
        client: Any,
        config: TopologyConfig,
        database_path: str | Path,
    ) -> "TopologyApplication":
        """Build the topology application from runtime-owned dependencies."""
        history = TopologyHistoryStore(database_path, config.retention_minutes)
        try:
            broadcaster = TopologySnapshotBroadcaster()
            collector = TopologyCollector(
                client=client,
                config=config,
                history=history,
                on_snapshot=broadcaster.publish,
            )
            return cls(collector, history, broadcaster)
        except Exception:
            history.close()
            raise

    def routes(self) -> list[Any]:
        """Return topology's namespaced browser routes."""
        return topology_routes(self.collector, self.history, self.broadcaster)

    def health(self) -> dict[str, Any]:
        """Return topology collector health."""
        return self.collector.health()

    async def start(self) -> None:
        """Start the shared topology collector."""
        await self.collector.start()

    async def stop(self) -> None:
        """Stop collection before closing its history store."""
        try:
            await self.collector.stop()
        finally:
            self.history.close()
