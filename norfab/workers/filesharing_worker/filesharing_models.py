from typing import Any, Union

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.models import Result

# --------------------------------------------------------------------------
# FILESHARING WORKER MODELS
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
        description="Filesharing worker inventory data",
    )


class GetStatusInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetStatusResult(Result):
    result: StrictStr = Field("OK", description="Filesharing worker status")


class ListFilesInput(BaseModel, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field(
        ...,
        description="Directory URL starting with nf:// to list files from",
    )


class ListFilesResult(Result):
    result: Union[None, list[StrictStr]] = Field(
        None,
        description="Directory entries",
    )


class FileDetailsInput(BaseModel, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field(
        ...,
        description="File URL starting with nf:// to get details for",
    )


class FileDetailsPayload(BaseModel):
    md5hash: Union[None, StrictStr] = Field(None, description="File MD5 hash")
    size_bytes: Union[None, StrictInt] = Field(None, description="File size in bytes")
    exists: StrictBool = Field(False, description="True if the file exists")


class FileDetailsResult(Result):
    result: FileDetailsPayload = Field(
        {},
        description="File details",
    )


class WalkInput(BaseModel, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field(
        ...,
        description="Directory URL starting with nf:// to walk",
    )


class WalkResult(Result):
    result: Union[None, list[StrictStr]] = Field(
        None,
        description="File URLs found under the directory",
    )


class FetchFileInput(BaseModel, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field(..., description="File URL starting with nf:// to fetch")
    chunk_size: StrictInt = Field(
        256000,
        description="Chunk size in bytes",
        alias="chunk-size",
    )
    offset: StrictInt = Field(0, description="Starting byte offset")
    chunk_timeout: StrictInt = Field(
        5,
        description="Client chunk request timeout in seconds",
        alias="chunk-timeout",
    )


class FetchFileResult(Result):
    result: Union[None, StrictBool] = Field(
        None,
        description="True when the file was streamed successfully",
    )
