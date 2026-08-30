"""NFWeb in-memory monitoring collection tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from norfab.clients.nfweb.monitoring.collector import MonitoringCollector
from norfab.clients.nfweb.monitoring.config import MonitoringConfig


def make_client() -> Mock:
    client = Mock()
    client.name = "nfweb"
    client.stats_send_to_broker = 12
    client.stats_recv_from_broker = 18
    client.stats_reconnect_to_broker = 1
    client.recv_thread.is_alive.return_value = True
    client.outbound_queue.qsize.return_value = 2
    client.mmi.side_effect = [
        {
            "status": "200",
            "results": {
                "status": "active",
                "cpu_percent": 8.5,
                "memory_rss_mbyte": 48.0,
                "uptime_seconds": 3600,
                "workers count": 1,
                "services count": 1,
            },
            "errors": [],
        },
        {
            "status": "200",
            "results": [
                {
                    "name": "nornir-worker-1",
                    "service": "nornir",
                    "status": "alive",
                    "holdtime": "12.5",
                    "keepalives tx/rx": "40 / 39",
                    "alive (s)": "300",
                }
            ],
            "errors": [],
        },
    ]
    client.run_job.return_value = {
        "nornir-worker-1": {
            "service": "nornir",
            "failed": False,
            "result": {
                "worker_cpu_percent": 23.0,
                "worker_ram_usage_mbyte": 128.0,
                "uptime_seconds": 300,
            },
        }
    }
    return client


def test_collect_once_merges_existing_status_interfaces() -> None:
    process = Mock()
    process.cpu_percent.side_effect = [0.0, 4.5]
    process.memory_info.return_value = Mock(rss=96 * 1024 * 1024)

    with patch(
        "norfab.clients.nfweb.monitoring.collector.psutil.Process",
        return_value=process,
    ):
        collector = MonitoringCollector(make_client(), MonitoringConfig())
        snapshot = collector.collect_once()

    assert snapshot.status == "complete"
    assert snapshot.broker.cpu_percent == 8.5
    assert snapshot.client.memory_mbyte == 96
    assert snapshot.client.messages_received == 18
    assert snapshot.workers[0].cpu_percent == 23.0
    assert snapshot.workers[0].keepalives_received == 39
    assert snapshot.workers[0].holdtime_seconds == 12.5


def test_history_is_memory_only_and_removes_expired_samples() -> None:
    process = Mock()
    process.cpu_percent.return_value = 0.0
    process.memory_info.return_value = Mock(rss=1)

    with patch(
        "norfab.clients.nfweb.monitoring.collector.psutil.Process",
        return_value=process,
    ):
        collector = MonitoringCollector(
            make_client(), MonitoringConfig(retention_minutes=1)
        )

    old = collector.collect_once()
    old.collected_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    collector.history.append(old)
    current = old.model_copy(deep=True)
    current.collected_at = datetime.now(timezone.utc)
    collector.collect_once = Mock(return_value=current)

    asyncio.run(collector.collect())

    assert list(collector.history) == [current]
