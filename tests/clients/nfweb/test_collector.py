import asyncio
import threading
from pathlib import Path
from typing import Any, Iterator

from norfab.clients.nfweb.topology.collector import TopologyCollector
from norfab.clients.nfweb.topology.config import TopologyConfig
from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.layers import (
    CollectionContext,
    InterfacesLayer,
    LLDPLayer,
    _submit_job,
    discover_device_options,
)
from norfab.clients.nfweb.topology.models import LayerPatch


class CompletedFuture:
    def __init__(
        self,
        result: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        self._result = result
        self._events = events or []
        self.done_event = threading.Event()
        self.done_event.set()

    def result(self, timeout: int) -> dict[str, Any]:
        return self._result

    def events(self, timeout: int) -> Iterator[dict[str, Any]]:
        yield from self._events


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def _job_result(self, service: str, task: str, **options: Any) -> dict[str, Any]:
        kwargs = options.get("kwargs", {})
        self.calls.append((service, task, kwargs))
        if (service, task) == ("netbox", "get_devices"):
            return {"netbox-worker": {"result": {"r1": {}, "r2": {}}, "errors": []}}
        if (service, task) == ("nornir", "get_nornir_hosts"):
            return {
                "nornir-worker": {
                    "result": ["r1", "nornir-only"],
                    "errors": [],
                }
            }
        if (service, task) == ("netbox", "get_topology"):
            return {
                "netbox-worker": {
                    "errors": [],
                    "result": {
                        "nodes": [
                            {
                                "id": "r1",
                                "name": "r1",
                                "ip": "10.0.0.1/32",
                                "status": "active",
                                "site": "dc1",
                            },
                            {
                                "id": "r2",
                                "name": "r2",
                                "ip": "10.0.0.2/32",
                                "status": "active",
                                "site": "dc1",
                            },
                        ],
                        "links": [
                            {
                                "source": "r1",
                                "target": "r2",
                                "src_iface": "Ethernet1",
                                "dst_iface": "Ethernet1",
                                "cable_status": "connected",
                            }
                        ],
                    },
                }
            }
        if (service, task) == ("nornir", "parse_ttp"):
            if kwargs["get"] == "lldp_neighbors":
                result = {
                    "r1": [
                        {
                            "interface": "Ethernet1",
                            "remote_device": "r2",
                            "remote_interface": "Ethernet1",
                            "remote_chassi_id": "001c.7300.0001",
                            "remote_device_management_ip": "10.0.0.2",
                        }
                    ],
                    "r2": [
                        {
                            "interface": "Ethernet1",
                            "remote_device": "r1",
                            "remote_interface": "Ethernet1",
                        }
                    ],
                }
            elif kwargs["get"] == "bgp_neighbors":
                result = {
                    "r1": [{"remote_address": "10.0.0.2", "state": "established"}],
                    "r2": [{"remote_address": "10.0.0.1", "state": "idle"}],
                }
            elif kwargs["get"] == "interfaces_status":
                result = {
                    "r1": [
                        {
                            "name": "Ethernet1",
                            "status_admin": "up",
                            "status_oper": "up",
                            "speed_bps": 100_000_000_000,
                            "output_utilization": 42,
                        }
                    ],
                    "r2": [
                        {
                            "name": "Ethernet1",
                            "status_admin": "up",
                            "status_oper": "down",
                            "errors_in": 7,
                        }
                    ],
                }
            else:
                raise AssertionError(f"unexpected TTP getter: {kwargs['get']}")
            return {"nornir-worker": {"result": result, "errors": []}}
        raise AssertionError(f"unexpected job: {service}:{task}")

    def submit_job(self, service: str, task: str, **options: Any) -> CompletedFuture:
        return CompletedFuture(self._job_result(service, task, **options))


def test_submit_job_captures_norfab_events() -> None:
    class EventClient:
        def submit_job(self, **kwargs: Any) -> CompletedFuture:
            return CompletedFuture(
                {"worker": {"result": {}, "errors": []}},
                [
                    {
                        "message": "fetched 2 devices",
                        "severity": "INFO",
                        "task": "get_topology",
                        "worker": "netbox-worker",
                        "status": "running",
                        "timestamp": "24-Aug-2026 10:00:00.000",
                    }
                ],
            )

    context = CollectionContext(config=TopologyConfig())

    result = asyncio.run(
        _submit_job(
            EventClient(),
            context,
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"device_regex": ".*"},
            timeout=60,
        )
    )

    assert result == {"worker": {"result": {}, "errors": []}}
    assert context.events[0].service == "netbox"
    assert context.events[0].worker == "netbox-worker"
    assert context.events[0].message == "fetched 2 devices"


def test_submit_job_wait_does_not_block_event_loop() -> None:
    future = CompletedFuture({"worker": {"result": {}, "errors": []}})
    future.done_event.clear()

    class EventClient:
        def submit_job(self, **kwargs: Any) -> CompletedFuture:
            return future

    async def exercise() -> dict[str, Any]:
        context = CollectionContext(config=TopologyConfig())
        task = asyncio.create_task(
            _submit_job(
                EventClient(),
                context,
                "netbox",
                "get_topology",
                workers="any",
                kwargs={},
                timeout=60,
            )
        )
        await asyncio.sleep(0)
        assert not task.done()
        future.done_event.set()
        return await task

    assert asyncio.run(exercise()) == {"worker": {"result": {}, "errors": []}}


def test_device_discovery_combines_netbox_and_nornir() -> None:
    options, errors = asyncio.run(
        discover_device_options(FakeClient(), TopologyConfig())
    )

    assert errors == []
    assert [(option.name, option.sources) for option in options] == [
        ("nornir-only", ["nornir"]),
        ("r1", ["netbox", "nornir"]),
        ("r2", ["netbox"]),
    ]


def test_lldp_normalizes_reverse_device_and_interface_names() -> None:
    class AliasClient(FakeClient):
        def _job_result(
            self, service: str, task: str, **options: Any
        ) -> dict[str, Any]:
            getter = options["kwargs"]["get"]
            if getter == "lldp_neighbors":
                result = {
                    "R1": [
                        {
                            "interface": "Ethernet1",
                            "remote_device": "r2.example.com.",
                            "remote_interface": "Et1",
                        }
                    ],
                    "r2": [
                        {
                            "interface": "Et1",
                            "remote_device": "r1.example.com",
                            "remote_interface": "Eth1",
                        }
                    ],
                }
            elif getter == "interfaces_status":
                result = {
                    "r1": [
                        {
                            "name": "Et1",
                            "status_oper": "up",
                            "output_utilization": 27,
                        }
                    ],
                    "R2": [{"name": "Ethernet1", "status_oper": "down"}],
                }
            else:
                raise AssertionError(f"unexpected getter: {getter}")
            return {"nornir-worker": {"result": result, "errors": []}}

    context = CollectionContext(
        config=TopologyConfig(devices=["r1", "r2"]),
        devices=["r1", "r2"],
    )
    client = AliasClient()
    async def collect_layers() -> tuple[LayerPatch, LayerPatch]:
        lldp = await LLDPLayer().collect(client, context)
        interfaces = await InterfacesLayer().collect(client, context)
        return lldp, interfaces

    lldp, interfaces = asyncio.run(collect_layers())
    _, links = TopologyCollector._merge([lldp, interfaces])

    assert list(links) == ["lldp:r1:ethernet1--r2:ethernet1"]
    link = next(iter(links.values()))
    assert {link.source, link.target} == {"r1", "r2"}
    assert link.metrics["source_output_utilization"] == 27
    assert link.health == "critical"


def test_collector_merges_live_layers_and_interface_health(tmp_path: Path) -> None:
    client = FakeClient()
    config = TopologyConfig(devices=["r1", "r2"])
    history = TopologyHistoryStore(tmp_path / "nfweb.sqlite")
    collector = TopologyCollector(client=client, config=config, history=history)

    snapshot = asyncio.run(collector.collect_once())

    assert snapshot.status == "complete"
    assert snapshot.layers == ["inventory", "lldp", "bgp", "interfaces"]
    assert {node.id for node in snapshot.nodes} == {"r1", "r2"}
    assert next(node for node in snapshot.nodes if node.id == "r2").health == "healthy"
    inventory_link = next(link for link in snapshot.links if link.layer == "inventory")
    assert inventory_link.health == "critical"
    assert inventory_link.metrics["source_output_utilization"] == 42
    assert inventory_link.metrics["target_errors_in"] == 7
    assert inventory_link.attributes["source_status_oper"] == "up"
    lldp_link = next(link for link in snapshot.links if link.layer == "lldp")
    assert lldp_link.attributes["remote_chassi_id"] == "001c.7300.0001"
    assert all(task != "crud_read" for _, task, _ in client.calls)
    assert all(task != "get_devices" for _, task, _ in client.calls)
    topology_call = next(
        call for call in client.calls if call[:2] == ("netbox", "get_topology")
    )
    assert topology_call[2] == {"devices": ["r1", "r2"]}
    first_collection_calls = len(client.calls)
    asyncio.run(collector.collect_once())
    assert len(client.calls) == first_collection_calls
    asyncio.run(collector.collect_once(force=True))
    assert len(client.calls) > first_collection_calls
    asyncio.run(collector.stop())
    history.close()


def test_collector_reports_partial_worker_failure(tmp_path: Path) -> None:
    class PartialClient(FakeClient):
        def _job_result(
            self, service: str, task: str, **options: Any
        ) -> dict[str, Any]:
            if service == "nornir":
                return {
                    "nornir-worker": {
                        "failed": True,
                        "errors": ["device connection failed"],
                        "result": None,
                    }
                }
            return super()._job_result(service, task, **options)

    history = TopologyHistoryStore(tmp_path / "nfweb.sqlite")
    collector = TopologyCollector(
        PartialClient(), TopologyConfig(devices=["r1", "r2"]), history
    )

    snapshot = asyncio.run(collector.collect_once())

    assert snapshot.status == "partial"
    assert snapshot.nodes
    assert any("device connection failed" in error.message for error in snapshot.errors)
    asyncio.run(collector.stop())
    history.close()


def test_collector_keeps_partial_worker_payload(tmp_path: Path) -> None:
    class PartialPayloadClient(FakeClient):
        def _job_result(
            self, service: str, task: str, **options: Any
        ) -> dict[str, Any]:
            response = super()._job_result(service, task, **options)
            if service == "netbox" and task == "get_topology":
                response["netbox-worker"]["errors"] = ["one cable could not be read"]
            return response

    history = TopologyHistoryStore(tmp_path / "nfweb.sqlite")
    collector = TopologyCollector(
        PartialPayloadClient(), TopologyConfig(devices=["r1", "r2"]), history
    )

    snapshot = asyncio.run(collector.collect_once())

    assert snapshot.status == "partial"
    assert {node.id for node in snapshot.nodes} == {"r1", "r2"}
    assert any(
        "one cable could not be read" in error.message for error in snapshot.errors
    )
    asyncio.run(collector.stop())
    history.close()


def test_empty_selection_does_not_collect(tmp_path: Path) -> None:
    client = FakeClient()
    history = TopologyHistoryStore(tmp_path / "nfweb.sqlite")
    collector = TopologyCollector(client, TopologyConfig(), history)

    assert asyncio.run(collector.collect()) is None
    assert client.calls == []
    assert history.count() == 0

    asyncio.run(collector.stop())
    history.close()


def test_device_selection_collects_selected_scope(tmp_path: Path) -> None:
    client = FakeClient()
    history = TopologyHistoryStore(tmp_path / "nfweb.sqlite")
    collector = TopologyCollector(client, TopologyConfig(), history)

    snapshot = asyncio.run(collector.select_devices(["r1"]))

    assert snapshot is not None
    assert snapshot.devices == ["r1"]
    assert history.count() == 1
    topology_call = next(
        call for call in client.calls if call[:2] == ("netbox", "get_topology")
    )
    assert topology_call[2] == {"devices": ["r1"]}

    asyncio.run(collector.stop())
    history.close()
