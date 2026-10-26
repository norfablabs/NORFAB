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
    url: StrictStr | list[StrictStr] = Field(
        ..., description="Git file URL or URL list to resolve"
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


class ResolveGitUrlEntry(Result):
    result: StrictStr | None = Field(None, description="Resolved published nf:// URL")


class ResolveGitUrlResult(Result):
    result: dict[StrictStr, ResolveGitUrlEntry] | StrictStr | None = Field(
        default_factory=dict,
        description="Resolved URL for string input, or per-URL results for list input",
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
