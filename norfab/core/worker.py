import logging
import time
import zmq
import json
import traceback
import threading
import queue
import os
import pickle
import psutil
import signal
import concurrent.futures
import copy
import inspect
import functools
import sqlite3
import zlib
from contextlib import contextmanager

from . import NFP
from .client import NFPClient
from .keepalives import KeepAliver
from .security import generate_certificates
from .inventory import logging_config_producer
from typing import Any, Callable, Dict, List, Optional, Union
from norfab.models import NorFabEvent, Result
from norfab import models
from norfab.core.inventory import NorFabInventory
from jinja2.nodes import Include
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, create_model

try:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
except Exception as e:
    pass

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NORFAB Worker Job Object
# --------------------------------------------------------------------------------------------


class Job:
    def __init__(
        self,
        worker: object = None,
        juuid: str = None,
        client_address: str = None,
        timeout: int = None,
        args: list = None,
        kwargs: dict = None,
        task: str = None,
    ):
        self.worker = worker
        self.juuid = juuid
        self.client_address = client_address
        self.timeout = timeout
        self.args = args or []
        self.kwargs = kwargs or {}
        self.task = task

    def event(self, message, **kwargs):
        kwargs.setdefault("task", self.task)
        if self.kwargs.get("progress", False) and self.juuid and self.worker:
            self.worker.event(
                message=message,
                juuid=self.juuid,
                client_address=self.client_address,
                **kwargs,
            )


# --------------------------------------------------------------------------------------------
# NORFAB Worker Task Object
# --------------------------------------------------------------------------------------------

# Dictionary to store all tasks references
NORFAB_WORKER_TASKS = {}


class Task:
    """
    Validate is a class-based decorator that accept arguments, designed to validate the
    input arguments of a task function using a specified Pydantic model. It ensures that
    the arguments passed to the decorated function conform to the schema defined in the model.

    Attributes:
        model (BaseModel): A Pydantic model used to validate the function arguments.
        name (str): The name of the task, which is used to register the task for calling, by default
            set equal to the name of decorated function.
        result_model (BaseModel): A Pydantic model used to validate the function's return value.
        fastapi (dict): Dictionary with parameters for FastAPI `app.add_api_route` method
        mcp (dict): Dictionary with parameters for MCP `mcp.types.Tool` class

    Methods:
        __call__(function: Callable) -> Callable:
            Wraps the target function and validates its arguments before execution.

        merge_args_to_kwargs(args: List, kwargs: Dict) -> Dict:
            Merges positional arguments (`args`) and keyword arguments (`kwargs`) into a single
            dictionary, mapping positional arguments to their corresponding parameter names
            based on the function's signature.

        validate_input(args: List, kwargs: Dict) -> None:
            Validates merged arguments against Pydantic model. If validation fails,
            an exception is raised.

    Usage:
        @Task()(input=YourPydanticModel)
        def your_function(arg1, arg2, ...):
            # Function implementation
            pass

    Notes:
        - The decorator uses `inspect.getfullargspec` to analyze the function's signature
          and properly map arguments for validation.
    """

    def __init__(
        self,
        input: Optional[BaseModel] = None,
        output: Optional[BaseModel] = None,
        description: Optional[str] = None,
        fastapi: Optional[dict] = None,
        mcp: Optional[dict] = None,
    ) -> None:
        self.input = input
        self.output = output or Result
        self.description = description
        if fastapi is False:
            self.fastapi = False
        else:
            self.fastapi = fastapi or {}
        if mcp is False:
            self.mcp = False
        else:
            self.mcp = mcp or {}

    def __call__(self, function: Callable) -> Callable:
        """
        Decorator to register a function as a worker task with input/output
        validation and optional argument filtering.

        This method wraps the provided function, validates its input arguments
        and output, and registers it as a task. It also removes 'job' and
        'progress' keyword arguments if the wrapped function does not accept them.

        Side Effects:

            - Sets self.function, self.description, and self.name based on the provided function.
            - Initializes input model if not already set.
            - Updates the global NORFAB_WORKER_TASKS with the task schema.
        """
        self.function = function
        self.description = self.description or function.__doc__
        self.name = function.__name__

        if self.input is None:
            self.make_input_model()

        @functools.wraps(self.function)
        def wrapper(*args, **kwargs):
            # remove `job` argument if function does not expect it
            if self.is_need_argument(function, "job") is False:
                _ = kwargs.pop("job", None)

            # remove `progress` argument if function does not expect it
            if self.is_need_argument(function, "progress") is False:
                _ = kwargs.pop("progress", None)

            # validate input arguments
            self.validate_input(args, kwargs)

            ret = self.function(*args, **kwargs)

            # validate result
            self.validate_output(ret)

            return ret

        NORFAB_WORKER_TASKS.update(self.make_task_schema(wrapper))

        log.debug(
            f"{function.__module__} PID {os.getpid()} registered task '{function.__name__}'"
        )

        return wrapper

    def make_input_model(self):
        """
        Dynamically creates a Pydantic input model for the worker's function by inspecting its signature.

        This method uses `inspect.getfullargspec` to extract the function's argument names, default values,
        keyword-only arguments, and type annotations. It then constructs a dictionary of field specifications,
        giving preference to type annotations where available, and excluding special parameters such as 'self',
        'return', 'job', and any *args or **kwargs. The resulting specification is used to create a Pydantic
        model, which is assigned to `self.input`.

        The generated model used for input validation.
        """
        (
            fun_args,  # list of the positional parameter names
            fun_varargs,  # name of the * parameter or None
            fun_varkw,  # name of the ** parameter or None
            fun_defaults,  # tuple of default argument values of the last n positional parameters
            fun_kwonlyargs,  # list of keyword-only parameter names
            fun_kwonlydefaults,  # dictionary mapping kwonlyargs parameter names to default values
            fun_annotations,  # dictionary mapping parameter names to annotations
        ) = inspect.getfullargspec(self.function)

        # form a dictionary keyed by args with their default values
        args_with_defaults = dict(
            zip(reversed(fun_args or []), reversed(fun_defaults or []))
        )

        # form a dictionary keyed by args that has no defaults with values set to
        # (Any, None) tuple if make_optional is True else set to (Any, ...)
        args_no_defaults = {
            k: (Any, ...) for k in fun_args if k not in args_with_defaults
        }

        # form dictionary keyed by args with annotations and tuple values
        args_with_hints = {
            k: (v, args_with_defaults.get(k, ...)) for k, v in fun_annotations.items()
        }

        # form merged kwargs giving preference to type hint annotations
        merged_kwargs = {**args_no_defaults, **args_with_defaults, **args_with_hints}

        # form final dictionary of fields
        fields_spec = {
            k: v
            for k, v in merged_kwargs.items()
            if k not in ["self", "return", "job", fun_varargs, fun_varkw]
        }

        log.debug(
            f"NorFab worker {self.name} task creating Pydantic input "
            f"model using fields spec: {fields_spec}"
        )

        # create Pydantic model
        self.input = create_model(self.name, **fields_spec)

    def make_task_schema(self, wrapper) -> dict:
        """
        Generates a task schema dictionary for the current worker.

        Args:
            wrapper (Callable): The function wrapper to be associated with the task.

        Returns:
            dict: A dictionary containing the task's metadata, including:
                - function: The provided wrapper function.
                - module: The module name where the original function is defined.
                - schema: A dictionary with the following keys:
                    - name (str): The name of the task.
                    - description (str): The description of the task.
                    - inputSchema (dict): The JSON schema for the input model.
                    - outputSchema (dict): The JSON schema for the output model.
                    - fastapi: FastAPI-specific metadata.
                    - mcp: Model Context protocol metadata
        """
        input_json_schema = self.input.model_json_schema()
        _ = input_json_schema.pop("title")
        output_json_schema = self.output.model_json_schema()

        return {
            self.name: {
                "function": wrapper,
                "module": self.function.__module__,
                "schema": {
                    "name": str(self.name),
                    "description": self.description,
                    "inputSchema": input_json_schema,
                    "outputSchema": output_json_schema,
                    "fastapi": self.fastapi,
                    "mcp": self.mcp,
                },
            }
        }

    def is_need_argument(self, function: callable, argument: str) -> bool:
        """
        Determines whether a given argument name is required by the function.
        """
        fun_args, *_ = inspect.getfullargspec(function)
        return argument in fun_args

    def merge_args_to_kwargs(self, args: List, kwargs: Dict) -> Dict:
        """
        Merges positional arguments (`args`) and keyword arguments (`kwargs`)
        into a single dictionary.

        This function uses the argument specification of the decorated function
        to ensure that all arguments are properly combined into a dictionary.
        This is particularly useful for scenarios where **kwargs need to be passed
        to another function or model (e.g., for validation purposes).

        Arguments:
            args (list): A list of positional arguments passed to the decorated function.
            kwargs (dict): A dictionary of keyword arguments passed to the decorated function.

        Return:
            dict: A dictionary containing the merged arguments, where positional arguments
                  are mapped to their corresponding parameter names.
        """
        merged_kwargs = {}

        (
            fun_args,  # list of the positional parameter names
            fun_varargs,  # name of the * parameter or None
            *_,  # ignore the rest
        ) = inspect.getfullargspec(self.function)

        # "def foo(a, b):" - combine "foo(1, 2)" args with "a, b" fun_args
        args_to_kwargs = dict(zip(fun_args, args))

        # "def foo(a, *b):" - combine "foo(1, 2, 3)" 2|3 args with "*b" fun_varargs
        if fun_varargs:
            args_to_kwargs[fun_varargs] = args[len(fun_args) :]

        merged_kwargs = {**kwargs, **args_to_kwargs}

        # remove reference to self if decorating class method
        _ = merged_kwargs.pop("self", None)

        return merged_kwargs

    def validate_input(self, args: List, kwargs: Dict) -> None:
        """Function to validate provided arguments against model"""
        merged_kwargs = self.merge_args_to_kwargs(args, kwargs)
        log.debug(f"{self.name} validating input arguments: {merged_kwargs}")
        # if below step succeeds, kwargs passed model validation
        _ = self.input(**merged_kwargs)
        log.debug(
            f"Validated input kwargs: {merged_kwargs} for function {self.function} using model {self.input}"
        )

    def validate_output(self, ret: Result) -> None:
        if isinstance(ret, Result) and self.output:
            _ = self.output(**ret.model_dump())
        log.debug(f"Validated {self.name} task result.")


# --------------------------------------------------------------------------------------------
# NORFAB Worker Job Database
# --------------------------------------------------------------------------------------------


class JobDatabase:
    """
    Thread-safe SQLite database manager for worker jobs.

    Handles all job persistence operations with proper thread safety through
    connection-level locking and WAL mode for concurrent reads.

    Attributes:
        db_path (str): Path to the SQLite database file.
        _local (threading.local): Thread-local storage for database connections.
        _lock (threading.Lock): Lock for write operations to ensure thread safety.
    """

    def __init__(self, db_path: str, jobs_compress: bool = True):
        """
        Initialize the job database.

        Args:
            db_path (str): Path to the SQLite database file.
            jobs_compress (bool): If True, compress request_data and result_data fields. Defaults to True.
        """
        self.db_path = db_path
        self.jobs_compress = jobs_compress
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local database connection.

        Returns:
            sqlite3.Connection: Thread-local database connection.
        """
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")

            # Verify JSON1 extension is available
            try:
                self._local.conn.execute("SELECT json('{}')").fetchone()
                log.debug(f"SQLite JSON1 extension is available")
            except sqlite3.OperationalError:
                log.warning(
                    f"SQLite JSON1 extension not available - JSON queries will be limited"
                )
        return self._local.conn

    @contextmanager
    def _transaction(self, write: bool = False):
        """
        Context manager for database transactions with optional write locking.

        Args:
            write (bool): If True, acquire write lock for the transaction.

        Yields:
            sqlite3.Connection: Database connection.
        """
        conn = self._get_connection()
        if write:
            with self._lock:
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        else:
            try:
                yield conn
            except Exception:
                raise

    def _compress_data(self, data: dict) -> str:
        """
        Compress dictionary data to base64-encoded string if compression is enabled.

        Args:
            data (dict): Dictionary to compress.

        Returns:
            str: Compressed and base64-encoded string if compression enabled, otherwise JSON string.
        """
        if self.jobs_compress:
            import base64
            json_str = json.dumps(data)
            compressed = zlib.compress(json_str.encode('utf-8'))
            return base64.b64encode(compressed).decode('utf-8')
        else:
            return json.dumps(data)

    def _decompress_data(self, data_str: str) -> dict:
        """
        Decompress base64-encoded compressed string back to dictionary.
        Automatically detects if data is compressed or plain JSON.

        Args:
            data_str (str): Compressed base64 string or plain JSON string.

        Returns:
            dict: Decompressed dictionary.
        """
        if not data_str:
            return {}

        # Try to detect if data is compressed (base64) or plain JSON
        try:
            # First, try to parse as JSON (uncompressed)
            return json.loads(data_str)
        except json.JSONDecodeError:
            # If JSON parsing fails, assume it's compressed
            import base64
            try:
                compressed = base64.b64decode(data_str.encode('utf-8'))
                decompressed = zlib.decompress(compressed)
                return json.loads(decompressed.decode('utf-8'))
            except Exception as e:
                log.error(f"Failed to decompress data: {e}")
                return {}

    def _initialize_database(self):
        """Initialize the database schema."""
        with self._transaction(write=True) as conn:
            # Jobs table - using JSON TEXT fields instead of BLOB
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    uuid TEXT PRIMARY KEY,
                    client_address TEXT NOT NULL,
                    task TEXT NOT NULL,
                    args TEXT,
                    kwargs TEXT,
                    timeout INTEGER,
                    status TEXT DEFAULT 'PENDING',
                    received_timestamp TEXT NOT NULL,
                    started_timestamp TEXT,
                    completed_timestamp TEXT,
                    request_data TEXT,
                    result_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Events table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_uuid TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT DEFAULT 'INFO',
                    task TEXT,
                    event_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_uuid) REFERENCES jobs(uuid) ON DELETE CASCADE
                )
            """
            )

            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_task ON jobs(task)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client_address)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_received ON jobs(received_timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_job_uuid ON events(job_uuid)"
            )

    def add_job(
        self,
        uuid: str,
        client_address: str,
        task: str,
        args: list,
        kwargs: dict,
        timeout: int,
        request_data: dict,
        timestamp: str,
    ) -> None:
        """
        Add a new job to the database.

        Args:
            uuid (str): Job UUID.
            client_address (str): Client address.
            task (str): Task name.
            args (list): Task arguments.
            kwargs (dict): Task keyword arguments.
            timeout (int): Job timeout.
            request_data (dict): Full request data as dictionary.
            timestamp (str): Received timestamp.
        """
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO jobs (uuid, client_address, task, args, kwargs, timeout,
                                 status, received_timestamp, request_data)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
                (
                    uuid,
                    client_address,
                    task,
                    json.dumps(args),
                    json.dumps(kwargs),
                    timeout,
                    timestamp,
                    self._compress_data(request_data),
                ),
            )

    def get_next_pending_job(self) -> tuple:
        """
        Get the next pending job and mark it as STARTED.

        Returns:
            tuple: (uuid, received_timestamp) or None if no pending jobs.
        """
        with self._transaction(write=True) as conn:
            # order jobs by their creation timestamp in ascending order - oldest first
            cursor = conn.execute(
                """
                SELECT uuid, received_timestamp FROM jobs
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT 1
            """
            )
            row = cursor.fetchone()
            if row:
                uuid = row["uuid"]
                conn.execute(
                    """
                    UPDATE jobs SET status = 'STARTED', started_timestamp = ?
                    WHERE uuid = ?
                """,
                    (time.ctime(), uuid),
                )
                return uuid, row["received_timestamp"]
            return None

    def complete_job(self, uuid: str, result_data: dict) -> None:
        """
        Mark a job as completed and store its result.

        Args:
            uuid (str): Job UUID.
            result_data (dict): Result data as dictionary.
        """
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'COMPLETED', completed_timestamp = ?, result_data = ?
                WHERE uuid = ?
            """,
                (time.ctime(), self._compress_data(result_data), uuid),
            )

    def fail_job(self, uuid: str, result_data: dict) -> None:
        """
        Mark a job as failed and store its result.

        Args:
            uuid (str): Job UUID.
            result_data (dict): Result data as dictionary.
        """
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'FAILED', completed_timestamp = ?, result_data = ?
                WHERE uuid = ?
            """,
                (time.ctime(), self._compress_data(result_data), uuid),
            )

    def get_job_info(
        self,
        uuid: str,
        include_result: bool = False,
        include_data: bool = False,
        include_events: bool = False,
    ) -> dict:
        """
        Get comprehensive job information including status, execution data, and optionally result data and events.

        Args:
            uuid (str): Job UUID.
            include_result (bool): If True, include result_data in the response. Defaults to False.
            include_data (bool): If True, include parsed job data (task, args, kwargs). Defaults to False.
            include_events (bool): If True, include job events. Defaults to False.

        Returns:
            dict: Job information with the following fields:
                - uuid: Job UUID
                - status: Job status (PENDING, STARTED, COMPLETED, FAILED)
                - received_timestamp: When job was received
                - started_timestamp: When job started execution
                - completed_timestamp: When job completed
                - client_address: Client address
                - task: Task name

            If include_data=True, also includes:
                - job_data: Dictionary with task, args, and kwargs

            If include_result=True, also includes:
                - job_result: Result data dictionary (if available)

            If include_events=True, also includes:
                - job_events: List of event dictionaries

            If none of the include flags are True, also returns:
                - args: Parsed task arguments list
                - kwargs: Parsed task keyword arguments dict
                - timeout: Job timeout
                - request_data: Full request data dictionary

            Returns None if job not found.
        """
        with self._transaction(write=False) as conn:
            # Build SELECT clause based on requested fields
            select_fields = [
                "uuid",
                "status",
                "received_timestamp",
                "started_timestamp",
                "completed_timestamp",
                "client_address",
                "task",
                "args",
                "kwargs",
                "timeout",
                "request_data",
            ]

            if include_result:
                select_fields.append("result_data")

            query = f"""
                SELECT {', '.join(select_fields)}
                FROM jobs WHERE uuid = ?
            """

            cursor = conn.execute(query, (uuid,))
            row = cursor.fetchone()

            if not row:
                return None

            result = dict(row)
            result.setdefault("job_data", None)
            result.setdefault("result_data", None)
            result.setdefault("job_events", [])

            # Determine output format based on flags
            if include_data or include_result or include_events:

                if include_data:
                    result["job_data"] = {
                        "task": row["task"],
                        "args": json.loads(row["args"]) if row["args"] else [],
                        "kwargs": json.loads(row["kwargs"]) if row["kwargs"] else {},
                    }

                if include_result and row["result_data"]:
                    result["result_data"] = self._decompress_data(row["result_data"])

                if include_events:
                    result["job_events"] = self.get_job_events(uuid)

            else:
                # Parse JSON fields
                result["args"] = json.loads(row["args"]) if row["args"] else []
                result["kwargs"] = json.loads(row["kwargs"]) if row["kwargs"] else {}

                # Decompress request_data if present
                if "request_data" in result and result["request_data"]:
                    result["request_data"] = self._decompress_data(result["request_data"])

            return result

    def add_event(
        self, job_uuid: str, message: str, severity: str, task: str, event_data: dict
    ) -> None:
        """
        Add an event for a job.

        Args:
            job_uuid (str): Job UUID.
            message (str): Event message.
            severity (str): Event severity.
            task (str): Task name.
            event_data (dict): Event data dictionary.
        """
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO events (job_uuid, message, severity, task, event_data)
                VALUES (?, ?, ?, ?, ?)
            """,
                (job_uuid, message, severity, task, json.dumps(event_data)),
            )

    def get_job_events(self, uuid: str) -> list:
        """
        Get all events for a job.

        Args:
            uuid (str): Job UUID.

        Returns:
            list: List of event dictionaries.
        """
        with self._transaction(write=False) as conn:
            cursor = conn.execute(
                """
                SELECT message, severity, task, event_data, created_at
                FROM events WHERE job_uuid = ?
                ORDER BY created_at ASC
            """,
                (uuid,),
            )
            return [
                {
                    "message": row["message"],
                    "severity": row["severity"],
                    "task": row["task"],
                    **json.loads(row["event_data"]),
                    "created_at": row["created_at"],
                }
                for row in cursor.fetchall()
            ]

    def list_jobs(
        self,
        pending: bool = True,
        completed: bool = True,
        task: str = None,
        last: int = None,
        client: str = None,
        uuid: str = None,
    ) -> list:
        """
        List jobs based on filters.

        Args:
            pending (bool): Include pending jobs.
            completed (bool): Include completed jobs.
            task (str): Filter by task name.
            last (int): Return only last N jobs.
            client (str): Filter by client address.
            uuid (str): Filter by specific UUID.

        Returns:
            list: List of job dictionaries.
        """
        with self._transaction(write=False) as conn:
            # Build query
            conditions = []
            params = []

            if uuid:
                conditions.append("uuid = ?")
                params.append(uuid)
            else:
                status_conditions = []
                if pending:
                    status_conditions.append("status IN ('PENDING', 'STARTED')")
                if completed:
                    status_conditions.append("status IN ('COMPLETED', 'FAILED')")
                if status_conditions:
                    conditions.append(f"({' OR '.join(status_conditions)})")

                if task:
                    conditions.append("task = ?")
                    params.append(task)
                if client:
                    conditions.append("client_address = ?")
                    params.append(client)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"""
                SELECT uuid, client_address, task, status,
                       received_timestamp, started_timestamp, completed_timestamp
                FROM jobs {where_clause}
                ORDER BY created_at DESC
            """

            if last:
                query += f" LIMIT {last}"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


    def close(self):
        """Close all database connections."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")


# --------------------------------------------------------------------------------------------
# NORFAB Worker watchdog Object
# --------------------------------------------------------------------------------------------


class WorkerWatchDog(threading.Thread):
    """
    Class to monitor worker performance.

    Attributes:
        worker (object): The worker instance being monitored.
        worker_process (psutil.Process): The process of the worker.
        watchdog_interval (int): Interval in seconds for the watchdog to check the worker's status.
        memory_threshold_mbyte (int): Memory usage threshold in megabytes.
        memory_threshold_action (str): Action to take when memory threshold is exceeded ("log" or "shutdown").
        runs (int): Counter for the number of times the watchdog has run.
        watchdog_tasks (list): List of additional tasks to run during each watchdog interval.

    Methods:
        check_ram(): Checks the worker's RAM usage and takes action if it exceeds the threshold.
        get_ram_usage(): Returns the worker's RAM usage in megabytes.
        run(): Main loop of the watchdog thread, periodically checks the worker's status and runs tasks.

    Args:
        worker (object): The worker object containing inventory attributes.
    """

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.worker_process = psutil.Process(os.getpid())

        # extract inventory attributes
        self.watchdog_interval = worker.inventory.get("watchdog_interval", 30)
        self.memory_threshold_mbyte = worker.inventory.get(
            "memory_threshold_mbyte", 1000
        )
        self.memory_threshold_action = worker.inventory.get(
            "memory_threshold_action", "log"
        )

        # initiate variables
        self.runs = 0
        self.watchdog_tasks = []

    def check_ram(self):
        """
        Checks the current RAM usage and performs an action if it exceeds the threshold.

        This method retrieves the current RAM usage and compares it to the predefined
        memory threshold. If the RAM usage exceeds the threshold, it performs an action
        based on the `memory_threshold_action` attribute. The possible actions are:

        - "log": Logs a warning message.
        - "shutdown": Raises a SystemExit exception to terminate the program.

        Raises:
            SystemExit: If the memory usage exceeds the threshold and the action is "shutdown".
        """
        mem_usage = self.get_ram_usage()
        if mem_usage > self.memory_threshold_mbyte:
            if self.memory_threshold_action == "log":
                log.warning(
                    f"{self.name} watchdog, '{self.memory_threshold_mbyte}' "
                    f"memory_threshold_mbyte exceeded, memory usage "
                    f"{mem_usage}MByte"
                )
            elif self.memory_threshold_action == "shutdown":
                raise SystemExit(
                    f"{self.name} watchdog, '{self.memory_threshold_mbyte}' "
                    f"memory_threshold_mbyte exceeded, memory usage "
                    f"{mem_usage}MByte, killing myself"
                )

    def get_ram_usage(self):
        """
        Get the RAM usage of the worker process.

        Returns:
            float: The RAM usage in megabytes.
        """
        return self.worker_process.memory_info().rss / 1024000

    def run(self):
        """
        Executes the worker's watchdog main loop, periodically running tasks and checking conditions.
        The method performs the following steps in a loop until the worker's exit event is set:

        1. Sleeps in increments of 0.1 seconds until the total sleep time reaches the watchdog interval.
        2. Runs built-in tasks such as checking RAM usage.
        3. Executes additional tasks provided by child classes.
        4. Updates the run counter.
        5. Resets the sleep counter to start the cycle again.

        Attributes:
            slept (float): The total time slept in the current cycle.
        """
        slept = 0
        while not self.worker.exit_event.is_set():
            # continue sleeping for watchdog_interval
            if slept < self.watchdog_interval:
                time.sleep(0.1)
                slept += 0.1
                continue

            # run built in tasks:
            self.check_ram()

            # run child classes tasks
            for task in self.watchdog_tasks:
                task()

            # update counters
            self.runs += 1

            slept = 0  # reset to go to sleep


# --------------------------------------------------------------------------------------------
# NORFAB worker
# --------------------------------------------------------------------------------------------


def _post(worker, post_queue, destroy_event):
    """
    Thread to receive POST requests and save them to database.

    Args:
        worker (Worker): The worker instance handling the request.
        post_queue (queue.Queue): The queue from which POST requests are received.
        destroy_event (threading.Event): Event to signal the thread to stop.

    Functionality:
        - Continuously processes POST requests from the queue until the destroy event is set.
        - Saves the request to the database.
        - Sends an acknowledgment back to the client.
    """
    while not destroy_event.is_set():
        try:
            work = post_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue

        timestamp = time.ctime()
        client_address = work[0]
        suuid = work[2]
        data = json.loads(work[3].decode("utf-8"))

        task = data.get("task")
        args = data.get("args", [])
        kwargs = data.get("kwargs", {})
        timeout = data.get("timeout", 60)

        # Store the entire work as JSON-serializable dict for request_data
        request_data = {
            "client_address": client_address.decode("utf-8"),
            "uuid": suuid.decode("utf-8"),
            "task": task,
            "args": args,
            "kwargs": kwargs,
            "timeout": timeout,
        }

        # Add job to database
        try:
            worker.db.add_job(
                uuid=suuid.decode("utf-8"),
                client_address=client_address.decode("utf-8"),
                task=task,
                args=args,
                kwargs=kwargs,
                timeout=timeout,
                request_data=request_data,
                timestamp=timestamp,
            )
            log.debug(
                f"{worker.name} - '{suuid.decode('utf-8')}' job added to database"
            )
        except Exception as e:
            log.error(f"{worker.name} - failed to add job to database: {e}")
            post_queue.task_done()
            continue

        # ack job back to client
        worker.send_to_broker(
            NFP.RESPONSE,
            [
                client_address,
                b"",
                suuid,
                b"202",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "ACCEPTED",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ],
        )
        log.debug(
            f"{worker.name} - '{suuid.decode('utf-8')}' job, sent ACK back to client '{client_address.decode('utf-8')}'"
        )

        post_queue.task_done()


def _get(worker, get_queue, destroy_event):
    """
    Thread to receive GET requests and retrieve job status/results from the database.

    This function handles GET requests intelligently based on job status:
    - If job is PENDING or STARTED: Returns current status with timestamps
    - If job is COMPLETED or FAILED: Returns full job results
    - If job is not found: Returns 404 error

    Args:
        worker (Worker): The worker instance handling the request.
        get_queue (queue.Queue): The queue from which GET requests are received.
        destroy_event (threading.Event): Event to signal the thread to stop.
    """
    while not destroy_event.is_set():
        try:
            work = get_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue

        client_address = work[0]
        suuid = work[2]
        uuid_str = suuid.decode("utf-8")

        # Get job info - first without result data for efficiency
        job_info = worker.db.get_job_info(uuid_str, include_result=False)

        if job_info is None:
            # Job not found
            reply = [
                client_address,
                b"",
                suuid,
                b"404",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": uuid_str,
                        "status": "JOB NOT FOUND",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ]
        elif job_info["status"] in ("PENDING", "STARTED"):
            # Job is still in progress - return status with timestamps
            reply = [
                client_address,
                b"",
                suuid,
                b"300",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": uuid_str,
                        "status": job_info["status"],
                        "service": worker.service.decode("utf-8"),
                        "received_timestamp": job_info.get("received_timestamp"),
                        "started_timestamp": job_info.get("started_timestamp"),
                    }
                ).encode("utf-8"),
            ]
        elif job_info["status"] in ("COMPLETED", "FAILED"):
            # Job is completed - fetch full result data
            job_info_with_result = worker.db.get_job_info(uuid_str, include_result=True)
            result_dict = job_info_with_result.get("result_data")

            if result_dict:
                # result_dict is already decompressed by get_job_info
                reply = [
                    client_address,
                    b"",
                    suuid,
                    result_dict.get("status_code", "200").encode("utf-8"),
                    json.dumps(result_dict.get("body", {})).encode("utf-8"),
                ]
            else:
                # Status says completed but no result data (shouldn't happen)
                reply = [
                    client_address,
                    b"",
                    suuid,
                    b"500",
                    json.dumps(
                        {
                            "worker": worker.name,
                            "uuid": uuid_str,
                            "status": "RESULT DATA MISSING",
                            "service": worker.service.decode("utf-8"),
                        }
                    ).encode("utf-8"),
                ]
        else:
            # Unknown status
            reply = [
                client_address,
                b"",
                suuid,
                b"500",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": uuid_str,
                        "status": f"UNKNOWN STATUS: {job_info['status']}",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ]

        worker.send_to_broker(NFP.RESPONSE, reply)

        get_queue.task_done()


def _event(worker, event_queue, destroy_event):
    """
    Thread function to emit events to Clients.

    Args:
        worker (Worker): The worker instance that is emitting events.
        event_queue (queue.Queue): The queue from which events are retrieved.
        destroy_event (threading.Event): An event to signal the thread to stop.

    The function continuously retrieves events from the event_queue, processes them,
    and sends them to the broker until the destroy_event is set.
    """
    while not destroy_event.is_set():
        try:
            event_data = event_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue
        uuid = event_data.pop("juuid")
        event = [
            event_data.pop("client_address").encode("utf-8"),
            b"",
            uuid.encode("utf-8"),
            b"200",
            json.dumps(
                {
                    "worker": worker.name,
                    "service": worker.service.decode("utf-8"),
                    "uuid": uuid,
                    **event_data,
                }
            ).encode("utf-8"),
        ]
        worker.send_to_broker(NFP.EVENT, event)
        event_queue.task_done()


def recv(worker, destroy_event):
    """
    Thread to process receive messages from broker.

    This function runs in a loop, polling the worker's broker socket for messages every second.
    When a message is received, it processes the message based on the command type and places
    it into the appropriate queue or handles it accordingly. If the keepaliver thread is not
    alive, it logs a warning and attempts to reconnect to the broker.

    Args:
        worker (Worker): The worker instance that contains the broker socket and queues.
        destroy_event (threading.Event): An event to signal the thread to stop.

    Commands:
        - NFP.POST: Places the message into the post_queue.
        - NFP.DELETE: Places the message into the delete_queue.
        - NFP.GET: Places the message into the get_queue.
        - NFP.KEEPALIVE: Processes a keepalive heartbeat.
        - NFP.DISCONNECT: Attempts to reconnect to the broker.
        - Other: Logs an invalid input message.
    """
    while not destroy_event.is_set():
        # Poll socket for messages every second
        try:
            items = worker.poller.poll(1000)
        except KeyboardInterrupt:
            break  # Interrupted
        if items:
            msg = worker.broker_socket.recv_multipart()
            log.debug(f"{worker.name} - received '{msg}'")
            empty = msg.pop(0)
            header = msg.pop(0)
            command = msg.pop(0)

            if command == NFP.POST:
                worker.post_queue.put(msg)
            elif command == NFP.DELETE:
                worker.delete_queue.put(msg)
            elif command == NFP.GET:
                worker.get_queue.put(msg)
            elif command == NFP.KEEPALIVE:
                worker.keepaliver.received_heartbeat([header] + msg)
            elif command == NFP.DISCONNECT:
                worker.reconnect_to_broker()
            else:
                log.debug(
                    f"{worker.name} - invalid input, header '{header}', command '{command}', message '{msg}'"
                )

        if not worker.keepaliver.is_alive():
            log.warning(f"{worker.name} - '{worker.broker}' broker keepalive expired")
            worker.reconnect_to_broker()


class NFPWorker:
    """
    NFPWorker class is responsible for managing worker operations,
    including connecting to a broker, handling jobs,  and maintaining
    keepalive connections. It interacts with the broker using ZeroMQ
    and manages job queues and events.

    Args:
        inventory (NorFabInventory): The inventory object containing base directory information.
        broker (str): The broker address.
        service (str): The service name.
        name (str): The name of the worker.
        exit_event: The event used to signal the worker to exit.
        log_level (str, optional): The logging level. Defaults to None.
        log_queue (object, optional): The logging queue. Defaults to None.
        multiplier (int, optional): The multiplier value. Defaults to 6.
        keepalive (int, optional): The keepalive interval in milliseconds. Defaults to 2500.
    """

    keepaliver = None
    stats_reconnect_to_broker = 0

    def __init__(
        self,
        inventory: NorFabInventory,
        broker: str,
        service: str,
        name: str,
        exit_event: object,
        log_level: str = None,
        log_queue: object = None,
        multiplier: int = 6,
        keepalive: int = 2500,
    ):
        self.setup_logging(log_queue, log_level)
        self.inventory = inventory
        self.max_concurrent_jobs = max(1, inventory.get("max_concurrent_jobs", 5))
        self.jobs_compress = inventory.get("jobs_compress", True)
        self.broker = broker
        self.service = service.encode("utf-8") if isinstance(service, str) else service
        self.name = name
        self.exit_event = exit_event
        self.broker_socket = None
        self.multiplier = multiplier
        self.keepalive = keepalive
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object
        self.zmq_auth = self.inventory.broker.get("zmq_auth", True)

        # create base directories
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "worker", self.name
        )
        os.makedirs(self.base_dir, exist_ok=True)

        # Initialize SQLite database for job management
        db_path = os.path.join(self.base_dir, f"{self.name}.db")
        self.db = JobDatabase(db_path, jobs_compress=self.jobs_compress)

        # create events and queues
        self.destroy_event = threading.Event()
        self.request_thread = None
        self.reply_thread = None
        self.recv_thread = None
        self.event_thread = None

        self.post_queue = queue.Queue(maxsize=0)
        self.get_queue = queue.Queue(maxsize=0)
        self.delete_queue = queue.Queue(maxsize=0)
        self.event_queue = queue.Queue(maxsize=0)

        # generate certificates and create directories
        if self.zmq_auth is not False:
            generate_certificates(
                self.base_dir,
                cert_name=self.name,
                broker_keys_dir=os.path.join(
                    self.inventory.base_dir,
                    "__norfab__",
                    "files",
                    "broker",
                    "public_keys",
                ),
                inventory=self.inventory,
            )
            self.public_keys_dir = os.path.join(self.base_dir, "public_keys")
            self.secret_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        self.client = NFPClient(
            self.inventory,
            self.broker,
            name=f"{self.name}-NFPClient",
            exit_event=self.exit_event,
        )

        self.tasks = NORFAB_WORKER_TASKS

    def setup_logging(self, log_queue, log_level: str) -> None:
        """
        Configures logging for the worker.

        This method sets up the logging configuration using a provided log queue and log level.
        It updates the logging configuration dictionary with the given log queue and log level,
        and then applies the configuration using `logging.config.dictConfig`.

        Args:
            log_queue (queue.Queue): The queue to be used for logging.
            log_level (str): The logging level to be set. If None, the default level is used.
        """
        logging_config_producer["handlers"]["queue"]["queue"] = log_queue
        if log_level is not None:
            logging_config_producer["root"]["level"] = log_level
        logging.config.dictConfig(logging_config_producer)

    def reconnect_to_broker(self):
        """
        Connect or reconnect to the broker.

        This method handles the connection or reconnection process to the broker.
        It performs the following steps:

        1. If there is an existing broker socket, it sends a disconnect message,
           unregisters the socket from the poller, and closes the socket.
        2. Creates a new DEALER socket and sets its identity.
        3. Loads the client's secret and public keys for CURVE authentication.
        4. Loads the server's public key for CURVE authentication.
        5. Connects the socket to the broker.
        6. Registers the socket with the poller for incoming messages.
        7. Sends a READY message to the broker to register the service.
        8. Starts or restarts the keepalive mechanism to maintain the connection.
        9. Increments the reconnect statistics counter.
        10. Logs the successful registration to the broker.
        """
        if self.broker_socket:
            self.send_to_broker(NFP.DISCONNECT)
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)
        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.name, "utf8")
        self.broker_socket.linger = 0

        if self.zmq_auth is not False:
            # We need two certificates, one for the client and one for
            # the server. The client must know the server's public key
            # to make a CURVE connection.
            client_secret_file = os.path.join(
                self.secret_keys_dir, f"{self.name}.key_secret"
            )
            client_public, client_secret = zmq.auth.load_certificate(client_secret_file)
            self.broker_socket.curve_secretkey = client_secret
            self.broker_socket.curve_publickey = client_public

            # The client must know the server's public key to make a CURVE connection.
            server_public_file = os.path.join(self.public_keys_dir, "broker.key")
            server_public, _ = zmq.auth.load_certificate(server_public_file)
            self.broker_socket.curve_serverkey = server_public

        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)

        # Register service with broker
        self.send_to_broker(NFP.READY)
        log.debug(f"{self.name} - NFP.READY sent to broker '{self.broker}'")

        # start keepalives
        if self.keepaliver is not None:
            self.keepaliver.restart(self.broker_socket)
        else:
            self.keepaliver = KeepAliver(
                address=None,
                socket=self.broker_socket,
                multiplier=self.multiplier,
                keepalive=self.keepalive,
                exit_event=self.destroy_event,
                service=self.service,
                whoami=NFP.WORKER,
                name=self.name,
                socket_lock=self.socket_lock,
            )
            self.keepaliver.start()

        self.stats_reconnect_to_broker += 1
        log.info(
            f"{self.name} - registered to broker at '{self.broker}', "
            f"service '{self.service.decode('utf-8')}'"
        )

    def send_to_broker(self, command, msg: list = None):
        """
        Send a message to the broker.

        Parameters:
            command (str): The command to send to the broker. Must be one of NFP.READY, NFP.DISCONNECT, NFP.RESPONSE, or NFP.EVENT.
            msg (list, optional): The message to send. If not provided, a default message will be created based on the command.

        Logs:
            Logs an error if the command is unsupported.
            Logs a debug message with the message being sent.

        Thread Safety:
            This method is thread-safe and uses a lock to ensure that the broker socket is accessed by only one thread at a time.
        """
        if command == NFP.READY:
            msg = [b"", NFP.WORKER, NFP.READY, self.service]
        elif command == NFP.DISCONNECT:
            msg = [b"", NFP.WORKER, NFP.DISCONNECT, self.service]
        elif command == NFP.RESPONSE:
            msg = [b"", NFP.WORKER, NFP.RESPONSE] + msg
        elif command == NFP.EVENT:
            msg = [b"", NFP.WORKER, NFP.EVENT] + msg
        else:
            log.error(
                f"{self.name} - cannot send '{command}' to broker, command unsupported"
            )
            return

        log.debug(f"{self.name} - sending '{msg}'")

        with self.socket_lock:
            self.broker_socket.send_multipart(msg)

    def load_inventory(self) -> dict:
        """
        Load inventory data from the broker for this worker.

        This function retrieves inventory data from the broker service using the worker's name.
        It logs the received inventory data and returns the results if available.

        Returns:
            dict: The inventory data results if available, otherwise an empty dictionary.
        """
        inventory_data = self.client.get(
            "sid.service.broker", "get_inventory", kwargs={"name": self.name}
        )

        log.debug(f"{self.name} - worker received inventory data {inventory_data}")

        if inventory_data["results"]:
            return inventory_data["results"]
        else:
            return {}

    def worker_exit(self) -> None:
        """
        Method to override in child classes with a set of actions to perform on exit call.

        This method should be implemented by subclasses to define any cleanup or finalization
        tasks that need to be performed when the worker is exiting.
        """
        return None

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self, job: Job) -> Result:
        """
        Retrieve the worker's inventory.

        This method should be overridden in child classes to provide the specific
        implementation for retrieving the inventory of a worker.

        Returns:
            Dict: A dictionary representing the worker's inventory.

        Raises:
            NotImplementedError: If the method is not overridden in a child class.
        """
        raise NotImplementedError

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        """
        Retrieve the version report of the worker.

        This method should be overridden in child classes to provide the specific
        version report of the worker.

        Returns:
            Dict: A dictionary containing the version information of the worker.

        Raises:
            NotImplementedError: If the method is not overridden in a child class.
        """
        raise NotImplementedError

    def destroy(self, message=None):
        """
        Cleanly shuts down the worker by performing the following steps:

        1. Calls the worker_exit method to handle any worker-specific exit procedures.
        2. Sets the destroy_event to signal that the worker is being destroyed.
        3. Calls the destroy method on the client to clean up client resources.
        4. Joins all the threads (request_thread, reply_thread, event_thread, recv_thread) if they are not None, ensuring they have finished execution.
        5. Closes the database connections.
        6. Destroys the context with a linger period of 0 to immediately close all sockets.
        7. Stops the keepaliver to cease any keepalive signals.
        8. Logs an informational message indicating that the worker has been destroyed, including an optional message.

        Args:
            message (str, optional): An optional message to include in the log when the worker is destroyed.
        """
        self.worker_exit()
        self.destroy_event.set()
        self.client.destroy()

        # join all the threads
        if self.request_thread is not None:
            self.request_thread.join()
        if self.reply_thread is not None:
            self.reply_thread.join()
        if self.event_thread is not None:
            self.event_thread.join()
        if self.recv_thread:
            self.recv_thread.join()

        # close database
        self.db.close()

        self.ctx.destroy(0)

        # stop keepalives
        self.keepaliver.stop()

        log.info(f"{self.name} - worker destroyed, message: '{message}'")

    def is_url(self, url: str) -> bool:
        """
        Check if the given string is a URL supported by NorFab File Service.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL supported by NorFab File Service, False otherwise.
        """
        return any(str(url).startswith(k) for k in ["nf://"])

    def fetch_file(
        self, url: str, raise_on_fail: bool = False, read: bool = True
    ) -> str:
        """
        Function to download file from broker File Sharing Service

        Args:
            url: file location string in ``nf://<filepath>`` format
            raise_on_fail: raise FIleNotFoundError if download fails
            read: if True returns file content, return OS path to saved file otherwise

        Returns:
            str: File content if read is True, otherwise OS path to the saved file.

        Raises:
            FileNotFoundError: If raise_on_fail is True and the download fails.
        """
        if not self.is_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        status, file_content = self.client.fetch_file(url=url, read=read)
        msg = f"{self.name} - worker '{url}' fetch file failed with status '{status}'"

        if status == "200":
            return file_content
        elif raise_on_fail is True:
            raise FileNotFoundError(msg)
        else:
            log.error(msg)
            return None

    def jinja2_render_templates(
        self, templates: list[str], context: dict = None, filters: dict = None
    ) -> str:
        """
        Renders a list of Jinja2 templates with the given context and optional filters.

        Args:
            templates (list[str]): A list of Jinja2 template strings or NorFab file paths.
            context (dict): A dictionary containing the context variables for rendering the templates.
            filters (dict, optional): A dictionary of custom Jinja2 filters to be used during rendering.

        Returns:
            str: The rendered templates concatenated into a single string.
        """
        rendered = []
        filters = filters or {}
        context = context or {}
        for template in templates:
            j2env = Environment(loader="BaseLoader")
            j2env.filters.update(filters)  # add custom filters
            renderer = j2env.from_string(template)
            template = renderer.render(**context)
            # download template file and render it again
            if template.startswith("nf://"):
                filepath = self.jinja2_fetch_template(template)
                searchpath, filename = os.path.split(filepath)
                j2env = Environment(loader=FileSystemLoader(searchpath))
                j2env.filters.update(filters)  # add custom filters
                renderer = j2env.get_template(filename)
                rendered.append(renderer.render(**context))
            # template content is fully rendered
            else:
                rendered.append(template)

        return "\n".join(rendered)

    def jinja2_fetch_template(self, url: str) -> str:
        """
        Helper function to recursively download a Jinja2 template along with
        other templates referenced using "include" statements.

        Args:
            url (str): A URL in the format ``nf://file/path`` to download the file.

        Returns:
            str: The file path of the downloaded Jinja2 template.

        Raises:
            FileNotFoundError: If the file download fails.
            Exception: If Jinja2 template parsing fails.
        """
        filepath = self.fetch_file(url, read=False)
        if filepath is None:
            msg = f"{self.name} - file download failed '{url}'"
            raise FileNotFoundError(msg)

        # download Jinja2 template "include"-ed files
        content = self.fetch_file(url, read=True)
        j2env = Environment(loader="BaseLoader")
        try:
            parsed_content = j2env.parse(content)
        except Exception as e:
            msg = f"{self.name} - Jinja2 template parsing failed '{url}', error: '{e}'"
            raise Exception(msg)

        # run recursion on include statements
        for node in parsed_content.find_all(Include):
            include_file = node.template.value
            base_path = os.path.split(url)[0]
            self.jinja2_fetch_template(os.path.join(base_path, include_file))

        return filepath

    def event(
        self,
        message: str,
        juuid: str,
        task: str,
        client_address: str,
        **kwargs,
    ) -> None:
        """
        Handles the creation and emission of an event.

        This method takes event data, processes it, and sends it to the event queue.
        It also saves the event data to the database for future reference.

        Args:
            message: The event message
            juuid: Job ID for which this event is generated
            task: Task name
            client_address: Client address
            **kwargs: Additional keyword arguments to be passed when creating a NorFabEvent instance

        Logs:
            Error: Logs an error message if the event data cannot be formed.
        """
        # construct NorFabEvent
        try:
            event_data = NorFabEvent(
                message=message,
                juuid=juuid,
                client_address=client_address,
                task=task,
                **kwargs,
            )
        except Exception as e:
            log.error(f"Failed to form event data, error {e}")
            return
        event_dict = event_data.model_dump(exclude_none=True)

        # emit event to the broker
        self.event_queue.put(event_dict)

        # check if need to emit log for this event
        if self.inventory["logging"].get("log_events", False):
            event_log = f"EVENT {self.name}:{task} - {message}"
            severity = event_dict.get("severity", "INFO")
            if severity == "INFO":
                log.info(event_log)
            elif severity == "DEBUG":
                log.debug(event_log)
            elif severity == "WARNING":
                log.warning(event_log)
            elif severity == "CRITICAL":
                log.critical(event_log)
            elif severity == "ERROR":
                log.error(event_log)

        # save event to database
        try:
            self.db.add_event(
                job_uuid=juuid,
                message=message,
                severity=event_dict.get("severity", "INFO"),
                task=task,
                event_data=event_dict,
            )
        except Exception as e:
            log.error(f"Failed to save event to database: {e}")

    @Task(fastapi={"methods": ["GET"]})
    def job_details(
        self,
        uuid: str = None,
        data: bool = True,
        result: bool = True,
        events: bool = True,
    ) -> Result:
        """
        Method to get job details by UUID for completed jobs.

        Args:
            uuid (str): The job UUID to return details for.
            data (bool): If True, return job data.
            result (bool): If True, return job result.
            events (bool): If True, return job events.

        Returns:
            Result: A Result object with the job details.
        """
        job = self.db.get_job_info(
            uuid=uuid, include_data=data, include_result=result, include_events=events
        )

        if job:
            return Result(
                task=f"{self.name}:job_details",
                result=job,
            )
        else:
            raise FileNotFoundError(f"{self.name} - job with UUID '{uuid}' not found")

    @Task(fastapi={"methods": ["GET"]})
    def job_list(
        self,
        pending: bool = True,
        completed: bool = True,
        task: str = None,
        last: int = None,
        client: str = None,
        uuid: str = None,
    ) -> Result:
        """
        Method to list worker jobs completed and pending.

        Args:
            pending (bool): If True or None, return pending jobs. If False, skip pending jobs.
            completed (bool): If True or None, return completed jobs. If False, skip completed jobs.
            task (str, optional): If provided, return only jobs with this task name.
            last (int, optional): If provided, return only the last N completed and last N pending jobs.
            client (str, optional): If provided, return only jobs submitted by this client.
            uuid (str, optional): If provided, return only the job with this UUID.

        Returns:
            Result: Result object with a list of jobs.
        """
        jobs = self.db.list_jobs(
            pending=pending,
            completed=completed,
            task=task,
            last=last,
            client=client,
            uuid=uuid,
        )

        # Add worker and service information to each job
        for job in jobs:
            job["worker"] = self.name
            job["service"] = self.service.decode("utf-8")
            # Map database status to expected status names
            if job["status"] in ("PENDING", "STARTED"):
                job["status"] = "PENDING"
                job["completed_timestamp"] = None
            elif job["status"] in ("COMPLETED", "FAILED"):
                job["status"] = "COMPLETED"

        return Result(
            task=f"{self.name}:job_list",
            result=jobs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=models.WorkerEchoIn,
        output=models.WorkerEchoOut,
    )
    def echo(
        self,
        job: Job,
        raise_error: Union[bool, int, str] = None,
        sleep: int = None,
        *args,
        **kwargs,
    ) -> Result:
        """
        Echoes the job information and optional arguments, optionally sleeping or raising an error.

        Args:
            job (Job): The job instance containing job details.
            raise_error (str, optional): If provided, raises a RuntimeError with this message.
            sleep (int, optional): If provided, sleeps for the specified number of seconds.
            *args: Additional positional arguments to include in the result.
            **kwargs: Additional keyword arguments to include in the result.

        Returns:
            Result: An object containing job details and any provided arguments.

        Raises:
            RuntimeError: If `raise_error` is provided.
        """
        if sleep:
            time.sleep(sleep)
        if raise_error:
            raise RuntimeError(raise_error)
        return Result(
            result={
                "juuid": job.juuid,
                "client_address": job.client_address,
                "timeout": job.timeout,
                "task": job.task,
                "args": args,
                "kwargs": kwargs,
            }
        )

    @Task(fastapi={"methods": ["GET"]})
    def list_tasks(self, name: Union[None, str] = None, brief: bool = False) -> Result:
        """
        Lists tasks supported by worker.

        Args:
            name (str, optional): The name of a specific task to retrieve
            brief (bool, optional): If True, returns only the list of task names

        Returns:
            Results returned controlled by this logic:

                - If brief is True returns a list of task names
                - If name is provided returns list with single item - OpenAPI schema of the specified task
                - Otherwise returns a list of schemas for all tasks

        Raises:
            KeyError: If a specific task name is provided but not registered in NORFAB_WORKER_TASKS.
        """
        ret = Result()
        if brief:
            ret.result = list(sorted(NORFAB_WORKER_TASKS.keys()))
        elif name:
            if name not in NORFAB_WORKER_TASKS:
                raise KeyError(f"{name} - task not registered")
            ret.result = [NORFAB_WORKER_TASKS[name]["schema"]]
        else:
            ret.result = [t["schema"] for t in NORFAB_WORKER_TASKS.values()]
        return ret

    def start_threads(self) -> None:
        """
        Starts multiple daemon threads required for the worker's operation.

        This method initializes and starts the following threads:
            - request_thread: Handles posting requests using the _post function.
            - reply_thread: Handles receiving replies using the _get function.
            - event_thread: Handles event processing using the _event function.
            - recv_thread: Handles receiving data using the recv function.

        Each thread is started as a daemon and is provided with the necessary arguments,
        including queues and events as required.

        Returns:
            None
        """
        # Start threads
        self.request_thread = threading.Thread(
            target=_post,
            daemon=True,
            name=f"{self.name}_post_thread",
            args=(
                self,
                self.post_queue,
                self.destroy_event,
            ),
        )
        self.request_thread.start()
        self.reply_thread = threading.Thread(
            target=_get,
            daemon=True,
            name=f"{self.name}_get_thread",
            args=(self, self.get_queue, self.destroy_event),
        )
        self.reply_thread.start()
        self.event_thread = threading.Thread(
            target=_event,
            daemon=True,
            name=f"{self.name}_event_thread",
            args=(self, self.event_queue, self.destroy_event),
        )
        self.event_thread.start()
        # start receive thread after other threads
        self.recv_thread = threading.Thread(
            target=recv,
            daemon=True,
            name=f"{self.name}_recv_thread",
            args=(
                self,
                self.destroy_event,
            ),
        )
        self.recv_thread.start()

    def run_next_job(self, uuid: str):
        """
        Processes the next job from the database.

        This method performs the following steps:

        1. Loads job data from the database.
        2. Parses the job data to extract the task name, arguments, keyword arguments, and timeout.
        3. Executes the specified task method on the worker instance with the provided arguments.
        4. Handles any exceptions raised during task execution, logging errors and creating a failed Result object if needed.
        5. Saves the result of the job execution to the database.
        6. Marks the job as completed or failed in the database.

        Args:
            uuid (str): The job UUID to process.

        Raises:
            TypeError: If the executed task does not return a Result object.
        """
        log.debug(f"{self.name} - processing job request {uuid}")

        # Load job data from database
        job_data = self.db.get_job_info(uuid)
        if not job_data:
            log.error(f"{self.name} - job {uuid} not found in database")
            return

        client_address = job_data["client_address"]
        task = job_data["task"]
        args = job_data["args"]
        kwargs = job_data["kwargs"]
        timeout = job_data["timeout"]

        job = Job(
            worker=self,
            client_address=client_address,
            juuid=uuid,
            task=task,
            timeout=timeout,
            args=copy.deepcopy(args),
            kwargs=copy.deepcopy(kwargs),
        )

        log.debug(
            f"{self.name} - doing task '{task}', timeout: '{timeout}', "
            f"args: '{args}', kwargs: '{kwargs}', client: '{client_address}', "
            f"job uuid: '{uuid}'"
        )

        # run the actual job
        try:
            task_started = time.ctime()
            result = NORFAB_WORKER_TASKS[task]["function"](
                self, *args, job=job, **kwargs
            )
            task_completed = time.ctime()
            if not isinstance(result, Result):
                raise TypeError(
                    f"{self.name} - task '{task}' did not return Result object, "
                    f"args: '{args}', kwargs: '{kwargs}', client: '{client_address}', "
                    f"job uuid: '{uuid}'; task returned '{type(result)}'"
                )
            result.task = result.task or f"{self.name}:{task}"
            result.status = result.status or "completed"
            result.juuid = result.juuid or uuid
            result.service = self.service.decode("utf-8")
            job_failed = False
        except Exception as e:
            task_completed = time.ctime()
            result = Result(
                task=f"{self.name}:{task}",
                errors=[traceback.format_exc()],
                messages=[f"Worker experienced error: '{e}'"],
                failed=True,
                juuid=uuid,
            )
            log.error(
                f"{self.name} - worker experienced error:\n{traceback.format_exc()}"
            )
            job_failed = True

        result.task_started = task_started
        result.task_completed = task_completed

        # Prepare result data for database storage as JSON-serializable dict
        result_data = {
            "client_address": client_address,
            "uuid": uuid,
            "status_code": "200",
            "body": {self.name: result.model_dump()},
            "worker": self.name,
            "service": self.service.decode("utf-8"),
        }

        # Save job result to database
        if job_failed:
            self.db.fail_job(uuid, result_data)
        else:
            self.db.complete_job(uuid, result_data)

    def work(self):
        """
        Executes the main worker loop, managing job execution using a thread pool.

        This method starts necessary background threads, then enters a loop where it:

        - Queries the database for the next pending job.
        - Atomically marks the job as started in the database.
        - Submits the job to a thread pool executor for concurrent processing.
        - Waits briefly if no pending jobs are found.
        - Continues until either the exit or destroy event is set.

        Upon exit, performs cleanup by calling the `destroy` method with a status message.
        """

        self.start_threads()

        # start job threads and submit jobs in an infinite loop
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_concurrent_jobs,
            thread_name_prefix=f"{self.name}-job-thread",
        ) as executor:
            while not self.exit_event.is_set() and not self.destroy_event.is_set():
                # Get next pending job from database
                job_info = self.db.get_next_pending_job()

                if job_info is None:
                    # No pending jobs, wait a bit
                    time.sleep(0.1)
                    continue

                uuid, received_timestamp = job_info
                log.debug(f"{self.name} - submitting job {uuid} to executor")

                # Submit the job to workers
                executor.submit(self.run_next_job, uuid)

        # make sure to clean up
        self.destroy(
            f"{self.name} - exit event is set '{self.exit_event.is_set()}', "
            f"destroy event is set '{self.destroy_event.is_set()}'"
        )
