"""Presentation-neutral models for the NFWeb topology application."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

TopologyHealth = Literal["healthy", "warning", "critical", "unknown"]
SnapshotStatus = Literal["complete", "partial", "empty", "failed"]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TopologyNode(BaseModel):
    """A stable device or external endpoint in the topology graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    kind: str = "device"
    health: TopologyHealth = "unknown"
    layers: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TopologyLink(BaseModel):
    """A physical, observed, or logical relationship between two nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    layer: str
    health: TopologyHealth = "unknown"
    metrics: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TopologyCollectionError(BaseModel):
    """A visible collection failure associated with one topology layer."""

    model_config = ConfigDict(extra="forbid")

    layer: str
    message: str
    worker: str | None = None


class TopologyCollectionEvent(BaseModel):
    """A NORFAB job event emitted while collecting a topology layer."""

    model_config = ConfigDict(extra="forbid")

    service: str
    message: str
    severity: str = "INFO"
    task: str | None = None
    worker: str | None = None
    status: str | None = None
    timestamp: str | None = None
    resource: str | list[str] | None = None


class TopologyDeviceOption(BaseModel):
    """One selectable device and the inventories where it was discovered."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sources: list[str]


class TopologyLogEntry(BaseModel):
    """One persistent terminal line derived from a topology snapshot."""

    model_config = ConfigDict(extra="forbid")

    id: str
    snapshot_id: str
    collected_at: datetime
    kind: Literal["event", "error"]
    service: str
    message: str
    severity: str
    task: str | None = None
    worker: str | None = None
    status: str | None = None
    timestamp: str | None = None
    resource: str | list[str] | None = None


class TopologyHistoryEntry(BaseModel):
    """One retained topology snapshot listed in the browser timeline."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    collected_at: datetime


class TopologySnapshot(BaseModel):
    """One complete or partial point-in-time topology graph."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(default_factory=lambda: uuid4().hex)
    collected_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = 0
    status: SnapshotStatus = "empty"
    devices: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    nodes: list[TopologyNode] = Field(default_factory=list)
    links: list[TopologyLink] = Field(default_factory=list)
    errors: list[TopologyCollectionError] = Field(default_factory=list)
    events: list[TopologyCollectionEvent] = Field(default_factory=list)


class LayerPatch(BaseModel):
    """Graph data and interface observations returned by one adapter."""

    model_config = ConfigDict(extra="forbid")

    name: str
    nodes: list[TopologyNode] = Field(default_factory=list)
    links: list[TopologyLink] = Field(default_factory=list)
    interface_observations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    errors: list[TopologyCollectionError] = Field(default_factory=list)
