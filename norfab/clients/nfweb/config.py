"""Shared configuration for the local NFWeb client."""

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from norfab.clients.nfweb.topology.config import TopologyConfig


class NFWebFooterConfig(BaseModel):
    """Safe browser-facing links and message displayed by the shared footer."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    message: StrictStr = Field("", max_length=200)
    fastapi_url: AnyHttpUrl | None = "http://127.0.0.1:8000/docs"
    docs_url: AnyHttpUrl | None = "https://docs.norfablabs.com/"
    github_url: AnyHttpUrl | None = "https://github.com/norfablabs/NORFAB"


class NFWebConfig(BaseModel):
    """Configuration loaded from ``client.nfweb`` in inventory.yaml."""

    model_config = ConfigDict(extra="forbid")

    port: StrictInt = Field(9005, ge=1, le=65535)
    open_browser: StrictBool = True
    footer: NFWebFooterConfig = Field(default_factory=NFWebFooterConfig)
    topology: TopologyConfig = Field(default_factory=TopologyConfig)
