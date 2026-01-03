from pydantic import (
    BaseModel,
    StrictStr,
    Field,
)
from typing import List, Dict
from norfab.models import Result


class ClientPostJobResponse(BaseModel):
    errors: List[StrictStr] = Field(...)
    status: StrictStr = Field(...)
    uuid: StrictStr = Field(...)
    workers: List[StrictStr] = Field(...)


class ClientGetJobWorkers(BaseModel):
    dispatched: List[StrictStr] = Field(...)
    done: List[StrictStr] = Field(...)
    pending: List[StrictStr] = Field(...)
    requested: StrictStr = Field(...)


class ClientGetJobResponse(BaseModel):
    errors: List[StrictStr] = Field(...)
    status: StrictStr = Field(...)
    workers: ClientGetJobWorkers = Field(...)
    results: Dict[StrictStr, Result] = Field(...)
