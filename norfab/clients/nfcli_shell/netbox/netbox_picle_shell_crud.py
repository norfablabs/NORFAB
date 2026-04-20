import builtins
import json
import logging

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.workers.netbox_worker.netbox_models import NetboxCommonArgs

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CrudListObjectsShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    app_filter: StrictStr = Field(
        None,
        description="Filter by app(s) e.g. dcim or dcim,ipam (comma-separated)",
        alias="app-filter",
    )
    include_metadata: StrictBool = Field(
        True,
        description="Include path/methods/schema_name/description",
        alias="include-metadata",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        app_filter = kwargs.get("app_filter")
        if isinstance(app_filter, str) and "," in app_filter:
            kwargs["app_filter"] = [s.strip() for s in app_filter.split(",")]

        result = NFCLIENT.run_job(
            "netbox",
            "crud_list_objects",
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


class CrudSearchShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    query: StrictStr = Field(..., description="Search term")
    object_types: StrictStr = Field(
        None,
        description="Comma-separated app.resource types to search e.g. dcim.devices,ipam.prefixes",
        alias="object-types",
    )
    fields: StrictStr = Field(
        None,
        description="Comma-separated fields to return",
    )
    brief: StrictBool = Field(
        False,
        description="Return brief representation",
        json_schema_extra={"presence": True},
    )
    limit: StrictInt = Field(
        10, ge=1, le=100, description="Max results per object type"
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
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

        result = NFCLIENT.run_job(
            "netbox",
            "crud_search",
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


class CrudReadShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    object_type: StrictStr = Field(
        ...,
        description='Object type e.g. "dcim.devices"',
        alias="object-type",
    )
    object_id: StrictStr = Field(
        None,
        description="Comma-separated integer ID(s)",
        alias="object-id",
    )
    filters: StrictStr = Field(
        None,
        description='JSON filter dict or list of dicts e.g. \'{"name":"ceos1"}\'',
    )
    fields: StrictStr = Field(
        None,
        description="Comma-separated fields to return",
    )
    brief: StrictBool = Field(
        False,
        description="Return brief representation",
        json_schema_extra={"presence": True},
    )
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")
    ordering: StrictStr = Field(
        None,
        description='Comma-separated ordering fields, prefix "-" for descending e.g. name or -name,id',
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        object_id = kwargs.get("object_id")
        if isinstance(object_id, str):
            parts = [s.strip() for s in object_id.split(",")]
            ids = [int(p) for p in parts]
            kwargs["object_id"] = ids[0] if len(ids) == 1 else ids

        filters = kwargs.get("filters")
        if isinstance(filters, str):
            kwargs["filters"] = json.loads(filters)

        fields = kwargs.get("fields")
        if isinstance(fields, str):
            kwargs["fields"] = [s.strip() for s in fields.split(",")]

        ordering = kwargs.get("ordering")
        if isinstance(ordering, str) and "," in ordering:
            kwargs["ordering"] = [s.strip() for s in ordering.split(",")]

        result = NFCLIENT.run_job(
            "netbox",
            "crud_read",
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


class CrudCreateShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    object_type: StrictStr = Field(
        ...,
        description='Object type e.g. "dcim.manufacturers"',
        alias="object-type",
    )
    data: StrictStr = Field(
        ...,
        description='JSON dict or list of dicts with object field values e.g. \'{"name":"Foo","slug":"foo"}\'',
    )
    dry_run: StrictBool = Field(
        False,
        description="Preview without creating",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        kwargs["data"] = json.loads(kwargs["data"])

        result = NFCLIENT.run_job(
            "netbox",
            "crud_create",
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


class CrudUpdateShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    object_type: StrictStr = Field(
        ...,
        description='Object type e.g. "dcim.manufacturers"',
        alias="object-type",
    )
    data: StrictStr = Field(
        ...,
        description='JSON dict or list of dicts; each must contain "id" e.g. \'{"id":1,"name":"Bar"}\'',
    )
    partial: StrictBool = Field(
        True,
        description="PATCH (partial=True) vs PUT (partial=False)",
        json_schema_extra={"presence": True},
    )
    dry_run: StrictBool = Field(
        False,
        description="Show diffs without updating",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        kwargs["data"] = json.loads(kwargs["data"])

        result = NFCLIENT.run_job(
            "netbox",
            "crud_update",
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


class CrudDeleteShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    object_type: StrictStr = Field(
        ...,
        description='Object type e.g. "dcim.manufacturers"',
        alias="object-type",
    )
    object_id: StrictStr = Field(
        ...,
        description="Comma-separated integer ID(s) to delete",
        alias="object-id",
    )
    dry_run: StrictBool = Field(
        False,
        description="Preview objects that would be deleted",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        object_id = kwargs.get("object_id")
        if isinstance(object_id, str):
            parts = [s.strip() for s in object_id.split(",")]
            ids = [int(p) for p in parts]
            kwargs["object_id"] = ids[0] if len(ids) == 1 else ids

        result = NFCLIENT.run_job(
            "netbox",
            "crud_delete",
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


class CrudGetChangelogsShell(NetboxCommonArgs, NetboxClientRunJobArgs):
    filters: StrictStr = Field(
        None,
        description=(
            "JSON filter dict or list of dicts; supported keys: user, action, "
            "changed_object_id, object_repr, time_before, time_after, q"
        ),
    )
    fields: StrictStr = Field(
        None,
        description="Comma-separated fields to return",
    )
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
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

        result = NFCLIENT.run_job(
            "netbox",
            "crud_get_changelogs",
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
