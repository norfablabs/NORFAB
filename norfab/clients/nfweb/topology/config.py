"""Configuration for NFWeb's topology application."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class TopologyLayersConfig(BaseModel):
    """Built-in topology layer switches."""

    model_config = ConfigDict(extra="forbid")

    inventory: StrictBool = True
    lldp: StrictBool = True
    bgp: StrictBool = True
    interfaces: StrictBool = True


class TopologyConfig(BaseModel):
    """Topology collection, history, scope, workers, and layers."""

    model_config = ConfigDict(extra="forbid")

    devices: list[StrictStr] = Field(default_factory=list)
    sites: list[StrictStr] = Field(default_factory=list)
    netbox_workers: StrictStr = "any"
    nornir_workers: StrictStr = "all"
    collection_interval: StrictInt = Field(30, ge=5, le=3600)
    inventory_refresh_interval: StrictInt = Field(300, ge=30, le=3600)
    retention_minutes: StrictInt = Field(180, ge=1, le=180)
    request_timeout: StrictInt = Field(60, ge=1, le=600)
    layers: TopologyLayersConfig = Field(default_factory=TopologyLayersConfig)
