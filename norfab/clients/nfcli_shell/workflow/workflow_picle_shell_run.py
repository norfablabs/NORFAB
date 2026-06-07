from typing import Union

from picle.models import Outputters
from pydantic import (
    Field,
    StrictStr,
)

from norfab.workers.workflow_worker.workflow_models import RunInput

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job


class WorkflowRunShell(
    ClientRunJobArgs, RunInput, use_enum_values=True, populate_by_name=True
):
    workflow: Union[None, StrictStr] = Field(
        None,
        description="Workflow to run",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[workflow-run]#"
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_workflow() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "workflow",
            "run",
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
