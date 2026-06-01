from typing import Any, Union

from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from norfab.models import Result

# --------------------------------------------------------------------------
# FAKENOS WORKER MODELS
# --------------------------------------------------------------------------


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: dict[StrictStr, StrictStr] = Field(
        {},
        description="Installed package versions keyed by package name",
    )


class GetInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="FakeNOS worker inventory data",
    )


class FakeNOSStartInput(BaseModel, use_enum_values=True, populate_by_name=True):
    """Input model for the ``FakeNOSWorker.start`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to start")
    inventory: Union[dict[StrictStr, Any], StrictStr, None] = Field(
        None, description="Inventory content or path/URL to an inventory file"
    )


class FakeNOSStopInput(BaseModel, use_enum_values=True, populate_by_name=True):
    """Input model for the ``FakeNOSWorker.stop`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to stop; stops all networks if omitted"
    )


class FakeNOSRestartInput(BaseModel, use_enum_values=True, populate_by_name=True):
    """Input model for the ``FakeNOSWorker.restart`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to restart")


class FakeNOSListNetworksInput(BaseModel, use_enum_values=True, populate_by_name=True):
    """Input model for the ``FakeNOSWorker.inspect_networks`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to show; shows all networks if omitted"
    )
    details: StrictBool = Field(
        True, description="Return detailed host information per network"
    )


class FakeNOSHostPayload(BaseModel):
    name: StrictStr = Field(None, description="FakeNOS host name")
    platform: Union[None, StrictStr] = Field(None, description="FakeNOS host platform")
    port: StrictInt = Field(None, description="Host TCP port")
    username: StrictStr = Field(None, description="Host username")
    password: StrictStr = Field(None, description="Host password")


class FakeNOSNetworkPayload(BaseModel):
    pid: StrictInt = Field(None, description="Network process ID")
    alive: StrictBool = Field(None, description="True if the network process is alive")
    hosts: list[FakeNOSHostPayload] = Field(
        [], description="FakeNOS hosts in the network"
    )
    hosts_count: StrictInt = Field(None, description="Number of hosts in the network")
    status: StrictStr = Field(None, description="Process status")
    uptime_seconds: StrictInt = Field(None, description="Network uptime in seconds")
    cpu_percent: StrictFloat = Field(None, description="Process CPU usage percentage")
    memory_rss_mb: StrictFloat = Field(None, description="Resident memory in MB")
    memory_vms_mb: StrictFloat = Field(None, description="Virtual memory in MB")
    num_threads: StrictInt = Field(None, description="Number of process threads")


class FakeNOSNetworkActionResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="FakeNOS network action result keyed by network name",
    )


class FakeNOSInspectNetworksResult(Result):
    result: Union[dict[StrictStr, FakeNOSNetworkPayload], list[StrictStr]] = Field(
        {},
        description="Network details keyed by name or list of network names",
    )


# --------------------------------------------------------------------------
# NORNIR INVENTORY TASKS MODELS
# --------------------------------------------------------------------------


class GetNornirInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    network: Union[None, StrictStr] = Field(
        None, description="FakeNOS network name to get Nornir inventory for"
    )
    groups: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Nornir groups to include in each host inventory entry",
    )


class GetNornirInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Nornir inventory data with hosts keyed by host name",
    )
