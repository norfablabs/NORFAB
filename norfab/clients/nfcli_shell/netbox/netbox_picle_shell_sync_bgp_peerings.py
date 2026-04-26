import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field

from norfab.workers.netbox_worker.bgp_peerings_tasks import SyncBgpPeeringsInput

from ..common import listen_events, log_error_or_result
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncBgpPeeringsShell(
    NetboxClientRunJobArgs, SyncBgpPeeringsInput, NorniHostsFilters
):
    process_deletions: bool = Field(
        False,
        description="Delete BGP sessions present in NetBox but not found on the device",
        alias="process-deletions",
        json_schema_extra={"presence": True},
    )
    filter_by_remote_as: Union[None, List[int]] = Field(
        None,
        description="Only sync sessions with matching remote AS number(s)",
        alias="filter-by-remote-as",
    )
    filter_by_peer_group: Union[None, List[str]] = Field(
        None,
        description="Only sync sessions with matching peer group name(s)",
        alias="filter-by-peer-group",
    )
    filter_by_description: Union[None, str] = Field(
        None,
        description="Only sync sessions whose description matches this glob pattern",
        alias="filter-by-description",
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 60)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
