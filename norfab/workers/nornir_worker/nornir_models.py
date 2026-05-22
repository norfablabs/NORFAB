from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
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