"""Browser contracts for the NFWeb monitoring application."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MonitoringRole = Literal["broker", "client", "worker"]
MonitoringStatus = Literal[
    "active",
    "alive",
    "dead",
    "degraded",
    "unreachable",
    "unknown",
]


class MonitoringComponent(BaseModel):
    """Current state and resource use for one NORFAB process."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: MonitoringRole
    status: MonitoringStatus
    service: str | None = None
    cpu_percent: float | None = None
    memory_mbyte: float | None = None
    uptime_seconds: int | None = None
    holdtime_seconds: float | None = None
    keepalives_sent: int | None = None
    keepalives_received: int | None = None
    messages_sent: int | None = None
    messages_received: int | None = None
    reconnects: int | None = None
    queue_depth: int | None = None
    worker_count: int | None = None
    service_count: int | None = None


class MonitoringSnapshot(BaseModel):
    """One live broker, client, and worker monitoring sample."""

    model_config = ConfigDict(extra="forbid")

    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = 0
    status: Literal["complete", "partial", "failed"] = "complete"
    broker: MonitoringComponent
    client: MonitoringComponent
    workers: list[MonitoringComponent] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
