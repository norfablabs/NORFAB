"""
Common Pydantic Models for PICLE Client Shells
"""

import logging
import time
from datetime import datetime
import threading
import functools
import json
import queue
from uuid import uuid4  # random uuid
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictStr,
    Field,
)
from enum import Enum
from typing import Union, Optional, List
from rich.console import Console

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------------------------------------------


def listen_events_thread(uuid, stop, NFCLIENT):
    """Helper function to pretty print events to command line"""
    richconsole = Console()
    start_time = time.time()
    time_fmt = "%d-%b-%Y %H:%M:%S.%f"
    richconsole.print(
        "-" * 45 + " Job Events " + "-" * 47 + "\n"
        f"{datetime.now().strftime(time_fmt)[:-3]} {uuid} job started"
    )
    while not (stop.is_set() or NFCLIENT.exit_event.is_set()):
        try:
            event = NFCLIENT.event_queue.get(block=True, timeout=0.1)
            NFCLIENT.event_queue.task_done()
        except queue.Empty:
            continue
        (
            empty,
            header,
            command,
            service,
            job_uuid,
            status,
            data,
        ) = event
        if job_uuid != uuid.encode("utf-8"):
            NFCLIENT.event_queue.put(event)
            continue

        # extract event parameters
        data = json.loads(data)
        service = data["service"]
        worker = data["worker"]
        task = data["task"]
        timestamp = data["timestamp"]
        message = data["message"]
        # color severity
        severity = data["severity"]
        severity = severity.replace("DEBUG", "[cyan]DEBUG[/cyan]")
        severity = severity.replace("INFO", "[green]INFO[/green]")
        severity = severity.replace("WARNING", "[yellow]WARNING[/yellow]")
        severity = severity.replace("CRITICAL", "[red]CRITICAL[/red]")
        # color status
        status = data["status"]
        status = status.replace("started", "[cyan]started[/cyan]")
        status = status.replace("completed", "[green]completed[/green]")
        status = status.replace("failed", "[red]failed[/red]")
        resource = data["resource"]
        if isinstance(resource, list):
            resource = ", ".join(resource)
        # log event message
        richconsole.print(
            f"{timestamp} {severity} {worker} {status} {service}.{task} {resource} - {message}"
        )

    elapsed = round(time.time() - start_time, 3)
    richconsole.print(
        f"{datetime.now().strftime(time_fmt)[:-3]} {uuid} job completed in {elapsed} seconds\n\n"
        + "-" * 45
        + " Job Results "
        + "-" * 44
        + "\n"
    )


def listen_events(fun):
    """Decorator to listen for events and print them to console"""

    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        events_thread_stop = threading.Event()
        uuid = uuid4().hex
        progress = kwargs.get("progress", True)

        # start events thread to handle job events printing
        if progress:
            events_thread = threading.Thread(
                target=listen_events_thread,
                name="NornirCliShell_events_listen_thread",
                args=(
                    uuid,
                    events_thread_stop,
                    NFCLIENT,
                ),
            )
            events_thread.start()

        # run decorated function
        try:
            res = fun(uuid, *args, **kwargs)
        finally:
            # stop events thread
            if NFCLIENT and progress:
                events_thread_stop.set()
                events_thread.join()

        return res

    return wrapper


def log_error_or_result(
    data: dict, verbose_result: bool = False, verbose_on_fail: bool = False
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
        else:
            ret[w_name] = w_res["result"]

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
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
