import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata
import uvicorn

from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from norfab.models.fastapi import (
    ClientPostJobResponse,
    ClientGetJobResponse,
)
from typing import Union, List, Dict, Any, Annotated, Optional
from diskcache import FanoutCache
from pydantic import BaseModel
from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException, Body, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.openapi.utils import get_openapi
from starlette import status
from starlette.routing import Route

SERVICE = "fastapi"
API_TITLE = "NORFAB REST API"

log = logging.getLogger(__name__)


class UnauthorizedMessage(BaseModel):
    detail: str = "Bearer token missing or unknown"


def create_api_endpoint(
    service: str, task_name: str, schema: dict, worker: object
) -> callable:
    """
    Creates an asynchronous FastAPI endpoint function for a given service task.

    Args:
        service (str): Service name.
        task_name (str): Task name.
        schema (dict): Input schema for the task.
        worker (object): Worker instance.

    Returns:
        function: An asynchronous endpoint function

    The generated endpoint expects a JSON body containing arguments for
    the job and returns the result of the job execution.
    """
    # We will handle a missing token ourselves
    get_bearer_token = HTTPBearer(auto_error=False)
    default_workers = schema["properties"].get("workers", {}).get("default", "all")

    def get_token(
        auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    ) -> str:
        # check token exists in database
        if (
            auth is None
            or worker.bearer_token_check(auth.credentials, Job()).result is False
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=UnauthorizedMessage().detail,
            )
        return auth.credentials

    async def endpoint(
        request: Request,
        token: str = Depends(get_token),
    ) -> Dict[Annotated[str, Body(description="Worker Name")], Result]:
        kwargs = await request.json()
        workers = kwargs.pop("workers", default_workers)

        log.debug(
            f"FastAPI running '{service}:{task_name}' task, on '{workers}' workers, job data: '{kwargs}'"
        )

        res = worker.client.run_job(
            service=service,
            task=task_name,
            kwargs=kwargs,
            workers=workers,
        )
        return res

    return endpoint


def make_openapi_schema(
    app, regenerate: bool = False, json_refs: Optional[dict] = None
) -> Dict:
    """
    Generates and returns the OpenAPI schema for a FastAPI application.

    Args:
        app (FastAPI): The FastAPI application instance.
        regenerate (bool, optional): If True, forces regeneration of the OpenAPI schema.
        json_refs (dict, optional): A dictionary of JSON references to include in
            the schema under the "$defs" key.

    Returns:
        dict: The generated OpenAPI schema as a dictionary.
    """
    # make app to re-generate openapi schema
    if regenerate is True:
        app.openapi_schema = None
        app.setup()

    openapi_schema = get_openapi(title=API_TITLE, version="1", routes=app.routes)

    # add json references
    if json_refs:
        openapi_schema["$defs"] = json_refs

    return openapi_schema


def service_tasks_api_discovery(
    worker, cycles: int = 30, discover_service: str = "all"
) -> Dict:
    """
    Periodically discovers available service tasks and dynamically registers
    FastAPI endpoints for them.

    This function performs the following steps in a loop:

    1. Retrieves a list of available services from the worker's client.
    2. For each service, fetches its available tasks.
    3. For each task, checks if it should be exposed via FastAPI (i.e.,
        `task["fastapi"]` is not False).
    4. If the corresponding API endpoint does not already exist, registers a new
        FastAPI route for the task, using its input schema and metadata.
    5. Forces regeneration of the OpenAPI schema after new endpoints are added.

    The loop runs on fastapi service startup up to 30 cycles or until the worker's
    exit event is set, with a 10-second delay between cycles.
    """
    result = {}
    json_refs = {}  # dictionary to store JSON references
    while not worker.exit_event.is_set() and cycles > 0:
        tasks = []
        services = []
        try:
            # get a list of workers and construct a list of services
            services = worker.client.get("mmi.service.broker", "show_workers")
            services = [
                s["service"]
                for s in services["results"]
                if discover_service == "all" or s["service"] == discover_service
            ]

            # retrieve NorFab services and their tasks
            for service in services:
                # skip already discovered services
                if service in result:
                    continue
                service_tasks = worker.client.run_job(
                    service=service,
                    task="list_tasks",
                    workers="any",
                    timeout=3,
                )
                # skip if client request timed out
                if service_tasks is None:
                    continue
                for wres in service_tasks.values():
                    for t in wres["result"]:
                        t["service"] = service
                    tasks.extend(wres["result"])

            for task in tasks:
                # skip task endpoint creation if set to false
                if task["fastapi"] is False:
                    continue
                # save service to results
                result.setdefault(task["service"], [])
                # continue with creating API endpoint for task
                path = f"{worker.api_prefix}/{task['service']}/{task['name']}/"
                for route in worker.app.routes:
                    if isinstance(route, Route) and route.path == path:
                        break  # do no re-create existing endpoints
                else:
                    # form OpenAPI schema for API endpoint
                    schema = task["inputSchema"]
                    fastapi_schema = task["fastapi"].pop("schema", {"properties": {}})
                    schema["properties"] = {
                        **fastapi_schema["properties"],
                        **schema["properties"],
                    }
                    _ = schema["properties"].pop("job", None)
                    # extract json references
                    if "$defs" in schema:
                        json_refs.update(schema.pop("$defs"))
                    # form add_api_route arguments
                    task["fastapi"].setdefault("methods", ["POST"])
                    task["fastapi"].setdefault("path", path)
                    task["fastapi"].setdefault("description", task["description"])
                    task["fastapi"].setdefault("name", task["name"])
                    # register API endpoint
                    log.debug(
                        f"Registering API endpoint {task['fastapi']['path']}, schema: {schema}"
                    )
                    worker.app.add_api_route(
                        endpoint=create_api_endpoint(
                            service=task["service"],
                            task_name=task["name"],
                            schema=schema,
                            worker=worker,
                        ),
                        responses={
                            status.HTTP_401_UNAUTHORIZED: dict(
                                model=UnauthorizedMessage
                            )
                        },
                        openapi_extra={
                            "requestBody": {
                                "required": True,
                                "content": {"application/json": {"schema": schema}},
                            }
                        },
                        tags=[f"NORFAB {task['service'].upper()}"],
                        **task["fastapi"],
                    )
                    worker.app.openapi_schema = make_openapi_schema(
                        app=worker.app, regenerate=True, json_refs=json_refs
                    )
                    # save discovered task to results
                    result[task["service"]].append(task["fastapi"]["name"])
        except Exception as e:
            log.exception(f"Failed to discover services tasks, error: {e}")

        cycles -= 1
        time.sleep(10)

    return result


class FastAPIWorker(NFPWorker):
    """
    FastAPIWorker is a worker class that integrates with FastAPI and Uvicorn to serve a FastAPI application.
    It handles initialization, starting the server, and managing bearer tokens.

    Args:
        inventory (str): Inventory configuration for the worker.
        broker (str): Broker URL to connect to.
        worker_name (str): Name of this worker.
        exit_event (threading.Event, optional): Event to signal worker to stop/exit.
        init_done_event (threading.Event, optional): Event to signal when worker is done initializing.
        log_level (str, optional): Logging level for this worker.
        log_queue (object, optional): Queue for logging.
    """

    def __init__(
        self,
        inventory: str,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.exit_event = exit_event
        self.api_prefix = "/api"

        # get inventory from broker
        self.fastapi_inventory = self.load_inventory()
        self.uvicorn_inventory = {
            "host": "0.0.0.0",
            "port": 8000,
            **self.fastapi_inventory.pop("uvicorn", {}),
        }

        # instantiate cache
        self.cache_dir = os.path.join(self.base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self._get_diskcache()
        self.cache.expire()

        # start FastAPI server
        self.fastapi_start()

        self.service_tasks_api_discovery_thread = threading.Thread(
            target=service_tasks_api_discovery, args=(self,)
        )
        self.service_tasks_api_discovery_thread.start()

        self.init_done_event.set()

    def _get_diskcache(self) -> FanoutCache:
        """
        Initializes and returns a FanoutCache object.

        The FanoutCache is configured with the following parameters:

        - directory: The directory where the cache will be stored.
        - shards: Number of shards to use for the cache.
        - timeout: Timeout for cache operations in seconds.
        - size_limit: Maximum size of the cache in bytes.

        Returns:
            FanoutCache: An instance of FanoutCache configured with the specified parameters.
        """
        return FanoutCache(
            directory=self.cache_dir,
            shards=4,
            timeout=1,  # 1 second
            size_limit=1073741824,  #  1 GigaByte
        )

    def fastapi_start(self):
        """
        Starts the FastAPI server.

        This method initializes the FastAPI application using the provided
        configuration, starts the Uvicorn server in a separate thread, and waits
        for the server to be fully started before logging the server's URL.

        Steps:

        1. Create the FastAPI application using `make_fast_api_app`.
        2. Configure the Uvicorn server with the application and settings.
        3. Start the Uvicorn server in a new thread.
        4. Wait for the server to start.
        5. Log the server's URL.'

        Attributes:
            self.app (FastAPI): The FastAPI application instance.
            self.uvicorn_server (uvicorn.Server): The Uvicorn server instance.
            self.uvicorn_server_thread (threading.Thread): The thread running the Uvicorn server.

        Raises:
            Exception: If the server fails to start.
        """
        self.app = make_fast_api_app(
            worker=self, config=self.fastapi_inventory.get("fastapi", {})
        )

        # start uvicorn server in a thread
        config = uvicorn.Config(app=self.app, **self.uvicorn_inventory)
        self.uvicorn_server = uvicorn.Server(config=config)

        self.uvicorn_server_thread = threading.Thread(target=self.uvicorn_server.run)
        self.uvicorn_server_thread.start()

        # wait for server to start
        while not self.uvicorn_server.started:
            time.sleep(0.001)

        log.info(
            f"{self.name} - Uvicorn server started, serving FastAPI app at "
            f"http://{self.uvicorn_inventory['host']}:{self.uvicorn_inventory['port']}"
        )

    def worker_exit(self):
        """
        Terminates the current process by sending a SIGTERM signal to itself.

        This method retrieves the current process ID using `os.getpid()` and then
        sends a SIGTERM signal to terminate the process using `os.kill()`.
        """
        os.kill(os.getpid(), signal.SIGTERM)

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        """
        Produce a report of the versions of various Python packages.

        This method collects the versions of several specified Python packages
        and returns them in a dictionary.

        Returns:
            Result: An object containing the task name and a dictionary with
                    the package names as keys and their respective versions as values.
        """
        libs = {
            "norfab": "",
            "fastapi": "",
            "uvicorn": "",
            "pydantic": "",
            "python-multipart": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(task=f"{self.name}:get_version", result=libs)

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self) -> Result:
        """
        Retrieve the inventory of the FastAPI worker.

        Returns:
            Dict: A dictionary containing the combined inventory of FastAPI and Uvicorn.
        """
        return Result(
            result={**self.fastapi_inventory, "uvicorn": self.uvicorn_inventory},
            task=f"{self.name}:get_inventory",
        )

    @Task(fastapi={"methods": ["GET"]})
    def get_openapi_schema(self, paths: bool = False) -> Result:
        """
        Generates and returns the OpenAPI schema for the FastAPI application.

        Args:
            paths (bool, optional): If True, returns a list of available API endpoint paths.
                If False, returns the full OpenAPI schema. Defaults to False.

        Returns:
            Result: An object containing either the list of endpoint paths or the full OpenAPI schema
        """
        schema = make_openapi_schema(self.app)
        if paths is True:
            return Result(
                result=list(schema["paths"].keys()),
                task=f"{self.name}:get_openapi_schema",
            )
        else:
            return Result(
                result=schema,
                task=f"{self.name}:get_openapi_schema",
            )

    @Task(fastapi=False, mcp=False)
    def bearer_token_store(
        self, job: Job, username: str, token: str, expire: int = None
    ) -> Result:
        """
        Method to store a bearer token in the database.

        This method stores a bearer token associated with a username in the cache.

        If an expiration time is not provided, it retrieves the default token TTL
        from the FastAPI inventory configuration.

        Args:
            username: str - The name of the user to store the token for.
            token: str - The token string to store.
            expire: int, optional - The number of seconds before the token expires.

        Returns:
            bool - Returns True if the token is successfully stored.
        """
        expire = expire or self.fastapi_inventory.get("auth_bearer", {}).get(
            "token_ttl", expire
        )
        self.cache.expire()
        cache_key = f"bearer_token::{token}"
        if cache_key in self.cache:
            user_token = self.cache.get(cache_key)
        else:
            user_token = {
                "token": token,
                "username": username,
                "created": str(datetime.now()),
            }
        self.cache.set(cache_key, user_token, expire=expire, tag=username)

        return Result(task=f"{self.name}:bearer_token_store", result=True)

    @Task(fastapi=False, mcp=False)
    def bearer_token_delete(
        self, job: Job, username: str = None, token: str = None
    ) -> Result:
        """
        Deletes a bearer token from the cache.
        This method removes a bearer token from the cache based on either
        the token itself or the associated username.

        If a token is provided, it will be removed directly. If a username
        is provided, all tokens associated with that username will be evicted
        from the cache.

        Args:
            username (str, optional): The username associated with the token(s) to be removed. Defaults to None.
            token (str, optional): The bearer token to be removed. Defaults to None.

        Returns:
            bool: True if the operation was successful, otherwise raises an exception.

        Raises:
            RuntimeError: If the token removal from the cache fails.
            Exception: If neither username nor token is provided.
        """
        self.cache.expire()
        token_removed_count = 0
        if token:
            cache_key = f"bearer_token::{token}"
            if cache_key in self.cache:
                if self.cache.delete(cache_key, retry=True):
                    token_removed_count = 1
                else:
                    raise RuntimeError(f"Failed to remove {username} token from cache")
        elif username:
            token_removed_count = self.cache.evict(tag=username, retry=True)
        else:
            raise Exception("Cannot delete, either username or token must be provided")

        log.info(
            f"{self.name} removed {token_removed_count} token(s) for user {username}"
        )

        return Result(task=f"{self.name}:bearer_token_delete", result=True)

    @Task(fastapi=False, mcp=False)
    def bearer_token_list(self, job: Job, username: str = None) -> Result:
        """
        Retrieves a list of bearer tokens from the cache, optionally filtered by username.

        Args:
            username (str, optional): The username to filter tokens by. Defaults to None.

        Returns:
            list: A list of dictionaries containing token information. Each dictionary contains:

                - "username" (str): The username associated with the token.
                - "token" (str): The bearer token.
                - "age" (str): The age of the token.
                - "creation" (str): The creation time of the token.
                - "expires" (str): The expiration time of the token, if available.

        If no tokens are found, a list with a single dictionary containing
        empty strings for all fields is returned.
        """

        self.cache.expire()
        ret = Result(task=f"{self.name}:bearer_token_list", result=[])

        for cache_key in self.cache:
            token_data, expires, tag = self.cache.get(
                cache_key, expire_time=True, tag=True
            )
            if username and tag != username:
                continue
            if expires is not None:
                expires = datetime.fromtimestamp(expires)
            creation = datetime.fromisoformat(token_data["created"])
            age = datetime.now() - creation
            ret.result.append(
                {
                    "username": token_data["username"],
                    "token": token_data["token"],
                    "age": str(age),
                    "creation": str(creation),
                    "expires": str(expires),
                }
            )

        # return empty result if no tokens found
        if not ret.result:
            ret.result = [
                {
                    "username": "",
                    "token": "",
                    "age": "",
                    "creation": "",
                    "expires": "",
                }
            ]

        return ret

    @Task(fastapi=False, mcp=False)
    def bearer_token_check(self, token: str, job: Job) -> Result:
        """
        Checks if the provided bearer token is present in the cache and still active.

        Args:
            token (str): The bearer token to check.

        Returns:
            bool: True if the token is found in the cache, False otherwise.
        """
        self.cache.expire()
        cache_key = f"bearer_token::{token}"
        return Result(
            task=f"{self.name}:bearer_token_check", result=cache_key in self.cache
        )

    @Task(fastapi={"methods": ["POST"]})
    def discover(self, job, service: str = "all", progress: bool = True) -> Result:
        """
        Discovers available services tasks and auto-generate API endpoints for them.

        Args:
            service (str, optional): The name of the service to discover. Defaults to "all".

        Returns:
            Result: An object containing the discovery results for the specified service.
        """
        job.event("Discovering NorFab services tasks")
        ret = Result(task=f"{self.name}:discover")
        ret.result = service_tasks_api_discovery(
            self, cycles=1, discover_service=service
        )

        return ret


# ------------------------------------------------------------------
# FastAPI REST API routes endpoints
# ------------------------------------------------------------------


def make_fast_api_app(worker: object, config: dict) -> FastAPI:
    """
    Create a FastAPI application with endpoints for posting, getting, and running jobs.

    This function sets up a FastAPI application with three endpoints:

    - POST /job: To post a job to the NorFab service.
    - GET /job: To get job results from the NorFab service.
    - POST /job/run: To run a job and return job results synchronously.

    Each endpoint requires a bearer token for authentication, which is validated
    against the worker's token database.

    Args:
        worker (object): An object representing the worker that will handle the job requests.
        config (dict): A dictionary of configuration options for the FastAPI application.

    Returns:
        FastAPI: A FastAPI application instance.
    """
    config = {
        "title": API_TITLE,
        "summary": "NorFab Services Tasks FastAPI application with endpoints for posting, getting, and running jobs",
        **config,
    }
    app = FastAPI(**config)

    # We will handle a missing token ourselves
    get_bearer_token = HTTPBearer(auto_error=False)

    def get_token(
        auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    ) -> str:
        # check token exists in database
        if (
            auth is None
            or worker.bearer_token_check(auth.credentials, Job()).result is False
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=UnauthorizedMessage().detail,
            )
        return auth.credentials

    @app.post(
        f"{worker.api_prefix}/job",
        responses={status.HTTP_401_UNAUTHORIZED: dict(model=UnauthorizedMessage)},
        tags=["NORFAB"],
    )
    def post_job(
        service: Annotated[
            str, Body(description="The name of the service to post the job to")
        ],
        task: Annotated[
            str, Body(description="The task to be executed by the service")
        ],
        args: Annotated[
            List[Any], Body(description="A list of positional arguments for the task")
        ] = None,
        kwargs: Annotated[
            Dict[str, Any],
            Body(description="A dictionary of keyword arguments for the task"),
        ] = None,
        workers: Annotated[
            Union[str, List[str]], Body(description="The workers to dispatch the task")
        ] = "all",
        uuid: Annotated[
            str, Body(description="Optional a unique identifier to use for the job")
        ] = None,
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
        token: str = Depends(get_token),
    ) -> ClientPostJobResponse:
        """
        Method to post the job to NorFab.

        Args:
            service: The name of the service to post the job to.
            task: The task to be executed by the service.
            args: A list of positional arguments for the task. Defaults to None.
            kwargs: A dictionary of keyword arguments for the task. Defaults to None.
            workers: The workers to dispatch the task. Defaults to "all".
            uuid: Optional a unique identifier to use for the job. Defaults to None.
            timeout: The timeout for the job in seconds. Defaults to 600.

        Returns:
            The response from the NorFab service.
        """
        log.debug(
            f"{worker.name} - received job post request, service {service}, task {task}, args {args}, kwargs {kwargs}"
        )
        res = worker.client.post(
            service=service,
            task=task,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )
        return res

    @app.get(
        f"{worker.api_prefix}/job",
        responses={status.HTTP_401_UNAUTHORIZED: dict(model=UnauthorizedMessage)},
        tags=["NORFAB"],
    )
    def get_job(
        service: Annotated[
            str, Body(description="The name of the service to get the job from")
        ],
        uuid: Annotated[str, Body(description="A unique identifier for the job")],
        workers: Annotated[
            Union[str, List[str]],
            Body(description="The workers to dispatch the get request to"),
        ] = "all",
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
        token: str = Depends(get_token),
    ) -> ClientGetJobResponse:
        """
        Method to get job results from NorFab.

        Args:
            service: The name of the service to get the job from.
            workers: The workers to dispatch the get request to. Defaults to "all".
            uuid: A unique identifier for the job.
            timeout: The timeout for the job get requests in seconds. Defaults to 600.

        Returns:
            The response from the NorFab service.
        """
        log.debug(
            f"{worker.name} - received job get request, service {service}, uuid {uuid}"
        )
        res = worker.client.get(
            service=service,
            uuid=uuid,
            workers=workers,
            timeout=timeout,
        )
        return res

    @app.post(
        f"{worker.api_prefix}/job/run",
        responses={status.HTTP_401_UNAUTHORIZED: dict(model=UnauthorizedMessage)},
        tags=["NORFAB"],
    )
    def run_job(
        service: Annotated[
            str, Body(description="The name of the service to post the job to")
        ],
        task: Annotated[
            str, Body(description="The task to be executed by the service")
        ],
        args: Annotated[
            List[Any], Body(description="A list of positional arguments for the task")
        ] = None,
        kwargs: Annotated[
            Dict[str, Any],
            Body(description="A dictionary of keyword arguments for the task"),
        ] = None,
        workers: Annotated[
            Union[str, List[str]], Body(description="The workers to dispatch the task")
        ] = "all",
        uuid: Annotated[
            str, Body(description="Optional a unique identifier to use for the job")
        ] = None,
        timeout: Annotated[
            int, Body(description="The timeout for the job in seconds")
        ] = 600,
        retry: Annotated[
            int, Body(description="The number of times to try and GET job results")
        ] = 10,
        token: str = Depends(get_token),
    ) -> Dict[str, Result]:
        """
        Method to run job and return job results synchronously. This function
        is blocking, internally it uses post/get methods to submit job request
        and waits for job results to come through for all workers request was
        dispatched to, exiting either once timeout expires or after all workers
        reported job result back to the client.

        Args:
            service: The name of the service to post the job to.
            task: The task to be executed by the service.
            args: A list of positional arguments for the task. Defaults to None.
            kwargs: A dictionary of keyword arguments for the task. Defaults to None.
            workers: The workers to dispatch the task. Defaults to "all".
            uuid: A unique identifier for the job. Defaults to None.
            timeout: The timeout for the job in seconds. Defaults to 600.
            retry: The number of times to try and GET job results. Defaults to 10.

        Returns:
            The response from the NorFab service.
        """
        log.debug(
            f"{worker.name} - received run job request, service {service}, task {task}, args {args}, kwargs {kwargs}"
        )
        res = worker.client.run_job(
            service=service,
            task=task,
            uuid=uuid,
            args=args,
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            retry=retry,
        )
        return res

    return app
