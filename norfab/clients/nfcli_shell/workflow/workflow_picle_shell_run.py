import builtins
from typing import Optional

from picle.models import Outputters
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from ..common import ClientRunJobArgs, listen_events, log_error_or_result


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
    def source_workflow() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "workflow",
            "run",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result
