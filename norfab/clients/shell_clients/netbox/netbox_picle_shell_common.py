import builtins

from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    root_validator,
    Field,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import ClientRunJobArgs


class NetboxClientRunJobArgs(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

    @staticmethod
    def source_workers():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.get("mmi.service.broker", "show_workers")
        reply = reply["results"]
        return ["all", "any"] + [
            w["name"] for w in reply if w["service"].startswith("netbox")
        ]
