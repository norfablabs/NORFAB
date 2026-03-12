import builtins
from typing import List, Union

from pydantic import (
    Field,
    StrictStr,
)

from ..common import ClientRunJobArgs


class NetboxClientRunJobArgs(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

    @staticmethod
    def source_workers():
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi("mmi.service.broker", "show_workers")
        reply = reply["results"]
        return ["all", "any"] + [
            w["name"] for w in reply if w["service"].startswith("netbox")
        ]
