import json
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictStr

from norfab.workers.netbox_worker.netbox_models import (
    CrudChangelogArgs,
    CrudCreateArgs,
    CrudDeleteArgs,
    CrudListObjectsArgs,
    CrudReadArgs,
    CrudSearchArgs,
    CrudUpdateArgs,
)

from ..common import log_error_or_result, run_future_job
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CrudListObjectsShell(
    NetboxClientRunJobArgs,
    CrudListObjectsArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        app_filter = kwargs.get("app_filter")
        if isinstance(app_filter, str) and "," in app_filter:
            kwargs["app_filter"] = [s.strip() for s in app_filter.split(",")]

        result = run_future_job(
            "netbox",
            "crud_list_objects",
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
        pipe = PipeFunctionsModel


class CrudSearchShell(
    NetboxClientRunJobArgs,
    CrudSearchArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    object_types: StrictStr = Field(
        None,
        description="Comma-separated app.resource types to search e.g. dcim.devices,ipam.prefixes",
        alias="object-types",
    )
    fields: StrictStr = Field(
        None,
        description="Comma-separated fields to return",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        object_types = kwargs.get("object_types")
        if isinstance(object_types, str):
            kwargs["object_types"] = [s.strip() for s in object_types.split(",")]

        fields = kwargs.get("fields")
        if isinstance(fields, str):
            kwargs["fields"] = [s.strip() for s in fields.split(",")]

        result = run_future_job(
            "netbox",
            "crud_search",
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
        pipe = PipeFunctionsModel


class CrudReadShell(
    NetboxClientRunJobArgs,
    CrudReadArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    filters: StrictStr = Field(
        None,
        description='JSON string - filter dict or list of dicts e.g. [{"name":"ceos1"}]',
    )
    fields: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="Comma-separated fields to return",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        ordering = kwargs.get("ordering")

        if isinstance(kwargs.get("object_id"), int):
            kwargs["object_id"] = [kwargs.get("object_id")]
        if isinstance(kwargs.get("filters"), str):
            kwargs["filters"] = json.loads(kwargs.get("filters"))
        if isinstance(kwargs.get("fields"), str):
            kwargs["fields"] = [s.strip() for s in kwargs["fields"].split(",")]
        if isinstance(ordering, str):
            kwargs["ordering"] = [ordering]

        result = run_future_job(
            "netbox",
            "crud_read",
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
        pipe = PipeFunctionsModel


class CrudCreateShell(
    NetboxClientRunJobArgs,
    CrudCreateArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    data: StrictStr = Field(
        ...,
        description='JSON dict or list of dicts with object field values e.g. \'{"name":"Foo","slug":"foo"}\'',
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        kwargs["data"] = json.loads(kwargs["data"])

        result = run_future_job(
            "netbox",
            "crud_create",
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
        pipe = PipeFunctionsModel


class CrudUpdateShell(
    NetboxClientRunJobArgs,
    CrudUpdateArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    data: StrictStr = Field(
        ...,
        description='JSON dict or list of dicts; each must contain "id" e.g. \'{"id":1,"name":"Bar"}\'',
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        kwargs["data"] = json.loads(kwargs["data"])

        result = run_future_job(
            "netbox",
            "crud_update",
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
        pipe = PipeFunctionsModel


class CrudDeleteShell(
    NetboxClientRunJobArgs,
    CrudDeleteArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    object_id: StrictStr = Field(
        ...,
        description="Comma-separated integer ID(s) to delete",
        alias="object-id",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        object_id = kwargs.get("object_id")
        if isinstance(object_id, str):
            parts = [s.strip() for s in object_id.split(",")]
            ids = [int(p) for p in parts]
            kwargs["object_id"] = ids[0] if len(ids) == 1 else ids

        result = run_future_job(
            "netbox",
            "crud_delete",
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
        pipe = PipeFunctionsModel


class CrudGetChangelogsShell(
    NetboxClientRunJobArgs,
    CrudChangelogArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    filters: StrictStr = Field(
        None,
        description="JSON filter dict or list of dicts for NetBox changelog lookup",
    )
    fields: StrictStr = Field(
        None,
        description="Comma-separated fields to return",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        filters = kwargs.get("filters")
        if isinstance(filters, str):
            kwargs["filters"] = json.loads(filters)

        fields = kwargs.get("fields")
        if isinstance(fields, str):
            kwargs["fields"] = [s.strip() for s in fields.split(",")]

        result = run_future_job(
            "netbox",
            "crud_get_changelogs",
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
        pipe = PipeFunctionsModel


class CrudCommands(BaseModel):
    list_objects: CrudListObjectsShell = Field(
        None,
        description="List available NetBox object types from OpenAPI schema",
        alias="list-objects",
    )
    search: CrudSearchShell = Field(
        None,
        description="Free-text search across NetBox object types",
    )
    get: CrudReadShell = Field(
        None,
        description="Retrieve NetBox objects by ID or filter",
    )
    create: CrudCreateShell = Field(
        None,
        description="Create one or multiple NetBox objects",
    )
    update: CrudUpdateShell = Field(
        None,
        description="Update one or multiple NetBox objects",
    )
    delete: CrudDeleteShell = Field(
        None,
        description="Delete one or multiple NetBox objects by ID",
    )
    changelogs: CrudGetChangelogsShell = Field(
        None,
        description="Retrieve NetBox change history",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-crud]#"
