import json

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    Field,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import TaskInput

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
    tabulate_worker_results,
)


class NornirTaskShell(
    TaskInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    plugin: StrictStr = Field(
        ...,
        description="Nornir task.plugin.name to import or nf://path/to/plugin/file.py",
    )
    arguments: StrictStr = Field(
        None,
        description="Plugin arguments JSON formatted string",
    )

    @staticmethod
    def source_plugin(choice: str = None) -> list:
        return ClientRunJobArgs.walk_norfab_files(choice)

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        # handle task argument
        arguments = json.loads(kwargs.pop("arguments", "{}"))
        if arguments and isinstance(arguments, dict):
            kwargs.update(arguments)

        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        if table:
            kwargs["add_details"] = True
            kwargs["to_dict"] = False

        result = run_future_job(
            "nornir",
            "task",
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
        if table:
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
        prompt = "nf[nornir-task]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
