from typing import Union, Dict, List, Optional, Any
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
    ConfigDict,
    model_validator,
)
from norfab.models import Result


# -----------------------------------------------------------------------------------------
# deploy Task Pydantic Models
# -----------------------------------------------------------------------------------------


class DeployTask(BaseModel, extra="forbid"):
    """
    Pydantic model for Containerlab worker deploy task.
    """

    topology: StrictStr = Field(..., description="Topology file path")
    reconfigure: StrictBool = Field(None, description="Reconfigure flag")
    timeout: StrictInt = Field(None, description="Deployment timeout in seconds")
    node_filter: StrictStr = Field(
        None, description="A filter to specify which nodes to deploy"
    )


class DeployTaskResponse(Result):
    result: Union[StrictStr, Dict] = Field(
        None, description="Result of the deploy task"
    )
