"""Shared polling and in-memory history for NFWeb monitoring."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import orjson
from tornado.ioloop import PeriodicCallback

from norfab.clients.nfweb.monitoring.config import MonitoringConfig
from norfab.clients.nfweb.monitoring.models import (
    MonitoringComponent,
    MonitoringDatabaseStats,
    MonitoringSnapshot,
    MonitoringWorkerDatabaseStats,
)
from norfab.core.monitoring import (
    BrokerMonitoringStats,
    ClientMonitoringStats,
    WorkerMonitoringStats,
)

log = logging.getLogger(__name__)

SnapshotCallback = Callable[[MonitoringSnapshot], Awaitable[None] | None]


class MonitoringCollector:
    """Poll existing NORFAB status interfaces and retain recent samples in memory."""

    def __init__(
        self,
        client: Any,
        config: MonitoringConfig,
        on_snapshot: SnapshotCallback | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.on_snapshot = on_snapshot
        history_size = config.retention_minutes * 60 // config.collection_interval + 1
        self.history: deque[MonitoringSnapshot] = deque(maxlen=history_size)
        self._periodic: PeriodicCallback | None = None
        self._collection_lock = asyncio.Lock()
        self._active_task: asyncio.Task | None = None
        self.running = False
        self.last_error: str | None = None
        self.last_completed_at: datetime | None = None

    @property
    def collecting(self) -> bool:
        """Return whether a collection cycle is active."""
        return self._collection_lock.locked()

    @property
    def latest(self) -> MonitoringSnapshot | None:
        """Return the latest in-memory sample."""
        return self.history[-1] if self.history else None

    async def start(self) -> None:
        """Start shared periodic polling and collect the first sample."""
        if self.running:
            return
        self.running = True
        self._periodic = PeriodicCallback(
            self.collect,
            self.config.collection_interval * 1000,
        )
        self._periodic.start()
        self._active_task = asyncio.create_task(self.collect())

    async def stop(self) -> None:
        """Stop polling and wait for the active collection cycle."""
        self.running = False
        if self._periodic is not None:
            self._periodic.stop()
        if self._active_task is not None and not self._active_task.done():
            await self._active_task
        async with self._collection_lock:
            pass

    async def collect(self) -> MonitoringSnapshot | None:
        """Collect one non-overlapping monitoring sample."""
        if self._collection_lock.locked():
            return None
        async with self._collection_lock:
            try:
                snapshot = await asyncio.to_thread(self.collect_once)
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("NFWeb monitoring collection failed")
                return None

            cutoff = snapshot.collected_at - timedelta(
                minutes=self.config.retention_minutes
            )
            while self.history and self.history[0].collected_at < cutoff:
                self.history.popleft()
            self.history.append(snapshot)
            self.last_error = None
            self.last_completed_at = snapshot.collected_at
            if self.on_snapshot is not None:
                result = self.on_snapshot(snapshot)
                if result is not None:
                    await result
            return snapshot

    def collect_once(self) -> MonitoringSnapshot:
        """Collect and validate broker, worker, and local-client statistics."""
        started = time.perf_counter()
        errors: list[str] = []

        broker_reply = self.client.mmi(
            "mmi.service.broker",
            "get_stats",
            timeout=self.config.request_timeout,
        )
        broker_stats = None
        if broker_reply.get("status") == "200":
            broker_stats = BrokerMonitoringStats.model_validate_json(
                orjson.dumps(broker_reply["results"])
            )
        else:
            errors.extend(
                broker_reply.get("errors") or ["broker statistics unavailable"]
            )

        worker_reply = self.client.run_job(
            service="all",
            workers="all",
            task="get_stats",
            timeout=self.config.request_timeout,
        )
        stats_by_name: dict[str, WorkerMonitoringStats] = {}
        for worker_name, response in worker_reply.items():
            if response.get("failed"):
                errors.append(
                    f"{worker_name}: worker did not respond during this sample interval"
                )
            else:
                stats_by_name[worker_name] = WorkerMonitoringStats.model_validate_json(
                    orjson.dumps(response["result"])
                )

        if broker_stats is None:
            broker = MonitoringComponent(
                id="broker",
                name="NFPBroker",
                role="broker",
                status="unreachable",
            )
            broker_workers = {}
        else:
            broker = MonitoringComponent(
                id="broker",
                name=broker_stats.name,
                role="broker",
                status=broker_stats.status,
                cpu_percent=broker_stats.process.cpu_percent,
                memory_mbyte=broker_stats.process.memory_rss_mbyte,
                uptime_seconds=broker_stats.process.uptime_seconds,
                messages_sent=broker_stats.messaging.sent,
                messages_received=broker_stats.messaging.received,
                worker_count=broker_stats.worker_count,
                service_count=broker_stats.service_count,
            )
            broker_workers = {worker.name: worker for worker in broker_stats.workers}

        client_stats = ClientMonitoringStats.model_validate_json(
            orjson.dumps(self.client.get_stats())
        )
        client = MonitoringComponent(
            id="client:nfweb",
            name=client_stats.name,
            role="client",
            status=client_stats.status if broker_stats else "degraded",
            cpu_percent=client_stats.process.cpu_percent,
            memory_mbyte=client_stats.process.memory_rss_mbyte,
            uptime_seconds=client_stats.process.uptime_seconds,
            messages_sent=client_stats.messaging.sent,
            messages_received=client_stats.messaging.received,
            reconnects=client_stats.reconnects,
            queue_depth=client_stats.outbound_queue_depth,
        )
        database = MonitoringDatabaseStats.model_validate(
            client_stats.jobs.model_dump()
        )

        workers: list[MonitoringComponent] = []
        for name, stats in stats_by_name.items():
            connection = broker_workers.get(name)
            workers.append(
                MonitoringComponent(
                    id=f"worker:{name}",
                    name=name,
                    role="worker",
                    service=stats.service,
                    status=connection.status if connection else stats.status,
                    cpu_percent=stats.process.cpu_percent,
                    memory_mbyte=stats.process.memory_rss_mbyte,
                    uptime_seconds=stats.process.uptime_seconds,
                    holdtime_seconds=(
                        connection.holdtime_seconds if connection else None
                    ),
                    keepalives_sent=stats.keepalives_sent,
                    keepalives_received=stats.keepalives_received,
                    messages_sent=stats.messaging.sent,
                    messages_received=stats.messaging.received,
                    reconnects=stats.reconnects,
                    queue_depth=stats.outbound_queue_depth,
                )
            )

        for name, connection in broker_workers.items():
            if name not in stats_by_name:
                errors.append(
                    f"{name}: worker did not respond during this sample interval"
                )
                workers.append(
                    MonitoringComponent(
                        id=f"worker:{name}",
                        name=name,
                        role="worker",
                        service=connection.service,
                        status=connection.status,
                        holdtime_seconds=connection.holdtime_seconds,
                        keepalives_sent=connection.keepalives_sent,
                        keepalives_received=connection.keepalives_received,
                    )
                )

        status = "complete" if not errors else "partial" if broker_stats else "failed"
        return MonitoringSnapshot(
            duration_ms=int((time.perf_counter() - started) * 1000),
            status=status,
            broker=broker,
            client=client,
            workers=sorted(workers, key=lambda worker: worker.name),
            database=database,
            errors=errors,
        )

    def worker_database_stats(
        self, worker_name: str, window_limit: int = 1000
    ) -> MonitoringWorkerDatabaseStats:
        """Summarize recent jobs returned by a worker's existing ``job_list`` task."""
        worker = next(
            (
                item
                for item in (self.latest.workers if self.latest is not None else [])
                if item.name == worker_name
            ),
            None,
        )
        if worker is None:
            raise LookupError(f"worker '{worker_name}' is not in the latest sample")

        response = self.client.run_job(
            service=worker.service or "all",
            workers=[worker_name],
            task="job_list",
            kwargs={"last": window_limit},
            timeout=self.config.request_timeout,
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"worker '{worker_name}' returned an invalid response")
        worker_response = response.get(worker_name)
        if not isinstance(worker_response, dict):
            raise RuntimeError(f"worker '{worker_name}' did not return job data")
        if worker_response.get("failed"):
            error = worker_response.get("errors") or worker_response.get("result")
            raise RuntimeError(str(error or "worker job database query failed"))

        jobs = worker_response.get("result") or []
        if not isinstance(jobs, list):
            raise RuntimeError(f"worker '{worker_name}' returned invalid job data")

        statuses = Counter(
            str(job.get("status") or "UNKNOWN").upper()
            for job in jobs
            if isinstance(job, dict)
        )
        tasks = Counter(
            str(job.get("task") or "unknown") for job in jobs if isinstance(job, dict)
        )
        timestamps = sorted(
            str(timestamp)
            for job in jobs
            if isinstance(job, dict)
            for timestamp in [
                job.get("received_timestamp")
                or job.get("started_timestamp")
                or job.get("completed_timestamp")
            ]
            if timestamp
        )
        return MonitoringWorkerDatabaseStats(
            worker=worker_name,
            service=worker.service,
            returned_jobs=len(jobs),
            window_limit=window_limit,
            potentially_truncated=len(jobs) >= window_limit,
            oldest_job_ts=timestamps[0] if timestamps else None,
            newest_job_ts=timestamps[-1] if timestamps else None,
            jobs_by_status=dict(statuses),
            jobs_by_task=dict(tasks.most_common()),
        )

    def health(self) -> dict[str, Any]:
        """Return safe collector health for the shared NFWeb health route."""
        return {
            "status": "ok" if self.last_error is None else "degraded",
            "collector_running": self.running,
            "last_completed_at": self.last_completed_at,
            "last_error": self.last_error,
            "sample_count": len(self.history),
        }
