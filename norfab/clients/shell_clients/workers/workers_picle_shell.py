import logging

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from typing import Union, Optional, List, Any, Dict, Tuple
from nornir_salt.plugins.functions import TabulateFormatter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# WORKERS SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class WorkerStatus(str, Enum):
    dead = "dead"
    alive = "alive"
    any_ = "any"


class ShowWorkersModel(BaseModel):
    service: StrictStr = Field("all", description="Service name")
    status: WorkerStatus = Field("any", description="Worker status")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_rich_table
        outputter_kwargs = {"sortby": "name"}

    @staticmethod
    def run(*args, **kwargs):
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", args=args, kwargs=kwargs
        )
        if reply["errors"]:
            return "\n".join(reply["errors"])
        else:
            return reply["results"]


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
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "all"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        kwargs["ping"] = "pong"

        result = NFCLIENT.run_job(
            service,
            "echo",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )

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
