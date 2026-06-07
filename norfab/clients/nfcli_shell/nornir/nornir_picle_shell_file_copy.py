from nornir_salt.plugins.functions import TabulateFormatter
from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import (
    FileCopyInput,
)
from norfab.workers.nornir_worker.nornir_models import (
    NrFileCopyPluginNetmiko as TaskNrFileCopyPluginNetmiko,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
)


class NrFileCopyPluginNetmiko(TaskNrFileCopyPluginNetmiko):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "netmiko"
        return NornirFileCopyShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrFileCopyPlugins(BaseModel):
    netmiko: NrFileCopyPluginNetmiko = Field(
        None, description="Use Netmiko plugin to copy files"
    )


class NornirFileCopyShell(
    FileCopyInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    source_file: StrictStr = Field(
        ..., description="Source file to copy", alias="source-file"
    )
    plugin: NrFileCopyPlugins = Field(None, description="Connection plugin parameters")

    @staticmethod
    def source_source_file() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

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
            "file_copy",
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
            table_data = []
            for w_name, w_res in result.items():
                for item in w_res:
                    item["worker"] = w_name
                    table_data.append(item)
            ret = TabulateFormatter(
                table_data,
                tabulate=table,
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
        prompt = "nf[nornir-file-copy]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
