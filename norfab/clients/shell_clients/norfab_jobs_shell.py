import builtins

from pydantic import (
    StrictStr,
    Field,
    BaseModel,
    StrictInt,
    StrictBool,
)
from .common import ClientRunJobArgs, log_error_or_result
from picle.models import Outputters


class ListJobsModel(ClientRunJobArgs):
    service: StrictStr = Field(..., description="Service name to return jobs for")
    workers: StrictStr = Field("all", description="Workers to return jobs for")
    last: StrictInt = Field(
        None, description="Return last N completed and last N pending jobs"
    )
    pending: StrictBool = Field(
        True, description="Return pending jobs", json_schema_extra={"presence": True}
    )
    completed: StrictBool = Field(
        True, description="Return completed jobs", json_schema_extra={"presence": True}
    )
    task: StrictStr = Field(None, description="Task name to return jobs for")
    client: StrictStr = Field(None, description="Client name to return jobs for")
    uuid: StrictStr = Field(None, description="Job UUID to return")

    @staticmethod
    def source_service():
        return ["netbox", "nornir"]

    @staticmethod
    def source_workers():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi("mmi.service.broker", "show_workers")
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            kwargs.pop("service"),
            "job_list",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result

        result = log_error_or_result(result, verbose_result=verbose_result)

        ret = []
        for worker_name, worker_results in result.items():
            ret.extend(worker_results)

        return ret

    class PicleConfig:
        outputter = Outputters.outputter_rich_table


class NorFabJobsShellCommands(BaseModel):
    summary: ListJobsModel = Field(None, description="List jobs")
    uuid: StrictStr = Field(None, description="Job UUID")

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT

        return NFCLIENT.job_db.get_job(kwargs["uuid"])

    class PicleConfig:
        subshell = True
