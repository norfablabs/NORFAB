import builtins

from pydantic import (
    StrictStr,
    Field,
)
from typing import Union, List
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
