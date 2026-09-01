"""Shared polling and in-memory history for NFWeb monitoring."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import psutil
from tornado.ioloop import PeriodicCallback

from norfab.clients.nfweb.monitoring.config import MonitoringConfig
from norfab.clients.nfweb.monitoring.models import (
    MonitoringComponent,
    MonitoringDatabaseStats,
    MonitoringSnapshot,
    MonitoringWorkerDatabaseStats,
)

log = logging.getLogger(__name__)

SnapshotCallback = Callable[[MonitoringSnapshot], Awaitable[None] | None]


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return int(number) if number is not None and number.is_integer() else None


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
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(interval=None)
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
        """Poll broker, worker, and local-client status using existing interfaces."""
        started = time.perf_counter()
        errors: list[str] = []

        broker_reply = self.client.mmi(
            "mmi.service.broker",
            "show_broker",
            timeout=self.config.request_timeout,
        )
        if not isinstance(broker_reply, dict):
            broker_reply = {
                "status": "500",
                "errors": ["broker returned an invalid status response"],
            }
        broker_data = (
            broker_reply.get("results", {})
            if broker_reply.get("status") == "200"
            else {}
        )
        if not isinstance(broker_data, dict):
            broker_data = {}
        if not broker_data:
            errors.extend(broker_reply.get("errors") or ["broker status unavailable"])

        workers_reply = self.client.mmi(
            "mmi.service.broker",
            "show_workers",
            timeout=self.config.request_timeout,
        )
        if not isinstance(workers_reply, dict):
            workers_reply = {
                "status": "500",
                "errors": ["broker returned an invalid worker response"],
            }
        worker_rows = (
            workers_reply.get("results", [])
            if workers_reply.get("status") == "200"
            else []
        )
        if not isinstance(worker_rows, list):
            errors.append("broker returned invalid worker status data")
            worker_rows = []
        if workers_reply.get("status") != "200":
            errors.extend(workers_reply.get("errors") or ["worker status unavailable"])

        worker_stats = self.client.run_job(
            service="all",
            workers="all",
            task="get_watchdog_stats",
            timeout=self.config.request_timeout,
        )
        stats_by_name: dict[str, dict[str, Any]] = {}
        unavailable_worker_names: set[str] = set()
        if not isinstance(worker_stats, dict):
            errors.append("worker watchdog statistics returned an invalid response")
            worker_stats = {}
        for worker_name, job in worker_stats.items():
            worker_name = str(worker_name)
            if not isinstance(job, dict):
                unavailable_worker_names.add(worker_name)
                continue
            if job.get("failed"):
                unavailable_worker_names.add(worker_name)
                continue
            result = job.get("result") or {}
            if not isinstance(result, dict):
                unavailable_worker_names.add(worker_name)
                continue
            stats_by_name[worker_name] = result

        broker = MonitoringComponent(
            id="broker",
            name="NFPBroker",
            role="broker",
            status="active" if broker_data else "unreachable",
            cpu_percent=broker_data.get("cpu_percent"),
            memory_mbyte=broker_data.get("memory_rss_mbyte"),
            uptime_seconds=broker_data.get("uptime_seconds"),
            worker_count=broker_data.get("workers count"),
            service_count=broker_data.get("services count"),
        )

        memory = self.process.memory_info()
        receiver_alive = bool(
            getattr(self.client, "recv_thread", None)
            and self.client.recv_thread.is_alive()
        )
        client = MonitoringComponent(
            id="client:nfweb",
            name=self.client.name,
            role="client",
            status="active" if broker_data and receiver_alive else "degraded",
            cpu_percent=self.process.cpu_percent(interval=None),
            memory_mbyte=memory.rss / 1024 / 1024,
            messages_sent=self.client.stats_send_to_broker,
            messages_received=self.client.stats_recv_from_broker,
            reconnects=self.client.stats_reconnect_to_broker,
            queue_depth=self.client.outbound_queue.qsize(),
        )

        database = MonitoringDatabaseStats()
        try:
            job_stats = self.client.job_db.jobs_stats()
            if isinstance(job_stats, dict):
                database = MonitoringDatabaseStats.model_validate(job_stats)
        except Exception as exc:
            errors.append(f"local client job statistics unavailable: {exc}")

        workers: list[MonitoringComponent] = []
        for row in worker_rows:
            if not isinstance(row, dict):
                errors.append("broker returned an invalid worker status row")
                continue
            worker_name = row.get("name")
            if not worker_name:
                continue
            name = str(worker_name)
            stats = stats_by_name.get(name, {})
            if (
                not stats
                or stats.get("worker_cpu_percent") is None
                or stats.get("worker_ram_usage_mbyte") is None
            ):
                unavailable_worker_names.add(name)
            keepalives = str(row.get("keepalives tx/rx", "")).split("/")
            holdtime = _optional_float(row.get("holdtime"))
            keepalives_sent = (
                _optional_int(keepalives[0].strip()) if len(keepalives) == 2 else None
            )
            keepalives_received = (
                _optional_int(keepalives[1].strip()) if len(keepalives) == 2 else None
            )
            if row.get("holdtime") not in (None, "") and holdtime is None:
                errors.append(f"{name}: invalid holdtime value")
            if row.get("keepalives tx/rx") and (
                keepalives_sent is None or keepalives_received is None
            ):
                errors.append(f"{name}: invalid keepalive counters")
            workers.append(
                MonitoringComponent(
                    id=f"worker:{name}",
                    name=name,
                    role="worker",
                    service=row.get("service") or stats.get("service"),
                    status=row.get("status", "unknown"),
                    cpu_percent=stats.get("worker_cpu_percent"),
                    memory_mbyte=stats.get("worker_ram_usage_mbyte"),
                    uptime_seconds=stats.get("uptime_seconds"),
                    holdtime_seconds=holdtime,
                    keepalives_sent=keepalives_sent,
                    keepalives_received=keepalives_received,
                )
            )

        known_workers = {worker.name for worker in workers}
        for name, stats in stats_by_name.items():
            if name not in known_workers:
                workers.append(
                    MonitoringComponent(
                        id=f"worker:{name}",
                        name=name,
                        role="worker",
                        service=stats.get("service"),
                        status="unknown",
                        cpu_percent=stats.get("worker_cpu_percent"),
                        memory_mbyte=stats.get("worker_ram_usage_mbyte"),
                        uptime_seconds=stats.get("uptime_seconds"),
                    )
                )

        errors.extend(
            f"{name}: worker did not respond during this sample interval"
            for name in sorted(unavailable_worker_names)
        )

        status = "complete" if not errors else "partial" if broker_data else "failed"
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
