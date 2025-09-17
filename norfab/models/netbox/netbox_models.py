import builtins

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
from norfab.models import Result
from .. import NorFabClientRunJob


class NetboxCommonArgs(BaseModel):
    """Model to enlist arguments common across Netbox service tasks"""

    instance: Optional[StrictStr] = Field(
        None,
        description="Netbox instance name to target",
    )
    dry_run: StrictBool = Field(
        None,
        description="Do not commit to database",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_instance():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.run_job("netbox", "get_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["result"]["instances"])


class NetboxFastApiArgs(NorFabClientRunJob):
    """Model to specify arguments for FastAPI REST API endpoints"""

    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )


class PrefixStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    container = "container"
    deprecated = "deprecated"


class CreatePrefixInput(NetboxCommonArgs, use_enum_values=True):
    parent: Union[StrictStr, dict] = Field(
        ...,
        description="Parent prefix to allocate new prefix from",
    )
    description: Union[None, StrictStr] = Field(
        None, description="Description for new prefix"
    )
    prefixlen: StrictInt = Field(30, description="The prefix length of the new prefix")
    vrf: Union[None, StrictStr] = Field(
        None, description="Name of the VRF to associate with the prefix"
    )
    tags: Union[None, StrictStr, list[StrictStr]] = Field(
        None, description="List of tags to assign to the prefix"
    )
    tenant: Union[None, StrictStr] = Field(
        None, description="Name of the tenant to associate with the prefix"
    )
    comments: Union[None, StrictStr] = Field(
        None, description="Comments for the prefix"
    )
    role: Union[None, StrictStr] = Field(
        None, description="Role to assign to the prefix"
    )
    site: Union[None, StrictStr] = Field(
        None, description="Name of the site to associate with the prefix"
    )
    status: Union[None, PrefixStatusEnum] = Field(
        None, description="Status of the prefix"
    )
    branch: Union[None, StrictStr] = Field(
        None, description="Branching plugin branch name to use"
    )
