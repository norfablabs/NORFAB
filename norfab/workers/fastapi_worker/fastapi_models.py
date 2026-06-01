from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.models import Result


class UnauthorizedMessage(BaseModel):
    detail: str = "Bearer token missing or unknown"


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: Dict[StrictStr, StrictStr] = Field(
        {},
        description="Installed package versions keyed by package name",
    )


class GetInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetInventoryResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {},
        description="FastAPI worker inventory and Uvicorn configuration",
    )


class GetOpenapiSchemaInput(BaseModel, use_enum_values=True, populate_by_name=True):
    paths: StrictBool = Field(
        False,
        description="Return only OpenAPI endpoint paths",
        json_schema_extra={"presence": True},
    )


class GetOpenapiSchemaResult(Result):
    result: Union[List[StrictStr], Dict[StrictStr, Any]] = Field(
        {},
        description="OpenAPI schema dictionary or list of API paths",
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
    result: List[BearerTokenPayload] = Field(
        [],
        description="Bearer token records",
    )


class BearerTokenCheckInput(BaseModel, use_enum_values=True, populate_by_name=True):
    token: StrictStr = Field(..., description="Bearer token string to check")


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
    result: Dict[StrictStr, List[StrictStr]] = Field(
        {},
        description="Discovered API endpoints keyed by service name",
    )
