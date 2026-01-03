import logging
import builtins

from picle.models import PipeFunctionsModel, Outputters
from pydantic import (
    BaseModel,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result
from .workflow_picle_shell_run import WorkflowRunShell

SERVICE = "workflow"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# WORKFLOW SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class WorkflowShowInventoryModel(ClientRunJobArgs):
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
            "workflow",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class WorkflowShowVersionModel(ClientRunJobArgs):
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
            "workflow",
            "get_version",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class WorkflowShowCommandsModel(BaseModel):
    inventory: WorkflowShowInventoryModel = Field(
        None,
        description="Show workflow workers inventory data",
    )
    version: WorkflowShowVersionModel = Field(
        None,
        description="Show workflow service workers version report",
    )


# ---------------------------------------------------------------------------------------------
# WORKFLOW SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class WorkflowServiceCommands(BaseModel):
    run: WorkflowRunShell = Field(None, description="Run workflows")

    class PicleConfig:
        subshell = True
        prompt = "nf[workflow]#"
