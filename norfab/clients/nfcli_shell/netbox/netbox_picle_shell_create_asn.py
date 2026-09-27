import json
from typing import Union

from picle.models import Outputters
from pydantic import Field, StrictStr

from norfab.workers.netbox_worker.netbox_models import CreateBgpAsnInput

from ..common import log_error_or_result, run_future_job
from .netbox_picle_shell_common import NetboxClientRunJobArgs


class CreateAsnShell(
    NetboxClientRunJobArgs,
    CreateBgpAsnInput,
    use_enum_values=True,
    populate_by_name=True,
):
    sites: Union[None, StrictStr, list[StrictStr]] = Field(
        None, description="Comma-separated site names to assign the ASN to"
    )
    tags: Union[None, StrictStr, list[StrictStr]] = Field(
        None, description="Comma-separated tag names"
    )
    custom_fields: Union[None, StrictStr, dict] = Field(
        None, description="JSON dictionary of ASN custom fields", alias="custom-fields"
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        for field in ("sites", "tags"):
            if isinstance(kwargs.get(field), str):
                kwargs[field] = [value.strip() for value in kwargs[field].split(",")]
        if isinstance(kwargs.get("custom_fields"), str):
            kwargs["custom_fields"] = json.loads(kwargs["custom_fields"])

        result = run_future_job(
            "netbox",
            "create_asn",
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
