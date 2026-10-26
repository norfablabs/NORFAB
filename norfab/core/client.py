import glob
import hashlib
import logging
import os
import queue
import shutil
import socket
import sqlite3
import threading
import time
import zlib
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

if TYPE_CHECKING:
    from norfab.core.agent import NFAgent
from urllib.parse import unquote
from uuid import uuid4  # random uuid

import orjson
import zmq

from norfab.core.inventory import NorFabInventory
from norfab.models import InputResponseModel, Result
from norfab.utils.markdown_results import markdown_results

from . import NFP
from .monitoring import (
    ClientMonitoringStats,
    DatabaseMonitoringStats,
    JobMonitoringStats,
    ProcessMonitor,
)
from .security import generate_certificates

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NORFAB client, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------


# Job status constants
class JobStatus:
    NEW = "NEW"
    SUBMITTING = "SUBMITTING"  # POST sent, waiting for broker ACK
    DISPATCHED = "DISPATCHED"  # Broker dispatched to workers
    STARTED = "STARTED"  # At least one worker started processing
    WAITING_CLIENT_INPUT = (
        "WAITING_CLIENT_INPUT"  # Worker is waiting for client response
    )
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"  # Job exceeded deadline without completion


TERMINAL_JOB_STATUSES = (
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.STALE,
)


class ClientJobDatabase:
    """Lightweight client-side job and events store."""

    def __init__(self, db_path: str, jobs_compress: bool = True) -> None:
        self.db_path = db_path
        self.jobs_compress = jobs_compress
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            # performance PRagmas
            self._local.conn.execute("PRAGMA cache_size=5000")  # 5MB cache
            self._local.conn.execute("PRAGMA temp_store=MEMORY")  # Use RAM for temp
            self._local.conn.execute("PRAGMA mmap_size=30000000")  # Memory-mapped I/O
            self._local.conn.execute("PRAGMA query_only=False")  # Default
            self._local.conn.execute("PRAGMA busy_timeout=5000")  # 5s timeout

        return self._local.conn

    @contextmanager
    def _transaction(self, write: bool = False):
        conn = self._get_connection()
        if write:
            with self._lock:
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        else:
            yield conn

    def _compress(self, data: Dict | List | Any) -> bytes:
        raw = orjson.dumps(data)
        return zlib.compress(raw, level=6) if self.jobs_compress else raw

    def _decompress(self, payload: bytes | None) -> Any:
        if payload is None:
            return None
        return orjson.loads(zlib.decompress(payload) if self.jobs_compress else payload)

    def _initialize_database(self) -> None:
        with self._transaction(write=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    uuid TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    task TEXT NOT NULL,
                    args BLOB,
                    kwargs BLOB,
                    timeout INTEGER,
                    deadline REAL,
                    status TEXT DEFAULT 'NEW',
                    workers_requested TEXT,
                    workers_dispatched TEXT,
                    workers_started TEXT,
                    workers_completed TEXT,
                    result_data BLOB,
                    errors TEXT,
                    received_timestamp TEXT NOT NULL,
                    started_timestamp TEXT,
                    completed_timestamp TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_poll_timestamp REAL DEFAULT 0
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_uuid TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT DEFAULT 'INFO',
                    task TEXT,
                    event_data BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_uuid) REFERENCES jobs(uuid) ON DELETE CASCADE
                )
                """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_service ON jobs(service)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON jobs(deadline)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_job_uuid ON events(job_uuid)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_last_poll ON jobs(last_poll_timestamp)"
            )

    def add_job(
        self,
        uuid: str,
        service: str,
        task: str,
        workers: Union[str, List[str]],
        args: list,
        kwargs: dict,
        timeout: int,
        deadline: float,
    ) -> None:

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO jobs (uuid, service, task, args, kwargs, timeout, deadline,
                                  status, workers_requested, received_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?)
                """,
                (
                    uuid,
                    service,
                    task,
                    self._compress({"args": args or []}),
                    self._compress({"kwargs": kwargs or {}}),
                    timeout,
                    deadline,
                    orjson.dumps(workers).decode("utf-8"),
                    now,
                    now,
                ),
            )

    def update_job(
        self,
        uuid: str,
        *,
        status: str | None = None,
        workers_dispatched: Set[str] | List[str] | None = None,
        workers_started: Set[str] | List[str] | None = None,
        workers_completed: Set[str] | List[str] | None = None,
        result_data: dict | None = None,
        errors: List[str] | None = None,
        append_errors: List[str] | None = None,
        started_ts: str | None = None,
        completed_ts: str | None = None,
        last_poll_ts: float | None = None,
    ) -> None:
        fields = []
        values: List[Any] = []

        def _store_set(label: str, value: Set[str] | List[str] | None) -> None:
            if value is None:
                return
            if isinstance(value, set):
                value = sorted(value)
            fields.append(f"{label} = ?")
            values.append(orjson.dumps(value).decode("utf-8"))

        if status:
            fields.append("status = ?")
            values.append(status)
        _store_set("workers_dispatched", workers_dispatched)
        _store_set("workers_started", workers_started)
        _store_set("workers_completed", workers_completed)
        if result_data is not None:
            fields.append("result_data = ?")
            values.append(self._compress(result_data))
        if errors is not None:
            fields.append("errors = ?")
            values.append(orjson.dumps(errors).decode("utf-8"))
        if started_ts:
            fields.append("started_timestamp = ?")
            values.append(started_ts)
        if completed_ts:
            fields.append("completed_timestamp = ?")
            values.append(completed_ts)
        if last_poll_ts is not None:
            fields.append("last_poll_timestamp = ?")
            values.append(last_poll_ts)

        if not fields and not append_errors:
            return

        # Handle appending errors to existing errors
        if append_errors:
            with self._transaction(write=False) as conn:
                cur = conn.execute("SELECT errors FROM jobs WHERE uuid = ?", (uuid,))
                row = cur.fetchone()
                existing_errors = (
                    orjson.loads(row["errors"]) if row and row["errors"] else []
                )
            existing_errors.extend(append_errors)
            fields.append("errors = ?")
            values.append(orjson.dumps(existing_errors).decode("utf-8"))

        if not fields:
            return

        where_clause = "uuid = ?"
        where_values: List[Any] = [uuid]
        if status is not None:
            terminal_placeholders = ", ".join("?" for _ in TERMINAL_JOB_STATUSES)
            where_clause += (
                f" AND (status NOT IN ({terminal_placeholders}) OR status = ?)"
            )
            where_values.extend(TERMINAL_JOB_STATUSES)
            where_values.append(status)

        with self._transaction(write=True) as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(fields)} WHERE {where_clause}",
                (*values, *where_values),
            )

    def expire_job(self, uuid: str) -> dict | None:
        """Finalize an expired job atomically, preserving completed worker results.

        Args:
            uuid: Job identifier.

        Returns:
            The current job snapshot, or None if the job does not exist.
            Expired jobs become STALE with failed timeout results whose payload
            is None. Completed worker results and terminal states are preserved.
            Active jobs are returned unchanged. Expiry does not cancel workers.
        """
        with self._transaction(write=True) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE uuid = ?", (uuid,)).fetchone()
            if row is None:
                return None
            job = self._hydrate(row)
            if job["status"] in TERMINAL_JOB_STATUSES or time.time() < job["deadline"]:
                return job
            message = (
                f"job '{uuid}' service '{job['service']}' task '{job['task']}' "
                f"timeout expired after {job['timeout']} seconds; worker execution may continue"
            )
            results = job.get("result_data") or {}
            workers = job["workers_dispatched"] or job["workers_requested"]
            if isinstance(workers, str):
                workers = [workers]
            # Keep completed results; synthesize timeouts only for missing replies.
            for worker in workers:
                if worker not in results:
                    results[worker] = Result(
                        result=None,
                        failed=True,
                        status="timeout",
                        errors=[message],
                        juuid=uuid,
                        service=job["service"],
                        task=job["task"],
                    ).model_dump()
            conn.execute(
                "UPDATE jobs SET status = ?, result_data = ?, errors = ?, completed_timestamp = ? WHERE uuid = ?",
                (
                    JobStatus.STALE,
                    self._compress(results),
                    orjson.dumps([message]).decode(),
                    time.ctime(),
                    uuid,
                ),
            )
            job.update(status=JobStatus.STALE, result_data=results, errors=[message])
            log.error(
                "%s; outstanding workers: %s",
                message,
                [w for w in workers if results[w].get("status") == "timeout"],
            )
            return job

    def fetch_jobs(
        self,
        statuses: List[str] = None,
        limit: int = 10,
        min_poll_age: float = 0,
        service: str = None,
        task: str = None,
        workers_completed: List[str] = None,
        last: int = None,
    ) -> List[dict]:
        """Fetch jobs with flexible filtering and complete job attributes.

        Args:
            statuses: List of job statuses to filter by (default: all statuses)
            limit: Maximum number of jobs to return (used when last is not specified)
            min_poll_age: Minimum seconds since last poll (for rate limiting GET requests)
            service: Service name to filter by (optional)
            task: Task name to filter by (optional)
            workers_completed: List of worker names that completed the job (optional)
            last: Return only the last x number of jobs (newest first), overrides limit (optional)

        Returns:
            List of job dictionaries with complete attributes including:
            uuid, service, task, args, kwargs, workers_*, status, result_data,
            errors, timestamps, etc.
        """
        conditions = []
        params = []

        # Filter by statuses
        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)

        # Filter by poll age (for dispatcher throttling)
        if min_poll_age > 0:
            poll_threshold = time.time() - min_poll_age
            conditions.append(
                "(last_poll_timestamp IS NULL OR last_poll_timestamp <= ?)"
            )
            params.append(poll_threshold)

        # Filter by service
        if service:
            conditions.append("service = ?")
            params.append(service)

        # Filter by task
        if task:
            conditions.append("task = ?")
            params.append(task)

        # Filter by workers_completed (JSON contains check)
        if workers_completed:
            # For each worker, check if it's in the JSON array
            worker_conditions = []
            for worker in workers_completed:
                # SQLite JSON string contains check
                worker_conditions.append("workers_completed LIKE ?")
                params.append(f'%"{worker}"%')
            conditions.append(f"({' OR '.join(worker_conditions)})")

        # Build WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Determine order and limit based on 'last' parameter
        order_direction = "DESC" if last is not None else "ASC"
        result_limit = last if last is not None else limit

        with self._transaction(write=False) as conn:
            cur = conn.execute(
                f"""
                SELECT uuid, service, task, args, kwargs, workers_requested, timeout, deadline,
                       workers_dispatched, workers_started, workers_completed, status,
                       result_data, errors, received_timestamp, started_timestamp,
                       completed_timestamp, created_at, last_poll_timestamp
                FROM jobs
                WHERE {where_clause}
                ORDER BY created_at {order_direction}, rowid {order_direction}
                LIMIT ?
                """,
                (*params, result_limit),
            )
            rows = cur.fetchall()
        return [self._hydrate(row) for row in rows]

    def get_job(self, uuid: str) -> dict | None:
        with self._transaction(write=False) as conn:
            cur = conn.execute(
                """
                  SELECT uuid, service, task, args, kwargs, timeout, deadline, status,
                       workers_requested, workers_dispatched, workers_started,
                       workers_completed, result_data, errors, created_at, completed_timestamp,
                       last_poll_timestamp
                FROM jobs WHERE uuid = ?
                """,
                (uuid,),
            )
            row = cur.fetchone()
        return self._hydrate(row) if row else None

    def _hydrate(self, row: sqlite3.Row) -> dict:
        if row is None:
            return None
        data = dict(row)
        data["args"] = self._decompress(data.get("args")) or {"args": []}
        data["kwargs"] = self._decompress(data.get("kwargs")) or {"kwargs": {}}
        data["args"] = data["args"].get("args", [])
        data["kwargs"] = data["kwargs"].get("kwargs", {})
        for field in [
            "workers_requested",
            "workers_dispatched",
            "workers_started",
            "workers_completed",
        ]:
            if data.get(field):
                data[field] = orjson.loads(data[field])
            else:
                data[field] = []
        if data.get("result_data"):
            data["result_data"] = self._decompress(data["result_data"])
        if data.get("errors"):
            data["errors"] = orjson.loads(data["errors"])
        else:
            data["errors"] = []
        data["timeout"] = data.get("timeout", 600) or 600
        data["deadline"] = data.get("deadline", 0) or 0
        data["last_poll_timestamp"] = data.get("last_poll_timestamp", 0) or 0
        return data

    def add_event(
        self,
        job_uuid: str,
        message: str,
        severity: str = "INFO",
        task: str | None = None,
        event_data: dict | None = None,
    ) -> None:
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO events (job_uuid, message, severity, task, event_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_uuid,
                    message,
                    severity,
                    task,
                    self._compress(event_data or {}),
                ),
            )

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

    def jobs_stats(self) -> dict:
        """Return job-level statistics from the jobs database."""
        stats = {
            # job counts
            "total_jobs": 0,  # Total number of jobs in the database
            "total_events": 0,  # Total number of events in the database
            "jobs_by_status": {},  # Job counts keyed by status string
            "jobs_by_service": {},  # Job counts keyed by service name
            "events_by_severity": {},  # Event counts keyed by severity level
            # job timing
            "jobs_last_24h": 0,  # Jobs created in the last 24 hours
            "oldest_job_ts": None,  # received_timestamp of the oldest job
            "newest_job_ts": None,  # received_timestamp of the newest job
            "avg_completion_seconds": None,  # Average completion time in seconds for COMPLETED jobs
        }

        with self._transaction(write=False) as conn:
            # ── Job counts ────────────────────────────────────────────────
            stats["total_jobs"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[
                0
            ]

            cur = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
            stats["jobs_by_status"] = {row[0]: row[1] for row in cur.fetchall()}

            cur = conn.execute("SELECT service, COUNT(*) FROM jobs GROUP BY service")
            stats["jobs_by_service"] = {row[0]: row[1] for row in cur.fetchall()}

            stats["total_events"] = conn.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

            cur = conn.execute(
                "SELECT severity, COUNT(*) FROM events GROUP BY severity"
            )
            stats["events_by_severity"] = {row[0]: row[1] for row in cur.fetchall()}

            # ── Job timing ────────────────────────────────────────────────
            cutoff = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400)
            )
            stats["jobs_last_24h"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE created_at >= ?", (cutoff,)
            ).fetchone()[0]

            row = conn.execute(
                "SELECT MIN(received_timestamp), MAX(received_timestamp) FROM jobs"
            ).fetchone()
            if row:
                stats["oldest_job_ts"] = row[0]
                stats["newest_job_ts"] = row[1]

            # Average completion time for jobs that have both timestamps recorded.
            # Timestamps are stored as ctime() strings, so we parse them in Python.
            cur = conn.execute("""
                SELECT received_timestamp, completed_timestamp
                FROM jobs
                WHERE status = 'COMPLETED'
                  AND received_timestamp IS NOT NULL
                  AND completed_timestamp IS NOT NULL
                """)
            completed_rows = cur.fetchall()
            if completed_rows:
                import calendar

                durations = []
                for r in completed_rows:
                    try:
                        start = calendar.timegm(time.strptime(r[0]))
                        end = calendar.timegm(time.strptime(r[1]))
                        durations.append(end - start)
                    except (ValueError, OverflowError):
                        pass
                if durations:
                    stats["avg_completion_seconds"] = round(
                        sum(durations) / len(durations), 3
                    )

        return stats

    def jobs_db_stats(self) -> dict:
        """Return SQLite database-level statistics."""
        stats = {
            # file sizes
            "db_size_bytes": 0,  # Database file size on disk in bytes
            "db_wal_size_bytes": 0,  # WAL file size on disk in bytes (0 if absent)
            "db_shm_size_bytes": 0,  # SHM file size on disk in bytes (0 if absent)
            "db_total_disk_bytes": 0,  # Sum of db + wal + shm file sizes
            # page / space
            "db_page_size": 0,  # SQLite page size in bytes
            "db_page_count": 0,  # Total number of pages allocated in the database
            "db_max_page_count": 0,  # Maximum allowed number of pages
            "db_freelist_count": 0,  # Number of unused (free) pages
            "db_used_size_bytes": 0,  # Approximate used space = (page_count - freelist_count) * page_size
            # configuration / runtime
            "db_cache_size": 0,  # Current cache size setting (number of pages)
            "db_journal_mode": "",  # Journal mode (e.g. 'wal', 'delete')
            "db_wal_autocheckpoint": 0,  # WAL auto-checkpoint page threshold (0 = disabled)
            "db_mmap_size": 0,  # Memory-mapped I/O size in bytes
            "db_soft_heap_limit": 0,  # SQLite soft heap memory limit in bytes (0 = none)
            "db_hard_heap_limit": 0,  # SQLite hard heap memory limit in bytes (0 = none)
            "db_data_version": 0,  # Monotonic counter incremented on each external write
            "db_sqlite_version": sqlite3.sqlite_version,  # SQLite library version string
        }

        # File sizes on disk (main db, WAL, SHM)
        for attr, suffix in [
            ("db_size_bytes", ""),
            ("db_wal_size_bytes", "-wal"),
            ("db_shm_size_bytes", "-shm"),
        ]:
            path = self.db_path + suffix
            try:
                stats[attr] = os.path.getsize(path) if os.path.exists(path) else 0
            except OSError:
                stats[attr] = 0
        stats["db_total_disk_bytes"] = (
            stats["db_size_bytes"]
            + stats["db_wal_size_bytes"]
            + stats["db_shm_size_bytes"]
        )

        with self._transaction(write=False) as conn:
            stats["db_page_size"] = conn.execute("PRAGMA page_size").fetchone()[0]
            stats["db_page_count"] = conn.execute("PRAGMA page_count").fetchone()[0]
            stats["db_max_page_count"] = conn.execute(
                "PRAGMA max_page_count"
            ).fetchone()[0]
            stats["db_freelist_count"] = conn.execute(
                "PRAGMA freelist_count"
            ).fetchone()[0]
            stats["db_cache_size"] = conn.execute("PRAGMA cache_size").fetchone()[0]
            stats["db_journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
            stats["db_wal_autocheckpoint"] = conn.execute(
                "PRAGMA wal_autocheckpoint"
            ).fetchone()[0]
            stats["db_mmap_size"] = conn.execute("PRAGMA mmap_size").fetchone()[0]
            stats["db_data_version"] = conn.execute("PRAGMA data_version").fetchone()[0]
            try:
                stats["db_soft_heap_limit"] = conn.execute(
                    "PRAGMA soft_heap_limit"
                ).fetchone()[0]
            except Exception:
                pass
            try:
                stats["db_hard_heap_limit"] = conn.execute(
                    "PRAGMA hard_heap_limit"
                ).fetchone()[0]
            except Exception:
                pass

        page_size = stats["db_page_size"]
        used_pages = stats["db_page_count"] - stats["db_freelist_count"]
        stats["db_used_size_bytes"] = max(0, used_pages) * page_size

        return stats


class NFPJobFuture:
    """Blocking handle for one submitted NorFab job."""

    terminal_marker = object()

    def __init__(
        self,
        client: object,
        uuid: str,
        service: str,
        task: str,
        workers: Union[str, list],
        timeout: int,
        kwargs: dict,
    ) -> None:
        self.client = client
        self.uuid = uuid
        self.service = service
        self.task = task
        self.workers = workers
        self.timeout = timeout
        self.kwargs = kwargs or {}
        self.events_buffer = queue.Queue(maxsize=0)
        self.done_event = threading.Event()
        self.final_job_snapshot = None
        self.input_request_ids = set()
        self.pending_inputs = {}

    def add_event(self, event: dict) -> bool:
        input_request = (event.get("extras") or {}).get("input_request")

        if event.get("event_type") == "input_request" and input_request:
            input_id = input_request.get("id")
            if input_id in self.input_request_ids:
                return False
            self.input_request_ids.add(input_id)

        self.events_buffer.put(event)
        return True

    def mark_done(self, job: dict | None = None) -> None:
        self.final_job_snapshot = job
        if not self.done_event.is_set():
            self.done_event.set()
            self.events_buffer.put(self.terminal_marker)

    def events(self, timeout: int | float | None = None):
        while True:
            try:
                event = self.events_buffer.get(block=True, timeout=timeout)
            except queue.Empty:
                break

            if event is self.terminal_marker:
                break

            yield event

    def result(self, timeout: int | float | None = None, markdown: bool = False) -> Any:
        wait_started = time.time()
        while not self.done_event.is_set():
            if self.client.exit_event.is_set() or self.client.destroy_event.is_set():
                return None

            wait_time = 0.2
            if timeout is not None:
                remaining_time = timeout - (time.time() - wait_started)
                if remaining_time <= 0:
                    # Finalize deadline expiry without waiting for the dispatcher.
                    job = self.client.job_db.expire_job(self.uuid)
                    if job and job["status"] in TERMINAL_JOB_STATUSES:
                        self.mark_done(job)
                        break
                    return None
                wait_time = min(wait_time, remaining_time)

            self.done_event.wait(wait_time)

        job = self.final_job_snapshot or self.client.job_db.get_job(self.uuid)
        result = None
        if job and job["status"] in (JobStatus.COMPLETED, JobStatus.STALE):
            result = job.get("result_data")

        if markdown and job:
            return markdown_results(job, self.service, self.task, self.kwargs)

        return result

    def send_response(
        self,
        input_id: str,
        value: Any,
        worker: str | None = None,
        cancel: bool = False,
        metadata: dict | None = None,
    ) -> None:
        job = self.client.job_db.get_job(self.uuid) or {}
        target_worker = worker or job.get("workers_dispatched") or self.workers
        payload = InputResponseModel(
            input_id=input_id,
            value=value,
            cancel=cancel,
            metadata=metadata or {},
        ).model_dump()
        self.client.send_to_broker(
            NFP.PUT,
            self.client.ensure_bytes(self.service),
            self.client.ensure_bytes(target_worker),
            self.client.ensure_bytes(self.uuid),
            self.client.ensure_bytes(payload),
        )


def zmq_send_recv(client: object) -> None:
    """
    ZeroMQ send/receive thread.

    This function owns the client's broker socket. Other threads submit prepared
    messages to the outbound queue instead of touching the socket directly.
    It continuously drains outbound messages and polls the broker socket until
    the client's exit event is set. It handles:
    - EVENT messages: stored in the events table
    - RESPONSE messages: updates job status in the database based on response type

    This thread is the ONLY thread that sends, polls, or receives on the socket.
    All job state changes are persisted to the database.

    Args:
        client (object): The client instance containing the broker socket,
                         poller, job_db, and configuration.
    """
    last_poll_error_log = 0
    while not client.exit_event.is_set() and not client.destroy_event.is_set():
        for _ in range(NFP.ZMQ_SEND_RECV_DRAIN_LIMIT):
            try:
                outbound = client.outbound_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if not client.destroy_event.is_set():
                    client.broker_socket.send_multipart(outbound)
                    client.monitoring.record_sent()
            except Exception as e:
                client.monitoring.record_send_failure()
                log.error(
                    f"{client.name} - failed to send queued message to broker, "
                    f"error '{e}'",
                    exc_info=True,
                )

        msg = None
        try:
            # Keep draining bounded batches without sleeping while work remains.
            # Otherwise, wait for broker traffic or an outgoing-queue notification.
            items = dict(
                client.poller.poll(0 if not client.outbound_queue.empty() else None)
            )
            if items.get(client.wakeup_reader.fileno(), 0) & zmq.POLLIN:
                try:
                    while client.wakeup_reader.recv(4096):
                        pass
                except BlockingIOError:
                    pass
            if items.get(client.broker_socket, 0) & zmq.POLLIN:
                try:
                    msg = client.broker_socket.recv_multipart(zmq.NOBLOCK)
                except zmq.Again:
                    # Readiness can become stale; resume polling instead of blocking.
                    pass
        except KeyboardInterrupt:
            break
        except Exception as e:
            if time.time() - last_poll_error_log > 10:
                log.error(
                    f"{client.name} - failed to poll broker socket, error '{e}'",
                    exc_info=True,
                )
                last_poll_error_log = time.time()
            time.sleep(0.1)
            continue

        if msg is None:
            continue

        client.monitoring.record_received()

        # Message format: [empty, header, command, service, uuid, status, payload]
        if len(msg) < 7:
            client.monitoring.record_receive_failure()
            log.error(f"{client.name} - received malformed message: {msg}")
            continue

        command = msg[2]
        juuid = msg[4].decode("utf-8")
        status = msg[5].decode("utf-8")

        log.debug(
            f"{client.name} - received '{command}' message from broker, juuid {juuid}, status {status}"
        )

        if command == NFP.STREAM:
            payload = msg[6]  # payload is a chunk of bytes
            try:
                handle_stream(client, juuid, status, payload)
            except Exception as e:
                log.error(
                    f"{client.name} - failed to process stream for job {juuid}, "
                    f"error '{e}'",
                    exc_info=True,
                )
            continue

        try:
            payload = orjson.loads(msg[6])
        except Exception as e:
            client.monitoring.record_receive_failure()
            log.error(
                f"{client.name} - failed to parse message, error '{e}'", exc_info=True
            )
            continue

        if command == NFP.PUT:
            client.put_queue.put((juuid, payload, msg[3]))
            client.dispatcher_event.set()

        # Handle EVENT messages
        if command == NFP.EVENT:
            handle_event(client, juuid, payload, msg)

        # Handle RESPONSE messages
        if command == NFP.RESPONSE:
            handle_response(client, juuid, status, payload)

        # handle MMI messages
        if command == NFP.MMI:
            client.mmi_queue.put(msg)


def handle_event(client: object, juuid: str, payload: dict, msg: list) -> None:
    """
    Store and deliver events, update input state, and queue marked result GETs.

    Args:
        client: The client instance
        juuid: Job UUID
        payload: Event payload dictionary
        msg: Original message multipart for queue
    """
    client.monitoring.record_event_received()
    future = client.job_futures.get(juuid)
    if future and not future.add_event(payload):
        return

    client.job_db.add_event(
        job_uuid=juuid,
        message=payload.get("message", ""),
        severity=payload.get("severity", "INFO"),
        task=payload.get("task"),
        event_data=payload,
    )

    job = client.job_db.get_job(juuid)
    if not job or job["status"] in TERMINAL_JOB_STATUSES:
        return
    worker = payload.get("worker")
    extras = payload.get("extras") or {}
    if worker not in job["workers_dispatched"]:
        return

    if job["task"] == "serve_file" and payload.get("status") == "running":
        transfer = client.file_transfers.get(juuid)
        if transfer and not transfer["started"]:
            transfer["started"] = True
            transfer["credit"] -= 1
            client.send_to_broker(
                NFP.PUT,
                b"all",
                client.ensure_bytes([worker]),
                juuid.encode(),
                orjson.dumps({"offset": 0}),
            )

    # Input events update the job immediately, without waiting for GET polling.
    if future and payload.get("event_type") in ("input_request", "input_response"):
        if payload["event_type"] == "input_request" and extras.get("input_request"):
            # Track each worker separately: several workers can need input at once.
            future.pending_inputs[worker] = extras["input_request"]["id"]
        elif future.pending_inputs.get(worker) == (
            extras.get("input_response") or {}
        ).get("input_id"):
            # An old response must not clear a newer request from the same worker.
            future.pending_inputs.pop(worker, None)
        # Keep the job waiting until every worker's outstanding request is resolved.
        client.job_db.update_job(
            juuid,
            status=(
                JobStatus.WAITING_CLIENT_INPUT
                if future.pending_inputs
                else JobStatus.STARTED
            ),
        )

    # handle worker reporting results completion
    if (
        payload.get("event_type") == "result_ready"
        and worker not in job["workers_completed"]
    ):
        # Completion notifications do not postpone periodic polling for other workers.
        client.send_to_broker(
            NFP.GET,
            client.ensure_bytes(job["service"]),
            client.ensure_bytes([worker]),
            client.ensure_bytes(juuid),
            client.ensure_bytes(
                {"task": job["task"], "kwargs": job["kwargs"], "args": job["args"]}
            ),
        )


def handle_response(client: object, juuid: str, status: str, payload: dict) -> None:
    """
    Handle RESPONSE messages and update job database accordingly.

    Uses job status to determine context:
    - SUBMITTING: expecting broker 202 with workers list
    - DISPATCHED/STARTED: expecting worker ACKs (202), results (200), or pending (300)

    Status codes:
    - 202: Accepted (POST acknowledged by broker or worker)
    - 200: OK (GET completed with results)
    - 300: Pending (job still in progress)
    - 4xx: Client errors
    - 5xx: Server errors
    """
    job = client.job_db.get_job(juuid)
    if not job:
        log.debug(f"{client.name} - received response for unknown job {juuid}")
        return

    # A finished job is immutable. Late acknowledgements and polling responses
    # may still arrive after completion, but must not reopen or otherwise alter
    # its final state.
    if job["status"] in TERMINAL_JOB_STATUSES:
        log.debug(
            f"{client.name} - ignoring status {status} response for "
            f"{job['status'].lower()} job {juuid}, job already finished"
        )
        return

    # Broker accepted POST - contains dispatched workers list
    if status == "202":  # ACCEPTED
        # Only the first POST acknowledgement establishes the worker set.
        if job["workers_dispatched"]:
            return
        workers_list = payload["workers"]
        client.job_db.update_job(
            juuid,
            status=JobStatus.DISPATCHED,
            workers_dispatched=workers_list,
            started_ts=time.ctime(),
        )
        log.debug(f"{client.name} - job {juuid} dispatched to workers: {workers_list}")
        return

    # Worker created the job
    if status == "201":  # JOB CREATED
        worker_single = payload["worker"]
        started = set(job.get("workers_started", []))
        started.add(worker_single)
        job_status = JobStatus.STARTED
        # A worker's acknowledgement must not clear another worker's input wait.
        if job["status"] == JobStatus.WAITING_CLIENT_INPUT:
            job_status = JobStatus.WAITING_CLIENT_INPUT
        client.job_db.update_job(
            juuid,
            status=job_status,
            workers_started=list(started),
        )
        log.debug(
            f"{client.name} - job {juuid} acknowledged by worker: {worker_single}"
        )
        return

    # Handle 200 OK - GET completed with results
    if status == "200":
        dispatched = set(job.get("workers_dispatched", []))
        completed = set(job.get("workers_completed", []))
        existing_results = job.get("result_data") or {}

        # Merge new results with existing (results keyed by worker name)
        if isinstance(payload, dict):
            for worker_name in payload.keys():
                completed.add(worker_name)
            existing_results.update(payload)

        # A worker with a saved result no longer needs input, even if its input-response event was missed.
        future = client.job_futures.get(juuid)
        if future:
            for worker in completed:
                future.pending_inputs.pop(worker, None)
        is_complete = completed == dispatched and len(dispatched) > 0

        # Finish only when every dispatched worker has returned a result.
        if is_complete:
            job_status = JobStatus.COMPLETED
        # Partial results must preserve any remaining worker's input wait.
        elif future and future.pending_inputs:
            job_status = JobStatus.WAITING_CLIENT_INPUT
        else:
            job_status = JobStatus.STARTED

        client.job_db.update_job(
            juuid,
            status=job_status,
            workers_completed=list(completed),
            result_data=existing_results,
            completed_ts=time.ctime() if is_complete else None,
        )

        if is_complete:
            log.info(f"{client.name} - Job {juuid} completed")
            log.debug(f"{client.name} - job {juuid} completed")
            future = client.job_futures.get(juuid)
            if future:
                future.mark_done(client.job_db.get_job(juuid))
        return

    # Handle 102 Processing - worker is waiting for client input
    if status == "102":
        worker = payload.get("worker")
        workers_started = set(job.get("workers_started", []))
        if worker:
            workers_started.add(worker)
        client.job_db.update_job(
            juuid,
            status=JobStatus.WAITING_CLIENT_INPUT,
            workers_started=list(workers_started),
        )

        input_request = payload.get("input_request")
        if input_request:
            # GET polling can find an input request whose event was missed.
            # Track it so another worker's reply does not clear the input wait.
            future = client.job_futures.get(juuid)
            if future:
                future.pending_inputs[worker] = input_request["id"]
            event = {
                "event_type": "input_request",
                "worker": worker,
                "service": payload.get("service", job["service"]),
                "uuid": juuid,
                "task": job["task"],
                "timestamp": time.strftime("%d-%b-%Y %H:%M:%S"),
                "message": input_request.get(
                    "question", "Worker is waiting for client input"
                ),
                "severity": "INFO",
                "status": "waiting_client_input",
                "resource": [],
                "timeout": input_request.get("timeout"),
                "extras": {"input_request": input_request},
            }
            future = client.job_futures.get(juuid)
            if not future or future.add_event(event):
                client.job_db.add_event(
                    job_uuid=juuid,
                    message=event["message"],
                    severity=event["severity"],
                    task=event["task"],
                    event_data=event,
                )
        return

    # Handle 300 Pending - job still in progress
    if status == "300":
        worker = payload.get("worker")
        workers_started = list(job.get("workers_started", []))
        if worker and worker not in workers_started:
            workers_started.append(worker)
        # A running worker's poll reply must not clear another worker's input wait.
        if job["status"] == JobStatus.WAITING_CLIENT_INPUT:
            job_status = JobStatus.WAITING_CLIENT_INPUT
        else:
            job_status = JobStatus.STARTED
        client.job_db.update_job(
            juuid,
            status=job_status,
            workers_started=workers_started,
        )
        return

    # Handle error statuses (4xx, 5xx)
    if status.startswith("4") or status.startswith("5"):
        error_msg = payload.get("error", payload.get("status", f"Error {status}"))
        client.job_db.update_job(
            juuid,
            status=JobStatus.FAILED,
            append_errors=[error_msg],
            completed_ts=time.ctime(),
        )
        future = client.job_futures.get(juuid)
        if future:
            future.mark_done(client.job_db.get_job(juuid))
        log.error(
            f"{client.name} - Job {juuid} failed with status {status}: {error_msg}"
        )
        return


def handle_stream(client, juuid: str, status: str, payload: bytes) -> None:
    job = client.job_db.get_job(juuid)
    file_transfer = client.file_transfers.get(juuid)

    if not job:
        log.error(f"{client.name} - received stream for unknown job {juuid}")
        return

    if not file_transfer:
        log.error(f"{client.name} - received stream for unknown file transfer {juuid}")
        return

    if (
        job["status"] in TERMINAL_JOB_STATUSES
        or file_transfer["destination"].closed
        or file_transfer["error"] is not None
    ):
        return

    try:
        file_transfer["destination"].write(payload)
    except OSError as exc:
        file_transfer["error"] = exc
        client.send_to_broker(
            NFP.PUT,
            client.ensure_bytes(job["service"]),
            client.ensure_bytes(job["workers_requested"]),
            juuid.encode(),
            orjson.dumps({"error": str(exc)}),
        )
        return
    file_transfer["file_hash"].update(payload)
    file_transfer["total_bytes_received"] += len(payload)
    file_transfer["credit"] += 1
    if file_transfer["total_bytes_received"] >= file_transfer["size_bytes"]:
        return

    # request next set of chunks up to credit
    while file_transfer["credit"] > 0 and file_transfer["chunk_requests_remaining"] > 0:
        file_transfer["offset"] += file_transfer[
            "chunk_size"
        ]  # Offset of next chunk request
        service = client.ensure_bytes(job["service"])
        uuid_bytes = client.ensure_bytes(juuid)
        workers = client.ensure_bytes(job["workers_requested"])
        request = client.ensure_bytes(
            {
                "offset": file_transfer["offset"],
            }
        )
        client.send_to_broker(NFP.PUT, service, workers, uuid_bytes, request)
        file_transfer["credit"] -= 1
        file_transfer["chunk_requests_remaining"] -= 1


def dispatch_new_jobs(client) -> None:
    """
    Find NEW jobs and send POST requests to broker.
    Non-blocking: sends request and updates status to SUBMITTING.
    """
    for job in client.job_db.fetch_jobs(
        [JobStatus.NEW], limit=client.dispatch_batch_size
    ):
        juuid = job["uuid"]
        if juuid not in client.job_futures:
            continue

        # Do not dispatch queued jobs whose deadline has already passed.
        if time.time() >= job["deadline"]:
            job = client.job_db.expire_job(juuid)
            client.job_futures[juuid].mark_done(job)
            continue

        try:
            # Send POST request (non-blocking)
            service = client.ensure_bytes(job["service"])
            uuid_bytes = client.ensure_bytes(juuid)
            workers = client.ensure_bytes(job["workers_requested"])
            request = client.ensure_bytes(
                {
                    "task": job["task"],
                    "kwargs": job["kwargs"] or {},
                    "args": job["args"] or [],
                    "timeout": job["timeout"],
                }
            )

            client.send_to_broker(NFP.POST, service, workers, uuid_bytes, request)

            # Update status - receiver will handle the response
            client.job_db.update_job(
                juuid,
                status=JobStatus.SUBMITTING,
                last_poll_ts=time.time(),
            )
            log.debug(f"{client.name} - dispatched POST for job {juuid}")

        except Exception as e:
            msg = f"{client.name} - failed to dispatch job {juuid}: {e}"
            log.error(msg, exc_info=True)
            client.job_db.update_job(
                juuid,
                status=JobStatus.FAILED,
                errors=[msg],
                completed_ts=time.ctime(),
            )
            future = client.job_futures.get(juuid)
            if future:
                future.mark_done(client.job_db.get_job(juuid))


def poll_active_jobs(client) -> None:
    """
    Expire overdue jobs and queue periodic job polling GET requests.
    Completion events retrieve results independently of the polling interval.
    """
    # Jobs that are ready for GET polling (dispatched or started)
    active_statuses = [
        JobStatus.SUBMITTING,
        JobStatus.DISPATCHED,
        JobStatus.STARTED,
        JobStatus.WAITING_CLIENT_INPUT,
    ]

    # Select overdue jobs before LIMIT so older running jobs cannot hide them.
    with client.job_db._transaction() as conn:
        overdue = conn.execute(
            "SELECT uuid FROM jobs WHERE status IN (?, ?, ?, ?) AND deadline <= ? "
            "ORDER BY deadline, rowid LIMIT ?",
            (*active_statuses, time.time(), client.dispatch_batch_size),
        ).fetchall()
    for row in overdue:
        job = client.job_db.expire_job(row["uuid"])
        future = client.job_futures.get(row["uuid"])
        if future:
            future.mark_done(job)

    # SUBMITTING jobs have no worker list yet and must not occupy polling batches.
    active_statuses.remove(JobStatus.SUBMITTING)
    # fetch_jobs filters by min_poll_age to enforce the periodic polling interval.
    for job in client.job_db.fetch_jobs(
        active_statuses,
        limit=client.dispatch_batch_size,
        min_poll_age=client.poll_interval,
    ):
        juuid = job["uuid"]
        if juuid not in client.job_futures:
            continue
        deadline = job["deadline"]
        now = time.time()

        # Check if job has exceeded deadline
        if now >= deadline:
            job = client.job_db.expire_job(juuid)
            future = client.job_futures.get(juuid)
            if future:
                future.mark_done(job)
            continue

        try:
            # Send GET request (non-blocking)
            service = client.ensure_bytes(job["service"])
            uuid_bytes = client.ensure_bytes(juuid)
            missing = sorted(
                set(job["workers_dispatched"]) - set(job["workers_completed"])
            )
            if not missing:
                continue
            workers = client.ensure_bytes(missing)
            request = client.ensure_bytes(
                {
                    "task": job["task"],
                    "kwargs": job["kwargs"] or {},
                    "args": job["args"] or [],
                }
            )

            client.send_to_broker(NFP.GET, service, workers, uuid_bytes, request)

            # Only periodic job polling advances the polling timestamp.
            client.job_db.update_job(
                juuid,
                last_poll_ts=time.time(),
            )
            log.debug(f"{client.name} - sent GET poll for job {juuid}")

        except Exception as e:
            log.error(f"{client.name} - failed to poll job {juuid}: {e}", exc_info=True)
            # Don't fail the job on poll error, just log and retry next cycle


def dispatcher(client) -> None:
    """
    Dispatcher thread: sends POST and GET requests asynchronously.

    This thread:
    1. Finds NEW jobs and sends POST requests to broker
    2. Finds DISPATCHED/STARTED jobs and sends GET requests to poll for results

    It does NOT wait for responses - the zmq_send_recv thread handles all
    incoming messages and updates the database.

    Args:
        client (object): The client instance containing job_db, exit_event, and configuration.
    """
    while not client.exit_event.is_set() and not client.destroy_event.is_set():
        try:
            dispatch_new_jobs(client)
            poll_active_jobs(client)
            client.handle_file_request()
        except Exception as e:
            log.error(f"{client.name} - dispatcher error: {e}", exc_info=True)
        has_active_jobs = any(
            not future.done_event.is_set()
            for future in list(client.job_futures.values())
        )
        if not client.put_queue.empty():
            continue
        client.dispatcher_event.wait(timeout=0.1 if has_active_jobs else 1)
        client.dispatcher_event.clear()

    # An external exit event must also release the socket thread's blocking poll.
    try:
        client.wakeup_writer.send(b"\x00")
    except BlockingIOError:
        pass  # A full notification buffer already guarantees a wake-up.


class NFPClient(object):
    """
    NFPClient is a client class for interacting with a broker using ZeroMQ for messaging.
    It handles sending and receiving messages, managing connections, and performing tasks.

    Attributes:
        broker (str): The broker address.
        ctx (zmq.Context): The ZeroMQ context.
        broker_socket (zmq.Socket): The ZeroMQ socket for communication with the broker.
        poller (zmq.Poller): The ZeroMQ poller for managing socket events.
        name (str): The name of the client.
        client_private_key_file (str): Path to the client's private key file.
        broker_public_key_file (str): Path to the broker's public key file.

    Methods:
        __init__(inventory, broker, name, exit_event=None):
            Initializes the NFPClient instance with the given parameters.
        ensure_bytes(workers) -> bytes:
            Helper function to convert workers target to bytes.
        reconnect_to_broker():
            Connects or reconnects to the broker.
        send_to_broker(command, service, workers, uuid, request):
            Sends a message to the broker.
        rcv_from_broker(command, service, uuid):
            Waits for a response from the broker.
        post(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job request to the broker and returns the result.
        get(service, task=None, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results.
        get_iter(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results and yields results iteratively.
        fetch_file(url: str | list[str], chunk_size=256000, pipeline=10, timeout=600, read=False):
            Downloads one file or a batch through the File Sharing service.
        run_job(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600):
            Runs a job and returns results produced by workers.
        run_job_iter(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600):
            Runs a job and yields results produced by workers iteratively.
        destroy():
            Cleans up and destroys the client instance.

    Args:
        inventory (NorFabInventory): The inventory object containing base directory information.
        broker: The broker object for communication.
        name (str): The name of the client.
        exit_event (threading.Event, optional): An event to signal client exit. Defaults to None.
    """

    broker = None
    ctx = None
    broker_socket = None
    poller = None
    name = None
    client_private_key_file = None
    broker_public_key_file = None
    public_keys_dir = None
    private_keys_dir = None
    agents = {}

    def __init__(
        self,
        inventory: NorFabInventory,
        broker: str,
        name: str,
        exit_event: Optional[threading.Event] = None,
    ) -> None:
        self.inventory = inventory
        self.name = name
        self.zmq_name = self.name
        self.broker = broker
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "client", self.name
        )
        self.file_transfers = {}  # file transfers tracker
        self.put_queue = queue.Queue()
        self.zmq_auth = self.inventory.broker.get("zmq_auth", True)
        self.build_message = NFP.MessageBuilder()
        self.monitoring = ProcessMonitor()

        # create base directories
        os.makedirs(self.base_dir, exist_ok=True)

        self.job_db = ClientJobDatabase(
            os.path.join(self.base_dir, f"{self.name}.db"),
            jobs_compress=True,
        )

        # generate certificates and create directories
        if self.zmq_auth is not False:
            generate_certificates(
                self.base_dir,
                cert_name=self.name,
                broker_keys_dir=os.path.join(
                    self.inventory.base_dir,
                    "__norfab__",
                    "files",
                    "broker",
                    "public_keys",
                ),
                inventory=self.inventory,
            )
            self.public_keys_dir = os.path.join(self.base_dir, "public_keys")
            self.private_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        self.exit_event = threading.Event() if exit_event is None else exit_event
        self.destroy_event = (
            threading.Event()
        )  # destroy event, used by worker to stop its client
        self.mmi_queue = queue.Queue(maxsize=0)
        self.outbound_queue = queue.Queue(maxsize=NFP.OUTBOUND_QUEUE_SIZE)
        # Native sockets allow any producer thread to wake the sole ZeroMQ owner.
        self.wakeup_reader, self.wakeup_writer = socket.socketpair()
        self.wakeup_reader.setblocking(False)
        self.wakeup_writer.setblocking(False)
        self.poller.register(self.wakeup_reader, zmq.POLLIN)
        self.job_futures = {}
        self.dispatcher_event = threading.Event()

        # Configuration for dispatcher
        self.poll_interval = 10  # Seconds between periodic GET polls for the same job
        self.dispatch_batch_size = 10  # Max jobs to process per dispatch cycle
        self.recover_job_futures()

        # start ZeroMQ owner thread - handles queued outgoing and incoming messages
        self.recv_thread = threading.Thread(
            target=zmq_send_recv,
            daemon=True,
            name=f"{self.name}_zmq_send_recv_thread",
            args=(self,),
        )
        self.recv_thread.start()

        # start dispatcher thread - sends POST/GET requests asynchronously
        self.dispatcher_thread = threading.Thread(
            target=dispatcher,
            daemon=True,
            name=f"{self.name}_dispatcher",
            args=(self,),
        )
        self.dispatcher_thread.start()

    def get_stats(self) -> dict:
        """Return the client's validated monitoring snapshot as a dictionary."""
        receiver_alive = bool(
            getattr(self, "recv_thread", None) and self.recv_thread.is_alive()
        )
        stats = ClientMonitoringStats(
            name=self.name,
            status="active" if receiver_alive else "starting",
            process=self.monitoring.process_stats(),
            messaging=self.monitoring.messaging_stats(),
            broker=self.broker,
            reconnects=self.monitoring.reconnects,
            outbound_queue_depth=self.outbound_queue.qsize(),
            jobs=JobMonitoringStats.model_validate(self.job_db.jobs_stats()),
            database=DatabaseMonitoringStats.model_validate(
                self.job_db.jobs_db_stats()
            ),
        )
        return stats.model_dump(mode="json")

    def get_status(self) -> dict:
        """Return client identity, runtime paths, and security configuration."""
        receiver_alive = bool(
            getattr(self, "recv_thread", None) and self.recv_thread.is_alive()
        )
        return {
            "name": self.name,
            "role": "client",
            "status": "active" if receiver_alive else "starting",
            "zmq_name": self.zmq_name,
            "broker": self.broker,
            "directories": {
                "base_dir": self.base_dir,
                "public_keys_dir": self.public_keys_dir,
                "private_keys_dir": self.private_keys_dir,
            },
            "security": {
                "client_private_key_file": self.client_private_key_file,
                "broker_public_key_file": self.broker_public_key_file,
                "zmq_auth": self.zmq_auth,
            },
        }

    def ensure_bytes(self, value: Union[bytes, str]) -> bytes:
        """
        Helper function to convert value to bytes.
        """
        if isinstance(value, bytes):
            return value
        # transform string to bytes
        if isinstance(value, str):
            return value.encode("utf-8")
        # convert value to json string
        else:
            return orjson.dumps(value)

    def reconnect_to_broker(self) -> None:
        """
        Connect or reconnect to the broker.

        This method handles the connection or reconnection to the broker by:

        - Closing the existing broker socket if it exists.
        - Creating a new DEALER socket.
        - Setting the socket options including the identity and linger.
        - Loading the client's private and public keys for CURVE encryption.
        - Loading the broker's public key for CURVE encryption.
        - Connecting the socket to the broker.
        - Registering the socket with the poller for incoming messages.
        - Logging the connection status.
        - Incrementing the reconnect statistics counter.
        """
        if self.broker_socket:
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)
        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.zmq_name, "utf8")
        self.broker_socket.linger = 0

        if self.zmq_auth is not False:
            # We need two certificates, one for the client and one for
            # the server. The client must know the server's public key
            # to make a CURVE connection.
            self.client_private_key_file = os.path.join(
                self.private_keys_dir, f"{self.name}.key_secret"
            )
            client_public, client_secret = zmq.auth.load_certificate(
                self.client_private_key_file
            )
            self.broker_socket.curve_secretkey = client_secret
            self.broker_socket.curve_publickey = client_public

            # The client must know the server's public key to make a CURVE connection.
            self.broker_public_key_file = os.path.join(
                self.public_keys_dir, "broker.key"
            )
            server_public, _ = zmq.auth.load_certificate(self.broker_public_key_file)
            self.broker_socket.curve_serverkey = server_public

        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)
        log.debug(f"{self.name} - client connected to broker at '{self.broker}'")
        self.monitoring.record_reconnect()

    def send_to_broker(
        self, command: str, service, workers, uuid: str, request
    ) -> None:
        """
        Sends a command to the broker.

        Args:
            command (str): The command to send (e.g., NFP.POST, NFP.GET).
            service (str): The service to which the command is related.
            workers (str): The workers involved in the command.
            uuid (str): The unique identifier for the request.
            request (str): The request payload to be sent.
        """
        if command == NFP.POST:
            msg = self.build_message.client_to_broker_post(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        elif command == NFP.GET:
            msg = self.build_message.client_to_broker_get(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        elif command == NFP.PUT:
            msg = self.build_message.client_to_broker_put(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        elif command == NFP.STREAM:
            msg = [b"", NFP.CLIENT, command, service, workers, uuid, request]
        elif command == NFP.MMI:
            msg = self.build_message.client_to_broker_mmi(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        else:
            log.error(
                f"{self.name} - cannot send '{command}' to broker, command unsupported"
            )
            return

        log.debug(f"{self.name} - queueing '{msg}'")

        if self.destroy_event.is_set():
            return

        try:
            self.outbound_queue.put_nowait(msg)
        except queue.Full:
            log.warning(
                f"{self.name} - outbound queue is full, dropping '{command}' "
                f"message to broker"
            )
            return

        try:
            self.wakeup_writer.send(b"\x00")
        except BlockingIOError:
            pass  # The queued message is safe; a notification is already pending.
        except OSError:
            if not self.destroy_event.is_set():
                raise

    def mmi(
        self,
        service: str,
        task: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: Union[str, list] = "all",
        uuid: hex = None,
        timeout: int = 30,
    ) -> dict:
        """
        Send an MMI (management interface) request to a service via the broker.

        MMI requests are intended for lightweight, broker-routed management or
        introspection operations (e.g., service metadata, health, inventory-like
        queries) that return a single aggregated response payload.

        Args:
            service: Target service name.
            task: Service task name to execute.
            args: Positional arguments for the task.
            kwargs: Keyword arguments for the task.
            workers: Workers selector. Can be ``"all"``, ``"any"``, or a list of names.
            uuid: Optional request UUID. If not provided, a random UUID is generated.
            timeout: Maximum time (seconds) to wait for the MMI reply.

        Returns:
            Dictionary containing ``status``, ``results``, and ``errors`` keys:

                - ``status``: HTTP-like status code as a string (e.g., ``"200"``, ``"408"``).
                - ``results``: Decoded JSON payload from the broker/service.
                - ``errors``: List of error strings.
        """
        service_str = service
        uuid_str = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        ret = {"status": "200", "results": {}, "errors": []}

        service = self.ensure_bytes(service_str)
        uuid = self.ensure_bytes(uuid_str)
        workers = self.ensure_bytes(workers)

        request = self.ensure_bytes(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        )

        log.info(
            f"{self.name} - Submitting MMI task '{task}' to service '{service_str}' with request uuid '{uuid_str}'"
        )
        self.send_to_broker(NFP.MMI, service, workers, uuid, request)

        deadline = time.time() + timeout
        while time.time() < deadline:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
                ret["errors"].append(
                    f"{self.name} - '{uuid_str}:{service_str}' MMI interrupted (client stopping)"
                )
                ret["status"] = "499"
                break

            try:
                msg = self.mmi_queue.get(block=True, timeout=0.5)
                self.mmi_queue.task_done()
            except queue.Empty:
                continue

            (
                empty,
                reply_header,
                reply_command,
                reply_service,
                reply_uuid,
                reply_status,
                reply_task_result,
            ) = msg

            # Defer unrelated replies and continue scanning.
            if reply_uuid != uuid:
                self.mmi_queue.put(msg)
                continue

            if reply_header != NFP.BROKER and reply_command != NFP.MMI:
                ret["errors"].append(
                    f"{self.name} - '{uuid_str}:{service_str}' MMI unexpected reply header/command"
                )
                ret["status"] = reply_status.decode("utf-8")
                break

            try:
                ret["results"] = orjson.loads(reply_task_result)
                ret["status"] = reply_status.decode("utf-8")
                log.info(
                    f"{self.name} - Completed MMI task '{task}' request '{uuid_str}' with status {ret['status']}"
                )
            except Exception as e:
                ret["errors"].append(
                    f"{self.name} - '{uuid_str}:{service_str}' MMI failed to decode reply payload: {e}"
                )
                ret["results"] = {"status": "Invalid MMI response payload"}
                ret["status"] = "500"
            break
        else:
            msg = f"{self.name} - '{uuid_str}:{service_str}' MMI request {timeout}s timeout exceeded."
            log.error(msg)
            ret["errors"].append(msg)
            ret["results"] = {"status": "MMI Request Timeout"}
            ret["status"] = "408"

        return ret

    def delete_fetched_files(self, filepath: str = "*") -> dict:
        """
        Delete files and folders matching the filepath glob pattern.

        Args:
            filepath (str): Glob pattern to match files/folders. Default is "*" (all files).

        Returns:
            dict: Dictionary with 'deleted' list of deleted paths and 'errors' list of error messages.
        """
        files_folder = os.path.join(self.base_dir, "fetchedfiles")

        result = {"deleted": [], "errors": []}

        # Build full pattern path
        pattern = os.path.join(files_folder, filepath)

        # Find all matching files and folders
        matches = glob.glob(pattern, recursive=True)

        # Sort by depth (deepest first) to avoid deleting parent before children
        matches.sort(key=lambda x: x.count(os.sep), reverse=True)

        for match in matches:
            try:
                if os.path.isfile(match):
                    os.remove(match)
                    result["deleted"].append(match)
                    log.debug(f"{self.name} - deleted file: {match}")
                elif os.path.isdir(match):
                    shutil.rmtree(match)
                    result["deleted"].append(match)
                    log.debug(f"{self.name} - deleted folder: {match}")
            except Exception as e:
                error_msg = f"Failed to delete {match}: {str(e)}"
                result["errors"].append(error_msg)
                log.error(f"{self.name} - {error_msg}")

        return result

    def fetch_file(
        self,
        url: str | list[str],
        chunk_size: int = 256000,
        pipeline: int = 10,
        timeout: int = 600,
        read: bool = False,
        *,
        worker: str = None,
        destination: str = None,
    ) -> dict | list[dict]:
        """Download files, reusing cached copies when their hashes match.

        Queries all FileSharing workers for file details, then downloads files
        sequentially, alternating between available workers in round-robin order.
        Selection restarts on each call. Git URLs use each worker's resolved path.

        Args:
            url: An nf:// or git:// URL, or a list of URLs. With worker, also
                accepts paths and file:// URLs resolved on that worker.
            chunk_size: Bytes per chunk. Defaults to 256000.
            pipeline: Maximum continuation requests in flight. Defaults to 10.
            timeout: Seconds to wait for each job. Defaults to 600.
            read: Return UTF-8 text instead of local paths. Defaults to False.
            worker: Exact source worker name. Omit for FileSharing discovery.
            destination: Output path for a single native worker file. Defaults
                to a cache path isolated by worker and source path.

        Returns:
            A dictionary with status, content, and error for a string URL, or a
            list of dictionaries in input order for a URL list. Missing files
            return status 404. An empty list returns an empty list.

        Raises:
            TypeError: If url is not a string or a list of strings.
            ValueError: Invalid chunk size, pipeline, timeout, or destination.
            TimeoutError: Native metadata or transfer job timed out.
            OSError: If a local file operation fails; stops the batch.
            UnicodeError: If read=True and the file is not valid UTF-8.
        """
        # Accept one URL or a list; keep the original return format.
        single = isinstance(url, str)
        if single:
            url = [url]
        if not isinstance(url, list) or any(not isinstance(item, str) for item in url):
            raise TypeError("url must be a string or a list of strings")
        if destination is not None and (
            not single or not worker or url[0].startswith(("nf://", "git://"))
        ):
            raise ValueError(
                "destination requires a single native path and a named worker"
            )
        if worker and (not 0 < chunk_size <= 1048576 or pipeline < 1 or timeout <= 0):
            raise ValueError(
                "chunk_size must be 1..1048576; pipeline and timeout must be positive"
            )
        # Resolve Git URLs to file paths on each worker.
        git_results = {}
        git_urls = [item for item in url if item.startswith("git://")]
        if git_urls:
            git_results = (
                self.run_job(
                    service="filesharing",
                    workers=[worker] if worker else "all",
                    task="resolve_git_url",
                    kwargs={"url": git_urls},
                    timeout=timeout,
                )
                or {}
            )

        # Get file sizes and hashes from all workers in one request.
        metadata_urls = [item for item in url if item.startswith("nf://")]
        for response in git_results.values():
            if not response["failed"]:
                metadata_urls.extend(
                    entry["result"]
                    for entry in (response["result"] or {}).values()
                    if not entry["failed"]
                )
        if worker:
            metadata_urls.extend(
                item for item in url if not item.startswith(("nf://", "git://"))
            )
        metadata = {}
        if metadata_urls:
            stat_uuid = uuid4().hex
            metadata = (
                self.run_job(
                    service="all" if worker else "filesharing",
                    task="file_stat",
                    uuid=stat_uuid,
                    workers=[worker] if worker else "all",
                    kwargs={"url": metadata_urls},
                    timeout=timeout,
                )
                or {}
            )
            if worker and self.job_db.get_job(stat_uuid)["status"] == JobStatus.STALE:
                raise TimeoutError("file metadata request timed out")
        workers = sorted(metadata)
        next_worker = 0
        results = []
        fetched_root = os.path.realpath(os.path.join(self.base_dir, "fetchedfiles"))
        # Loop over URLs and download each file from an available worker.
        for item in url:
            result = {"status": "404", "content": None, "error": "file not found"}
            results.append(result)
            native = bool(worker) and not item.startswith(("nf://", "git://"))
            if not native and not item.startswith(("nf://", "git://")):
                result.update(status="500", error="Invalid url format")
                continue

            # Choose the next worker that has this file.
            resolved_url = item
            details = None
            # Try each worker once, starting where the previous selection left off.
            for offset in range(len(workers)):
                # Wrap back to the first worker after reaching the end of the list.
                index = (next_worker + offset) % len(workers)
                selected_worker = workers[index]
                response = metadata[selected_worker]
                if response["failed"]:
                    continue
                candidate_url = item
                if item.startswith("git://"):
                    resolution = git_results.get(selected_worker)
                    if not resolution or resolution["failed"]:
                        continue
                    entry = (resolution["result"] or {}).get(item)
                    if not entry or entry["failed"]:
                        continue
                    candidate_url = entry["result"]
                entry = (response["result"] or {}).get(candidate_url)
                if entry and entry["failed"]:
                    result["error"] = entry["errors"]
                if entry and not entry["failed"]:
                    details = entry["result"]
                    resolved_url = candidate_url
                    # Start the next file with the worker after this one.
                    next_worker = (index + 1) % len(workers)
                    break
            if native and details is None:
                continue
            if not native and not resolved_url.startswith("nf://"):
                continue
            if native:
                local_path = (
                    os.path.abspath(destination)
                    if destination
                    else os.path.join(
                        fetched_root,
                        hashlib.sha256(worker.encode()).hexdigest(),
                        hashlib.sha256(item.encode()).hexdigest(),
                        os.path.basename(self.safe_path(item)),
                    )
                )
            else:
                local_path = os.path.realpath(
                    os.path.join(
                        fetched_root,
                        *resolved_url.removeprefix("nf://")
                        .replace("\\", "/")
                        .lstrip("/")
                        .split("/"),
                    )
                )
            # Reject paths outside the local cache directory.
            try:
                safe = (
                    native
                    or os.path.commonpath([fetched_root, local_path]) == fetched_root
                )
            except ValueError:
                safe = False
            if not safe:
                result.update(status="500", error="Invalid url path")
                continue
            if details is None:
                continue
            result.update(status="200", error=None)
            # Check whether the cached file matches the worker's copy.
            cached = False
            if (
                os.path.isfile(local_path)
                and os.path.getsize(local_path) == details["size_bytes"]
            ):
                cached = self.file_stat(local_path)["md5hash"] == details["md5hash"]
            # Download the file if it is missing or has changed.
            if not cached:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                uuid = uuid4().hex
                self.file_transfers[uuid] = {
                    **details,
                    "started": False,
                    "error": None,
                    "destination": open(local_path, "wb"),
                    "total_bytes_received": 0,
                    "offset": 0,
                    "credit": pipeline,
                    "chunk_size": chunk_size,
                    "file_hash": hashlib.md5(),
                    # The starting event triggers the first request; pipeline the rest.
                    "chunk_requests_remaining": max(
                        0,
                        (details["size_bytes"] + chunk_size - 1) // chunk_size - 1,
                    ),
                }
                try:
                    # Fetch from the worker that supplied the file details.
                    reply = (
                        self.run_job(
                            uuid=uuid,
                            service="all",
                            workers=[selected_worker],
                            task="serve_file",
                            kwargs={"path": resolved_url, "chunk_size": chunk_size},
                            timeout=timeout,
                        )
                        or {}
                    )
                    transfer = self.file_transfers[uuid]
                    if transfer["error"] is not None:
                        raise transfer["error"]
                    if (
                        native
                        and self.job_db.get_job(uuid)["status"] == JobStatus.STALE
                    ):
                        raise TimeoutError(f"file transfer timed out: {item}")
                    # Check the worker reply and the downloaded file hash.
                    response = reply.get(selected_worker)
                    if response and response["failed"]:
                        result.update(status="404", error=response["errors"])
                    elif (
                        transfer["total_bytes_received"] != details["size_bytes"]
                        or transfer["file_hash"].hexdigest() != details["md5hash"]
                    ):
                        result.update(
                            status="400",
                            error="Download failed, size or MD5 hash mismatch",
                        )
                    elif not response:
                        result.update(status="404", error="File download failed")
                finally:
                    self.file_transfers.pop(uuid)["destination"].close()
                if result["status"] != "200":
                    continue
            # Return the file contents or its local path.
            if read:
                with open(local_path, "r", encoding="utf-8") as file_obj:
                    result["content"] = file_obj.read()
            else:
                result["content"] = local_path
        return results[0] if single else results

    @staticmethod
    def safe_path(url: str) -> str:
        """Resolve a path on the client filesystem.

        Args:
            url: Plain path, file://relative URL, or file:///absolute URL.

        Returns:
            Absolute local path. Native paths are not sandboxed or confined.

        Raises:
            ValueError: Empty path or unsupported URL scheme. Published nf://
                and git:// URLs must be downloaded with fetch_file instead.
        """
        if not isinstance(url, str) or not url:
            raise ValueError("file path must be a nonempty string")
        if "://" in url and not url.startswith("file://"):
            raise ValueError("invalid URL format")
        path = unquote(url[7:]) if url.startswith("file://") else url
        if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return os.path.abspath(path)

    def file_stat(self, url: str) -> dict:
        """Read local file size and MD5 without contacting a worker.

        Args:
            url: Plain path or file:// URL on this client.

        Returns:
            Metadata with md5hash, size_bytes, and exists, matching the worker
            task's metadata fields. MD5 detects corruption, not authenticity.

        Raises:
            ValueError: Invalid path or unsupported URL scheme.
            OSError: The file is missing, unreadable, or a directory.
        """
        file_hash = hashlib.md5()
        size = 0
        with open(self.safe_path(url), "rb") as source:
            for chunk in iter(lambda: source.read(8192), b""):
                file_hash.update(chunk)
                size += len(chunk)
        return {"md5hash": file_hash.hexdigest(), "size_bytes": size, "exists": True}

    def handle_file_request(self) -> None:
        """Handle one queued file request on the client dispatcher thread.

        Return immediately when the queue is empty. Valid requests receive file
        metadata or one binary chunk; access and read failures receive an error
        reply. Malformed requests without usable routing are discarded. Processing
        one request per call leaves time for job dispatch and result polling.
        """
        try:
            juuid, request, service = self.put_queue.get_nowait()
        except queue.Empty:
            return
        if not isinstance(request, dict) or request.get("file_read") is not True:
            return
        worker, url = request.get("worker"), request.get("path")
        if not isinstance(worker, str):
            return
        job = self.job_db.get_job(juuid)
        supplied = False
        values = [job["args"], job["kwargs"]] if job else []
        while values:
            value = values.pop()
            if isinstance(value, dict):
                values.extend(value.values())
            elif isinstance(value, (list, tuple)):
                values.extend(value)
            elif value == url:
                supplied = True
                break
        if (
            job
            and job["status"] not in TERMINAL_JOB_STATUSES
            and isinstance(url, str)
            and url.startswith("file://")
            and supplied
            and worker in job["workers_dispatched"]
        ):
            try:
                if request.get("file_details"):
                    command = NFP.PUT
                    data = orjson.dumps({"file_details": self.file_stat(url)})
                else:
                    offset, size = request["offset"], request["size"]
                    if type(offset) is not int or type(size) is not int:
                        raise ValueError("offset and size must be integers")
                    if offset < 0 or not 0 < size <= 1048576:
                        raise ValueError(
                            "offset must be nonnegative and size between 1 and 1048576"
                        )
                    with open(self.safe_path(url), "rb") as source:
                        source.seek(offset)
                        data = source.read(size)
                    command = NFP.STREAM
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                OverflowError,
            ) as exc:
                command = NFP.PUT
                data = orjson.dumps({"file_error": str(exc)})
        else:
            command = NFP.PUT
            data = orjson.dumps({"file_error": "file was not supplied in this job"})
        self.send_to_broker(
            command,
            service,
            self.ensure_bytes([worker]),
            juuid.encode(),
            data,
        )

    def upload_file(
        self,
        url: str,
        worker: str,
        destination: str = None,
        timeout: int = 600,
        chunk_size: int = 256000,
    ) -> dict:
        """Ask a worker to pull a local file through the running receive job.

        Args:
            url: Local file://relative or file:///absolute URL.
            worker: Exact destination worker name, from any service.
            destination: Output path on the worker, overwritten if present.
                Defaults to a unique file in its client's fetchedfiles directory.
            timeout: Job timeout in seconds.
            chunk_size: Bytes per request, from 1 through 1048576.

        Returns:
            Normal job results keyed by worker; successful results contain the
            destination path. Failed transfers may leave partial files.

        Raises:
            ValueError: URL does not use file://.
        """
        if not url.startswith("file://"):
            raise ValueError("upload_file requires a file:// URL")
        return self.run_job(
            "all",
            "receive_file",
            workers=[worker],
            timeout=timeout,
            kwargs={"url": url, "destination": destination, "chunk_size": chunk_size},
        )

    def recover_job_futures(self) -> None:
        active_statuses = [
            JobStatus.NEW,
            JobStatus.SUBMITTING,
            JobStatus.DISPATCHED,
            JobStatus.STARTED,
            JobStatus.WAITING_CLIENT_INPUT,
        ]
        for job in self.job_db.fetch_jobs(active_statuses, limit=10000):
            if job["deadline"] and time.time() >= job["deadline"]:
                self.job_db.expire_job(job["uuid"])
                continue

            if job["status"] == JobStatus.SUBMITTING:
                self.job_db.update_job(job["uuid"], status=JobStatus.NEW)

            # Poll restored jobs immediately to fetch results saved while the client was offline.
            self.job_db.update_job(job["uuid"], last_poll_ts=0)
            self.job_futures[job["uuid"]] = NFPJobFuture(
                client=self,
                uuid=job["uuid"],
                service=job["service"],
                task=job["task"],
                workers=job["workers_requested"],
                timeout=job["timeout"],
                kwargs=job["kwargs"],
            )

    def submit_job(
        self,
        service: str,
        task: str,
        uuid: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: Union[str, list] = "all",
        timeout: int = 600,
    ) -> NFPJobFuture:
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        deadline = time.time() + timeout

        self.job_db.add_job(
            uuid, service, task, workers, args, kwargs, timeout, deadline
        )
        future = NFPJobFuture(
            client=self,
            uuid=uuid,
            service=service,
            task=task,
            workers=workers,
            timeout=timeout,
            kwargs=kwargs,
        )
        self.job_futures[uuid] = future
        self.dispatcher_event.set()
        log.info(
            f"{self.name} - Submitted job {uuid} to service '{service}', task '{task}', workers '{workers}'"
        )

        return future

    def run_job(
        self,
        service: str,
        task: str,
        uuid: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: Union[str, list] = "all",
        timeout: int = 600,
        markdown: bool = False,
        nowait: bool = False,
    ) -> Any:
        """
        Run a job on the specified service and task, with optional arguments and timeout settings.

        This method submits a job to the database and waits for the dispatcher and receiver
        threads to process it asynchronously. The job progresses through states:
        NEW -> SUBMITTING -> DISPATCHED -> STARTED -> COMPLETED (or FAILED/STALE)

        Args:
            service (str): The name of the service to run the job on.
            task (str): The task to be executed.
            uuid (str, optional): A unique identifier for the job. If not provided, a new UUID will be generated. Defaults to None.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to run the job on. Defaults to "all".
            timeout (int, optional): The maximum time in seconds to wait for the job to complete. Defaults to 600.
            markdown (bool, optional): Convert results to markdown representation
            nowait (bool, optional): If false, wait for job to complete for timeout, return job details otherwise

        Returns:
            Any: Worker results, including failed timeout results for stale jobs
                (status="timeout", result=None). Expiry does not cancel workers.
                Returns None on client failure or shutdown.
        """
        future = self.submit_job(
            service=service,
            task=task,
            uuid=uuid,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )

        if nowait is True:
            return {
                "uuid": future.uuid,
                "service": service,
            }

        return future.result(timeout=timeout, markdown=markdown)

    def get_agent(self, profile: str = "default") -> "NFAgent":
        """
        Return an NFAgent bound to this client for agentic AI interactions.

        The agent is built lazily on first call to ``invoke`` or ``stream``.
        Configuration is read from ``inventory.yaml`` under
        ``client -> agent_profiles -> <profile>``.

        Args:
            profile (str): Agent profile name defined in inventory.yaml.
                Defaults to ``"default"``.

        Returns:
            NFAgent: Configured agent instance ready to call.

        Raises:
            ImportError: If ``norfab[clientagent]`` dependencies are not installed.
            ValueError: If the requested profile is not found in the inventory.

        Example::

            agent = client.get_agent(profile="default")
            answer = agent.invoke("Show me interfaces with errors on all routers")
        """
        try:
            from norfab.core.agent import NFAgent
        except ImportError:
            log.error(
                "Agent dependencies not installed. Run: pip install norfab[clientagent]",
                exc_info=True,
            )
            return None

        if profile not in self.agents:
            self.agents[profile] = NFAgent(client=self, profile=profile)

        return self.agents[profile]

    def destroy(self) -> None:
        """
        Gracefully shuts down the client.

        This method logs an interrupt message, sets the destroy event, waits
        for background threads to stop, then destroys the client context to
        ensure a clean shutdown.
        """
        if self.ctx.closed:
            return
        log.info(f"{self.name} - client interrupt received, killing client")
        self.destroy_event.set()
        self.dispatcher_event.set()
        try:
            self.wakeup_writer.send(b"\x00")
        except BlockingIOError:
            pass  # A pending notification will wake the socket thread.
        for future in self.job_futures.values():
            future.mark_done(self.job_db.get_job(future.uuid))
        # Wait for background threads to exit before destroying the ZMQ context.
        # Without this, the dispatcher/receiver threads may still be executing
        # between their destroy_event check and a socket call, causing
        # "not a socket" ZMQError when ctx.destroy() closes sockets under them.
        if self.recv_thread.is_alive():
            self.recv_thread.join()
        if self.dispatcher_thread.is_alive():
            self.dispatcher_thread.join()
        self.poller.unregister(self.wakeup_reader)
        self.wakeup_reader.close()
        self.wakeup_writer.close()
        self.job_db.close()
        self.ctx.destroy()
        # close all file transfer files
        for file_transfer in self.file_transfers.values():
            file_transfer["destination"].close()
