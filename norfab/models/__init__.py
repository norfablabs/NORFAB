from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
    model_validator,
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
    message: StrictStr = Field(..., mandatory=True)
    client_address: StrictStr = Field(..., mandatory=True)
    juuid: StrictStr = Field(..., mandatory=True)
    task: StrictStr = Field(..., mandatory=True)
    status: EventStatusValues = Field(EventStatusValues.running, mandatory=False)
    resource: Union[StrictStr, List[StrictStr]] = Field([], mandatory=False)
    severity: EventSeverityLevels = Field(EventSeverityLevels.info, mandatory=False)
    timestamp: Union[StrictStr] = Field(None, mandatory=False)
    extras: Dict = Field({}, mandatory=False)
    timeout: StrictInt = Field(None, mandatory=False)

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
        [], description="List of resources names worked on by the task"
    )
    status: Optional[ResultStatuses] = Field(None, description="Task status")

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
