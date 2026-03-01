import builtins

from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictStr,
    Field,
)
from enum import Enum
from typing import Union, Optional, List, Dict
from norfab.models import NorFabClientRunJob

# --------------------------------------------------------------------------
# CONFIGURATION MODEL
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
# CORE MODELs
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
        None, description="Branching plugin branch name to use"
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


class InterfaceTypeEnum(str, Enum):
    virtual = "virtual"
    other = "other"
    bridge = "bridge"
    lag = "lag"


class CreateDeviceInterfacesInput(NetboxCommonArgs, use_enum_values=True):
    devices: List = Field(
        ...,
        description="List of device names or device objects to create interfaces for",
    )
    interface_name: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="Name(s) of the interface(s) to create",
    )
    interface_type: InterfaceTypeEnum = Field(
        "other",
        description="Name(s) of the interface(s) to create",
        alias="interface-type",
    )
    description: Union[None, StrictStr] = Field(
        None, description="Interface description"
    )
    speed: StrictInt = Field(None, description="Interface speed in Kbps")
    mtu: StrictInt = Field(None, description="Maximum transmission unit size in bytes")
