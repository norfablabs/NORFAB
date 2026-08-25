"""Shared configuration for the local NFWeb client."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from norfab.clients.nfweb.topology.config import TopologyConfig


class NFWebConfig(BaseModel):
    """Configuration loaded from ``client.nfweb`` in inventory.yaml."""

    model_config = ConfigDict(extra="forbid")

    port: StrictInt = Field(8080, ge=1, le=65535)
    open_browser: StrictBool = True
    topology: TopologyConfig = Field(default_factory=TopologyConfig)
