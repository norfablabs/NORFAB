from typing import List, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

# -----------------------------------------------------------------------------------------
# FAKENOS TASKS PYDANTIC MODELS
# -----------------------------------------------------------------------------------------


class FakeNOSStartInput(BaseModel):
    """Input model for the ``FakeNOSWorker.start`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to start")
    inventory: Union[dict, StrictStr, None] = Field(
        None, description="Inventory content (dict) or path/URL to an inventory file"
    )


class FakeNOSStopInput(BaseModel):
    """Input model for the ``FakeNOSWorker.stop`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to stop; stops all networks if omitted"
    )


class FakeNOSRestartInput(BaseModel):
    """Input model for the ``FakeNOSWorker.restart`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to restart")


class FakeNOSListNetworksInput(BaseModel):
    """Input model for the ``FakeNOSWorker.inspect_networks`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to show; shows all networks if omitted"
    )
    details: StrictBool = Field(
        False, description="Return detailed host information per network"
    )


class GetNornirInventoryInput(BaseModel):
    network: StrictStr = Field(
        None, description="FakeNOS network name to get Nornir inventory for"
    )
    groups: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of groups to include in host's inventory",
    )
