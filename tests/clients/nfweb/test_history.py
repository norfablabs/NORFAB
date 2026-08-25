from datetime import datetime, timedelta, timezone
from pathlib import Path

from norfab.clients.nfweb.topology.history import TopologyHistoryStore
from norfab.clients.nfweb.topology.models import (
    TopologyCollectionEvent,
    TopologyNode,
    TopologySnapshot,
)


def _snapshot(collected_at: datetime, node_id: str) -> TopologySnapshot:
    return TopologySnapshot(
        collected_at=collected_at,
        status="complete",
        devices=[node_id],
        layers=["inventory"],
        nodes=[TopologyNode(id=node_id, label=node_id)],
    )


def test_history_round_trip(tmp_path: Path) -> None:
    store = TopologyHistoryStore(tmp_path / "nfweb.sqlite", retention_minutes=180)
    now = datetime.now(timezone.utc)
    first = _snapshot(now - timedelta(minutes=2), "r1")
    second = _snapshot(now, "r2")

    store.insert(first)
    store.insert(second)

    assert store.count() == 2
    assert store.latest() == second
    assert store.get(first.snapshot_id) == first
    assert [entry.snapshot_id for entry in store.history()] == [
        first.snapshot_id,
        second.snapshot_id,
    ]
    assert store.history()[0].collected_at == first.collected_at
    assert [entry.snapshot_id for entry in store.history(["r1"])] == [first.snapshot_id]
    assert store.latest(["r1"]) == first
    store.close()


def test_history_cleanup_is_bounded(tmp_path: Path) -> None:
    store = TopologyHistoryStore(tmp_path / "nfweb.sqlite", retention_minutes=180)
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(now, "r1")
    store.insert(snapshot)

    removed = store.cleanup(now=now + timedelta(minutes=181))

    assert removed == 1
    assert store.count() == 0
    store.close()


def test_logs_are_scope_aware_and_bounded_to_300(tmp_path: Path) -> None:
    store = TopologyHistoryStore(tmp_path / "nfweb.sqlite", retention_minutes=180)
    snapshot = _snapshot(datetime.now(timezone.utc), "r1")
    snapshot.events = [
        TopologyCollectionEvent(
            service="nornir",
            task="parse_ttp",
            worker="worker-1",
            status="running",
            message=f"event {index}",
        )
        for index in range(305)
    ]
    store.insert(snapshot)

    logs = store.logs(["r1"])

    assert len(logs) == 300
    assert logs[0].message == "event 5"
    assert logs[-1].message == "event 304"
    assert store.logs(["r2"]) == []
    store.close()
