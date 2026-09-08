"""In-memory monitoring models and process instrumentation for NORFAB."""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal

import psutil
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


class ProcessMonitoringStats(BaseModel):
    """Resource use for one NORFAB process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    cpu_percent: float
    memory_rss_mbyte: float
    uptime_seconds: int


class MessagingMonitoringStats(BaseModel):
    """Lifetime message counters for one NORFAB process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    sent: int = 0
    received: int = 0
    events_received: int = 0
    send_failures: int = 0
    receive_failures: int = 0


class JobMonitoringStats(BaseModel):
    """Aggregate client job and event statistics."""

    model_config = ConfigDict(extra="forbid", strict=True)

    total_jobs: int = 0
    total_events: int = 0
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    jobs_by_service: dict[str, int] = Field(default_factory=dict)
    events_by_severity: dict[str, int] = Field(default_factory=dict)
    jobs_last_24h: int = 0
    oldest_job_ts: str | None = None
    newest_job_ts: str | None = None
    avg_completion_seconds: float | None = None


class DatabaseMonitoringStats(BaseModel):
    """SQLite storage and runtime statistics for a client job database."""

    model_config = ConfigDict(extra="forbid", strict=True)

    db_size_bytes: int = 0
    db_wal_size_bytes: int = 0
    db_shm_size_bytes: int = 0
    db_total_disk_bytes: int = 0
    db_page_size: int = 0
    db_page_count: int = 0
    db_max_page_count: int = 0
    db_freelist_count: int = 0
    db_used_size_bytes: int = 0
    db_cache_size: int = 0
    db_journal_mode: str = ""
    db_wal_autocheckpoint: int = 0
    db_mmap_size: int = 0
    db_soft_heap_limit: int = 0
    db_hard_heap_limit: int = 0
    db_data_version: int = 0
    db_sqlite_version: str = ""


class BaseMonitoringStats(BaseModel):
    """Fields shared by broker, client, and worker monitoring responses."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1.0"] = "1.0"
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    name: str
    role: Literal["broker", "client", "worker"]
    status: str
    process: ProcessMonitoringStats
    messaging: MessagingMonitoringStats


class BrokerWorkerMonitoringStats(BaseModel):
    """Broker-side connection statistics for one registered worker."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    service: str
    status: Literal["alive", "dead"]
    holdtime_seconds: float
    uptime_seconds: int
    keepalives_sent: int
    keepalives_received: int


class BrokerMonitoringStats(BaseMonitoringStats):
    """Validated broker monitoring response."""

    role: Literal["broker"] = "broker"
    endpoint: str
    worker_count: int
    service_count: int
    keepalive_interval_ms: int
    keepalive_multiplier: int
    workers: list[BrokerWorkerMonitoringStats] = Field(default_factory=list)


class ClientMonitoringStats(BaseMonitoringStats):
    """Validated client monitoring response."""

    role: Literal["client"] = "client"
    broker: str
    reconnects: int
    outbound_queue_depth: int
    jobs: JobMonitoringStats
    database: DatabaseMonitoringStats


class WorkerMonitoringStats(BaseMonitoringStats):
    """Validated worker monitoring response."""

    # Generic consumers validate common fields while worker-specific subclasses
    # declare and validate their additional metrics.
    model_config = ConfigDict(extra="allow", strict=True)

    role: Literal["worker"] = "worker"
    service: str
    broker: str
    reconnects: int
    outbound_queue_depth: int
    running_jobs: int
    max_concurrent_jobs: int
    watchdog_runs: int
    keepalives_sent: int
    keepalives_received: int
    sid_inventory_status: Literal["initialising", "failed", "completed"] | None = None


class ProcessMonitor:
    """Thread-safe, process-local counter and resource monitor."""

    def __init__(self) -> None:
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(interval=None)
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.messages_sent = 0
        self.messages_received = 0
        self.events_received = 0
        self.send_failures = 0
        self.receive_failures = 0
        self.reconnects = 0

    def record_sent(self) -> None:
        with self._lock:
            self.messages_sent += 1

    def record_received(self) -> None:
        with self._lock:
            self.messages_received += 1

    def record_event_received(self) -> None:
        with self._lock:
            self.events_received += 1

    def record_send_failure(self) -> None:
        with self._lock:
            self.send_failures += 1

    def record_receive_failure(self) -> None:
        with self._lock:
            self.receive_failures += 1

    def record_reconnect(self) -> None:
        with self._lock:
            self.reconnects += 1

    def process_stats(self) -> ProcessMonitoringStats:
        memory = self.process.memory_info()
        return ProcessMonitoringStats(
            cpu_percent=self.process.cpu_percent(interval=None),
            memory_rss_mbyte=memory.rss / 1024 / 1024,
            uptime_seconds=int(time.time() - self.started_at),
        )

    def messaging_stats(self) -> MessagingMonitoringStats:
        with self._lock:
            return MessagingMonitoringStats(
                sent=self.messages_sent,
                received=self.messages_received,
                events_received=self.events_received,
                send_failures=self.send_failures,
                receive_failures=self.receive_failures,
            )


class WorkerWatchDog(threading.Thread):
    """Run periodic worker health checks and service-specific maintenance tasks."""

    def __init__(self, worker: Any) -> None:
        super().__init__()
        self.worker = worker
        self.watchdog_interval = worker.inventory.get("watchdog_interval", 30)
        self.memory_threshold_mbyte = worker.inventory.get(
            "memory_threshold_mbyte", 1000
        )
        self.memory_threshold_action = worker.inventory.get(
            "memory_threshold_action", "log"
        )
        self.runs = 0
        self.watchdog_tasks: list = []

    def get_stats(self) -> dict[str, Any]:
        """Return watchdog-specific values for the worker monitoring snapshot."""
        return {"sid_inventory_status": self.worker.status.get("sid_inventory_status")}

    def configuration(self) -> dict[str, Any]:
        """Return base watchdog configuration."""
        return {
            "watchdog_interval": self.watchdog_interval,
            "memory_threshold_mbyte": self.memory_threshold_mbyte,
            "memory_threshold_action": self.memory_threshold_action,
        }

    def check_ram(self) -> None:
        """Apply the configured action when process memory exceeds its threshold."""
        memory_mbyte = self.worker.monitoring.process.memory_info().rss / 1024 / 1024
        if memory_mbyte <= self.memory_threshold_mbyte:
            return
        if self.memory_threshold_action == "log":
            log.warning(
                f"{self.worker.name} watchdog - memory_threshold_mbyte "
                f"'{self.memory_threshold_mbyte}' exceeded, memory usage "
                f"'{memory_mbyte:.2f}' MByte"
            )
        elif self.memory_threshold_action == "shutdown":
            raise SystemExit(
                f"{self.worker.name} watchdog - memory_threshold_mbyte "
                f"'{self.memory_threshold_mbyte}' exceeded, memory usage "
                f"'{memory_mbyte:.2f}' MByte, shutting down"
            )

    def run(self) -> None:
        """Run watchdog checks until the worker exits."""
        slept = 0.0
        while not self.worker.exit_event.is_set():
            if slept < self.watchdog_interval:
                time.sleep(0.1)
                slept += 0.1
                continue
            self.check_ram()
            for task in self.watchdog_tasks:
                task()
            self.runs += 1
            slept = 0.0
