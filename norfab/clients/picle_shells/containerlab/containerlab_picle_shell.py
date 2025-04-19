import logging

from rich.console import Console
from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    root_validator,
    Field,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import log_error_or_result

RICHCONSOLE = Console()
SERVICE = "containerlab"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class ContainerlabShowCommandsModel(BaseModel):
    inventory: Callable = Field(
        "get_inventory",
        description="show containerlab inventory data",
        json_schema_extra={"outputter": Outputters.outputter_rich_yaml},
    )
    version: Callable = Field(
        "get_version",
        description="show containerlab service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_rich_yaml,
            "initial_indent": 2,
        },
    )
    status: Callable = Field(
        "get_containerlab_status",
        description="show containerlab status",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("containerlab", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("containerlab", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_containerlab_status(**kwargs):
        workers = kwargs.pop("workers", "any")
        result = NFCLIENT.run_job(
            "containerlab", "get_containerlab_status", workers=workers, kwargs=kwargs
        )
        result = log_error_or_result(result)
        return result


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class ContainerlabServiceCommands(BaseModel):
    class PicleConfig:
        subshell = True
        prompt = "nf[containerlab]#"
