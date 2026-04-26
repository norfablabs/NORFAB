import builtins
import json
import logging

from picle.models import Outputters, PipeFunctionsModel

from norfab.workers.netbox_worker.bgp_peerings_tasks import UpdateBgpPeeringInput

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class UpdateBgpPeeringShell(NetboxClientRunJobArgs, UpdateBgpPeeringInput):

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        # Parse JSON strings for bulk argument
        if isinstance(kwargs.get("bulk_update"), str):
            kwargs["bulk_update"] = json.loads(kwargs["bulk_update"])
        if isinstance(kwargs.get("import_policies"), str):
            kwargs["import_policies"] = [
                p.strip() for p in kwargs["import_policies"].split(",") if p.strip()
            ]
        if isinstance(kwargs.get("export_policies"), str):
            kwargs["export_policies"] = [
                p.strip() for p in kwargs["export_policies"].split(",") if p.strip()
            ]
        if isinstance(kwargs.get("prefix_list_in"), str):
            kwargs["prefix_list_in"] = [kwargs["prefix_list_in"]]
        if isinstance(kwargs.get("prefix_list_out"), str):
            kwargs["prefix_list_out"] = [kwargs["prefix_list_out"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_bgp_peering",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
