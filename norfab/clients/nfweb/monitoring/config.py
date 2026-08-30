"""Configuration for NFWeb's monitoring application."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class MonitoringConfig(BaseModel):
    """Polling and in-memory retention settings for fabric monitoring."""

    model_config = ConfigDict(extra="forbid")

    collection_interval: StrictInt = Field(5, ge=5, le=3600)
    retention_minutes: StrictInt = Field(180, ge=1, le=180)
    request_timeout: StrictInt = Field(10, ge=1, le=600)
