import logging
import sqlite3
import base64
import zlib
import zmq
import time
import json
import os
import threading
import queue
import hashlib
from contextlib import contextmanager
from uuid import uuid4  # random uuid

from .security import generate_certificates
from . import NFP
from norfab.core.inventory import NorFabInventory
from norfab.utils.markdown_results import markdown_results
from typing import Any, Optional, Tuple, Iterator, Dict, List, Set, Union

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NIRFAB client, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------


class ClientJobDatabase:
    """Lightweight client-side job and events store."""

    def __init__(self, db_path: str, jobs_compress: bool = True):
        self.db_path = db_path
        self.jobs_compress = jobs_compress
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _transaction(self, write: bool = False):
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
            yield conn

    def _compress(self, data: Dict | List | Any) -> str:
        if not self.jobs_compress:
            return json.dumps(data)
        raw = json.dumps(data).encode("utf-8")
        return base64.b64encode(zlib.compress(raw)).decode("utf-8")

    def _decompress(self, payload: str) -> Any:
        if payload is None:
            return None
        if not self.jobs_compress:
            return json.loads(payload)
        raw = base64.b64decode(payload.encode("utf-8"))
        return json.loads(zlib.decompress(raw).decode("utf-8"))

    def _initialize_database(self) -> None:
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    uuid TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    task TEXT NOT NULL,
                    args TEXT,
                    kwargs TEXT,
                    timeout INTEGER,
                    retry INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'NEW',
                    workers_requested TEXT,
                    workers_dispatched TEXT,
                    workers_started TEXT,
                    workers_completed TEXT,
                    result_data TEXT,
                    errors TEXT,
                    received_timestamp TEXT NOT NULL,
                    started_timestamp TEXT,
                    completed_timestamp TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_service ON jobs(service)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_job_uuid ON events(job_uuid)"
            )

    def add_job(
        self,
        uuid: str,
        service: str,
        task: str,
        workers: Any,
        args: list,
        kwargs: dict,
        timeout: int,
        retry: int = 0,
    ) -> None:
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO jobs (uuid, service, task, args, kwargs, timeout,
                                  retry, status, workers_requested, received_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?)
                """,
                (
                    uuid,
                    service,
                    task,
                    self._compress({"args": args or []}),
                    self._compress({"kwargs": kwargs or {}}),
                    timeout,
                    retry,
                    json.dumps(workers),
                    time.ctime(),
                ),
            )

    def update_job(
        self,
        uuid: str,
        *,
        status: str | None = None,
        workers_dispatched: Set[str] | None = None,
        workers_started: Set[str] | None = None,
        workers_completed: Set[str] | None = None,
        result_data: dict | None = None,
        errors: List[str] | None = None,
        started_ts: str | None = None,
        completed_ts: str | None = None,
        retry: int | None = None,
    ) -> None:
        fields = []
        values: List[Any] = []

        def _store_set(label: str, value: Set[str] | None):
            if value is None:
                return
            fields.append(f"{label} = ?")
            values.append(json.dumps(sorted(value)))

        if status:
            fields.append("status = ?")
            values.append(status)
        _store_set("workers_dispatched", workers_dispatched)
        _store_set("workers_started", workers_started)
        _store_set("workers_completed", workers_completed)
        if result_data is not None:
            fields.append("result_data = ?")
            values.append(self._compress(result_data))
        if errors is not None:
            fields.append("errors = ?")
            values.append(json.dumps(errors))
        if started_ts:
            fields.append("started_timestamp = ?")
            values.append(started_ts)
        if completed_ts:
            fields.append("completed_timestamp = ?")
            values.append(completed_ts)
        if retry is not None:
            fields.append("retry = ?")
            values.append(retry)

        if not fields:
            return

        fields.append("created_at = created_at")  # keeps SQL valid when join lists
        with self._transaction(write=True) as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(fields)} WHERE uuid = ?",
                (*values, uuid),
            )

    def fetch_jobs(self, statuses: List[str], limit: int = 10) -> List[dict]:
        placeholders = ",".join(["?"] * len(statuses))
        with self._transaction(write=False) as conn:
            cur = conn.execute(
                f"""
                  SELECT uuid, service, task, args, kwargs, workers_requested, timeout, retry,
                      workers_dispatched, workers_started, workers_completed, status
                FROM jobs
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (*statuses, limit),
            )
            rows = cur.fetchall()
        return [self._hydrate(row) for row in rows]

    def get_job(self, uuid: str) -> dict | None:
        with self._transaction(write=False) as conn:
            cur = conn.execute(
                """
                  SELECT uuid, service, task, args, kwargs, timeout, retry, status,
                       workers_requested, workers_dispatched, workers_started,
                       workers_completed, result_data, errors
                FROM jobs WHERE uuid = ?
                """,
                (uuid,),
            )
            row = cur.fetchone()
        return self._hydrate(row) if row else None

    def _hydrate(self, row: sqlite3.Row) -> dict:
        if row is None:
            return None
        data = dict(row)
        data["args"] = self._decompress(data.get("args")) or {"args": []}
        data["kwargs"] = self._decompress(data.get("kwargs")) or {"kwargs": {}}
        data["args"] = data["args"].get("args", [])
        data["kwargs"] = data["kwargs"].get("kwargs", {})
        for field in [
            "workers_requested",
            "workers_dispatched",
            "workers_started",
            "workers_completed",
        ]:
            if data.get(field):
                data[field] = json.loads(data[field])
            else:
                data[field] = []
        if data.get("result_data"):
            data["result_data"] = self._decompress(data["result_data"])
        if data.get("errors"):
            data["errors"] = json.loads(data["errors"])
        else:
            data["errors"] = []
        data["retry"] = data.get("retry", 0) or 0
        return data

    def add_event(
        self,
        job_uuid: str,
        message: str,
        severity: str = "INFO",
        task: str | None = None,
        event_data: dict | None = None,
    ) -> None:
        with self._transaction(write=True) as conn:
            conn.execute(
                """
                INSERT INTO events (job_uuid, message, severity, task, event_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_uuid,
                    message,
                    severity,
                    task,
                    self._compress(json.dumps(event_data or {})),
                ),
            )

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")


def recv(client):
    """
    Thread to process and handle received messages from a broker.

    This function continuously polls the client's broker socket for messages
    until the client's exit event is set. It processes the received messages
    and places them into the appropriate queues based on the message type.

    Args:
        client (object): The client instance containing the broker socket,
                         poller, and queues for handling messages.

    Raises:
        KeyboardInterrupt: If the polling is interrupted by a keyboard interrupt.
    """
    while not client.exit_event.is_set():
        # Poll socket for messages every 1000ms interval
        try:
            items = client.poller.poll(1000)
        except KeyboardInterrupt:
            break  # Interrupted
        except:
            continue
        if items:
            with client.socket_lock:
                msg = client.broker_socket.recv_multipart()
            log.debug(f"{client.name} - received '{msg}'")
            if msg[2] == NFP.EVENT:
                # sample event message:
                # [
                #   b'',
                #   b'NFPC01',
                #   b'0x08',
                #   b'nornir',
                #   b'd5433e88c6a0460fa695e2981aa593f6',
                #   b'200',
                #   b'{
                #       "worker": "nornir-worker-1",
                #       "service": "nornir",
                #       "uuid": "d5433e88c6a0460fa695e2981aa593f6",
                #       "message": "Task completed",
                #       "task": "cli.netmiko_send_commands",
                #       "status": "completed",
                #       "resource": ["ceos-spine-1", "ceos-spine-2"],
                #       "severity": "INFO",
                #       "timestamp": "04-Jan-2026 10:00:06.512",
                #       "extras": {}
                #   }'
                # ]
                client.event_queue.put(msg)
                client.stats_recv_event_from_broker += 1
                try:
                    payload = msg[-1]
                    event = json.loads(payload.decode("utf-8"))
                    juuid = event.get("uuid")
                    client.job_db.add_event(
                        job_uuid=juuid,
                        message=event["message"],
                        severity=event["severity"],
                        task=event["task"],
                        event_data=event,
                    )
                except Exception:
                    log.error(
                        f"{client.name} - failed to store event '{msg}'", exc_info=True
                    )
            else:
                client.recv_queue.put(msg)
                client.stats_recv_from_broker += 1


class NFPClient(object):
    """
    NFPClient is a client class for interacting with a broker using ZeroMQ for messaging.
    It handles sending and receiving messages, managing connections, and performing tasks.

    Attributes:
        broker (str): The broker address.
        ctx (zmq.Context): The ZeroMQ context.
        broker_socket (zmq.Socket): The ZeroMQ socket for communication with the broker.
        poller (zmq.Poller): The ZeroMQ poller for managing socket events.
        name (str): The name of the client.
        stats_send_to_broker (int): Counter for messages sent to the broker.
        stats_recv_from_broker (int): Counter for messages received from the broker.
        stats_reconnect_to_broker (int): Counter for reconnections to the broker.
        stats_recv_event_from_broker (int): Counter for events received from the broker.
        client_private_key_file (str): Path to the client's private key file.
        broker_public_key_file (str): Path to the broker's public key file.

    Methods:
        __init__(inventory, broker, name, exit_event=None, event_queue=None):
            Initializes the NFPClient instance with the given parameters.
        ensure_bytes(workers) -> bytes:
            Helper function to convert workers target to bytes.
        reconnect_to_broker():
            Connects or reconnects to the broker.
        send_to_broker(command, service, workers, uuid, request):
            Sends a message to the broker.
        rcv_from_broker(command, service, uuid):
            Waits for a response from the broker.
        post(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job request to the broker and returns the result.
        get(service, task=None, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results.
        get_iter(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results and yields results iteratively.
        fetch_file(url, destination=None, chunk_size=250000, pipiline=10, timeout=600, read=False):
            Downloads a file from the Broker File Sharing Service.
        run_job(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600, retry=10):
            Runs a job and returns results produced by workers.
        run_job_iter(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600):
            Runs a job and yields results produced by workers iteratively.
        destroy():
            Cleans up and destroys the client instance.

    Args:
        inventory (NorFabInventory): The inventory object containing base directory information.
        broker: The broker object for communication.
        name (str): The name of the client.
        exit_event (threading.Event, optional): An event to signal client exit. Defaults to None.
        event_queue (queue.Queue, optional): A queue for handling events. Defaults to None.
    """

    broker = None
    ctx = None
    broker_socket = None
    poller = None
    name = None
    stats_send_to_broker = 0
    stats_recv_from_broker = 0
    stats_reconnect_to_broker = 0
    stats_recv_event_from_broker = 0
    client_private_key_file = None
    broker_public_key_file = None
    public_keys_dir = None
    private_keys_dir = None

    def __init__(
        self,
        inventory: NorFabInventory,
        broker: str,
        name: str,
        exit_event: Optional[threading.Event] = None,
        event_queue: Optional[queue.Queue] = None,
    ):
        self.inventory = inventory
        self.name = name
        self.zmq_name = f"{self.name}-{uuid4().hex}"
        self.broker = broker
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "client", self.name
        )
        self.running_job = None
        self.zmq_auth = self.inventory.broker.get("zmq_auth", True)
        self.socket_lock = threading.Lock()  # used to protect socket object
        self.build_message = NFP.MessageBuilder()

        # create base directories
        os.makedirs(self.base_dir, exist_ok=True)

        self.job_db = ClientJobDatabase(
            os.path.join(self.base_dir, f"{self.name}.db"),
            jobs_compress=True,
        )

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
            self.private_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        self.exit_event = threading.Event() if exit_event is None else exit_event
        self.destroy_event = (
            threading.Event()
        )  # destroy event, used by worker to stop its client
        self.recv_queue = queue.Queue(maxsize=0)
        self.event_queue = event_queue or queue.Queue(maxsize=1000)

        # start receive thread
        self.recv_thread = threading.Thread(
            target=recv, daemon=True, name=f"{self.name}_recv_thread", args=(self,)
        )
        self.recv_thread.start()

        # start run-to-completion thread
        self.job_runner_thread = threading.Thread(
            target=self._run_jobs_to_completion,
            daemon=True,
            name=f"{self.name}_job_runner",
        )
        self.job_runner_thread.start()

    def ensure_bytes(self, value: Any) -> bytes:
        """
        Helper function to convert value to bytes.
        """
        if isinstance(value, bytes):
            return value
        # transform string to bytes
        if isinstance(value, str):
            return value.encode("utf-8")
        # convert value to json string
        else:
            return json.dumps(value).encode("utf-8")

    def reconnect_to_broker(self):
        """
        Connect or reconnect to the broker.

        This method handles the connection or reconnection to the broker by:

        - Closing the existing broker socket if it exists.
        - Creating a new DEALER socket.
        - Setting the socket options including the identity and linger.
        - Loading the client's private and public keys for CURVE encryption.
        - Loading the broker's public key for CURVE encryption.
        - Connecting the socket to the broker.
        - Registering the socket with the poller for incoming messages.
        - Logging the connection status.
        - Incrementing the reconnect statistics counter.
        """
        if self.broker_socket:
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)
        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.zmq_name, "utf8")
        self.broker_socket.linger = 0

        if self.zmq_auth is not False:
            # We need two certificates, one for the client and one for
            # the server. The client must know the server's public key
            # to make a CURVE connection.
            self.client_private_key_file = os.path.join(
                self.private_keys_dir, f"{self.name}.key_secret"
            )
            client_public, client_secret = zmq.auth.load_certificate(
                self.client_private_key_file
            )
            self.broker_socket.curve_secretkey = client_secret
            self.broker_socket.curve_publickey = client_public

            # The client must know the server's public key to make a CURVE connection.
            self.broker_public_key_file = os.path.join(
                self.public_keys_dir, "broker.key"
            )
            server_public, _ = zmq.auth.load_certificate(self.broker_public_key_file)
            self.broker_socket.curve_serverkey = server_public

        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)
        log.debug(f"{self.name} - client connected to broker at '{self.broker}'")
        self.stats_reconnect_to_broker += 1

    def send_to_broker(self, command, service, workers, uuid, request):
        """
        Sends a command to the broker.

        Args:
            command (str): The command to send (e.g., NFP.POST, NFP.GET).
            service (str): The service to which the command is related.
            workers (str): The workers involved in the command.
            uuid (str): The unique identifier for the request.
            request (str): The request payload to be sent.
        """
        if command == NFP.POST:
            msg = self.build_message.client_to_broker_post(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        elif command == NFP.GET:
            msg = self.build_message.client_to_broker_get(
                command=command,
                service=service,
                workers=workers,
                uuid=uuid,
                request=request,
            )
        else:
            log.error(
                f"{self.name} - cannot send '{command}' to broker, command unsupported"
            )
            return

        log.debug(f"{self.name} - sending '{msg}'")

        with self.socket_lock:
            self.broker_socket.send_multipart(msg)
            self.stats_send_to_broker += 1

    def rcv_from_broker(
        self, command: bytes, service: bytes, uuid: bytes
    ) -> Tuple[Any, Any]:
        """
        Wait for a response from the broker for a given command, service, and uuid.

        Args:
            command (str): The command sent to the broker.
            service (str): The service to which the command is sent.
            uuid (str): The unique identifier for the request.

        Returns:
            tuple: A tuple containing the reply status and the reply task result.

        Raises:
            AssertionError: If the reply header, command, or service does not match the expected values.
        """
        retries = 3
        while retries > 0:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
                break
            try:
                msg = self.recv_queue.get(block=True, timeout=3)
                self.recv_queue.task_done()
            except queue.Empty:
                if retries:
                    log.warning(
                        f"{self.name} - '{uuid}:{service}:{command}' job, "
                        f"no reply from broker '{self.broker}', reconnecting"
                    )
                    self.reconnect_to_broker()
                retries -= 1
                continue

            (
                empty,
                reply_header,
                reply_command,
                reply_service,
                reply_uuid,
                reply_status,
                reply_task_result,
            ) = msg

            # find message from recv queue for given uuid
            if reply_uuid == uuid:
                assert (
                    reply_header == NFP.CLIENT
                ), f"Was expecting client header '{NFP.CLIENT}' received '{reply_header}'"
                assert (
                    reply_command == command
                ), f"Was expecting reply command '{command}' received '{reply_command}'"
                if service != b"all":
                    assert (
                        reply_service == service
                    ), f"Was expecting reply from '{service}' but received reply from '{reply_service}' service"

                return reply_status, reply_task_result
            else:
                self.recv_queue.put(msg)
        else:
            log.error(
                f"{self.name} - '{uuid}:{service}:{command}' job, "
                f"client {retries} retries attempts exceeded"
            )
            return b"408", b'{"status": "Request Timeout"}'

    def post(
        self,
        service: str,
        task: str,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        uuid: hex = None,
        timeout: int = 600,
    ) -> dict:
        """
        Send a job POST request to the broker.

        Args:
            service (str): The name of the service to send the request to.
            task (str): The task to be executed by the service.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to handle the task. Defaults to "all".
            uuid (hex, optional): The unique identifier for the job. Defaults to None.
            timeout (int, optional): The timeout for the request in seconds. Defaults to 600.

        Returns:
            A dictionary containing the ``status``, ``workers``, ``errors``, and ``uuid`` keys of the request:

                - ``status``: Status of the request.
                - ``uuid``: Unique identifier of the request.
                - ``errors``: List of error strings.
                - ``workers``: A list of worker names who acknowledged this POST request.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        ret = {"status": b"200", "workers": [], "errors": [], "uuid": uuid}

        service = self.ensure_bytes(service)
        uuid = self.ensure_bytes(uuid)
        workers = self.ensure_bytes(workers)

        request = self.ensure_bytes(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        )

        # run POST response loop
        start_time = time.time()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
                return ret
            self.send_to_broker(
                NFP.POST, service, workers, uuid, request
            )  # 1 send POST to broker
            status, post_response = self.rcv_from_broker(
                NFP.RESPONSE, service, uuid
            )  # 2 receive RESPONSE from broker
            if status == b"202":  # 3 go over RESPONSE status and decide what to do
                break
            else:
                msg = f"{self.name} - '{uuid}' job, POST Request not accepted by broker '{post_response}'"
                log.error(msg)
                ret["errors"].append(msg)
                ret["status"] = status
                return ret
        else:
            msg = f"{self.name} - '{uuid}' job, broker POST Request Timeout"
            log.error(msg)
            ret["errors"].append(msg)
            ret["status"] = b"408"
            return ret

        # get a list of workers where job was dispatched to
        post_response = json.loads(post_response)

        assert (
            "workers" in post_response
        ), f"{self.name} - '{uuid}' job, POST response missing 'workers' {post_response}"

        workers_dispatched = set(post_response["workers"])
        log.debug(
            f"{self.name} - broker dispatched job '{uuid}' POST request to workers {workers_dispatched}"
        )

        # wait workers to ACK POSTed job
        start_time = time.time()
        workers_acked = set()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
                return ret
            status, response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            response = json.loads(response)
            if status == b"202":  # ACCEPTED
                log.debug(
                    f"{self.name} - '{uuid}' job, acknowledged by worker '{response}'"
                )
                workers_acked.add(response["worker"])
                if workers_acked == workers_dispatched:
                    break
            else:
                msg = (
                    f"{self.name} - '{uuid}:{service}:{task}' job, "
                    f"unexpected POST request status '{status}', response '{response}'"
                )
                log.error(msg)
                ret["errors"].append(msg)
        else:
            msg = (
                f"{self.name} - '{uuid}' job, POST request timeout exceeded, these workers did not "
                f"acknowledge the job {workers_dispatched - workers_acked}"
            )
            log.error(msg)
            ret["errors"].append(msg)
            ret["status"] = b"408"

        ret["workers"] = list(workers_acked)
        ret["status"] = ret["status"].decode("utf-8")

        log.debug(f"{self.name} - '{uuid}' job POST request completed '{ret}'")

        return ret

    def get(
        self,
        service: str,
        task: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: Union[str, list] = "all",
        uuid: hex = None,
        timeout: int = 600,
    ) -> dict:
        """
        Send job GET request message to broker requesting job results.

        Args:
            task (str): service task name to run
            args (list): list of positional arguments for the task
            kwargs (dict): dictionary of keyword arguments for the task
            workers (list): workers to target - ``all``, ``any``, or list of workers' names
            timeout (int): job timeout in seconds, for how long client waits for job result before giving up

        Returns:
            Dictionary containing ``status``, ``results``, ``errors``, and ``workers`` keys:

                - ``status``: Status of the request.
                - ``results``: Dictionary keyed by workers' names containing the results.
                - ``errors``: List of error strings.
                - ``workers``: Dictionary containing worker states (requested, done, dispatched, pending).
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        wkrs = {
            "requested": workers,
            "done": set(),
            "dispatched": set(),
            "pending": set(),
        }
        ret = {"status": b"200", "results": {}, "errors": [], "workers": wkrs}

        service = self.ensure_bytes(service)
        uuid = self.ensure_bytes(uuid)
        workers = self.ensure_bytes(workers)

        request = self.ensure_bytes(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        )

        # run GET response loop
        start_time = time.time()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
                return None
            # dispatch GET request to workers
            self.send_to_broker(NFP.GET, service, workers, uuid, request)
            status, get_response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            # ret["status"] = status
            # received actual GET request results from broker e.g. MMI, SID or FSS services
            if status == b"200":
                ret["results"] = json.loads(get_response.decode("utf-8"))
                break
            # received non DISPATCH response from broker
            if status != b"202":
                msg = f"{status}, {self.name} job '{uuid}' GET Request not accepted by broker '{get_response}'"
                log.error(msg)
                ret["status"] = status
                ret["errors"].append(msg)
                break
            get_response = json.loads(get_response)
            wkrs["dispatched"] = set(get_response["workers"])
            # collect GET responses from individual workers
            workers_responded = set()
            while timeout > time.time() - start_time:
                # check if need to stop
                if self.exit_event.is_set() or self.destroy_event.is_set():
                    return None
                status, response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
                log.debug(
                    f"{self.name} - job '{uuid}' response from worker '{response}'"
                )
                response = json.loads(response)  # dictionary keyed by worker name
                if status == b"200":  # OK
                    ret["results"].update(response)
                    log.debug(
                        f"{self.name} - job '{uuid}' results returned by worker '{response}'"
                    )
                    for w in response.keys():
                        wkrs["done"].add(w)
                        workers_responded.add(w)
                        if w in wkrs["pending"]:
                            wkrs["pending"].remove(w)
                    if wkrs["done"] == wkrs["dispatched"]:
                        break
                elif status == b"300":  # PENDING
                    wkrs["pending"].add(response["worker"])
                    workers_responded.add(response["worker"])
                else:
                    if response.get("worker"):
                        workers_responded.add(response["worker"])
                    msg = (
                        f"{self.name} - '{uuid}:{service}:{task}' job, "
                        f"unexpected GET Response status '{status}', response '{response}'"
                    )
                    log.error(msg)
                    ret["errors"].append(msg)
                if workers_responded == wkrs["dispatched"]:
                    break
            if wkrs["done"] == wkrs["dispatched"]:
                break
            time.sleep(0.2)
        else:
            msg = f"{self.name} - '{uuid}' job, broker {timeout}s GET request timeout expired"
            log.info(msg)
            ret["errors"].append(msg)
            # set status to pending if at least one worker is pending
            if wkrs["pending"]:
                ret["status"] = b"300"  # PENDING
            else:
                ret["status"] = b"408"  # TIMEOUT

        if ret["status"] == b"408":
            ret["status"] = "408"
        # set status to pending if at least one worker is pending
        elif wkrs["pending"]:
            ret["status"] = "300"
        else:
            ret["status"] = ret["status"].decode("utf-8")

        return ret

    def _process_new_jobs(self):
        for job in self.job_db.fetch_jobs(["NEW"], limit=5):
            deadline = job.get("timeout")
            now = time.time()
            if deadline and now >= deadline:
                self.job_db.update_job(
                    job["uuid"],
                    status="FAILED",
                    errors=["POST timeout reached"],
                    completed_ts=time.ctime(),
                )
                continue
            per_call_timeout = job["timeout"]
            if deadline and isinstance(deadline, (int, float)):
                remaining = max(1, int(deadline - now))
                per_call_timeout = remaining
            try:
                post_result = self.post(
                    job["service"],
                    job["task"],
                    job["args"],
                    job["kwargs"],
                    job["workers_requested"],
                    job["uuid"],
                    per_call_timeout,
                )
                if post_result.get("status") == "200":
                    workers_dispatched = post_result["workers"]
                    self.job_db.update_job(
                        job["uuid"],
                        status="DISPATCHED",
                        workers_dispatched=list(workers_dispatched),
                        started_ts=time.ctime(),
                    )
                else:
                    self.job_db.update_job(
                        job["uuid"],
                        status="FAILED",
                        errors=post_result.get("errors", []),
                        completed_ts=time.ctime(),
                    )
            except Exception as exc:  # keep loop resilient
                msg = f"Failed to process new job: {str(exc)}"
                log.error(msg, exc_info=True)
                self.job_db.update_job(
                    job["uuid"],
                    status="FAILED",
                    errors=[msg],
                    completed_ts=time.ctime(),
                )

    def _process_active_jobs(self):
        active_statuses = ["DISPATCHED", "SUBMITTED", "STARTED"]
        for job in self.job_db.fetch_jobs(active_statuses, limit=10):
            retries_left = int(job.get("retry", 0) or 0)
            deadline = job["timeout"]
            now = time.time()
            if now >= deadline:
                self.job_db.update_job(
                    job["uuid"],
                    status="FAILED",
                    errors=["GET timeout reached"],
                    completed_ts=time.ctime(),
                    retry=retries_left,
                )
                continue

            remaining = max(1, int(deadline - now))
            per_call_timeout = remaining / retries_left

            try:
                get_resp = self.get(
                    job["service"],
                    job["task"],
                    job["args"],
                    job["kwargs"],
                    job["workers_dispatched"],
                    job["uuid"],
                    timeout=per_call_timeout,
                )
            except Exception as exc:
                retries_left -= 1
                update_status = "FAILED" if retries_left <= 0 else job["status"]
                msg = (
                    f"Job GET error, retries left {retries_left}, exception: {str(exc)}"
                )
                log.error(msg, exc_info=True)
                self.job_db.update_job(
                    job["uuid"],
                    status=update_status,
                    errors=[msg],
                    completed_ts=time.ctime() if update_status == "FAILED" else None,
                    retry=retries_left,
                )
                continue

            status = get_resp["status"]
            workers_info = get_resp["workers"]
            dispatched = set(job["workers_dispatched"])
            started = set(job["workers_started"]) or set()
            completed = set(job["workers_completed"]) or set()

            if status == "300":  # JOB PENDING or STARTED
                retries_left -= 1
                started |= set(workers_info.get("pending", []))
                now = time.time()
                timed_out = deadline and now >= deadline
                exhausted = retries_left <= 0
                if timed_out or exhausted:
                    msg = (
                        "Job GET timeout reached"
                        if timed_out
                        else "Job GET retries exhausted"
                    )
                    log.error(msg)
                    self.job_db.update_job(
                        job["uuid"],
                        status="FAILED",
                        errors=[msg],
                        workers_started=list(started),
                        completed_ts=time.ctime(),
                        retry=retries_left,
                    )
                    continue
                self.job_db.update_job(
                    job["uuid"],
                    status="STARTED",
                    workers_started=list(started),
                    retry=retries_left,
                )
                continue

            if status == "200":  # JOB COMPLETED
                completed |= set(workers_info.get("done", []))
                started |= completed
                is_complete = completed == dispatched
                self.job_db.update_job(
                    job["uuid"],
                    status="COMPLETED" if is_complete else "STARTED",
                    workers_started=list(started),
                    workers_completed=list(completed),
                    result_data=get_resp["results"],
                    completed_ts=time.ctime() if is_complete else None,
                    retry=retries_left,
                )
                continue

            msg = f"Job GET error, unexpected status {status}, errors: {get_resp['errors']}"
            log.error(msg)
            self.job_db.update_job(
                job["uuid"],
                status="FAILED",
                errors=get_resp.get("errors", []),
                completed_ts=time.ctime(),
                retry=retries_left,
            )

    def _run_jobs_to_completion(self):
        while not self.exit_event.is_set() and not self.destroy_event.is_set():
            self._process_new_jobs()
            self._process_active_jobs()
            time.sleep(0.2)

    def fetch_file(
        self,
        url: str,
        destination: str = None,
        chunk_size: int = 250000,
        pipiline: int = 10,
        timeout: int = 600,
        read: bool = False,
    ) -> Tuple[str, Any]:
        """
        Fetches a file from a given URL and saves it to a specified destination.

        Parameters:
            url (str): The URL of the file to be fetched.
            destination (str, optional): The local path where the file should be saved. If None, a default path is used.
            chunk_size (int, optional): The size of each chunk to be fetched. Default is 250000 bytes.
            pipiline (int, optional): The number of chunks to be fetched in parallel. Default is 10.
            timeout (int, optional): The maximum time (in seconds) to wait for the file to be fetched. Default is 600 seconds.
            read (bool, optional): If True, the file content is read and returned. If False, the file path is returned. Default is False.

        Returns:
            tuple: A tuple containing the status code (str) and the reply (str). The reply can be the file content, file path, or an error message.

        Raises:
            Exception: If there is an error in fetching the file or if the file's MD5 hash does not match the expected hash.
        """
        uuid = self.ensure_bytes(str(uuid4().hex))
        total = 0  # Total bytes received
        chunks = 0  # Total chunks received
        offset = 0  # Offset of next chunk request
        credit = pipiline  # Up to PIPELINE chunks in transit
        service = b"fss.service.broker"
        workers = b"any"
        reply = ""
        status = "200"
        downloaded = False
        md5hash = None

        # define file destination
        if destination is None:
            destination = os.path.join(
                self.base_dir, "fetchedfiles", *os.path.split(url.replace("nf://", ""))
            )

        # make sure all destination directories exist
        os.makedirs(os.path.split(destination)[0], exist_ok=True)

        # get file details
        request = self.ensure_bytes({"task": "file_details", "kwargs": {"url": url}})
        self.send_to_broker(NFP.GET, service, workers, uuid, request)
        rcv_status, file_details = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
        file_details = json.loads(file_details)

        # check if file already downloaded
        if os.path.isfile(destination):
            file_hash = hashlib.md5()
            with open(destination, "rb") as f:
                chunk = f.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = f.read(8192)
            md5hash = file_hash.hexdigest()
            downloaded = md5hash == file_details["md5hash"]
            log.debug(f"{self.name} - file already downloaded, nothing to do")

        # fetch file content from broker and save to local file
        if file_details["exists"] is True and downloaded is False:
            file_hash = hashlib.md5()
            with open(destination, "wb") as dst_file:
                start_time = time.time()
                while timeout > time.time() - start_time:
                    # check if need to stop
                    if self.exit_event.is_set() or self.destroy_event.is_set():
                        return "400", ""
                    # ask for chunks
                    while credit:
                        request = self.ensure_bytes(
                            {
                                "task": "fetch_file",
                                "kwargs": {
                                    "offset": offset,
                                    "chunk_size": chunk_size,
                                    "url": url,
                                },
                            }
                        )
                        self.send_to_broker(NFP.GET, service, workers, uuid, request)
                        offset += chunk_size
                        credit -= 1
                    # receive chunks from broker
                    status, chunk = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
                    log.debug(
                        f"{self.name} - status '{status}', chunk '{chunks}', downloaded '{total}'"
                    )
                    dst_file.write(chunk)
                    file_hash.update(chunk)
                    chunks += 1
                    credit += 1
                    size = len(chunk)
                    total += size
                    if size < chunk_size:
                        break  # Last chunk received; exit
                else:
                    reply = "File download failed - timeout"
                    status = "408"
            # verify md5hash
            md5hash = file_hash.hexdigest()
        elif file_details["exists"] is False:
            reply = "File download failed - file not found"
            status = "404"

        # decide on what to reply and status
        if file_details["exists"] is not True:
            reply = reply
        elif md5hash != file_details["md5hash"]:
            reply = "File download failed - MD5 hash mismatch"
            status = "417"
        elif read:
            with open(destination, "r", encoding="utf-8") as f:
                reply = f.read()
        else:
            reply = destination
        # decode status
        if isinstance(status, bytes):
            status = status.decode("utf-8")

        return status, reply

    def run_job(
        self,
        service: str,
        task: str,
        uuid: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: Union[str, list] = "all",
        timeout: int = 600,
        retry: int = 10,
        markdown: bool = False,
    ) -> Any:
        """
        Run a job on the specified service and task, with optional arguments, timeout and retry settings.

        Args:
            service (str): The name of the service to run the job on.
            task (str): The task to be executed.
            uuid (str, optional): A unique identifier for the job. If not provided, a new UUID will be generated. Defaults to None.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to run the job on. Defaults to "all".
            timeout (int, optional): The maximum time in seconds to wait for the job to complete. Defaults to 600.
            retry (int, optional): The number of times to retry getting the job results. Defaults to 10.
            markdown (bool, optional): Convert results to markdown representation

        Returns:
            Any: The result of the job if successful, or None if the job failed or timed out.

        Raises:
            Exception: If the POST request to start the job fails or if an unexpected status is returned during the GET request.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        deadline = int(time.time() + timeout)
        result = None

        self.job_db.add_job(uuid, service, task, workers, args, kwargs, deadline, retry)

        while time.time() < deadline:
            if self.exit_event.is_set() or self.destroy_event.is_set():
                break
            job = self.job_db.get_job(uuid)
            if job["status"] == "COMPLETED":
                result = job.get("result_data")
                break
            if job["status"] == "FAILED":
                break
            time.sleep(0.2)

        return markdown_results(job, service, task, kwargs) if markdown else result

    def destroy(self):
        """
        Gracefully shuts down the client.

        This method logs an interrupt message, sets the destroy event, and
        destroys the client context to ensure a clean shutdown.
        """
        log.info(f"{self.name} - client interrupt received, killing client")
        self.destroy_event.set()
        self.job_db.close()
        self.ctx.destroy()
