from typing import Any, Dict, Union

from pydantic import BaseModel, Field, StrictStr

from norfab.models import Result

# --------------------------------------------------------------------------
# WORKFLOW WORKER MODELS
# --------------------------------------------------------------------------


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: Dict[StrictStr, StrictStr] = Field(
        {},
        description="Installed package versions keyed by package name",
    )


class GetInventoryInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetInventoryResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {},
        description="Workflow worker inventory data",
    )


class RunInput(BaseModel, use_enum_values=True, populate_by_name=True):
    workflow: Union[StrictStr, Dict[StrictStr, Any]] = Field(
        ...,
        description="Workflow definition or URL to a YAML workflow file",
    )


class RunResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {},
        description="Workflow execution results keyed by workflow name",
    )
