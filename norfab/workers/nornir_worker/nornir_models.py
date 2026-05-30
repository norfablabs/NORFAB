from enum import Enum
from typing import Any, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from norfab.models import Result

# --------------------------------------------------------------------------
# COMMON NORNIR TASK MODELS
# --------------------------------------------------------------------------


class NornirHostsFilters(BaseModel, extra="forbid", use_enum_values=True):
    """Common host filter arguments supported by Nornir-Salt FFun."""

    FO: Union[None, dict[StrictStr, Any], list[dict[StrictStr, Any]]] = Field(
        None,
        title="Filter Object",
        description="Filter hosts using a Nornir-Salt Filter Object",
    )
    FB: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using glob patterns",
    )
    FH: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Hostname",
        description="Filter hosts by hostname",
    )
    FC: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts by name containment pattern",
    )
    FR: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using regular expressions",
    )
    FG: Union[None, StrictStr] = Field(
        None,
        title="Filter Group",
        description="Filter hosts by group",
    )
    FP: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP prefix",
    )
    FL: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter List",
        description="Filter hosts by names list",
    )
    FM: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter platforM",
        description="Filter hosts by platform",
    )
    FX: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter eXclude",
        description="Exclude hosts by name",
    )
    FN: Union[None, StrictBool] = Field(
        None,
        title="Filter Negate",
        description="Negate the host filter match",
        json_schema_extra={"presence": True},
    )

    @model_validator(mode="before")
    @classmethod
    def validate_mapping(cls, data: Any) -> Any:
        if data is None or isinstance(data, dict):
            if not isinstance(data, dict):
                return data
            normalized = data.copy()
            for key, value in data.items():
                if key == "FO" or key == "FN" or not key.startswith("F"):
                    continue
                if isinstance(value, list):
                    normalized[key] = [str(item) for item in value]
                elif value is not None:
                    normalized[key] = str(value)
            return normalized
        raise TypeError("Nornir host filters must be provided as a mapping")


class NornirCommonArgs(
    NornirHostsFilters, extra="allow", use_enum_values=True, populate_by_name=True
):
    """Common Nornir task arguments accepted by task serializers and processors."""

    to_dict: StrictBool = Field(
        True,
        description="Return task results as a dictionary keyed by host",
        alias="to-dict",
    )
    add_details: StrictBool = Field(
        False,
        description="Add Nornir task execution details to results",
        alias="add-details",
        json_schema_extra={"presence": True},
    )
    progress: StrictBool = Field(
        True,
        description="Emit progress events during task execution",
        json_schema_extra={"presence": True},
    )
    run_num_workers: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of threads for task execution",
        alias="num-workers",
    )
    run_num_connectors: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of threads for device connections",
        alias="num-connectors",
    )
    run_connect_retry: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of connection attempts",
        alias="connect-retry",
    )
    run_task_retry: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of attempts to run each task",
        alias="task-retry",
    )
    run_reconnect_on_fail: Union[None, StrictBool] = Field(
        None,
        description="RetryRunner reconnects to a host after task failure",
        alias="reconnect-on-fail",
        json_schema_extra={"presence": True},
    )
    run_connect_check: Union[None, StrictBool] = Field(
        None,
        description="RetryRunner tests TCP connectivity before opening connection",
        alias="connect-check",
        json_schema_extra={"presence": True},
    )
    run_connect_timeout: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner TCP connection check timeout in seconds",
        alias="connect-timeout",
    )
    run_creds_retry: Any = Field(
        None,
        description="RetryRunner connection credentials and parameters to retry",
        alias="creds-retry",
    )
    tf: Union[None, StrictStr] = Field(
        None,
        description="File group name to save task results on the worker",
    )
    tf_skip_failed: Union[None, StrictBool] = Field(
        None,
        description="Skip failed task results when saving to file",
        alias="tf-skip-failed",
        json_schema_extra={"presence": True},
    )
    diff: Union[None, StrictStr] = Field(
        None,
        description="File group name to diff task results against",
    )
    diff_last: Union[None, StrictInt, StrictStr] = Field(
        None,
        description="Previous saved file version to diff against",
        alias="diff-last",
    )
    dp: Any = Field(
        None,
        description="Nornir-Salt DataProcessor pipeline definition",
    )
    xml_flake: Union[None, StrictStr] = Field(
        None,
        description="XML flake pattern for DataProcessor",
        alias="xml-flake",
    )
    match: Union[None, StrictStr] = Field(
        None,
        description="Pattern to match in task output",
    )
    before: StrictInt = Field(
        0,
        description="Number of lines before a match to include",
    )
    run_ttp: Union[None, StrictStr] = Field(
        None,
        description="TTP template to run with DataProcessor",
        alias="run-ttp",
    )
    ttp_structure: StrictStr = Field(
        "flat_list",
        description="TTP result structure for DataProcessor",
        alias="ttp-structure",
    )
    remove_tasks: StrictBool = Field(
        True,
        description="Remove task output when processors produce final results",
        alias="remove-tasks",
        json_schema_extra={"presence": True},
    )
    tests: Any = Field(
        None,
        description="Nornir-Salt TestsProcessor tests definition",
    )
    subset: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Test subset name or glob pattern to execute",
    )
    failed_only: StrictBool = Field(
        False,
        description="Return failed test results only",
        alias="failed-only",
        json_schema_extra={"presence": True},
    )
    groups: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Test group names to execute",
    )
    xpath: Union[None, StrictStr] = Field(
        None,
        description="XPath expression to run with DataProcessor",
    )
    jmespath: Union[None, StrictStr] = Field(
        None,
        description="JMESPath expression to run with DataProcessor",
    )
    iplkp: Union[None, StrictStr] = Field(
        None,
        description="IP lookup mode for DataProcessor",
    )
    ntfsm: Union[None, StrictBool] = Field(
        None,
        description="Parse output with NTC TextFSM templates",
        json_schema_extra={"presence": True},
    )


class NornirSerializedResult(Result):
    result: Union[dict[StrictStr, Any], list[Any], None] = Field(
        {},
        description="Serialized Nornir task result keyed by host or returned as a list",
    )


class NornirCliPlugin(str, Enum):
    netmiko = "netmiko"
    scrapli = "scrapli"
    napalm = "napalm"
