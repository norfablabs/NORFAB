from typing import Any, Union

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.models import Result

# --------------------------------------------------------------------------
# CONTAINERLAB WORKER MODELS
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
        description="Containerlab worker inventory data",
    )


class GetContainerlabStatusInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    pass


class GetContainerlabStatusResult(Result):
    result: dict[StrictStr, StrictStr] = Field(
        {},
        description="Containerlab worker status data",
    )


class GetRunningLabsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Containerlab inspect timeout in seconds",
    )


class GetRunningLabsResult(Result):
    result: list[StrictStr] = Field(
        [],
        description="Names of running Containerlab labs",
    )


class RunContainerlabCommandInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    args: list[StrictStr] = Field(
        ...,
        description="Containerlab command arguments to execute",
    )
    cwd: Union[None, StrictStr] = Field(
        None,
        description="Working directory to execute the command in",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Command timeout in seconds",
    )
    env: Union[None, dict[StrictStr, StrictStr]] = Field(
        None,
        description="Environment variables to use when running the command",
    )
    expect_output: StrictBool = Field(
        True,
        description="Fail the command result when no output is returned",
    )


class RunContainerlabCommandResult(Result):
    result: Union[None, StrictStr, dict[StrictStr, Any], list[Any]] = Field(
        None,
        description="Parsed JSON output or raw command output",
    )


class DeployInput(BaseModel, use_enum_values=True, populate_by_name=True):
    topology: StrictStr = Field(
        ...,
        description="Topology file path or URL to deploy",
    )
    reconfigure: StrictBool = Field(
        False,
        description="Reconfigure an already deployed lab",
        json_schema_extra={"presence": True},
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Deployment timeout in seconds",
    )
    node_filter: Union[None, StrictStr] = Field(
        None,
        description="Comma-separated list of node names to deploy",
        alias="node-filter",
    )


class DeployResult(Result):
    result: Union[None, StrictStr, dict[StrictStr, Any], list[Any]] = Field(
        None,
        description="Containerlab deployment output",
    )


class DestroyLabInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: StrictStr = Field(
        ...,
        description="Containerlab lab name to destroy",
        alias="lab-name",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Destroy timeout in seconds",
    )


class LabActionResult(Result):
    result: Union[None, dict[StrictStr, StrictBool]] = Field(
        None,
        description="Action status keyed by lab name",
    )


class InspectInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: Union[None, StrictStr] = Field(
        None,
        description="Containerlab lab name to inspect",
        alias="lab-name",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Inspect timeout in seconds",
    )
    details: StrictBool = Field(
        False,
        description="Return detailed container information",
        json_schema_extra={"presence": True},
    )


class InspectResult(Result):
    result: Union[None, dict[StrictStr, list[dict[StrictStr, Any]]]] = Field(
        None,
        description="Container details keyed by lab name",
    )


class SaveInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: StrictStr = Field(
        ...,
        description="Containerlab lab name to save",
        alias="lab-name",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Save timeout in seconds",
    )


class RestartLabInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: StrictStr = Field(
        ...,
        description="Containerlab lab name to restart",
        alias="lab-name",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Restart timeout in seconds",
    )


class GetNornirInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: Union[None, StrictStr] = Field(
        None,
        description="Containerlab lab name to build Nornir inventory for",
        alias="lab-name",
    )
    timeout: Union[None, StrictInt] = Field(
        None,
        description="Inspect timeout in seconds",
    )
    groups: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Nornir groups to include in each host inventory entry",
    )
    use_default_credentials: StrictBool = Field(
        True,
        description="Use Containerlab default credentials for hosts",
        alias="use-default-credentials",
        json_schema_extra={"presence": True},
    )


class GetNornirInventoryResult(Result):
    result: dict[StrictStr, dict[StrictStr, Any]] = Field(
        {},
        description="Nornir inventory data with hosts keyed by host name",
    )


class DeployNetboxInput(BaseModel, use_enum_values=True, populate_by_name=True):
    lab_name: Union[None, StrictStr] = Field(
        None,
        description="Containerlab lab name to deploy",
        alias="lab-name",
    )
    tenant: Union[None, StrictStr] = Field(
        None,
        description="NetBox tenant name to build lab topology from",
    )
    filters: Union[None, list[dict[StrictStr, Any]]] = Field(
        None,
        description="NetBox device filters to build lab topology from",
    )
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="NetBox device names to include in the lab topology",
    )
    instance: Union[None, StrictStr] = Field(
        None,
        description="NetBox instance name to query",
        alias="netbox-instance",
    )
    image: Union[None, StrictStr] = Field(
        None,
        description="Container image to use for lab devices",
    )
    ipv4_subnet: StrictStr = Field(
        "172.100.100.0/24",
        description="Management IPv4 subnet for the lab",
        alias="ipv4-subnet",
    )
    ports: tuple[StrictInt, StrictInt] = Field(
        (12000, 15000),
        description="TCP/UDP port range to allocate for nodes",
    )
    progress: StrictBool = Field(
        False,
        description="Emit progress events while preparing topology",
        json_schema_extra={"presence": True},
    )
    reconfigure: StrictBool = Field(
        False,
        description="Reconfigure an already deployed lab",
        json_schema_extra={"presence": True},
    )
    timeout: StrictInt = Field(
        600,
        description="Deployment timeout in seconds",
    )
    node_filter: Union[None, StrictStr] = Field(
        None,
        description="Comma-separated list of node names to deploy",
        alias="node-filter",
    )
    dry_run: StrictBool = Field(
        False,
        description="Return generated topology without deploying it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )


class DeployNetboxResult(Result):
    result: Union[None, dict[StrictStr, Any], list[Any], StrictStr] = Field(
        None,
        description="Generated topology data or Containerlab deployment output",
    )
