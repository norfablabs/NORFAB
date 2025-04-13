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


class WorkerResult(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    failed: StrictBool = Field(..., mandatory=True)
    juuid: StrictStr = Field(..., mandatory=True)
    messages: List[StrictStr] = Field(..., mandatory=True)
    result: Any = Field(..., mandatory=True)


class ClientPostJobResponse(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    status: StrictStr = Field(..., mandatory=True)
    uuid: StrictStr = Field(..., mandatory=True)
    workers: List[StrictStr] = Field(..., mandatory=True)


class ClientGetJobWorkers(BaseModel):
    dispatched: List[StrictStr] = Field(..., mandatory=True)
    done: List[StrictStr] = Field(..., mandatory=True)
    pending: List[StrictStr] = Field(..., mandatory=True)
    requested: StrictStr = Field(..., mandatory=True)


class ClientGetJobResponse(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    status: StrictStr = Field(..., mandatory=True)
    workers: ClientGetJobWorkers = Field(..., mandatory=True)
    results: Dict[StrictStr, WorkerResult] = Field(..., mandatory=True)
