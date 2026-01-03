import builtins

from pydantic import (
    StrictBool,
    StrictStr,
    Field,
)
from picle.models import Outputters
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from typing import Optional


class WorkflowRunShell(ClientRunJobArgs):
    workflow: StrictStr = Field(
        None,
        description="Workflow to run",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[workflow-run]#"
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_workflow():
        NFCLIENT = builtins.NFCLIENT
        workflow_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return workflow_files["results"]

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "workflow",
            "run",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result
