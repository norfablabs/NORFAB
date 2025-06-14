from typing import Union, Dict, List, Optional, Any
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
    ConfigDict,
    model_validator,
)
from norfab.models import Result


class NornirHostsFilters(BaseModel, extra="forbid"):
    """
    Model to list common filter arguments for FFun function
    """

    FO: Optional[Union[Dict, List[Dict]]] = Field(
        None, title="Filter Object", description="Filter hosts using Filter Object"
    )
    FB: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using Glob Patterns",
    )
    FH: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter Hostname", description="Filter hosts by hostname"
    )
    FC: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts containment of pattern in name",
    )
    FR: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using Regular Expressions",
    )
    FG: Optional[StrictStr] = Field(
        None, title="Filter Group", description="Filter hosts by group"
    )
    FP: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP Prefix",
    )
    FL: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter List", description="Filter hosts by names list"
    )
    FM: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter platforM", description="Filter hosts by platform"
    )
    FX: Optional[Union[List[str], str]] = Field(
        None, title="Filter eXclude", description="Filter hosts excluding them by name"
    )
    FN: Optional[StrictBool] = Field(
        None,
        title="Filter Negate",
        description="Negate the match",
        json_schema_extra={"presence": True},
    )

    @model_validator(mode="before")
    def convert_filters_to_strings(cls, data: Any) -> Any:
        """Converts filters values to strings."""
        for k in list(data.keys()):
            if k.startswith("F"):
                data[k] = str(data[k])
        return data


# -----------------------------------------------------------------------------------------
# get_nornir_hosts Task Pydantic Models
# -----------------------------------------------------------------------------------------


class GetNornirHosts(NornirHostsFilters, extra="forbid"):
    """
    Pydantic model for Nornir get_nornir_hosts task.
    """

    job: object = Field(None, description="Job instance running this task")
    details: Optional[StrictBool] = Field(
        None, description="get_nornir_hosts task input arguments schema"
    )


class HostDetails(BaseModel, extra="forbid"):
    platform: StrictStr = Field(None, description="Host's platform name")
    hostname: StrictStr = Field(None, description="Host's hostname")
    port: StrictStr = Field(None, description="Host's port to initiate connection with")
    groups: List[StrictStr] = Field(None, description="Host's groups")
    username: StrictStr = Field(None, description="Host's username")


class GetNornirHostsResponse(Result):
    result: Union[List[StrictStr], Dict[StrictStr, HostDetails]] = Field(
        None, description="get_nornir_host results schema"
    )
