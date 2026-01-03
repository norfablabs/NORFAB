import logging
import builtins

from rich.console import Console
from picle.models import PipeFunctionsModel, Outputters
from pydantic import (
    BaseModel,
    StrictBool,
    StrictStr,
    Field,
)
from typing import Optional, Any
from ..common import ClientRunJobArgs, log_error_or_result, listen_events

RICHCONSOLE = Console()
SERVICE = "agent"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# AGENT SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class AgentShowCommandsModel(BaseModel):
    inventory: Any = Field(
        None,
        description="show agent inventory data",
        json_schema_extra={"function": "get_inventory"},
    )
    version: Any = Field(
        None,
        description="show agent service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    status: Any = Field(
        None,
        description="show agent status",
        json_schema_extra={"function": "get_status"},
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_inventory(**kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("agent", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("agent", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_status(**kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        result = NFCLIENT.run_job("agent", "get_status", workers=workers, kwargs=kwargs)
        result = log_error_or_result(result)
        return result


# ---------------------------------------------------------------------------------------------
# AGENT RUN TASK SHELL MODEL
# ---------------------------------------------------------------------------------------------


class AgentInvoke(ClientRunJobArgs):
    instructions: StrictStr = Field(None, description="Provide instructions")
    name: StrictStr = Field(None, description="Agent name to interact with")
    progress: Optional[StrictBool] = Field(
        True,
        description="Emit execution progress",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_rich_markdown

    @staticmethod
    def source_name():
        NFCLIENT = builtins.NFCLIENT
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return ["NorFab"] + broker_files["results"]

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.get("verbose_result", False)

        # run the job
        result = NFCLIENT.run_job(
            "agent",
            "invoke",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )
        result = log_error_or_result(result, verbose_result=verbose_result)

        if verbose_result:
            return result, Outputters.outputter_nested
        else:
            return list(result.items())[0][-1]


# ---------------------------------------------------------------------------------------------
# AGENT SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class AgentServiceCommands(ClientRunJobArgs):
    invoke: AgentInvoke = Field(
        None,
        description="Invoke an agent to chat or run a task",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[agent]#"
