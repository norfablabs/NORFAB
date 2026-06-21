import json
from enum import Enum
from typing import Dict, List, Optional, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import TestInput

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
    tabulate_worker_results,
)


class EnumTableTypes(str, Enum):
    table_brief = "brief"
    table_terse = "terse"
    table_extend = "extend"


class NornirTestShell(
    TestInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    suite: StrictStr = Field(..., description="Nornir suite nf://path/to/file.py")
    job_data: Optional[StrictStr] = Field(
        None, description="Path to YAML file with job data", alias="job-data"
    )
    table: Union[EnumTableTypes, Dict, StrictBool] = Field(
        "brief",
        description="Table format (brief, terse, extend) or parameters or True",
        json_schema_extra={"presence": "brief"},
    )
    groups: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="Test groups to run",
    )

    @staticmethod
    def source_suite() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def source_job_data() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        dry_run = kwargs.get("dry_run", False)

        # extract job_data
        if kwargs.get("job_data") and not kwargs["job_data"].startswith("nf://"):
            kwargs["job_data"] = json.loads(kwargs["job_data"])

        if kwargs.get("groups") and isinstance(kwargs["groups"], str):
            kwargs["groups"] = [kwargs["groups"]]

        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        if table and not (verbose_result or dry_run):
            kwargs["add_details"] = True
            kwargs["to_dict"] = False

        result = run_future_job(
            "nornir",
            "test",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        # form table results
        if verbose_result or dry_run:
            ret = (
                result,
                Outputters.outputter_nested,
            )
        elif table:
            ret = tabulate_worker_results(
                result=result,
                table=table,
                headers=headers,
                headers_exclude=headers_exclude,
                sortby=sortby,
                reverse=reverse,
            )
        else:
            ret = result

        return ret

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-test]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
