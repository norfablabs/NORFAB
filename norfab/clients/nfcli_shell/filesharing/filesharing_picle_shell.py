import builtins
import logging
from typing import Any, Optional

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictBool, StrictStr

from norfab.workers.filesharing_worker.filesharing_models import (
    CreateRemoteGitInput,
    FileDetailsInput,
    ListFilesInput,
    RemoteNameInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job

log = logging.getLogger(__name__)


class RemotesModel(ClientRunJobArgs):
    """Show configured File Sharing remotes.

    ``brief`` flattens remotes from the selected workers into a compact table.
    ``summary`` returns nested per-worker counts. The default view returns the
    complete redacted remote definitions, while ``verbose-result`` preserves the
    full NorFab job envelopes.
    """

    brief: StrictBool = Field(
        False,
        description="Show a compact table of remote status",
        json_schema_extra={"presence": True},
    )
    summary: StrictBool = Field(
        False,
        description="Show a summary of remote counts and state",
        json_schema_extra={"presence": True},
    )
    name: Optional[StrictStr] = Field(None, description="Filter by remote name")
    detail: StrictBool = Field(
        False,
        description="Show complete remote details",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        brief = kwargs.pop("brief", False)
        summary = kwargs.pop("summary", False)
        kwargs.pop("detail", False)
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "filesharing",
            "get_remotes",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(
            result,
            verbose_result=verbose_result,
            verbose_on_fail=verbose_result,
        )
        if verbose_result:
            return result, Outputters.outputter_nested

        if summary:
            remote_summary = {}
            for worker_name, remotes in result.items():
                remote_summary[worker_name] = {
                    "total": len(remotes),
                    "git": sum(1 for remote in remotes if remote.get("type") == "git"),
                    "auto_sync": sum(
                        1 for remote in remotes if remote.get("auto_sync")
                    ),
                    "manual": sum(
                        1 for remote in remotes if not remote.get("auto_sync")
                    ),
                    "last_sync_attempt": {
                        remote.get("name"): remote.get("last_sync_attempt")
                        for remote in remotes
                    },
                }
            return remote_summary, Outputters.outputter_nested

        if brief:
            rows = []
            for worker_name, remotes in result.items():
                rows.extend(
                    {
                        "worker": worker_name,
                        "name": remote.get("name"),
                        "mount": remote.get("mount"),
                        "type": remote.get("type"),
                        "branch": remote.get("branch"),
                        "auto_sync": remote.get("auto_sync"),
                        "sync_interval": remote.get("sync_interval"),
                    }
                    for remote in remotes
                )
            return rows, Outputters.outputter_rich_table

        return result, Outputters.outputter_nested

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class ListFilesModel(ListFilesInput, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field("nf://", description="Directory to list content for")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            workers="any",
            kwargs={"url": "nf://"},
        )
        for _w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        reply = run_future_job(
            "filesharing",
            "list_files",
            args=args,
            kwargs=kwargs,
            workers="any",
        )
        for _w_name, wres in reply.items():
            return wres["result"]

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CopyFileModel(BaseModel):
    url: StrictStr = Field("nf://", description="File location")
    destination: Optional[StrictStr] = Field(
        None, description="File location to save downloaded content"
    )
    read: Optional[StrictBool] = Field(False, description="Print file content")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            kwargs={"url": "nf://"},
            workers="any",
        )
        for _w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        return builtins.NFCLIENT.fetch_file(**kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class FileDetailsModel(FileDetailsInput, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field("nf://", description="File location")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            kwargs={"url": "nf://"},
            workers="any",
        )
        for _w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        reply = run_future_job(
            "filesharing",
            "file_details",
            args=args,
            kwargs=kwargs,
            workers="any",
        )
        for _w_name, wres in reply.items():
            return wres["result"]

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class FilesModel(ListFilesModel):
    """Show files or inspect one file in the shared namespace.

    Examples:
        ``show filesharing files url nf://`` lists a directory.
        ``show filesharing files details url nf://path/file.txt`` returns file
        size, existence, and MD5 information.
    """

    details: FileDetailsModel = Field(None, description="Show details for one file")


class DeleteFetchedFiles(ClientRunJobArgs):
    filepath: StrictStr = Field("*", description="Files location glob pattern")

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "all",
            "delete_fetched_files",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    @staticmethod
    def source_filepath() -> list:
        broker_files = run_future_job(
            "filesharing", "any", "walk", kwargs={"url": "nf://"}
        )
        for _w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def source_workers() -> list:
        nfclient = builtins.NFCLIENT
        reply = nfclient.mmi("mmi.service.broker", "show_workers")
        workers = [item["name"] for item in reply["results"]]

        return ["all", "any"] + workers

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CreateGitRemoteModel(CreateRemoteGitInput, ClientRunJobArgs):
    """Register and initialize a Git remote on File Sharing workers."""

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "filesharing",
            "create_remote_git",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CloneGitRemoteModel(RemoteNameInput, ClientRunJobArgs):
    """Synchronize a registered Git remote and make its mount available."""

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "filesharing",
            "git_clone",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class DeleteGitRemoteModel(RemoteNameInput, ClientRunJobArgs):
    """Delete and unregister a Git remote from File Sharing workers."""

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "filesharing",
            "delete_remote_git",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class GitCommandsModel(BaseModel):
    create_remote: CreateGitRemoteModel = Field(
        None, description="Register and initialize a Git remote", alias="create-remote"
    )
    clone_remote: CloneGitRemoteModel = Field(
        None,
        description="Synchronize a Git remote and make it available",
        alias="clone-remote",
    )
    delete_remote: DeleteGitRemoteModel = Field(
        None, description="Delete and unregister a Git remote", alias="delete-remote"
    )


class FileSharingServiceCommands(BaseModel):
    """
    # Sample Usage

    ## copy

    Copy a file from the shared namespace into the client fetch directory:

    ``filesharing copy url nf://cli/commands.txt``

    Copy file to a destination relative to the current working directory:

    ``filesharing copy url nf://cli/commands.txt destination commands.txt``

    """

    copy_: CopyFileModel = Field(None, description="Copy files", alias="copy")
    delete_fetched_files: DeleteFetchedFiles = Field(
        None, description="Delete local client files", alias="delete-fetched-files"
    )
    git: GitCommandsModel = Field(None, description="Manage Git remotes")

    class PicleConfig:
        subshell = True
        prompt = "nf[filesharing]#"


class ShowFileSharingModel(BaseModel):
    files: FilesModel = Field(None, description="Show files in the shared namespace")
    remotes: RemotesModel = Field(None, description="Show file sharing remotes")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_yaml
        outputter_kwargs = {"absolute_indent": 2}
