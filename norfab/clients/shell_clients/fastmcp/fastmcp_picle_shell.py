import logging
import builtins

from picle.models import PipeFunctionsModel, Outputters
from pydantic import (
    BaseModel,
    StrictBool,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result
from .fastmcp_picle_shell_discover import Discover
from typing import Any

SERVICE = "fasmcp"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# FASTMCP SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class FastMCPShowInventoryModel(ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastmcp",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class FastMCPShowStatusModel(ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastmcp",
            "get_status",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class FastMCPShowToolsModel(ClientRunJobArgs):
    brief: StrictBool = Field(
        None,
        description="show tools names only",
        json_schema_extra={"presence": True},
    )
    service: StrictStr = Field(
        None,
        description="filter tools by service name",
    )
    name: StrictStr = Field(
        None,
        description="filter tools by name using glob pattern",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastmcp",
            "get_tools",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class FastMCPShowCommandsModel(BaseModel):
    inventory: FastMCPShowInventoryModel = Field(
        None,
        description="show FastMCP inventory data",
    )
    version: Any = Field(
        None,
        description="show FastMCP service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    status: FastMCPShowStatusModel = Field(
        None,
        description="show FastMCP server status",
    )
    tools: FastMCPShowToolsModel = Field(
        None,
        description="show FastMCP server tools",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_version(**kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("fastmcp", "get_version", workers=workers)
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# FASTMCP SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class FastMCPServiceCommands(BaseModel):
    discover: Discover = Field(
        None, description="Discover NorFab services tasks and create tools"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[fastmcp]#"
