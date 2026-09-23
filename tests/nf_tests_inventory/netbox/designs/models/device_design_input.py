from pydantic import BaseModel, ConfigDict


class DesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[str]
