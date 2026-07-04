import builtins
import logging
from enum import Enum
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# WORKERS SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class WorkerStatus(str, Enum):
    dead = "dead"
    alive = "alive"
    any_ = "any"


class ShowWorkersStatusBrief(BaseModel):
    service: StrictStr = Field("all", description="Service name")
    status: WorkerStatus = Field("any", description="Worker status")

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", args=args, kwargs=kwargs
        )
        if reply["errors"]:
            return "\n".join(reply["errors"])
        else:
            return reply["results"]

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_rich_table
        outputter_kwargs = {"sortby": "name"}


class ShowWorkersStatistics(ClientRunJobArgs):

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "all",
            "get_watchdog_stats",
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
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class ShowWorkersVersion(ClientRunJobArgs):

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "all",
            "get_version",
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
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class ListWorkersJobsModel(ClientRunJobArgs):
    workers: StrictStr = Field("all", description="Workers to return jobs for")
    service: StrictStr = Field("all", description="Service name to return jobs for")
    last: StrictInt = Field(
        10, description="Return last N completed and last N pending jobs, default is 10"
    )
    pending: StrictBool = Field(
        True, description="Return pending jobs", json_schema_extra={"presence": True}
    )
    completed: StrictBool = Field(
        True, description="Return completed jobs", json_schema_extra={"presence": True}
    )
    client: StrictStr = Field(None, description="Client name to return jobs for")
    uuid: StrictStr = Field(None, description="Job UUID to return")
    task: StrictStr = Field(None, description="Task name to return jobs for")

    @staticmethod
    def source_client() -> list:
        return ["self"]

    @staticmethod
    def source_service() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        services = sorted({i["service"] for i in reply["results"]})

        return ["all"] + services

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if kwargs.get("client") == "self":
            kwargs["client"] = NFCLIENT.zmq_name

        result = run_future_job(
            service,
            "job_list",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        ret = []
        for worker_results in result.values():
            ret.extend(worker_results)

        return ret

    class PicleConfig:
        outputter = Outputters.outputter_rich_table


class WorkersJobDetailsModel(ClientRunJobArgs):
    uuid: StrictStr = Field(..., description="Job UUID")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Workers to return jobs for"
    )
    service: StrictStr = Field("all", description="Service name to return jobs for")
    result: StrictBool = Field(
        True, description="Return job result", json_schema_extra={"presence": True}
    )
    events: StrictBool = Field(
        True, description="Return job events", json_schema_extra={"presence": True}
    )

    @staticmethod
    def source_service() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        services = sorted({i["service"] for i in reply["results"]})

        return ["all"] + services

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            service,
            "job_details",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class ShowWorkersJobsModel(BaseModel):
    summary: ListWorkersJobsModel = Field(None, description="List jobs")
    details: WorkersJobDetailsModel = Field(None, description="Show job details")

    class PicleConfig:
        pass


class ShowWorkersModel(BaseModel):
    brief: ShowWorkersStatusBrief = Field(None, description="Show workers brief info")
    statistics: ShowWorkersStatistics = Field(
        None, description="Show workers statistics"
    )
    version: ShowWorkersVersion = Field(None, description="Show workers version info")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


# ---------------------------------------------------------------------------------------------
# WORKERS UTILITIES SHELL MODELS
# ---------------------------------------------------------------------------------------------


class WorkersPingCommand(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Workers to ping"
    )
    service: Union[StrictStr, List[StrictStr]] = Field(
        "all",
        description="Service to ping",
    )
    sleep: StrictInt = Field(None, description="SLeep for given time")
    raise_error: Union[StrictBool, StrictStr, StrictInt] = Field(
        None,
        description="Raise RuntimeError with provided message",
        alias="raise-error",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)
        kwargs["ping"] = "pong"

        result = run_future_job(
            service,
            "echo",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )


class WorkersShellCommand(ClientRunJobArgs):
    command: StrictStr = Field(
        ...,
        description="Shell command to run on workers",
        json_schema_extra={"multiline": True},
    )
    command_timeout: StrictInt = Field(
        None,
        description="Shell command timeout in seconds",
        alias="command-timeout",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)

        command_timeout = kwargs.pop("command_timeout", None)
        if command_timeout is not None:
            kwargs["timeout"] = command_timeout

        result = run_future_job(
            "all",
            "run_shell_cmd",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )


# ---------------------------------------------------------------------------------------------
# WORKERS MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NorfabWorkersCommands(BaseModel):
    ping: WorkersPingCommand = Field(None, description="Ping workers")
    run_shell_command: WorkersShellCommand = Field(
        None,
        description="Run shell command on workers",
        alias="run-shell-command",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[workers]#"
