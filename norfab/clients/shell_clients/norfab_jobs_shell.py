import builtins

from enum import Enum
from pydantic import (
    StrictStr,
    Field,
    BaseModel,
    StrictInt,
    StrictBool,
)
from typing import List, Union
from .common import ClientRunJobArgs, log_error_or_result
from picle.models import Outputters, PipeFunctionsModel


class JobStatus(str, Enum):
    NEW = "NEW"
    SUBMITTING = "SUBMITTING"  # POST sent, waiting for broker ACK
    DISPATCHED = "DISPATCHED"  # Broker dispatched to workers
    STARTED = "STARTED"  # At least one worker started processing
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"  # Job exceeded deadline without completion


class ListJobsSummaryModel(ClientRunJobArgs):

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT

        return None

    class PicleConfig:
        outputter = Outputters.outputter_rich_table


class NorFabJobsShellCommands(BaseModel):
    # summary: ListJobsModel = Field(None, description="List jobs")
    uuid: StrictStr = Field(None, description="Job UUID")
    service: StrictStr = Field(None, description="Service name to return jobs for")
    workers_completed: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Workers to return jobs for"
    )
    last: StrictInt = Field(10, description="Return last N jobs")
    statuses: List[JobStatus] = Field(None, description="Return jobs by status")
    task: StrictStr = Field(None, description="Task name to return jobs for")
    uuid: StrictStr = Field(None, description="Job UUID to return")
    details: StrictBool = Field(
        None,
        description="Return complete jobs details",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        details = kwargs.pop("details", None)
        uuid = kwargs.pop("uuid", None)

        if kwargs.get("workers_completed"):
            if isinstance(kwargs["workers_completed"], str):
                kwargs["workers_completed"] = [kwargs["workers_completed"]]

        if uuid:
            jobs = NFCLIENT.job_db.get_job(uuid)
            jobs = [jobs]
        else:
            jobs = NFCLIENT.job_db.fetch_jobs(**kwargs)

        if details:
            return jobs, Outputters.outputter_nested
        else:
            return (
                [
                    {
                        "uuid": j["uuid"],
                        "service": j["service"],
                        "task": j["task"],
                        "status": j["status"],
                        "created": j["created_at"],
                        "completed": j["completed_timestamp"],
                    }
                    for j in jobs
                ],
                Outputters.outputter_rich_table,
            )

    @staticmethod
    def source_workers_completed():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi("mmi.service.broker", "show_workers")
        return [i["name"] for i in reply["results"]]

    @staticmethod
    def source_service():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi("mmi.service.broker", "show_workers")
        return [i["service"] for i in reply["results"]]

    class PicleConfig:
        pipe = PipeFunctionsModel
