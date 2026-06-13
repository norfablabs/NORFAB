from typing import Any, Union

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.models import Result

# --------------------------------------------------------------------------
# FASTMCP WORKER MODELS
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
        description="FastMCP worker inventory data",
    )


class GetToolsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    brief: StrictBool = Field(
        False,
        description="Return only tool names",
        json_schema_extra={"presence": True},
    )
    service: StrictStr = Field(
        "all",
        description="Service name to filter tools by",
    )
    name: StrictStr = Field(
        "*",
        description="Glob pattern to filter tool names",
    )


class GetToolsResult(Result):
    result: Union[list[StrictStr], dict[StrictStr, dict[StrictStr, Any]]] = Field(
        {},
        description="Tool names or tool definitions keyed by tool name",
    )


class GetPromptsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    brief: StrictBool = Field(
        False,
        description="Return only prompt names",
        json_schema_extra={"presence": True},
    )
    service: StrictStr = Field(
        "all",
        description="Service name to filter prompts by",
    )
    name: StrictStr = Field(
        "*",
        description="Glob pattern to filter prompt names",
    )


class GetPromptsResult(Result):
    result: Union[list[StrictStr], dict[StrictStr, dict[StrictStr, Any]]] = Field(
        {},
        description=(
            "Prompt names or definitions with message templates keyed by prompt name"
        ),
    )


class DiscoverInput(BaseModel, use_enum_values=True, populate_by_name=True):
    service: StrictStr = Field(
        "all",
        description="Service name to discover tasks for",
    )
    progress: StrictBool = Field(
        True,
        description="Emit progress events while discovering tasks",
        json_schema_extra={"presence": True},
    )


class DiscoverResult(Result):
    result: dict[StrictStr, dict[StrictStr, Any]] = Field(
        {},
        description="Discovered MCP tools keyed by service name",
    )


class GetStatusInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetStatusPayload(BaseModel):
    name: StrictStr = Field(None, description="MCP server name")
    url: StrictStr = Field(None, description="MCP server URL")
    tools_count: StrictInt = Field(None, description="Number of registered tools")
    prompts_count: StrictInt = Field(None, description="Number of registered prompts")


class GetStatusResult(Result):
    result: GetStatusPayload = Field(
        {},
        description="FastMCP server status",
    )


class BearerTokenStoreInput(BaseModel, use_enum_values=True, populate_by_name=True):
    username: StrictStr = Field(..., description="User name to store the token for")
    token: StrictStr = Field(..., description="Bearer token string to store")
    expire: Union[None, StrictInt] = Field(
        None,
        description="Token expiration time in seconds",
    )


class BoolResult(Result):
    result: StrictBool = Field(
        False,
        description="True when the operation succeeds",
    )


class BearerTokenDeleteInput(BaseModel, use_enum_values=True, populate_by_name=True):
    username: Union[None, StrictStr] = Field(
        None, description="User name whose tokens should be deleted"
    )
    token: Union[None, StrictStr] = Field(
        None, description="Bearer token string to delete"
    )


class BearerTokenListInput(BaseModel, use_enum_values=True, populate_by_name=True):
    username: Union[None, StrictStr] = Field(
        None, description="User name to list tokens for"
    )


class BearerTokenPayload(BaseModel):
    username: StrictStr = Field("", description="Token owner user name")
    token: StrictStr = Field("", description="Bearer token string")
    age: StrictStr = Field("", description="Token age")
    creation: StrictStr = Field("", description="Token creation timestamp")
    expires: StrictStr = Field("", description="Token expiration timestamp")


class BearerTokenListResult(Result):
    result: list[BearerTokenPayload] = Field(
        [],
        description="Bearer token records",
    )


class BearerTokenCheckInput(BaseModel, use_enum_values=True, populate_by_name=True):
    token: StrictStr = Field(..., description="Bearer token string to check")
