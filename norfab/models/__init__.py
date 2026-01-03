from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
    model_validator,
    ConfigDict,
)
from enum import Enum
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from datetime import datetime
from norfab.core.exceptions import NorfabJobFailedError

# ------------------------------------------------------
# NorFab event models
# ------------------------------------------------------


class EventSeverityLevels(str, Enum):
    info = "INFO"
    debug = "DEBUG"
    warning = "WARNING"
    critical = "CRITICAL"
    error = "ERROR"


class EventStatusValues(str, Enum):
    pending = "pending"
    scheduled = "scheduled"
    started = "started"
    running = "running"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"


class NorFabEvent(BaseModel):
    message: StrictStr = Field(...)
    client_address: StrictStr = Field(...)
    juuid: StrictStr = Field(...)
    task: StrictStr = Field(...)
    status: EventStatusValues = Field(default=EventStatusValues.running)
    resource: Union[StrictStr, List[StrictStr]] = Field(default=[])
    severity: EventSeverityLevels = Field(default=EventSeverityLevels.info)
    timestamp: Union[StrictStr] = Field(None)
    extras: Dict = Field(None)
    timeout: StrictInt = Field(None)

    @model_validator(mode="after")
    def add_defaults(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().strftime("%d-%b-%Y %H:%M:%S.%f")[:-3]

        return self


# ------------------------------------------------------
# NorFab worker result models
# ------------------------------------------------------


class ResultStatuses(str, Enum):
    completed = "completed"
    no_match = "no_match"
    failed = "failed"
    skipped = "skipped"
    error = "error"
    created = "created"
    updated = "updated"
    unchanged = "unchanged"


class Result(BaseModel, use_enum_values=True):
    """
    NorFab Worker Task Result model.

    Args:
        result (Any): Result of the task execution, see task's documentation for details.
        failed (bool): Whether the execution failed or not.
        errors (Optional[List[str]]): Exception thrown during the execution of the task (if any).
        task (str): Task function name that produced the results.
        messages (Optional[List[str]]): List of messages produced by the task.
        juuid (Optional[str]): Job UUID associated with the task.
        resources (Optional[List[str]]): list of resources names worked on by the task.
        status (Optional[str]): Status of the job, `status` attribute values:

            - 'completed' - task was executed successfully and resources were found
            - 'no_match' - task was executed, but no resources matched the criteria or filters provided
            - 'failed' - task was executed, but failed
            - 'skipped' - task was not executed, but skipped for some reason
            - `error` - attempted to execute the task, but an error occurred

    Methods:
        __repr__(): Returns a string representation of the Result object.
        __str__(): Returns a string representation of the result or errors.
        raise_for_status(message=""): Raises an error if the job failed.
        dictionary(): Serializes the result to a dictionary.
    """

    result: Optional[Any] = Field(
        None,
        description="Result of the task execution, see task's documentation for details",
    )
    failed: Optional[StrictBool] = Field(
        False, description="True if the execution failed, False otherwise"
    )
    errors: Optional[List[StrictStr]] = Field(
        [], description="Exceptions thrown during the execution of the task (if any)"
    )
    task: Optional[StrictStr] = Field(
        None, description="Task name that produced the results"
    )
    messages: Optional[List[StrictStr]] = Field(
        [], description="Messages produced by the task for the client"
    )
    juuid: Optional[StrictStr] = Field(
        None, description="Job ID associated with the task"
    )
    resources: Optional[List[StrictStr]] = Field(
        [], description="List of resources names involved in task"
    )
    status: Optional[ResultStatuses] = Field(None, description="Task status")
    task_started: Optional[StrictStr] = Field(
        None, description="Timestamp when task was started"
    )
    task_completed: Optional[StrictStr] = Field(
        None, description="Timestamp when task was completed"
    )
    service: Optional[StrictStr] = Field(
        None, description="Name of the service produced this result"
    )
    diff: Optional[Union[dict, StrictStr]] = Field(
        None, description="Difference in state"
    )
    dry_run: Optional[StrictBool] = Field(
        False, description="True if dry run, False otherwise"
    )

    def raise_for_status(self, message=""):
        """
        Raises a NorfabJobFailedError if the job has failed.

        Parameters:
            message (str): Optional. Additional message to include in the error. Default is an empty string.

        Raises:
            NorfabJobFailedError: If the job has failed, this error is raised with the provided message and the list of errors.
        """
        if self.failed:
            if message:
                raise NorfabJobFailedError(
                    f"{message}; Errors: {'; '.join(self.errors)}"
                )
            else:
                raise NorfabJobFailedError(f"Errors: {'; '.join(self.errors)}")


# ------------------------------------------------------
# NorFab worker tasks models
# ------------------------------------------------------


class WorkerEchoIn(BaseModel):
    job: object = Field(..., description="NorFab job object")
    sleep: StrictInt = Field(None, description="SLeep for given time")
    raise_error: Union[StrictBool, StrictStr, StrictInt] = Field(
        None, description="Raise RuntimeError with provided message"
    )
    model_config = ConfigDict(extra="allow")


class WorkerEchoOut(Result):
    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------
# NorFab Client Run Job model
# ------------------------------------------------------


class NorFabClientRunJob(BaseModel):

    workers: Union[List[StrictInt], StrictStr] = Field(
        None, description="The workers to run the job on"
    )
    timeout: StrictInt = Field(
        600, description="The maximum time in seconds to wait for the job to complete"
    )
    retry: StrictInt = Field(
        10, description="The number of times to retry getting the job results"
    )
