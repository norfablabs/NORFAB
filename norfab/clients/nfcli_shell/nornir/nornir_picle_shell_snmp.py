import json
from typing import List, Optional, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import (
    SnmpBulkGetInput,
    SnmpBulkTableInput,
    SnmpBulkWalkInput,
    SnmpGetInput,
    SnmpGetNextInput,
    SnmpMultiGetInput,
    SnmpMultiSetInput,
    SnmpMultiWalkInput,
    SnmpSetInput,
    SnmpTableInput,
    SnmpWalkInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
)

SERVICE = "nornir"


def _ensure_list(kwargs: dict, *keys: str) -> None:
    for key in keys:
        if isinstance(kwargs.get(key), str):
            kwargs[key] = [kwargs[key]]


class SnmpGetShell(
    SnmpGetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_get",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpGetNextShell(
    SnmpGetNextInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_getnext",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpMultiGetShell(
    SnmpMultiGetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    oids: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of numeric OIDs to retrieve via SNMP MULTIGET",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        _ensure_list(kwargs, "oids")

        result = run_future_job(
            "nornir",
            "snmp_multiget",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpWalkShell(
    SnmpWalkInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_walk",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpMultiWalkShell(
    SnmpMultiWalkInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    oids: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of numeric OIDs at which to start each SNMP MULTIWALK",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        _ensure_list(kwargs, "oids")

        result = run_future_job(
            "nornir",
            "snmp_multiwalk",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpBulkGetShell(
    SnmpBulkGetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    repeating_oids: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of numeric OIDs for repeating (column) retrieval via SNMP BULKGET",
    )
    scalar_oids: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None,
        description="Optional list of numeric OIDs for scalar retrieval",
        alias="scalar-oids",
    )
    max_list_size: Optional[StrictInt] = Field(
        10,
        description="Maximum number of OIDs per GETBULK request",
        alias="max-list-size",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        _ensure_list(kwargs, "repeating_oids", "scalar_oids")

        result = run_future_job(
            "nornir",
            "snmp_bulkget",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpBulkWalkShell(
    SnmpBulkWalkInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    oids: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of numeric OIDs at which to start each SNMP BULKWALK",
    )
    bulk_size: Optional[StrictInt] = Field(
        10,
        description="Maximum number of OIDs per GETBULK request",
        alias="bulk-size",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        _ensure_list(kwargs, "oids")

        result = run_future_job(
            "nornir",
            "snmp_bulkwalk",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpTableShell(
    SnmpTableInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_table",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpBulkTableShell(
    SnmpBulkTableInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    bulk_size: Optional[StrictInt] = Field(
        10,
        description="Maximum number of OIDs per GETBULK request",
        alias="bulk-size",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_bulktable",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpSetShell(
    SnmpSetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "snmp_set",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class SnmpMultiSetShell(
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    mappings: StrictStr = Field(
        ...,
        description="JSON object mapping numeric OIDs to values for SNMP MULTISET",
        examples=['{"1.3.6.1.2.1.1.6.0": "Brisbane lab"}'],
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        # Parse JSON mappings string to dict
        mappings_str = kwargs.pop("mappings", "{}")
        kwargs["mappings"] = json.loads(mappings_str)

        result = run_future_job(
            "nornir",
            "snmp_multiset",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class NornirSnmpShell(BaseModel):
    get: SnmpGetShell = Field(
        None,
        description="Perform an SNMP GET operation on network devices",
    )
    get_next: SnmpGetNextShell = Field(
        None,
        description="Perform an SNMP GETNEXT operation on network devices",
        alias="get-next",
    )
    multi_get: SnmpMultiGetShell = Field(
        None,
        description="Perform an SNMP MULTIGET operation on network devices",
        alias="multi-get",
    )
    walk: SnmpWalkShell = Field(
        None,
        description="Perform an SNMP WALK operation on network devices",
    )
    multi_walk: SnmpMultiWalkShell = Field(
        None,
        description="Perform an SNMP MULTIWALK operation on network devices",
        alias="multi-walk",
    )
    bulk_get: SnmpBulkGetShell = Field(
        None,
        description="Perform an SNMP BULKGET operation on network devices",
        alias="bulk-get",
    )
    bulk_walk: SnmpBulkWalkShell = Field(
        None,
        description="Perform an SNMP BULKWALK operation on network devices",
        alias="bulk-walk",
    )
    table: SnmpTableShell = Field(
        None,
        description="Perform an SNMP TABLE operation on network devices",
    )
    bulk_table: SnmpBulkTableShell = Field(
        None,
        description="Perform an SNMP BULKTABLE operation on network devices using GETBULK",
        alias="bulk-table",
    )
    set: SnmpSetShell = Field(
        None,
        description="Perform an SNMP SET operation on network devices",
    )
    multi_set: SnmpMultiSetShell = Field(
        None,
        description="Perform an SNMP MULTISET operation on network devices",
        alias="multi-set",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-snmp]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
