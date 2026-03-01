import logging
import sqlite3
import zlib
import zmq
import time
import orjson
import os
import threading
import queue
import hashlib
import glob
import shutil
from contextlib import contextmanager
from uuid import uuid4  # random uuid

from .security import generate_certificates
from . import NFP
from norfab.core.inventory import NorFabInventory
from norfab.utils.markdown_results import markdown_results
from typing import Any, Optional, Tuple, Dict, List, Set, Union

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NIRFAB client, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------


# Job status constants
class JobStatus:
    NEW = "NEW"
    SUBMITTING = "SUBMITTING"  # POST sent, waiting for broker ACK
    DISPATCHED = "DISPATCHED"  # Broker dispatched to workers
    STARTED = "STARTED"  # At least one worker started processing
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"  # Job exceeded deadline without completion


class ClientJobDatabase:
    """Lightweight client-side job and events store."""

    def __init__(self, db_path: str, jobs_compress: bool = True):
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
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
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
        return zlib.compress(raw, level=1) if self.jobs_compress else raw

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
                "CREATE INDEX IF NOT EXISTS idx_events_job_uuid ON events(job_uuid)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_last_poll ON jobs(last_poll_timestamp)"
            )

    def add_job(
        self,
        uuid: str,
        service: str,
        task: str,
        workers: Any,
        args: list,
        kwargs: dict,
        timeout: int,
        deadline: float,
    ) -> None:

        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO jobs (uuid, service, task, args, kwargs, timeout, deadline,
                                  status, workers_requested, received_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?)
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
                    time.ctime(),
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

        def _store_set(label: str, value: Set[str] | List[str] | None):
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

        with self._transaction(write=True) as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(fields)} WHERE uuid = ?",
                (*values, uuid),
            )

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
                ORDER BY created_at {order_direction}
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


def recv(client):
    """
    Receiver thread: processes all incoming messages from the broker and updates the database.

    This function continuously polls the client's broker socket for messages
    until the client's exit event is set. It handles:
    - EVENT messages: stored in the events table
    - RESPONSE messages: updates job status in the database based on response type

    The receiver thread is the ONLY thread that reads from the socket, eliminating
    contention issues. All job state changes are persisted to the database.

    Args:
        client (object): The client instance containing the broker socket,
                         poller, job_db, and configuration.
    """
    while not client.exit_event.is_set() and not client.destroy_event.is_set():
        # Poll socket for messages every 500ms interval
        try:
            items = client.poller.poll(500)
        except KeyboardInterrupt:
            break
        except Exception:
            continue

        if not items:
            continue

        with client.socket_lock:
            try:
                msg = client.broker_socket.recv_multipart(zmq.NOBLOCK)
            except zmq.Again:
                continue

        client.stats_recv_from_broker += 1

        # Message format: [empty, header, command, service, uuid, status, payload]
        if len(msg) < 7:
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
            handle_stream(client, juuid, status, payload)
            continue

        try:
            payload = orjson.loads(msg[6])
        except Exception as e:
            log.error(
                f"{client.name} - failed to parse message, error '{e}'", exc_info=True
            )
            continue

        # Handle EVENT messages
        if command == NFP.EVENT:
            handle_event(client, juuid, payload, msg)

        # Handle RESPONSE messages
        if command == NFP.RESPONSE:
            handle_response(client, juuid, status, payload)

        # handle MMI messages
        if command == NFP.MMI:
            client.mmi_queue.put(msg)


def handle_event(client: object, juuid: str, payload: dict, msg: list):
    """
    Handle EVENT messages and update job database accordingly.

    Args:
        client: The client instance
        juuid: Job UUID
        payload: Event payload dictionary
        msg: Original message multipart for queue
    """
    client.event_queue.put(msg)
    client.stats_recv_event_from_broker += 1
    client.job_db.add_event(
        job_uuid=juuid,
        message=payload.get("message", ""),
        severity=payload.get("severity", "INFO"),
        task=payload.get("task"),
        event_data=payload,
    )


def handle_response(client, juuid: str, status: str, payload: dict):
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

    # Broker accepted POST - contains dispatched workers list
    if status == "202":  # ACCEPTED
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
        client.job_db.update_job(
            juuid,
            status=JobStatus.STARTED,
            workers_started=list(started),
        )
        log.debug(
            f"{client.name} - job {juuid} acknowledged by worker: {worker_single}"
        )
        return

        # GET dispatched to workers (broker 202 response to GET)
        if workers_list:
            log.debug(
                f"{client.name} - job {juuid} GET dispatched to workers: {workers_list}"
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

        is_complete = completed == dispatched and len(dispatched) > 0

        client.job_db.update_job(
            juuid,
            status=JobStatus.COMPLETED if is_complete else JobStatus.STARTED,
            workers_completed=list(completed),
            result_data=existing_results,
            completed_ts=time.ctime() if is_complete else None,
        )

        if is_complete:
            log.debug(f"{client.name} - job {juuid} completed")
        return

    # Handle 300 Pending - job still in progress
    if status == "300":
        worker = payload.get("worker")
        if worker and worker not in job["workers_started"]:
            job["workers_started"].append(worker)
            client.job_db.update_job(
                juuid,
                status=JobStatus.STARTED,
                workers_started=job["workers_started"],
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
        log.error(f"{client.name} - job {juuid} failed: {error_msg}")
        return


def handle_stream(client, juuid: str, status: str, payload: bytes):
    job = client.job_db.get_job(juuid)
    file_transfer = client.file_transfers.get(juuid)

    if not job:
        log.error(f"{client.name} - received stream for unknown job {juuid}")
        return

    if not file_transfer:
        log.error(f"{client.name} - received stream for unknown file transfer {juuid}")
        return

    destination = file_transfer["destination"]  # file object
    size = len(payload)
    file_transfer["credit"] += 1  # Up to PIPELINE chunks in transit
    file_transfer["total_bytes_received"] += size

    # save received chunk
    destination.write(payload)
    file_transfer["file_hash"].update(payload)

    # check if done
    if file_transfer["total_bytes_received"] >= file_transfer["size_bytes"]:
        destination.close()

        # check md5hash mismatch
        file_hash = file_transfer["file_hash"].hexdigest()
        if file_hash != file_transfer["md5hash"]:
            client.job_db.update_job(
                juuid,
                status=JobStatus.FAILED,
                errors=["Download failed, MD5 hash mismatch"],
            )
            log.error(
                f"{client.name} - file download failed, MD5 hash mismatch, job '{juuid}', filename '{destination.name}'"
            )

        log.debug(
            f"{client.name} - finished file download, job '{juuid}', filename '{destination.name}'"
        )
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


def dispatch_new_jobs(client):
    """
    Find NEW jobs and send POST requests to broker.
    Non-blocking: sends request and updates status to SUBMITTING.
    """
    for job in client.job_db.fetch_jobs(
        [JobStatus.NEW], limit=client.dispatch_batch_size
    ):
        juuid = job["uuid"]

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


def poll_active_jobs(client):
    """
    Find active jobs and send GET requests to poll for results.
    Non-blocking: sends request with 5-second throttling via last_poll_timestamp.
    """
    # Jobs that are ready for GET polling (dispatched or started)
    active_statuses = [JobStatus.DISPATCHED, JobStatus.STARTED]

    # fetch_jobs filters by min_poll_age to enforce polling throttle
    for job in client.job_db.fetch_jobs(
        active_statuses,
        limit=client.dispatch_batch_size,
        min_poll_age=client.poll_interval,
    ):
        juuid = job["uuid"]
        deadline = job["deadline"]
        now = time.time()

        # Check if job has exceeded deadline
        if now >= deadline:
            client.job_db.update_job(
                juuid,
                status=JobStatus.STALE,
                errors=["Job deadline reached without completion"],
                completed_ts=time.ctime(),
            )
            continue

        try:
            # Send GET request (non-blocking)
            service = client.ensure_bytes(job["service"])
            uuid_bytes = client.ensure_bytes(juuid)
            workers = client.ensure_bytes(job["workers_dispatched"])
            request = client.ensure_bytes(
                {
                    "task": job["task"],
                    "kwargs": job["kwargs"] or {},
                    "args": job["args"] or [],
                }
            )

            client.send_to_broker(NFP.GET, service, workers, uuid_bytes, request)

            # Update last_poll_ts to enforce 5-second throttle
            client.job_db.update_job(
                juuid,
                last_poll_ts=time.time(),
            )
            log.debug(f"{client.name} - sent GET poll for job {juuid}")

        except Exception as e:
            log.error(f"{client.name} - failed to poll job {juuid}: {e}", exc_info=True)
            # Don't fail the job on poll error, just log and retry next cycle


def dispatcher(client):
    """
    Dispatcher thread: sends POST and GET requests asynchronously.

    This thread:
    1. Finds NEW jobs and sends POST requests to broker
    2. Finds DISPATCHED/STARTED jobs and sends GET requests to poll for results

    It does NOT wait for responses - the receiver thread handles all incoming
    messages and updates the database.

    Args:
        client (object): The client instance containing job_db, exit_event, and configuration.
    """
    while not client.exit_event.is_set() and not client.destroy_event.is_set():
        try:
            dispatch_new_jobs(client)
            poll_active_jobs(client)
        except Exception as e:
            log.error(f"{client.name} - dispatcher error: {e}", exc_info=True)
        time.sleep(0.1)


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
        stats_send_to_broker (int): Counter for messages sent to the broker.
        stats_recv_from_broker (int): Counter for messages received from the broker.
        stats_reconnect_to_broker (int): Counter for reconnections to the broker.
        stats_recv_event_from_broker (int): Counter for events received from the broker.
        client_private_key_file (str): Path to the client's private key file.
        broker_public_key_file (str): Path to the broker's public key file.

    Methods:
        __init__(inventory, broker, name, exit_event=None, event_queue=None):
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
        fetch_file(url, destination=None, chunk_size=250000, pipeline=10, timeout=600, read=False):
            Downloads a file from the Broker File Sharing Service.
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
        event_queue (queue.Queue, optional): A queue for handling events. Defaults to None.
    """

    broker = None
    ctx = None
    broker_socket = None
    poller = None
    name = None
    stats_send_to_broker = 0
    stats_recv_from_broker = 0
    stats_reconnect_to_broker = 0
    stats_recv_event_from_broker = 0
    client_private_key_file = None
    broker_public_key_file = None
    public_keys_dir = None
    private_keys_dir = None

    def __init__(
        self,
        inventory: NorFabInventory,
        broker: str,
        name: str,
        exit_event: Optional[threading.Event] = None,
        event_queue: Optional[queue.Queue] = None,
    ):
        self.inventory = inventory
        self.name = name
        self.zmq_name = f"{self.name}-{uuid4().hex}"
        self.broker = broker
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "client", self.name
        )
        self.file_transfers = {}  # file transfers tracker
        self.zmq_auth = self.inventory.broker.get("zmq_auth", True)
        self.socket_lock = threading.Lock()  # used to protect socket object
        self.build_message = NFP.MessageBuilder()

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
        self.event_queue = event_queue or queue.Queue(maxsize=1000)

        # Configuration for dispatcher
        self.poll_interval = 0.5  # Seconds between GET polls for same job (throttling)
        self.dispatch_batch_size = 10  # Max jobs to process per dispatch cycle

        # start receiver thread - handles all incoming messages
        self.recv_thread = threading.Thread(
            target=recv, daemon=True, name=f"{self.name}_recv_thread", args=(self,)
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

    def ensure_bytes(self, value: Any) -> bytes:
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

    def reconnect_to_broker(self):
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
        self.stats_reconnect_to_broker += 1

    def send_to_broker(self, command, service, workers, uuid, request):
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

        log.debug(f"{self.name} - sending '{msg}'")

        with self.socket_lock:
            if self.destroy_event.is_set():
                return
            self.broker_socket.send_multipart(msg)
            self.stats_send_to_broker += 1

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
        url: str,
        chunk_size: int = 256000,
        pipeline: int = 10,
        timeout: int = 600,
        read: bool = False,
    ) -> Tuple[str, Any]:
        """
        Fetches a file from a given URL and saves it to a specified destination.

        Parameters:
            url (str): The URL of the file to be fetched.
            chunk_size (int, optional): The size of each chunk to be fetched. Default is 250000 bytes.
            pipeline (int, optional): The number of chunks to be fetched in transit. Default is 10.
            timeout (int, optional): The maximum time (in seconds) to wait for the file to be fetched. Default is 600 seconds.
            read (bool, optional): If True, the file content is read and returned. If False, the file path is returned. Default is False.

        Returns:
            tuple: A tuple containing the status code (str) and the reply (str). The reply can be the file content, file path, or an error message.

        Raises:
            Exception: If there is an error in fetching the file or if the file's MD5 hash does not match the expected hash.
        """

        # round up digit e.g. if 2.0 -> 2 if 2.1 -> 3 if 0.01 -> 1
        def round_up(num):
            return max(1, (int(num) + (not num.is_integer())))

        uuid = uuid4().hex
        result = {"status": "200", "content": None, "error": None}
        downloaded = False

        # run sanity checks
        if not url.startswith("nf://"):
            result["status"] = "500"
            result["error"] = "Invalid url format"
            return result

        # prevent path traversal / absolute paths
        url_path = url.replace("nf://", "")
        url_path = url_path.lstrip("/\\")
        destination = os.path.abspath(
            os.path.join(self.base_dir, "fetchedfiles", *url_path.split("/"))
        )
        fetched_root = os.path.abspath(os.path.join(self.base_dir, "fetchedfiles"))
        if os.path.commonpath([fetched_root, destination]) != fetched_root:
            result["status"] = "500"
            result["error"] = "Invalid url path"
            return result

        os.makedirs(os.path.split(destination)[0], exist_ok=True)

        self.file_transfers[uuid] = {
            "total_bytes_received": 0,  # Total bytes received
            "offset": 0,  # Offset of next chunk request
            "credit": pipeline,  # Up to PIPELINE chunks in transit
            "chunk_size": chunk_size,
            "file_hash": hashlib.md5(),
        }

        # get file details
        file_details = self.run_job(
            service="filesharing",
            workers="all",
            task="file_details",
            kwargs={"url": url},
            timeout=timeout,
        )
        for w_name, w_res in file_details.items():
            if not w_res["failed"]:
                file_details = w_res["result"]
                self.file_transfers[uuid].update(file_details)
                self.file_transfers[uuid]["w_name"] = w_name
                self.file_transfers[uuid]["chunk_requests_remaining"] = round_up(
                    file_details["size_bytes"] / chunk_size
                )
                break
        else:
            result["status"] = "404"
            result["error"] = "File download failed - file not found"
            _ = self.file_transfers.pop(uuid)
            return result

        log.debug(f"{self.name}:fetch_file - retrieved file details - {file_details}")

        # check if file already downloaded
        if os.path.isfile(destination):
            file_hash = hashlib.md5()
            with open(destination, "rb") as f:
                chunk = f.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = f.read(8192)
            md5hash = file_hash.hexdigest()
            downloaded = md5hash == file_details["md5hash"]

        if file_details["exists"] and not downloaded:
            self.file_transfers[uuid]["destination"] = open(destination, "wb")
            # decrement by 1 because calling fetch_job sends first chunk
            self.file_transfers[uuid]["chunk_requests_remaining"] -= 1
            # run fetch file job
            file_fetch_job = self.run_job(
                uuid=uuid,
                service="filesharing",
                workers=[w_name],
                task="fetch_file",
                kwargs={"url": url, "offset": 0, "chunk_size": chunk_size},
                timeout=timeout,
            )
            file_fetch_job = file_fetch_job[w_name]

            if file_fetch_job["failed"]:
                result["status"] = "404"
                result["error"] = file_fetch_job["errors"]
                downloaded = False
            else:
                downloaded = True

        if downloaded:
            # Verify streaming did not mark job failed (e.g., MD5 mismatch)
            download_job = self.job_db.get_job(uuid)
            if download_job and download_job.get("status") == JobStatus.FAILED:
                result["error"] = (
                    f"File download job {uuid} failed: {download_job.get('errors', [])}"
                )
                result["status"] = "400"
            elif read:
                with open(destination, "r", encoding="utf-8") as f:
                    result["content"] = f.read()
            else:
                result["content"] = destination

        _ = self.file_transfers.pop(uuid)

        return result

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
            Any: The result of the job if successful, or None if the job failed, timed out, or became stale.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        result = None
        job = None
        deadline = time.time() + timeout

        self.job_db.add_job(
            uuid, service, task, workers, args, kwargs, timeout, deadline
        )

        if nowait:
            return {
                "uuid": uuid,
                "service": service,
            }
        else:
            while time.time() < deadline:
                if self.exit_event.is_set() or self.destroy_event.is_set():
                    break
                job = self.job_db.get_job(uuid)
                if not job:
                    break
                if job["status"] == JobStatus.COMPLETED:
                    result = job.get("result_data")
                    break
                if job["status"] == JobStatus.FAILED:
                    log.warning(
                        f"{self.name} - job {uuid} failed: {job.get('errors', [])}"
                    )
                    break
                if job["status"] == JobStatus.STALE:
                    log.warning(
                        f"{self.name} - job {uuid} became stale: {job.get('errors', [])}"
                    )
                    break
                time.sleep(0.2)

            return markdown_results(job, service, task, kwargs) if markdown else result

    def destroy(self):
        """
        Gracefully shuts down the client.

        This method logs an interrupt message, sets the destroy event, waits
        for background threads to stop, then destroys the client context to
        ensure a clean shutdown.
        """
        log.info(f"{self.name} - client interrupt received, killing client")
        self.destroy_event.set()
        # Wait for background threads to exit before destroying the ZMQ context.
        # Without this, the dispatcher/receiver threads may still be executing
        # between their destroy_event check and a socket call, causing
        # "not a socket" ZMQError when ctx.destroy() closes sockets under them.
        if self.recv_thread.is_alive():
            self.recv_thread.join(timeout=2)
        if self.dispatcher_thread.is_alive():
            self.dispatcher_thread.join(timeout=2)
        self.job_db.close()
        self.ctx.destroy()
        # close all file transfer files
        for file_transfer in self.file_transfers.values():
            file_transfer["destination"].close()
