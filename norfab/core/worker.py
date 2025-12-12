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

file_write_lock = threading.Lock()
queue_file_lock = threading.Lock()


def dumper(data, filename):
    """
    Serializes and saves data to a file using pickle.

    Args:
        data (any): The data to be serialized and saved.
        filename (str): The name of the file where the data will be saved.
    """
    with file_write_lock:
        with open(filename, "wb") as f:
            pickle.dump(data, f)


def loader(filename):
    """
    Load and deserialize a Python object from a file.

    This function opens a file in binary read mode, reads its content, and
    deserializes it using the pickle module. The file access is synchronized
    using a file write lock to ensure thread safety.

    Args:
        filename (str): The path to the file to be loaded.

    Returns:
        object: The deserialized Python object from the file.
    """
    with file_write_lock:
        with open(filename, "rb") as f:
            return pickle.load(f)


def request_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated request filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the request file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.req")


def reply_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated reply filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the reply file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.rep")


def event_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated event filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the event file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.event")


def _post(worker, post_queue, queue_filename, destroy_event, base_dir_jobs):
    """
    Thread to receive POST requests and save them to hard disk.

    Args:
        worker (Worker): The worker instance handling the request.
        post_queue (queue.Queue): The queue from which POST requests are received.
        queue_filename (str): The filename where the job queue is stored.
        destroy_event (threading.Event): Event to signal the thread to stop.
        base_dir_jobs (str): The base directory where job files are stored.

    Functionality:
        - Ensures the message directory exists.
        - Continuously processes POST requests from the queue until the destroy event is set.
        - Saves the request to the hard disk.
        - Writes a reply indicating the job is pending.
        - Adds the job request to the queue file.
        - Sends an acknowledgment back to the client.
    """
    # Ensure message directory exists
    if not os.path.exists(base_dir_jobs):
        os.mkdir(base_dir_jobs)

    while not destroy_event.is_set():
        try:
            work = post_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue
        timestamp = time.ctime()
        client_address = work[0]
        suuid = work[2]
        filename = request_filename(suuid, base_dir_jobs)
        dumper(work, filename)

        # write reply for this job indicating it is pending
        filename = reply_filename(suuid, base_dir_jobs)
        dumper(
            [
                client_address,
                b"",
                suuid,
                b"300",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "PENDING",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ],
            filename,
        )
        log.debug(f"{worker.name} - '{suuid}' job, saved PENDING reply filename")

        # add job request to the queue_filename
        with queue_file_lock:
            with open(queue_filename, "ab") as f:
                f.write(f"{suuid.decode('utf-8')}--{timestamp}\n".encode("utf-8"))
        log.debug(f"{worker.name} - '{suuid}' job, added job to queue filename")

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
            f"{worker.name} - '{suuid}' job, sent ACK back to client '{client_address}'"
        )

        post_queue.task_done()


def _get(worker, get_queue, destroy_event, base_dir_jobs):
    """
    Thread to receive GET requests and retrieve results from the hard disk.

    Args:
        worker (Worker): The worker instance handling the request.
        get_queue (queue.Queue): The queue from which GET requests are received.
        destroy_event (threading.Event): Event to signal the thread to stop.
        base_dir_jobs (str): The base directory where job results are stored.
    """
    while not destroy_event.is_set():
        try:
            work = get_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue

        client_address = work[0]
        suuid = work[2]
        rep_filename = reply_filename(suuid, base_dir_jobs)

        if os.path.exists(rep_filename):
            reply = loader(rep_filename)
        else:
            reply = [
                client_address,
                b"",
                suuid,
                b"400",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "JOB RESULTS NOT FOUND",
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


def close(delete_queue, queue_filename, destroy_event, base_dir_jobs):
    pass


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
        self.base_dir_jobs = os.path.join(self.base_dir, "jobs")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.base_dir_jobs, exist_ok=True)

        # create events and queues
        self.destroy_event = threading.Event()
        self.request_thread = None
        self.reply_thread = None
        self.close_thread = None
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

        # create queue file
        self.queue_filename = os.path.join(self.base_dir_jobs, f"{self.name}.queue.txt")
        if not os.path.exists(self.queue_filename):
            with open(self.queue_filename, "w") as f:
                pass
        self.queue_done_filename = os.path.join(
            self.base_dir_jobs, f"{self.name}.queue.done.txt"
        )
        if not os.path.exists(self.queue_done_filename):
            with open(self.queue_done_filename, "w") as f:
                pass

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
        4. Joins all the threads (request_thread, reply_thread, close_thread, event_thread, recv_thread) if they are not None, ensuring they have finished execution.
        5. Destroys the context with a linger period of 0 to immediately close all sockets.
        6. Stops the keepaliver to cease any keepalive signals.
        7. Logs an informational message indicating that the worker has been destroyed, including an optional message.

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
        if self.close_thread is not None:
            self.close_thread.join()
        if self.event_thread is not None:
            self.event_thread.join()
        if self.recv_thread:
            self.recv_thread.join()

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
        severity: str,
        **kwargs,
    ) -> None:
        """
        Handles the creation and emission of an event.

        This method takes event data, processes it, and sends it to the event queue.
        It also saves the event data locally for future reference.

        Args:
            message: The event message
            juuid: Job ID for which this event is generated
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
                severity=severity,
                **kwargs,
            )
        except Exception as e:
            log.error(f"Failed to form event data, error {e}")
            return
        event_data = event_data.model_dump(exclude_none=True)
        # emit event to the broker
        self.event_queue.put(event_data)
        # check if need to emit log for this event
        if self.inventory["logging"].get("log_events", False):
            event_log = f"EVENT {self.name}:{task} - {message}"
            if severity == "INFO":
                log.info(event_log)
            if severity == "DEBUG":
                log.debug(event_log)
            if severity == "WARNING":
                log.warning(event_log)
            if severity == "CRITICAL":
                log.critical(event_log)
            if severity == "ERROR":
                log.error(event_log)
        # save event locally
        filename = event_filename(juuid, self.base_dir_jobs)
        events = loader(filename) if os.path.exists(filename) else []
        events.append(event_data)
        dumper(events, filename)

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
        job = None
        with queue_file_lock:
            with open(self.queue_done_filename, "rb+") as f:
                for entry in f.readlines():
                    job_data, job_result, job_events = None, None, []
                    job_entry = entry.decode("utf-8").strip()
                    suuid, start, end = job_entry.split("--")  # {suuid}--startend
                    if suuid != uuid:
                        continue
                    # load job request details
                    client_address, empty, juuid, job_data_bytes = loader(
                        request_filename(suuid, self.base_dir_jobs)
                    )
                    if data:
                        job_data = json.loads(job_data_bytes.decode("utf-8"))
                    # load job result details
                    if result:
                        rep_filename = reply_filename(suuid, self.base_dir_jobs)
                        if os.path.exists(rep_filename):
                            job_result = loader(rep_filename)
                            job_result = json.loads(job_result[-1].decode("utf-8"))
                            job_result = job_result[self.name]
                    # load event details
                    if events:
                        events_filename = event_filename(suuid, self.base_dir_jobs)
                        if os.path.exists(events_filename):
                            job_events = loader(events_filename)

                    job = {
                        "uuid": suuid,
                        "client": client_address.decode("utf-8"),
                        "received_timestamp": start,
                        "done_timestamp": end,
                        "status": "COMPLETED",
                        "job_data": job_data,
                        "job_result": job_result,
                        "job_events": job_events,
                    }

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
        job_pending = []
        # load pending jobs
        if pending is True:
            with queue_file_lock:
                with open(self.queue_filename, "rb+") as f:
                    for entry in f.readlines():
                        job_entry = entry.decode("utf-8").strip()
                        suuid, start = job_entry.split("--")  # {suuid}--start
                        suuid = suuid.lstrip("+")  # remove job started indicator
                        if uuid and uuid != suuid:
                            continue
                        client_address, empty, juuid, data = loader(
                            request_filename(suuid, self.base_dir_jobs)
                        )
                        if client and client_address.decode("utf-8") != client:
                            continue
                        job_task = json.loads(data.decode("utf-8"))["task"]
                        # check if need to skip this job
                        if task and job_task != task:
                            continue
                        job_pending.append(
                            {
                                "uuid": suuid,
                                "client": client_address.decode("utf-8"),
                                "received_timestamp": start,
                                "done_timestamp": None,
                                "task": job_task,
                                "status": "PENDING",
                                "worker": self.name,
                                "service": self.service.decode("utf-8"),
                            }
                        )
        job_completed = []
        # load done jobs
        if completed is True:
            with queue_file_lock:
                with open(self.queue_done_filename, "rb+") as f:
                    for entry in f.readlines():
                        job_entry = entry.decode("utf-8").strip()
                        suuid, start, end = job_entry.split("--")  # {suuid}--startend
                        if uuid and suuid != uuid:
                            continue
                        client_address, empty, juuid, data = loader(
                            request_filename(suuid, self.base_dir_jobs)
                        )
                        if client and client_address.decode("utf-8") != client:
                            continue
                        job_task = json.loads(data.decode("utf-8"))["task"]
                        # check if need to skip this job
                        if task and job_task != task:
                            continue
                        job_completed.append(
                            {
                                "uuid": suuid,
                                "client": client_address.decode("utf-8"),
                                "received_timestamp": start,
                                "done_timestamp": end,
                                "task": job_task,
                                "status": "COMPLETED",
                                "worker": self.name,
                                "service": self.service.decode("utf-8"),
                            }
                        )
        if last:
            return Result(
                task=f"{self.name}:job_list",
                result=job_completed[len(job_completed) - last :]
                + job_pending[len(job_pending) - last :],
            )
        else:
            return Result(
                task=f"{self.name}:job_list",
                result=job_completed + job_pending,
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
            - close_thread: Handles closing operations using the close function.
            - event_thread: Handles event processing using the _event function.
            - recv_thread: Handles receiving data using the recv function.

        Each thread is started as a daemon and is provided with the necessary arguments,
        including queues, filenames, events, and base directory paths as required.

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
                self.queue_filename,
                self.destroy_event,
                self.base_dir_jobs,
            ),
        )
        self.request_thread.start()
        self.reply_thread = threading.Thread(
            target=_get,
            daemon=True,
            name=f"{self.name}_get_thread",
            args=(self, self.get_queue, self.destroy_event, self.base_dir_jobs),
        )
        self.reply_thread.start()
        self.close_thread = threading.Thread(
            target=close,
            daemon=True,
            name=f"{self.name}_close_thread",
            args=(
                self.delete_queue,
                self.queue_filename,
                self.destroy_event,
                self.base_dir_jobs,
            ),
        )
        self.close_thread.start()
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

    def run_next_job(self, entry):
        """
        Processes the next job in the queue based on the provided job entry.

        This method performs the following steps:

        1. Loads job data from the job queue using the entry identifier.
        2. Parses the job data to extract the task name, arguments, keyword arguments, and timeout.
        3. Executes the specified task method on the worker instance with the provided arguments.
        4. Handles any exceptions raised during task execution, logging errors and creating a failed Result object if needed.
        5. Saves the result of the job execution to a reply file for the client.
        6. Marks the job as processed by removing it from the queue file and appending it to the queue done file.

        Args:
            entry (str): The job queue entry string, typically containing the job's unique identifier.

        Raises:
            TypeError: If the executed task does not return a Result object.
        """
        # load job data
        suuid = entry.split("--")[0]  # {suuid}--start

        log.debug(f"{self.name} - processing job request {suuid}")

        client_address, empty, juuid, data = loader(
            request_filename(suuid, self.base_dir_jobs)
        )

        data = json.loads(data)
        task = data.pop("task")
        args = data.pop("args", [])
        kwargs = data.pop("kwargs", {})
        timeout = data.pop("timeout", 60)

        job = Job(
            worker=self,
            client_address=client_address.decode("utf-8"),
            juuid=juuid.decode("utf-8"),
            task=task,
            timeout=timeout,
            args=copy.deepcopy(args),
            kwargs=copy.deepcopy(kwargs),
        )

        log.debug(
            f"{self.name} - doing task '{task}', timeout: '{timeout}', data: "
            f"'{data}', args: '{args}', kwargs: '{kwargs}', client: "
            f"'{client_address}', job uuid: '{juuid}'"
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
                    f"{self.name} - task '{task}' did not return Result object, data: {data}, args: '{args}', "
                    f"kwargs: '{kwargs}', client: '{client_address}', job uuid: '{juuid}'; task returned '{type(result)}'"
                )
            result.task = result.task or f"{self.name}:{task}"
            result.status = result.status or "completed"
            result.juuid = result.juuid or juuid.decode("utf-8")
            result.service = self.service.decode("utf-8")
        except Exception as e:
            task_completed = time.ctime()
            result = Result(
                task=f"{self.name}:{task}",
                errors=[traceback.format_exc()],
                messages=[f"Worker experienced error: '{e}'"],
                failed=True,
                juuid=juuid.decode("utf-8"),
            )
            log.error(
                f"{self.name} - worker experienced error:\n{traceback.format_exc()}"
            )
        result.task_started = task_started
        result.task_completed = task_completed

        # save job results to reply file
        dumper(
            [
                client_address,
                b"",
                suuid.encode("utf-8"),
                b"200",
                json.dumps({self.name: result.model_dump()}).encode("utf-8"),
            ],
            reply_filename(suuid, self.base_dir_jobs),
        )

        # mark job entry as processed - remove from queue file and save into queue done file
        with queue_file_lock:
            with open(self.queue_filename, "rb+") as qf:
                with open(self.queue_done_filename, "rb+") as qdf:
                    qdf.seek(0, os.SEEK_END)  # go to the end
                    entries = qf.readlines()
                    qf.seek(0, os.SEEK_SET)  # go to the beginning
                    qf.truncate()  # empty file content
                    for entry in entries:
                        entry = entry.decode("utf-8").strip()
                        # save done entry to queue_done_filename
                        if suuid in entry:
                            entry = f"{entry.lstrip('+')}--{time.ctime()}\n".encode(
                                "utf-8"
                            )
                            qdf.write(entry)
                        # re-save remaining entries to queue_filename
                        else:
                            qf.write(f"{entry}\n".encode("utf-8"))

    def work(self):
        """
        Executes the main worker loop, managing job execution using a thread pool.

        This method starts necessary background threads, then enters a loop where it:

        - Acquires a lock to safely read and modify the job queue file.
        - Searches for the next unstarted job entry, marks it as started, and updates the queue file.
        - Submits the job to a thread pool executor for concurrent processing.
        - Waits briefly if no unstarted jobs are found.
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
                # extract next job id
                with queue_file_lock:
                    with open(self.queue_filename, "rb+") as qf:
                        entries = [
                            e.decode("utf-8").strip() for e in qf.readlines()
                        ]  # read jobs
                        if not entries:  # cycle until file is not empty
                            time.sleep(0.1)
                            continue
                        qf.seek(0, os.SEEK_SET)  # go to the beginning
                        qf.truncate()  # empty file content
                        for index, entry in enumerate(entries):
                            # grab entry that is not started
                            if entry and not entry.startswith("+"):
                                entries[index] = f"+{entry}"  # mark job as started
                                # save job entries back
                                entries = "\n".join(entries) + "\n"
                                qf.write(entries.encode("utf-8"))
                                break
                        else:
                            # save job entries back
                            entries = "\n".join(entries) + "\n"
                            qf.write(entries.encode("utf-8"))
                            time.sleep(0.1)
                            continue
                # submit the job to workers
                executor.submit(self.run_next_job, entry)

        # make sure to clean up
        self.destroy(
            f"{self.name} - exit event is set '{self.exit_event.is_set()}', "
            f"destroy event is set '{self.destroy_event.is_set()}'"
        )
