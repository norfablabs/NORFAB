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
    client.job_db.jobs_stats.return_value = {
        "total_jobs": 120,
        "total_events": 42,
        "jobs_last_24h": 17,
        "avg_completion_seconds": 1.25,
        "jobs_by_status": {"COMPLETED": 112, "FAILED": 8},
        "jobs_by_service": {"nornir": 120},
        "events_by_severity": {"INFO": 40, "ERROR": 2},
        "oldest_job_ts": None,
        "newest_job_ts": None,
    }
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
    assert snapshot.database.total_jobs == 120
    assert snapshot.database.jobs_by_status == {"COMPLETED": 112, "FAILED": 8}
    assert snapshot.workers[0].cpu_percent == 23.0
    assert snapshot.workers[0].keepalives_received == 39
    assert snapshot.workers[0].holdtime_seconds == 12.5


def test_collect_once_keeps_malformed_worker_metrics_partial() -> None:
    process = Mock()
    process.cpu_percent.return_value = 0.0
    process.memory_info.return_value = Mock(rss=1)
    client = make_client()
    replies = list(client.mmi.side_effect)
    worker_reply = replies[1]
    worker_reply["results"][0]["holdtime"] = "not-a-number"
    worker_reply["results"][0]["keepalives tx/rx"] = "bad / counters"
    client.mmi.side_effect = replies

    with patch(
        "norfab.clients.nfweb.monitoring.collector.psutil.Process",
        return_value=process,
    ):
        snapshot = MonitoringCollector(client, MonitoringConfig()).collect_once()

    assert snapshot.status == "partial"
    assert snapshot.workers[0].holdtime_seconds is None
    assert snapshot.workers[0].keepalives_sent is None
    assert snapshot.workers[0].keepalives_received is None
    assert "nornir-worker-1: invalid holdtime value" in snapshot.errors
    assert "nornir-worker-1: invalid keepalive counters" in snapshot.errors


def test_collect_once_names_workers_missing_from_sample_interval() -> None:
    process = Mock()
    process.cpu_percent.return_value = 0.0
    process.memory_info.return_value = Mock(rss=1)
    client = make_client()
    replies = list(client.mmi.side_effect)
    replies[1]["results"].append(
        {
            "name": "nornir-worker-2",
            "service": "nornir",
            "status": "alive",
            "holdtime": "12.5",
            "keepalives tx/rx": "40 / 39",
        }
    )
    client.mmi.side_effect = replies
    client.run_job.return_value = {
        "nornir-worker-1": {
            "service": "nornir",
            "failed": False,
            "result": {
                "worker_cpu_percent": None,
                "worker_ram_usage_mbyte": 128.0,
            },
        }
    }

    with patch(
        "norfab.clients.nfweb.monitoring.collector.psutil.Process",
        return_value=process,
    ):
        snapshot = MonitoringCollector(client, MonitoringConfig()).collect_once()

    assert snapshot.status == "partial"
    assert snapshot.workers[0].cpu_percent is None
    assert snapshot.workers[1].cpu_percent is None
    assert snapshot.errors == [
        "nornir-worker-1: worker did not respond during this sample interval",
        "nornir-worker-2: worker did not respond during this sample interval",
    ]


def test_worker_database_stats_uses_existing_job_list_task() -> None:
    process = Mock()
    process.cpu_percent.return_value = 0.0
    process.memory_info.return_value = Mock(rss=1)
    client = make_client()

    with patch(
        "norfab.clients.nfweb.monitoring.collector.psutil.Process",
        return_value=process,
    ):
        collector = MonitoringCollector(client, MonitoringConfig())
        collector.history.append(collector.collect_once())

    client.run_job.return_value = {
        "nornir-worker-1": {
            "failed": False,
            "result": [
                {
                    "task": "cli",
                    "status": "COMPLETED",
                    "received_timestamp": "2026-08-31T10:00:00+00:00",
                },
                {
                    "task": "cli",
                    "status": "PENDING",
                    "received_timestamp": "2026-08-31T10:01:00+00:00",
                },
            ],
        }
    }
    client.run_job.reset_mock()

    statistics = collector.worker_database_stats("nornir-worker-1")

    assert statistics.returned_jobs == 2
    assert statistics.jobs_by_status == {"COMPLETED": 1, "PENDING": 1}
    assert statistics.jobs_by_task == {"cli": 2}
    assert statistics.newest_job_ts == "2026-08-31T10:01:00+00:00"
    client.run_job.assert_called_once_with(
        service="nornir",
        workers=["nornir-worker-1"],
        task="job_list",
        kwargs={"last": 1000},
        timeout=10,
    )


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
