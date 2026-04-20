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

from ..common import ClientRunJobArgs, listen_events, log_error_or_result

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
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
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
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
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
    @listen_events
    def run(uuid: str, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)
        kwargs["ping"] = "pong"

        result = NFCLIENT.run_job(
            service,
            "echo",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
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

    class PicleConfig:
        subshell = True
        prompt = "nf[workers]#"
