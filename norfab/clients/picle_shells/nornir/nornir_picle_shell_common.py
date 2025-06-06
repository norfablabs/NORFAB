import json

from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    model_validator,
    Field,
)
from ..common import log_error_or_result
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from rich.console import Console

RICHCONSOLE = Console()

# ---------------------------------------------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_nornir_results(data: Union[list, dict]):
    """
    Pretty print Nornir task results.

    Order of output is deterministic - same tasks will be printed in same
    order no matter how many times they are run thanks to sing ``sorted``
    """
    indent = "    "
    ret = []
    # print text data e.g. tabulate table
    if not isinstance(data, dict):
        data = data.replace("FAIL", "[bold red]FAIL[/bold red]")
        data = data.replace("PASS", "[bold green]PASS[/bold green]")
        data = data.replace("ERROR", "[bold yellow]ERROR[/bold yellow]")
        # RICHCONSOLE.print(data)
        return data

    # iterate over Nornir results dictionary, unpack and pretty print it
    for worker in sorted(data.keys()):
        hosts_results = data[worker]
        if isinstance(hosts_results, dict):
            for host in sorted(hosts_results.keys()):
                tasks = hosts_results[host]
                ret.append(f"[bold green]{host}[/bold green]:")
                for task in sorted(tasks.keys()):
                    result = tasks[task]
                    ret.append(f"{1*indent}[bold blue]{task}[/bold blue]:")
                    if isinstance(result, str):
                        for line in result.splitlines():
                            ret.append(f"{2*indent}{line}")
                    elif isinstance(result, dict):
                        for k, v in result.items():
                            if isinstance(v, (dict, list)):
                                v = json.dumps(v, indent=indent)
                            lines = str(v).splitlines()
                            if len(lines) == 0:
                                ret.append(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: ''"
                                )
                            elif len(lines) == 1:
                                ret.append(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: {lines[0]}"
                                )
                            else:
                                ret.append(f"{2*indent}[bold yellow]{k}[/bold yellow]")
                                for line in lines:
                                    ret.append(f"{3*indent}{line}")
                    elif isinstance(result, list):
                        for i in result:
                            if isinstance(i, str):
                                if i.strip().splitlines():  # multiline
                                    for line in i.strip().splitlines():
                                        ret.append(
                                            f"{2*indent}[bold yellow]{line}[/bold yellow]"
                                        )
                                else:
                                    ret.append(
                                        f"{2*indent}[bold yellow]{i.strip()}[/bold yellow]"
                                    )
                            elif isinstance(
                                i,
                                (
                                    dict,
                                    list,
                                ),
                            ):
                                for line in json.dumps(
                                    result, indent=indent
                                ).splitlines():
                                    ret.append(
                                        f"{2*indent}[bold yellow]{line}[/bold yellow]"
                                    )
                                break  # we printed full result, stop
                            else:
                                ret.append(
                                    f"{2*indent}[bold yellow]{result}[/bold yellow]"
                                )
                    else:
                        ret.append(f"{2*indent}[bold yellow]{result}[/bold yellow]")
        # handle to_dict is False
        elif isinstance(hosts_results, list):
            ret.append(hosts_results)

    return "\n".join(ret)


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class NornirCommonArgs(BaseModel):
    add_details: Optional[StrictBool] = Field(
        False,
        description="Add task details to results",
        json_schema_extra={"presence": True},
        alias="add-details",
    )
    run_num_workers: Optional[StrictInt] = Field(
        None,
        description="RetryRunner number of threads for tasks execution",
        alias="num-workers",
    )
    run_num_connectors: Optional[StrictInt] = Field(
        None,
        description="RetryRunner number of threads for device connections",
        alias="num-connectors",
    )
    run_connect_retry: Optional[StrictInt] = Field(
        None,
        description="RetryRunner number of connection attempts",
        alias="connect-retry",
    )
    run_task_retry: Optional[StrictInt] = Field(
        None,
        description="RetryRunner number of attempts to run task",
        alias="task-retry",
    )
    run_reconnect_on_fail: Optional[StrictBool] = Field(
        None,
        description="RetryRunner perform reconnect to host on task failure",
        json_schema_extra={"presence": True},
        alias="reconnect-on-fail",
    )
    run_connect_check: Optional[StrictBool] = Field(
        None,
        description="RetryRunner test TCP connection before opening actual connection",
        json_schema_extra={"presence": True},
        alias="connect-check",
    )
    run_connect_timeout: Optional[StrictInt] = Field(
        None,
        description="RetryRunner timeout in seconds to wait for test TCP connection to establish",
        alias="connect-timeout",
    )
    run_creds_retry: Optional[List] = Field(
        None,
        description="RetryRunner list of connection credentials and parameters to retry",
        alias="creds-retry",
    )
    tf: Optional[StrictStr] = Field(
        None,
        description="File group name to save task results to on worker file system",
    )
    tf_skip_failed: Optional[StrictBool] = Field(
        None,
        description="Save results to file for failed tasks",
        json_schema_extra={"presence": True},
        alias="tf-skip-failed",
    )
    diff: Optional[StrictStr] = Field(
        None,
        description="File group name to run the diff for",
    )
    diff_last: Optional[Union[StrictStr, StrictInt]] = Field(
        None,
        description="File version number to diff, default is 1 (last)",
        alias="diff-last",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )


class EnumTableTypes(str, Enum):
    table_brief = "brief"
    table_terse = "terse"
    table_extend = "extend"


class TabulateTableModel(BaseModel):
    table: Union[EnumTableTypes, Dict, StrictBool] = Field(
        None,
        description="Table format (brief, terse, extend) or parameters or True",
        presence="brief",
    )
    headers: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Table headers"
    )
    headers_exclude: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Table headers to exclude", alias="headers-exclude"
    )
    sortby: StrictStr = Field(None, description="Table header column to sort by")
    reverse: StrictBool = Field(
        None, description="Table reverse the sort by order", presence=True
    )

    def source_table():
        return ["brief", "terse", "extend", "True"]


class NorniHostsFilters(BaseModel):
    """
    Model to list common filter arguments for FFun function
    """

    FO: Optional[Union[Dict, List[Dict]]] = Field(
        None, title="Filter Object", description="Filter hosts using Filter Object"
    )
    FB: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using Glob Patterns",
    )
    FH: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter Hostname", description="Filter hosts by hostname"
    )
    FC: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts containment of pattern in name",
    )
    FR: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using Regular Expressions",
    )
    FG: Optional[StrictStr] = Field(
        None, title="Filter Group", description="Filter hosts by group"
    )
    FP: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP Prefix",
    )
    FL: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter List", description="Filter hosts by names list"
    )
    FM: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter platforM", description="Filter hosts by platform"
    )
    FX: Optional[Union[List[str], str]] = Field(
        None, title="Filter eXclude", description="Filter hosts excluding them by name"
    )
    FN: Optional[StrictBool] = Field(
        None,
        title="Filter Negate",
        description="Negate the match",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def source_hosts():
        ret = set()
        result = NFCLIENT.run_job("nornir", "get_nornir_hosts")
        result = log_error_or_result(result)
        # result is a dict keyed by worker name with lists of hosts values
        for worker, result in result.items():
            for host in result:
                ret.add(host)
        return list(ret)

    @staticmethod
    def source_FL():
        return NorniHostsFilters.source_hosts()

    @staticmethod
    def get_nornir_hosts(**kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")

        result = NFCLIENT.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
        )
        result = log_error_or_result(result, verbose_result=verbose_result)

        return result
