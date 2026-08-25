import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

from norfab.clients.nfweb.server import make_nfweb_application
from norfab.clients.nfweb.topology.application import TopologyApplication
from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.models import (
    TopologyCollectionEvent,
    TopologySnapshot,
)
from norfab.clients.nfweb.topology.web import TopologySnapshotBroadcaster


class FakeCollector:
    def __init__(self, snapshot: TopologySnapshot) -> None:
        self.snapshot = snapshot
        self.last_error = None
        self.collecting = False
        self.force_values: list[bool] = []
        self.selected_devices = ["r1"]

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "collector_running": True,
            "snapshot_count": 1,
        }

    async def collect(self, force: bool = False) -> TopologySnapshot:
        self.force_values.append(force)
        return self.snapshot

    async def device_inventory(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": "r1", "sources": ["netbox", "nornir"]},
                {"name": "r2", "sources": ["netbox"]},
            ],
            "selected": self.selected_devices,
            "errors": [],
        }

    async def select_devices(self, devices: list[str]) -> TopologySnapshot | None:
        self.selected_devices = devices
        return self.snapshot if devices else None


class TestNFWebApplication(AsyncHTTPTestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory(prefix="nfweb-test-")
        self.temporary_directory = Path(self._temporary_directory.name)
        self.static_path = self.temporary_directory / "static"
        self.static_path.mkdir()
        (self.static_path / "index.html").write_text("<h1>NFWeb</h1>", encoding="utf-8")
        self.topology_history = TopologyHistoryStore(
            self.temporary_directory / "nfweb.sqlite"
        )
        self.snapshot = TopologySnapshot(
            collected_at=datetime.now(timezone.utc),
            status="empty",
            devices=["r1"],
            events=[
                TopologyCollectionEvent(
                    service="nornir",
                    task="parse_ttp",
                    message="collection started",
                )
            ],
        )
        self.topology_history.insert(self.snapshot)
        self.collector = FakeCollector(self.snapshot)
        super().setUp()

    def get_app(self) -> Application:
        topology = TopologyApplication(
            self.collector,
            self.topology_history,
            TopologySnapshotBroadcaster(),
        )
        return make_nfweb_application([topology], static_path=self.static_path)

    def tearDown(self) -> None:
        super().tearDown()
        self.topology_history.close()
        self._temporary_directory.cleanup()

    def test_health_route(self) -> None:
        health = self.fetch("/api/v1/health")

        assert health.code == 200
        assert (
            json.loads(health.body)["applications"]["topology"]["collector_running"]
            is True
        )

    def test_no_arbitrary_job_route_exists(self) -> None:
        response = self.fetch("/api/v1/job/run", method="POST", body=b"{}")

        assert response.code == 405

    def test_refresh_route_forces_collection(self) -> None:
        response = self.fetch(
            "/api/v1/topology/refresh",
            method="POST",
            headers={
                "Origin": self.get_url("/").rstrip("/"),
                "X-NFWeb-Request": "topology-refresh",
            },
            body=b"",
        )

        assert response.code == 200
        assert json.loads(response.body)["snapshot_id"] == self.snapshot.snapshot_id
        assert self.collector.force_values == [True]

    def test_refresh_route_rejects_cross_origin_request(self) -> None:
        response = self.fetch(
            "/api/v1/topology/refresh",
            method="POST",
            headers={
                "Origin": "http://example.com",
                "X-NFWeb-Request": "topology-refresh",
            },
            body=b"",
        )

        assert response.code == 403
        assert self.collector.force_values == []

    def test_api_rejects_non_loopback_host_header(self) -> None:
        response = self.fetch(
            "/api/v1/health",
            headers={"Host": "attacker.example"},
        )

        assert response.code == 403

    def test_devices_route_returns_combined_inventory(self) -> None:
        response = self.fetch("/api/v1/topology/devices")

        assert response.code == 200
        assert json.loads(response.body)["devices"][0] == {
            "name": "r1",
            "sources": ["netbox", "nornir"],
        }

    def test_logs_route_returns_active_scope_events(self) -> None:
        response = self.fetch("/api/v1/topology/logs")

        assert response.code == 200
        log = json.loads(response.body)[0]
        assert log["message"] == "collection started"
        assert log["snapshot_id"] == self.snapshot.snapshot_id

    def test_selection_route_applies_scope(self) -> None:
        response = self.fetch(
            "/api/v1/topology/selection",
            method="POST",
            headers={
                "Origin": self.get_url("/").rstrip("/"),
                "X-NFWeb-Request": "topology-selection",
                "Content-Type": "application/json",
            },
            body=json.dumps({"devices": ["r2"]}),
        )

        assert response.code == 200
        assert json.loads(response.body)["selected"] == ["r2"]
        assert self.collector.selected_devices == ["r2"]

    def test_refresh_requires_selected_devices(self) -> None:
        self.collector.selected_devices = []

        response = self.fetch(
            "/api/v1/topology/refresh",
            method="POST",
            headers={
                "Origin": self.get_url("/").rstrip("/"),
                "X-NFWeb-Request": "topology-refresh",
            },
            body=b"",
        )

        assert response.code == 400
        assert self.collector.force_values == []

    def test_packaged_index_is_served_with_browser_policy(self) -> None:
        response = self.fetch("/")

        assert response.code == 200
        assert response.body == b"<h1>NFWeb</h1>"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
        assert (
            f"ws://{response.effective_url.removeprefix('http://').rstrip('/')}"
            in response.headers["Content-Security-Policy"]
        )
        assert " ws:;" not in response.headers["Content-Security-Policy"]


def test_application_requires_built_frontend(tmp_path: Path) -> None:
    class EmptyApplication:
        name = "empty"

        def routes(self) -> list[Any]:
            return []

        def health(self) -> dict[str, str]:
            return {"status": "ok"}

    with pytest.raises(FileNotFoundError, match="frontend is not built"):
        make_nfweb_application([EmptyApplication()], static_path=tmp_path)
