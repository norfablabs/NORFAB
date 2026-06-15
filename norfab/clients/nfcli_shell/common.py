"""
Common Pydantic Models for PICLE Client Shells
"""

import builtins
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)
from rich.console import Console
from rich.prompt import Confirm, Prompt

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_event(event: dict, richconsole: Console = None) -> None:
    """Print one job event to terminal."""
    richconsole = richconsole or Console()
    service = event.get("service", "")
    worker = event.get("worker", "")
    task = event.get("task", "")
    timestamp = event.get("timestamp", "")
    message = event.get("message", "")
    severity = event.get("severity", "INFO")
    severity = severity.replace("DEBUG", "[cyan]DEBUG[/cyan]")
    severity = severity.replace("INFO", "[green]INFO[/green]")
    severity = severity.replace("WARNING", "[yellow]WARNING[/yellow]")
    severity = severity.replace("CRITICAL", "[red]CRITICAL[/red]")
    severity = severity.replace("ERROR", "[red]ERROR[/red]")
    status = event.get("status", "")
    status = status.replace("started", "[cyan]started[/cyan]")
    status = status.replace("running", "[cyan]running[/cyan]")
    status = status.replace(
        "waiting_client_input", "[yellow]waiting_client_input[/yellow]"
    )
    status = status.replace("received", "[green]received[/green]")
    status = status.replace("completed", "[green]completed[/green]")
    status = status.replace("failed", "[red]failed[/red]")
    status = status.replace("timeout", "[red]timeout[/red]")
    status = status.replace("cancelled", "[red]cancelled[/red]")
    resource = event.get("resource", "")
    if isinstance(resource, list):
        resource = ", ".join(resource)
    richconsole.print(
        f"{timestamp} {severity} {worker} {status} {service}.{task} {resource} - {message}"
    )


def collect_input_request(
    future: Any, event: dict, richconsole: Console = None, outputter: callable = None
) -> None:
    """Prompt user for one input request event and send the response."""
    if event.get("event_type") != "input_request":
        return

    input_request = (event.get("extras") or {}).get("input_request")
    if not input_request:
        return

    richconsole = richconsole or Console()
    question = input_request.get("question", "Worker asks for input")
    default = input_request.get("default")
    choices = input_request.get("choices")
    preview = (input_request.get("metadata") or {}).get("preview")

    if preview is not None:
        richconsole.print("\n[bold]Dry-run preview:[/bold]")
        if outputter:
            richconsole.print(outputter(preview))
        else:
            richconsole.print(preview)
        richconsole.print()

    if isinstance(default, bool):
        response = Confirm.ask(question, default=default, console=richconsole)
    else:
        prompt_kwargs = {}
        if default is not None:
            prompt_kwargs["default"] = str(default)
        if choices:
            prompt_kwargs["choices"] = [str(choice) for choice in choices]
        response = Prompt.ask(question, console=richconsole, **prompt_kwargs)

    future.send_response(
        input_id=input_request["id"],
        value=response,
        worker=event.get("worker"),
    )


def run_future_job(
    service: str,
    task: str,
    uuid: str = None,
    args: list = None,
    kwargs: dict = None,
    workers: Union[str, list] = "all",
    timeout: int = 600,
    markdown: bool = False,
    nowait: bool = False,
    outputter: callable = None,
) -> Any:
    """Submit a job, handle events and input requests, then return job result."""
    NFCLIENT = builtins.NFCLIENT
    future = NFCLIENT.submit_job(
        service=service,
        task=task,
        uuid=uuid,
        args=args,
        kwargs=kwargs,
        workers=workers,
        timeout=timeout,
    )

    if nowait is True:
        return {"uuid": future.uuid, "service": service}

    richconsole = Console()
    start_time = time.time()
    time_format = "%d-%b-%Y %H:%M:%S.%f"

    richconsole.print(
        "-" * 45 + " Job Events " + "-" * 47 + "\n\n"
        f"{datetime.now().strftime(time_format)[:-3]} [green]INFO[/green] {future.uuid} job started"
    )

    for event in future.events():
        collect_input_request(future, event, richconsole, outputter)
        print_event(event, richconsole)

    elapsed = round(time.time() - start_time, 3)
    richconsole.print(
        f"{datetime.now().strftime(time_format)[:-3]} [green]INFO[/green] {future.uuid} job completed in {elapsed} seconds\n\n"
        + "-" * 45
        + " Job Results "
        + "-" * 44
        + "\n"
    )

    return future.result(markdown=markdown)


def log_error_or_result(
    data: dict, verbose_result: bool = False, verbose_on_fail: bool = True
) -> dict:
    """
    Logs errors or messages from the provided data dictionary and returns a dictionary of results based on verbosity settings.

    Args:
        data (dict): A dictionary where each key is a worker name and each
            value is a dictionary containing job result
        verbose_result (bool, optional): If True, includes the full result
            dictionary for each worker in the return value
        verbose_on_fail (bool, optional): If True, includes the full result
            dictionary for failed tasks

    Returns:
        dict: A dictionary containing either the full result or just the "result"
            field for each worker, depending on verbosity settings.

    Logs:
        - Errors if present in the worker's result.
        - Informational messages if present and no errors exist.
    """
    ret = {}

    if data is None:
        log.error("Result data is empty.")
        return
    if not isinstance(data, dict):
        log.error(f"Data is not a dictionary but '{type(data)}'")
        return data

    for w_name, w_res in data.items():
        # decide what to log
        if w_res["errors"]:
            errors = "\n".join(w_res["errors"])
            log.error(f"{w_name} '{w_res['task']}' errors:\n{errors}")
        elif w_res["messages"]:
            messages = "\n".join(w_res["messages"])
            log.info(f"{w_name} '{w_res['task']}' messages:\n{messages}")

        # decide what results to return
        if verbose_result:
            ret[w_name] = w_res
        elif verbose_on_fail and w_res["failed"] is True:
            ret[w_name] = w_res
        elif w_res["result"]:
            ret[w_name] = w_res["result"]
        else:  # skip workers with no results
            pass

    return ret


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class BoolEnum(Enum):
    TRUE = True
    FALSE = False


class ClientRunJobArgs(BaseModel):
    timeout: Optional[StrictInt] = Field(None, description="Job timeout")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter workers to target"
    )
    verbose_result: StrictBool = Field(
        False,
        description="Control output details",
        json_schema_extra={"presence": True},
        alias="verbose-result",
    )
    nowait: Optional[StrictBool] = Field(
        False,
        description="Do not wait for job to complete",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def walk_norfab_files():
        response = run_future_job("filesharing", "walk", kwargs={"url": "nf://"})
        wname, wres = next(iter(response.items()))
        return wres["result"]
