"""Bounded storage for the NFWeb topology application's snapshots."""

import sqlite3
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import orjson

from norfab.clients.nfweb.topology.models import (
    TopologyHistoryEntry,
    TopologyLogEntry,
    TopologySnapshot,
)


class TopologyHistoryStore:
    """Persist and query a rolling window of compressed topology snapshots."""

    def __init__(self, database_path: str | Path, retention_minutes: int = 180) -> None:
        database_path = Path(database_path)
        self.retention_minutes = retention_minutes
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS topology_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    collected_ts REAL NOT NULL,
                    payload BLOB NOT NULL
                )
                """)
            self._connection.execute("""
                CREATE INDEX IF NOT EXISTS ix_topology_snapshots_collected_ts
                ON topology_snapshots(collected_ts)
                """)
        self.cleanup()

    def insert(self, snapshot: TopologySnapshot) -> None:
        """Insert one snapshot and enforce the configured retention window."""
        payload = zlib.compress(orjson.dumps(snapshot.model_dump(mode="json")))
        collected_at = snapshot.collected_at.astimezone(timezone.utc)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO topology_snapshots (
                    snapshot_id, collected_ts, payload
                ) VALUES (?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    collected_at.timestamp(),
                    payload,
                ),
            )
        self.cleanup()

    def latest(self, devices: list[str] | None = None) -> TopologySnapshot | None:
        """Return the newest snapshot, optionally for one exact device scope."""
        rows = self._connection.execute(
            "SELECT payload FROM topology_snapshots ORDER BY collected_ts DESC"
        ).fetchall()
        for row in rows:
            snapshot = self._decode(row)
            if devices is None or snapshot.devices == devices:
                return snapshot
        return None

    def get(self, snapshot_id: str) -> TopologySnapshot | None:
        """Return one snapshot by its public identifier."""
        row = self._connection.execute(
            "SELECT payload FROM topology_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return self._decode(row) if row else None

    def history(self, devices: list[str] | None = None) -> list[TopologyHistoryEntry]:
        """Return retained snapshot timestamps, optionally for one exact device scope."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.retention_minutes)
        rows = self._connection.execute(
            """
            SELECT snapshot_id, collected_ts, payload
            FROM topology_snapshots
            WHERE collected_ts >= ?
            ORDER BY collected_ts ASC
            """,
            (cutoff.timestamp(),),
        ).fetchall()
        if devices is None:
            return [self._history_entry(row) for row in rows]
        return [
            self._history_entry(row)
            for row in rows
            if self._decode(row).devices == devices
        ]

    def logs(self, devices: list[str], limit: int = 300) -> list[TopologyLogEntry]:
        """Return the newest terminal entries for one device scope."""
        if limit <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.retention_minutes)
        rows = self._connection.execute(
            """
            SELECT payload
            FROM topology_snapshots
            WHERE collected_ts >= ?
            ORDER BY collected_ts ASC
            """,
            (cutoff.timestamp(),),
        ).fetchall()
        entries: list[TopologyLogEntry] = []
        for row in rows:
            snapshot = self._decode(row)
            if snapshot.devices != devices:
                continue
            entries.extend(
                TopologyLogEntry(
                    id=f"{snapshot.snapshot_id}:event:{index}",
                    snapshot_id=snapshot.snapshot_id,
                    collected_at=snapshot.collected_at,
                    kind="event",
                    **event.model_dump(),
                )
                for index, event in enumerate(snapshot.events)
            )
            entries.extend(
                TopologyLogEntry(
                    id=f"{snapshot.snapshot_id}:error:{index}",
                    snapshot_id=snapshot.snapshot_id,
                    collected_at=snapshot.collected_at,
                    kind="error",
                    service="topology",
                    task=error.layer,
                    worker=error.worker,
                    severity="ERROR",
                    status="failed",
                    timestamp=snapshot.collected_at.isoformat(),
                    message=error.message,
                )
                for index, error in enumerate(snapshot.errors)
            )
        return entries[-limit:]

    def cleanup(self, now: datetime | None = None) -> int:
        """Delete snapshots older than the rolling retention cutoff."""
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(minutes=self.retention_minutes)
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM topology_snapshots WHERE collected_ts < ?",
                (cutoff.timestamp(),),
            )
        return cursor.rowcount

    def count(self) -> int:
        """Return the number of retained snapshots."""
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM topology_snapshots"
        ).fetchone()
        return int(row["count"])

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> TopologySnapshot:
        payload = orjson.loads(zlib.decompress(row["payload"]))
        return TopologySnapshot.model_validate(payload)

    @staticmethod
    def _history_entry(row: sqlite3.Row) -> TopologyHistoryEntry:
        return TopologyHistoryEntry(
            snapshot_id=row["snapshot_id"],
            collected_at=datetime.fromtimestamp(row["collected_ts"], timezone.utc),
        )
