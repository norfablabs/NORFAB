"""NFWeb in-memory monitoring collection tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from norfab.clients.nfweb.monitoring.collector import MonitoringCollector
from norfab.clients.nfweb.monitoring.config import MonitoringConfig
from norfab.core.monitoring import ClientMonitoringStats


def make_client() -> Mock:
    client = Mock()
    client.get_stats.return_value = ClientMonitoringStats(
        name="nfweb",
        status="active",
        process={
            "cpu_percent": 4.5,
            "memory_rss_mbyte": 96.0,
            "uptime_seconds": 120,
        },
        messaging={"sent": 12, "received": 18},
        broker="tcp://127.0.0.1:5555",
        reconnects=1,
        outbound_queue_depth=2,
        jobs={
            "total_jobs": 120,
            "total_events": 42,
            "jobs_last_24h": 17,
            "avg_completion_seconds": 1.25,
            "jobs_by_status": {"COMPLETED": 112, "FAILED": 8},
            "jobs_by_service": {"nornir": 120},
            "events_by_severity": {"INFO": 40, "ERROR": 2},
        },
        database={},
    ).model_dump(mode="json")
    client.mmi.return_value = {
        "status": "200",
        "results": {
            "schema_version": "1.0",
            "name": "NFPBroker",
            "role": "broker",
            "status": "active",
            "process": {
                "cpu_percent": 8.5,
                "memory_rss_mbyte": 48.0,
                "uptime_seconds": 3600,
            },
            "messaging": {"sent": 30, "received": 25},
            "endpoint": "tcp://127.0.0.1:5555",
            "worker_count": 1,
            "service_count": 1,
            "keepalive_interval_ms": 2500,
            "keepalive_multiplier": 6,
            "workers": [
                {
                    "name": "nornir-worker-1",
                    "service": "nornir",
                    "status": "alive",
                    "holdtime_seconds": 12.5,
                    "uptime_seconds": 300,
                    "keepalives_sent": 40,
                    "keepalives_received": 39,
                }
            ],
        },
        "errors": [],
    }
    client.run_job.return_value = {
        "nornir-worker-1": {
            "service": "nornir",
            "failed": False,
            "result": {
                "schema_version": "1.0",
                "name": "nornir-worker-1",
                "role": "worker",
                "status": "active",
                "process": {
                    "cpu_percent": 23.0,
                    "memory_rss_mbyte": 128.0,
                    "uptime_seconds": 300,
                },
                "messaging": {"sent": 20, "received": 15},
                "service": "nornir",
                "broker": "tcp://127.0.0.1:5555",
                "reconnects": 1,
                "outbound_queue_depth": 0,
                "running_jobs": 1,
                "max_concurrent_jobs": 5,
                "watchdog_runs": 10,
                "keepalives_sent": 40,
                "keepalives_received": 39,
                "sid_inventory_status": "completed",
                "dead_connections_cleaned": 2,
                "idle_connections_cleaned": 3,
                "failed_hosts_recovered": 1,
                "errdisabled_hosts": 0,
                "nornir_hosts": 4,
                "netbox_inventory_status": None,
                "containerlab_inventory_status": None,
            },
        }
    }
    return client


class TestMonitoringCollector:
    def test_collect_once_reads_unified_monitoring_stats(self) -> None:
        client = make_client()
        snapshot = MonitoringCollector(client, MonitoringConfig()).collect_once()

        assert snapshot.status == "complete"
        assert snapshot.broker.cpu_percent == 8.5
        assert snapshot.broker.messages_received == 25
        assert snapshot.client.memory_mbyte == 96
        assert snapshot.client.messages_received == 18
        assert snapshot.database.total_jobs == 120
        assert snapshot.database.jobs_by_status == {"COMPLETED": 112, "FAILED": 8}
        assert snapshot.workers[0].cpu_percent == 23.0
        assert snapshot.workers[0].keepalives_received == 39
        assert snapshot.workers[0].holdtime_seconds == 12.5
        assert "details" not in client.run_job.return_value["nornir-worker-1"]["result"]

    def test_collect_once_rejects_invalid_broker_metrics(self) -> None:
        client = make_client()
        client.mmi.return_value["results"]["workers"][0]["holdtime_seconds"] = "12.5"

        with pytest.raises(ValidationError):
            MonitoringCollector(client, MonitoringConfig()).collect_once()

    def test_collect_once_names_worker_missing_from_sample_interval(self) -> None:
        client = make_client()
        client.mmi.return_value["results"]["workers"].append(
            {
                "name": "nornir-worker-2",
                "service": "nornir",
                "status": "alive",
                "holdtime_seconds": 12.5,
                "uptime_seconds": 300,
                "keepalives_sent": 40,
                "keepalives_received": 39,
            }
        )

        snapshot = MonitoringCollector(client, MonitoringConfig()).collect_once()

        assert snapshot.status == "partial"
        assert snapshot.workers[1].cpu_percent is None
        assert snapshot.errors == [
            "nornir-worker-2: worker did not respond during this sample interval"
        ]

    def test_worker_database_stats_uses_existing_job_list_task(self) -> None:
        client = make_client()
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

    def test_history_is_memory_only_and_removes_expired_samples(self) -> None:
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
