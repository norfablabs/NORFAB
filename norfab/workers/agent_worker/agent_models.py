from typing import Any

from pydantic import BaseModel, Field, StrictBool, StrictStr

from norfab.models import Result


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: dict[StrictStr, StrictStr] = Field(
        {},
        description="Agent worker package and platform versions",
    )


class GetInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetInventoryResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="Agent worker inventory data",
    )


class GetStatusInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetStatusResult(Result):
    result: StrictStr = Field(
        "OK",
        description="Agent worker status",
    )


class InvokeInput(BaseModel, use_enum_values=True, populate_by_name=True):
    instructions: StrictStr = Field(
        ...,
        description="Instructions to send to the agent",
    )
    name: StrictStr = Field(
        "NorFab",
        description="Agent profile name or URL",
    )
    verbose_result: StrictBool = Field(
        False,
        description="Return the full agent response object",
        alias="verbose-result",
        json_schema_extra={"presence": True},
    )


class InvokeResult(Result):
    result: Any = Field(
        None,
        description="Agent response payload",
    )
