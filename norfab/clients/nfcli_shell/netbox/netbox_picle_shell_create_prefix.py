import json
import logging

from picle.models import Outputters

from norfab.workers.netbox_worker.netbox_models import CreatePrefixInput

from ..common import log_error_or_result, run_future_job
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CreatePrefixShell(
    NetboxClientRunJobArgs,
    CreatePrefixInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("tags"), str):
            kwargs["tags"] = [kwargs["tags"]]

        if "{" in kwargs["parent"] and "}" in kwargs["parent"]:
            kwargs["parent"] = json.loads(kwargs["parent"])

        result = run_future_job(
            "netbox",
            "create_prefix",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
