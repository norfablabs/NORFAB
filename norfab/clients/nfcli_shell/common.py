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
    status = event.get("status", "")
    resource = event.get("resource", "")
    timestamp = str(timestamp)
    timestamp_parts = timestamp.split()
    if len(timestamp_parts) >= 2 and "-" in timestamp_parts[0]:
        timestamp = timestamp_parts[1]
    elif len(timestamp_parts) >= 5:
        timestamp = timestamp_parts[3]
    if "." in timestamp:
        seconds, milliseconds = timestamp.split(".", 1)
        timestamp = f"{seconds}.{milliseconds[:3]}"
    message = " ".join(str(message).split())
    severity = f"{severity:<5}"
    severity = severity.replace("DEBUG", "[cyan]DEBUG[/cyan]")
    severity = severity.replace("INFO", "[green]INFO[/green]")
    severity = severity.replace("WARNING", "[yellow]WARNING[/yellow]")
    severity = severity.replace("CRITICAL", "[red]CRITICAL[/red]")
    severity = severity.replace("ERROR", "[red]ERROR[/red]")
    status = f"{status:<10}"
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
    if isinstance(resource, list):
        resource = ", ".join(resource)
    resource = f" {resource}" if resource else ""
    richconsole.print(
        f"{timestamp:<12} {severity} {worker:<16} {status} "
        f"{service}.{task}{resource} {message}",
        no_wrap=True,
        overflow="ellipsis",
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
        richconsole.print(
            "\n─────────────────────────────────── [bold]Dry-run preview[/bold] ─────────────────────────────────────"
        )
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

    richconsole.print(
        "\n─────────────────────────────────────── [bold]Continue[/bold] ────────────────────────────────────────\n"
    )

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
    started_at = datetime.now().strftime(time_format)[:-3]
    workers_text = workers if isinstance(workers, str) else ", ".join(workers)
    stats = {"events": 0, "warnings": 0, "errors": 0, "workers": set()}

    richconsole.print(
        "────────────────────────────────────────── [bold]Job[/bold] ──────────────────────────────────────────\n"
        f"UUID     {future.uuid}\n"
        f"Task     {service}.{task}\n"
        f"Workers  {workers_text}\n"
        f"Timeout  {timeout}s\n"
        f"Started  {started_at}\n"
        "\n───────────────────────────────────────── [bold]Events[/bold] ────────────────────────────────────────"
    )

    for event in future.events():
        collect_input_request(future, event, richconsole, outputter)
        print_event(event, richconsole)
        stats["events"] += 1
        severity = event.get("severity", "INFO")
        if isinstance(severity, Enum):
            severity = severity.value
        severity = str(severity).strip().upper()
        if severity == "WARNING":
            stats["warnings"] += 1
        elif severity in {"ERROR", "CRITICAL"}:
            stats["errors"] += 1
        worker = event.get("worker")
        worker = "" if worker is None else str(worker).strip()
        if worker:
            stats["workers"].add(worker)

    elapsed = round(time.time() - start_time, 3)
    result = future.result(markdown=markdown)
    worker_count = len(result) if isinstance(result, dict) else len(stats["workers"])
    richconsole.print(
        f"\nCompleted in {elapsed:.2f}s | workers: {worker_count} | "
        f"events: {stats['events']} | warnings: {stats['warnings']} | "
        f"errors: {stats['errors']}\n"
        "\n────────────────────────────────────── [bold]Job Results[/bold] ─────────────────────────────────────\n"
    )

    return result


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
    def walk_norfab_files(choice: str = None):
        NFCLIENT = builtins.NFCLIENT
        response = NFCLIENT.run_job("filesharing", "walk", kwargs={"url": "nf://"})
        wname, wres = next(iter(response.items()))
        files = wres["result"]
        choice = choice or "nf://"
        parent = choice if choice.endswith("/") else choice.rsplit("/", 1)[0] + "/"
        ret = []
        seen = set()

        for file in files:
            if not file.startswith(choice):
                continue

            relative_path = file.removeprefix(parent)
            if "/" in relative_path:
                top_level = f"{parent}{relative_path.split('/', 1)[0]}/"
            else:
                top_level = file

            if top_level not in seen:
                ret.append(top_level.strip())
                seen.add(top_level.strip())

        return ret
