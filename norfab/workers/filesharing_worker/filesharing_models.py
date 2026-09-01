import logging
import os
from typing import Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from norfab.models import Result

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# FILESHARING WORKER MODELS
# --------------------------------------------------------------------------


class RemoteInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StrictStr = Field(
        ..., min_length=1, description="Unique name used to identify the remote"
    )
    mount: Union[StrictStr, None] = Field(
        None,
        min_length=1,
        description="Relative path to make the repository available at; defaults to name",
    )
    description: StrictStr = Field(
        "", description="Optional human-readable remote description"
    )
    url: StrictStr = Field(..., min_length=1, description="Git repository URL")
    branch: Union[StrictStr, None] = Field(
        None, min_length=1, description="Git branch to synchronize"
    )
    type: StrictStr = Field(
        ..., min_length=1, description="Remote driver type; use git"
    )
    username: Union[StrictStr, None] = Field(
        None, min_length=1, description="HTTPS username for an authenticated remote"
    )
    password: Union[StrictStr, None] = Field(
        None,
        min_length=1,
        description="HTTPS password or access token for an authenticated remote",
    )
    auto_sync: StrictBool = Field(
        False,
        description="Periodically synchronize the remote after it is created",
        json_schema_extra={"presence": True},
    )
    sync_interval: StrictInt = Field(
        30, description="Seconds between automatic synchronization attempts"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Remote name is not a safe local folder name")
        return value

    @field_validator("mount")
    @classmethod
    def validate_mount(cls, value: str | None) -> str | None:
        if value is None:
            return value
        mount = value.replace("\\", "/")
        if (
            ":" in mount
            or mount.startswith("/")
            or any(part in {"", ".", ".."} for part in mount.split("/"))
        ):
            raise ValueError("Remote mount must be a safe relative path")
        return mount

    @model_validator(mode="after")
    def validate_git_remote(self) -> "RemoteInventory":
        self.mount = self.mount or self.name
        effective_interval = max(5, min(self.sync_interval, 86_400))
        if self.sync_interval != effective_interval:
            log.warning(
                f"Clamped remote '{self.name}' sync interval to {effective_interval} seconds"
            )
            self.sync_interval = effective_interval
        if self.type == "git":
            if self.branch is None:
                raise ValueError("Remote branch is required for git remotes")
            if (self.username is None) != (self.password is None):
                raise ValueError(
                    "Remote username and password must be provided together"
                )
        return self


class FileSharingInventory(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: Literal["filesharing"] = Field(
        "filesharing", description="Worker service type"
    )
    base_dir: StrictStr = Field(
        ..., min_length=1, description="Local directory containing shared files"
    )
    remotes: list[RemoteInventory] = Field(
        default_factory=list,
        description="Git remotes to create when the worker starts",
    )

    @model_validator(mode="after")
    def validate_remote_names(self) -> "FileSharingInventory":
        normalized_mounts = set()
        for remote in self.remotes:
            normalized_mount = os.path.normcase(
                os.path.abspath(os.path.join(self.base_dir, remote.mount))
            )
            if normalized_mount in normalized_mounts:
                raise ValueError(
                    f"Remote mount '{remote.mount}' collides with another remote"
                )
            normalized_mounts.add(normalized_mount)
        return self


class RemoteState(BaseModel):
    name: StrictStr = Field(..., description="Remote name")
    status: StrictStr = Field(..., description="Current synchronization status")
    last_sync_attempt: Union[StrictStr, None] = Field(
        None, description="UTC timestamp of the most recent synchronization attempt"
    )


class RemoteNameInput(BaseModel, use_enum_values=True, populate_by_name=True):
    name: StrictStr = Field(..., min_length=1, description="Configured remote name")


class ResolveGitUrlInput(BaseModel, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field(
        ...,
        min_length=1,
        description="Git file URL in git://<remote-name>/<path> format",
    )


class CreateRemoteGitInput(RemoteInventory):
    """Complete configuration used to register and initialize a Git remote."""

    model_config = ConfigDict(extra="ignore")


class GetRemotesInput(BaseModel, use_enum_values=True, populate_by_name=True):
    name: Union[StrictStr, None] = Field(
        None, min_length=1, description="Optional remote name to return"
    )


class GetRemotesResult(Result):
    result: list[dict[StrictStr, Any]] = Field(
        default_factory=list,
        description="Configured remotes with passwords redacted",
    )


class CreateRemoteGitResult(Result):
    result: Union[RemoteState, None] = Field(
        None, description="Remote state after local repository initialization"
    )


class DeleteRemoteGitResult(Result):
    result: Union[StrictBool, None] = Field(
        None, description="True when the local remote data was deleted"
    )


class GitCloneResult(Result):
    result: Union[RemoteState, None] = Field(
        None, description="Remote state after Git synchronization"
    )


class ResolveGitUrlResult(Result):
    result: Union[StrictStr, None] = Field(
        None,
        description="Resolved nf:// URL after successful Git synchronization",
    )


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
