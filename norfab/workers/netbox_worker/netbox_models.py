import builtins
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from norfab.models import NorFabClientRunJob

# --------------------------------------------------------------------------
# NETBOX WORKER CONFIGURATION MODEL
# --------------------------------------------------------------------------


class CacheUseEnum(str, Enum):
    force = "force"
    refresh = "refrresh"


class NetboxInstanceConfig(BaseModel):
    default: StrictBool = Field(
        None, description="Is this default instance of Netbox or not"
    )
    url: StrictStr = Field(None, description="Netbox URL")
    token: StrictStr = Field(None, description="Netbox auth token")
    ssl_verify: StrictBool = Field(True, description="Verify SSL vertsor not")


class NetboxConfigModel(BaseModel):
    cache_use: Union[CacheUseEnum, StrictBool] = Field(
        True, description="Use cache or not"
    )
    cache_ttl: StrictInt = Field(True, description="Cache TTL")
    instances: Dict[StrictStr, NetboxInstanceConfig] = Field(
        None, description="Netbox instance config keyed by instance name"
    )


# --------------------------------------------------------------------------
# CORE NETBOX WORKER MODELS
# --------------------------------------------------------------------------


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
    branch: Union[None, StrictStr] = Field(
        None,
        description="NetBox branching plugin branch name to use",
    )

    @staticmethod
    def source_instance() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.run_job("netbox", "get_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["result"]["instances"])


class NetboxFastApiArgs(NorFabClientRunJob):
    """Model to specify arguments for FastAPI REST API endpoints"""

    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

