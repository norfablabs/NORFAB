import json
import logging
import sys
import importlib.metadata
import requests
import os
import pynetbox
import re
import time

from fnmatch import fnmatchcase
from datetime import datetime, timedelta
from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from typing import Any, Union
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from .netbox_models import NetboxFastApiArgs
from diskcache import FanoutCache

from .design_tasks import NetboxDesignTasks
from .interfaces_tasks import NetboxInterfacesTasks
from .devices_tasks import NetboxDevicesTasks
from .connections_tasks import NetboxConnectionsTasks
from .netbox_exceptions import UnsupportedNetboxVersion
from .circuits_tasks import NetboxCircuitsTasks
from .nornir_inventory_tasks import NetboxNornirInventoryTasks
from .bgp_peerings_tasks import NetboxBgpPeeringsTasks
from .prefix_tasks import NetboxPrefixTasks
from .containerlab_inventory_tasks import NetboxContainerlabInventoryTasks
from .ip_tasks import NetboxIpTasks
from .branch_tasks import NetboxBranchTasks

SERVICE = "netbox"

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------


def _form_query_v4(obj, filters, fields, alias=None) -> str:
    """
    Helper function to form graphql query for Netbox version 4.

    Args:
        obj (str): The object to return data for, e.g., 'device', 'interface', 'ip_address'.
        filters (dict): A dictionary of key-value pairs to filter by.
        fields (list): A list of data fields to return.
        alias (str, optional): An alias value for the requested object.

    Returns:
        str: A formatted GraphQL query string.
    """
    filters_list = []
    fields = " ".join(fields)
    if isinstance(filters, str):
        filters = filters.replace("'", '"')  # swap quotes
        if alias:
            query = f"{alias}: {obj}(filters: {filters}) {{{fields}}}"
        else:
            query = f"{obj}(filters: {filters}) {{{fields}}}"
    elif isinstance(filters, dict):
        for k, v in filters.items():
            if isinstance(v, (list, set, tuple)):
                items = ", ".join(f'"{i}"' for i in v)
                filters_list.append(f"{k}: [{items}]")
            elif "{" in v and "}" in v:
                filters_list.append(f"{k}: {v}")
            else:
                filters_list.append(f'{k}: "{v}"')
        filters_string = ", ".join(filters_list)
        filters_string = filters_string.replace("'", '"')  # swap quotes
        if alias:
            query = f"{alias}: {obj}(filters: {{{filters_string}}}) {{{fields}}}"
        else:
            query = f"{obj}(filters: {{{filters_string}}}) {{{fields}}}"

    return query


class NetboxWorker(
    NFPWorker,
    NetboxDesignTasks,
    NetboxInterfacesTasks,
    NetboxDevicesTasks,
    NetboxConnectionsTasks,
    NetboxCircuitsTasks,
    NetboxNornirInventoryTasks,
    NetboxBgpPeeringsTasks,
    NetboxPrefixTasks,
    NetboxContainerlabInventoryTasks,
    NetboxIpTasks,
    NetboxBranchTasks,
):
    """
    NetboxWorker class for interacting with Netbox API and managing inventory.

    Args:
        inventory (dict): The inventory data.
        broker (object): The broker instance.
        worker_name (str): The name of the worker.
        exit_event (threading.Event, optional): Event to signal exit.
        init_done_event (threading.Event, optional): Event to signal initialization completion.
        log_level (int, optional): Logging level.
        log_queue (object, optional): Queue for logging.

    Raises:
        AssertionError: If the inventory has no Netbox instances.

    Attributes:
        default_instance (str): Default Netbox instance name.
        inventory (dict): Inventory data.
        nb_version (tuple): Netbox version.
        compatible_ge_v4 (tuple): Minimum supported Netbox v4 version (4.4.0+).
    """

    default_instance = None
    inventory = None
    nb_version = {}  # dict keyed by instance name and version
    compatible_ge_v4 = (
        4,
        4,
        0,
    )  # 4.4.0 - minimum supported Netbox v4

    def __init__(
        self,
        inventory,
        broker,
        worker_name,
        exit_event=None,
        init_done_event=None,
        log_level=None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.cache = None

        # get inventory from broker
        self.netbox_inventory = self.load_inventory()
        if not self.netbox_inventory:
            log.critical(
                f"{self.name} - Broker {self.broker} returned no inventory for {self.name}, killing myself..."
            )
            self.destroy()

        assert self.netbox_inventory.get(
            "instances"
        ), f"{self.name} - inventory has no Netbox instances"

        # extract parameters from imvemtory
        self.netbox_connect_timeout = self.netbox_inventory.get(
            "netbox_connect_timeout", 10
        )
        self.netbox_read_timeout = self.netbox_inventory.get("netbox_read_timeout", 300)
        self.cache_use = self.netbox_inventory.get("cache_use", True)
        self.cache_ttl = self.netbox_inventory.get("cache_ttl", 31557600)  # 1 Year
        self.branch_create_timeout = self.netbox_inventory.get(
            "branch_create_timeout", 120
        )

        # find default instance
        for name, params in self.netbox_inventory["instances"].items():
            if params.get("default") is True:
                self.default_instance = name
                break
        else:
            self.default_instance = name

        # check Netbox compatibility
        self._verify_compatibility()

        # instantiate cache
        self.cache_dir = os.path.join(self.base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self._get_diskcache()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self) -> None:
        """
        Worker exist sanity checks. Closes the cache if it exists.

        This method checks if the cache attribute is present and not None.
        If the cache exists, it closes the cache to release any resources
        associated with it.
        """
        if self.cache:
            self.cache.close()

    # ----------------------------------------------------------------------
    # Netbox Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_inventory(self) -> Result:
        """
        NorFab Task to return running inventory for NetBox worker.

        Returns:
            dict: A dictionary containing the NetBox inventory.
        """
        return Result(
            task=f"{self.name}:get_inventory", result=dict(self.netbox_inventory)
        )

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_version(self, **kwargs: Any) -> Result:
        """
        Retrieves the version information of Netbox instances.

        Returns:
            dict: A dictionary containing the version information of the Netbox
        """
        libs = {
            "norfab": "",
            "pynetbox": "",
            "requests": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
            "diskcache": "",
            "netbox_version": self.nb_version,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(task=f"{self.name}:get_version", result=libs)

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_netbox_status(self, instance: Union[None, str] = None) -> Result:
        """
        Retrieve the status of NetBox instances.

        This method queries the status of a specific NetBox instance if the
        `instance` parameter is provided. If no instance is specified, it
        queries the status of all instances in the NetBox inventory.

        Args:
            instance (str, optional): The name of the specific NetBox instance to query.

        Returns:
            dict: A dictionary containing the status of the requested NetBox
                  instance(s).
        """
        ret = Result(result={}, task=f"{self.name}:get_netbox_status")
        if instance:
            ret.result[instance] = self._query_netbox_status(instance)
        else:
            for name in self.netbox_inventory["instances"].keys():
                ret.result[name] = self._query_netbox_status(name)
        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_compatibility(self, job: Job) -> Result:
        """
        Checks the compatibility of Netbox instances based on their version.

        This method retrieves the status and version of Netbox instances and determines
        if they are compatible with the required versions. It logs a warning if any
        instance is not reachable.

        Args:
            job: NorFab Job object containing relevant metadata

        Returns:
            dict: A dictionary where the keys are the instance names and the values are
                  booleans indicating compatibility (True/False) or None if the instance
                  is not reachable.
        """
        ret = Result(task=f"{self.name}:get_compatibility", result={})
        netbox_status = self.get_netbox_status(job=job)
        for instance, params in netbox_status.result.items():
            if params["status"] is not True:
                log.warning(f"{self.name} - {instance} Netbox instance not reachable")
                ret.result[instance] = None
            else:
                if "-docker-" in params["netbox-version"].lower():
                    self.nb_version[instance] = tuple(
                        [
                            int(i)
                            for i in params["netbox-version"]
                            .lower()
                            .split("-docker-")[0]
                            .split(".")
                        ]
                    )
                else:
                    self.nb_version[instance] = tuple(
                        [int(i) for i in params["netbox-version"].split(".")]
                    )
                # check Netbox 4.4+ compatibility
                if self.nb_version[instance] >= self.compatible_ge_v4:
                    ret.result[instance] = True
                else:
                    ret.result[instance] = False
                    log.error(
                        f"{self.name} - {instance} Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )

        return ret

    def _verify_compatibility(self):
        """
        Verifies the compatibility of Netbox instances.

        This method checks the compatibility of Netbox instances by calling the
        `get_compatibility` method. If any of the instances are not compatible,
        it raises a RuntimeError with a message indicating which instances are
        not compatible.

        Raises:
            RuntimeError: If any of the Netbox instances are not compatible.
        """
        compatibility = self.get_compatibility(job=Job())
        if not all(i is not False for i in compatibility.result.values()):
            raise RuntimeError(
                f"{self.name} - not all Netbox instances are compatible: {compatibility.result}"
            )

    def has_plugin(self, plugin_name: str, instance: str, strict: bool = False) -> bool:
        """
        Check if a specified plugin is installed in a given NetBox instance.

        Args:
            plugin_name (str): The name of the plugin to check for.
            instance (str): The identifier or address of the NetBox instance.
            strict (bool, optional): If True, raises a RuntimeError when the plugin is not found.

        Returns:
            bool: True if the plugin is installed, False otherwise.
        """
        nb_status = self._query_netbox_status(instance)

        if plugin_name in nb_status["plugins"]:
            return True
        elif strict is True:
            raise RuntimeError(
                f"'{instance}' Netbox instance has no '{plugin_name}' plugin installed"
            )

        return False

    def _query_netbox_status(self, name):
        """
        Queries the Netbox API for the status of a given instance.

        Args:
            name (str): The name of the Netbox instance to query.

        Returns:
            dict: A dictionary containing the status and any error message. The dictionary has the following keys:

                - "error" (str or None): Error message if the query failed, otherwise None.
                - "status" (bool): True if the query was successful, False otherwise.
                - Additional keys from the Netbox API response if the query was successful.

        Raises:
            None: All exceptions are caught and handled within the method.
        """
        params = self._get_instance_params(name)

        ret = {
            "error": None,
            "status": True,
        }

        try:
            response = requests.get(
                f"{params['url']}/api/status",
                verify=params.get("ssl_verify", True),
                timeout=(self.netbox_connect_timeout, self.netbox_read_timeout),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token {params['token']}",
                },
            )
            response.raise_for_status()
            ret.update(response.json())
        except Exception as e:
            ret["status"] = False
            msg = (
                f"{self.name} - failed to query Netbox API URL "
                f"'{params['url']}', token ends "
                f"with '..{params['token'][-6:]}'; error: '{e}'"
            )
            log.error(msg)
            ret["error"] = msg

        return ret

    def _get_instance_params(self, name: str = None) -> dict:
        """
        Retrieve instance parameters from the NetBox inventory.

        Args:
            name (str): The name of the instance to retrieve parameters for.

        Returns:
            dict: A dictionary containing the parameters of the specified instance.

        Raises:
            KeyError: If the specified instance name is not found in the inventory.

        If the `ssl_verify` parameter is set to False, SSL warnings will be disabled.
        Otherwise, SSL warnings will be enabled.
        """
        name = name or self.default_instance
        params = self.netbox_inventory["instances"][name]

        # check if need to disable SSL warnings
        if params.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        else:
            requests.packages.urllib3.enable_warnings(InsecureRequestWarning)

        return params

    def _get_pynetbox(self, instance, branch: str = None):
        """
        Helper function to instantiate a pynetbox API object.

        Args:
            instance (str): The instance name for which to get the pynetbox API object.
            branch (str, optional): Branch name to use, need to have branching plugin installed.
                Creates branch if it does not exist in Netbox.

        Returns:
            pynetbox.core.api.Api: An instantiated pynetbox API object.

        Raises:
            Exception: If the pynetbox library is not installed.

        If SSL verification is disabled in the instance parameters,
        this function will disable warnings for insecure requests.
        """
        params = self._get_instance_params(instance)
        nb = pynetbox.api(url=params["url"], token=params["token"], threading=True)

        if params.get("ssl_verify") == False:
            nb.http_session.verify = False

        # add branch
        if branch is not None and self.has_plugin(
            "netbox_branching", instance, strict=True
        ):
            try:
                nb_branch = nb.plugins.branching.branches.get(name=branch)
            except Exception:
                msg = "Failed to retrieve branch '{branch}' from Netbox"
                raise RuntimeError(msg)

            # create new branch
            if not nb_branch:
                nb_branch = nb.plugins.branching.branches.create(name=branch)

            # wait for branch provisioning to complete
            if not nb_branch.status.value.lower() == "ready":
                retries = 0
                while retries < self.branch_create_timeout:
                    nb_branch = nb.plugins.branching.branches.get(name=branch)
                    if nb_branch.status.value.lower() == "ready":
                        break
                    time.sleep(1)
                    retries += 1
                else:
                    raise RuntimeError(f"Branch '{branch}' was created but not ready")

            nb.http_session.headers["X-NetBox-Branch"] = nb_branch.schema_id

            log.info(f"Instantiated pynetbox instance with branch '{branch}'")

        return nb

    def _get_diskcache(self) -> FanoutCache:
        """
        Creates and returns a FanoutCache object.

        The FanoutCache is configured with the specified directory, number of shards,
        timeout, and size limit.

        Returns:
            FanoutCache: A configured FanoutCache instance.
        """
        return FanoutCache(
            directory=self.cache_dir,
            shards=4,
            timeout=1,  # 1 second
            size_limit=1073741824,  #  GigaByte
        )

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def cache_list(self, keys: str = "*", details: bool = False) -> Result:
        """
        Retrieve a list of cache keys, optionally with details about each key.

        Args:
            keys (str): A pattern to match cache keys against. Defaults to "*".
            details (bool): If True, include detailed information about each cache key. Defaults to False.

        Returns:
            list: A list of cache keys or a list of dictionaries with detailed information if `details` is True.
        """
        self.cache.expire()
        ret = Result(task=f"{self.name}:cache_list", result=[])
        for cache_key in self.cache:
            if fnmatchcase(cache_key, keys):
                if details:
                    _, expires = self.cache.get(cache_key, expire_time=True)
                    expires = datetime.fromtimestamp(expires)
                    creation = expires - timedelta(seconds=self.cache_ttl)
                    age = datetime.now() - creation
                    ret.result.append(
                        {
                            "key": cache_key,
                            "age": str(age),
                            "creation": str(creation),
                            "expires": str(expires),
                        }
                    )
                else:
                    ret.result.append(cache_key)
        return ret

    @Task(
        fastapi={"methods": ["DELETE"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def cache_clear(self, job: Job, key: str = None, keys: str = None) -> Result:
        """
        Clears specified keys from the cache.

        Args:
            job: NorFab Job object containing relevant metadata
            key (str, optional): A specific key to remove from the cache.
            keys (str, optional): A glob pattern to match multiple keys to remove from the cache.

        Returns:
            list: A list of keys that were successfully removed from the cache.

        Raises:
            RuntimeError: If a specified key or a key matching the glob pattern could not be removed from the cache.

        Notes:

        - If neither `key` nor `keys` is provided, the function will return a message indicating that there is nothing to clear.
        - If `key` is provided, it will attempt to remove that specific key from the cache.
        - If `keys` is provided, it will attempt to remove all keys matching the glob pattern from the cache.
        """
        ret = Result(task=f"{self.name}:cache_clear", result=[])
        # check if has keys to clear
        if key == keys == None:  # noqa
            ret.result = "Noting to clear, specify key or keys"
            return ret
        # remove specific key from cache
        if key:
            if key in self.cache:
                if self.cache.delete(key, retry=True):
                    ret.result.append(key)
                else:
                    raise RuntimeError(f"Failed to remove {key} from cache")
            else:
                ret.messages.append(f"Key {key} not in cache.")
        # remove all keys matching glob pattern
        if keys:
            for cache_key in self.cache:
                if fnmatchcase(cache_key, keys):
                    if self.cache.delete(cache_key, retry=True):
                        ret.result.append(cache_key)
                    else:
                        raise RuntimeError(f"Failed to remove {key} from cache")
        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def cache_get(
        self, job: Job, key: str = None, keys: str = None, raise_missing: bool = False
    ) -> Result:
        """
        Retrieve values from the cache based on a specific key or a pattern of keys.

        Args:
            job: NorFab Job object containing relevant metadata
            key (str, optional): A specific key to retrieve from the cache.
            keys (str, optional): A glob pattern to match multiple keys in the cache.
            raise_missing (bool, optional): If True, raises a KeyError if the specific
                key is not found in the cache. Defaults to False.

        Returns:
            dict: A dictionary containing the results of the cache retrieval. The keys are
                the cache keys and the values are the corresponding cache values.

        Raises:
            KeyError: If raise_missing is True and the specific key is not found in the cache.
        """
        ret = Result(task=f"{self.name}:cache_clear", result={})
        # get specific key from cache
        if key:
            if key in self.cache:
                ret.result[key] = self.cache[key]
            elif raise_missing:
                raise KeyError(f"Key {key} not in cache.")
        # get all keys matching glob pattern
        if keys:
            for cache_key in self.cache:
                if fnmatchcase(cache_key, keys):
                    ret.result[cache_key] = self.cache[cache_key]
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def graphql(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        obj: Union[str, dict] = None,
        filters: Union[None, dict, str] = None,
        fields: Union[None, list] = None,
        queries: Union[None, dict] = None,
        query_string: str = None,
    ) -> Result:
        """
        Function to query Netbox v3 or Netbox v4 GraphQL API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance: Netbox instance name
            dry_run: only return query content, do not run it
            obj: Object to query
            filters: Filters to apply to the query
            fields: Fields to retrieve in the query
            queries: Dictionary of queries to execute
            query_string: Raw query string to execute

        Returns:
            dict: GraphQL request data returned by Netbox

        Raises:
            RuntimeError: If required arguments are not provided
            Exception: If GraphQL query fails
        """
        nb_params = self._get_instance_params(instance)
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:graphql", resources=[instance])

        # form graphql query(ies) payload
        if queries:
            queries_list = []
            for alias, query_data in queries.items():
                query_data["alias"] = alias
                if self.nb_version[instance] >= (4, 4, 0):
                    queries_list.append(_form_query_v4(**query_data))
                else:
                    raise UnsupportedNetboxVersion(
                        f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )
            queries_strings = "    ".join(queries_list)
            query = f"query {{{queries_strings}}}"
        elif obj and filters and fields:
            if self.nb_version[instance] >= (4, 4, 0):
                query = _form_query_v4(obj, filters, fields)
            else:
                raise UnsupportedNetboxVersion(
                    f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                    f"minimum required version is {self.compatible_ge_v4}"
                )
            query = f"query {{{query}}}"
        elif query_string:
            query = query_string
        else:
            raise RuntimeError(
                f"{self.name} - graphql method expects queries argument or obj, filters, "
                f"fields arguments or query_string argument provided"
            )
        payload = json.dumps({"query": query})

        # form and return dry run response
        if dry_run:
            ret.result = {
                "url": f"{nb_params['url']}/graphql/",
                "data": payload,
                "verify": nb_params.get("ssl_verify", True),
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token ...{nb_params['token'][-6:]}",
                },
            }
            return ret

        # send request to Netbox GraphQL API
        log.debug(
            f"{self.name} - sending GraphQL query '{payload}' to URL '{nb_params['url']}/graphql/'"
        )
        req = requests.post(
            url=f"{nb_params['url']}/graphql/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {nb_params['token']}",
            },
            data=payload,
            verify=nb_params.get("ssl_verify", True),
            timeout=(self.netbox_connect_timeout, self.netbox_read_timeout),
        )
        try:
            req.raise_for_status()
        except Exception:
            raise Exception(
                f"{self.name} -  Netbox GraphQL query failed, query '{query}', "
                f"URL '{req.url}', status-code '{req.status_code}', reason '{req.reason}', "
                f"response content '{req.text}'"
            )

        # return results
        reply = req.json()
        if reply.get("errors"):
            msg = f"{self.name} - GrapQL query error '{reply['errors']}', query '{payload}'"
            log.error(msg)
            ret.errors.append(msg)
            if reply.get("data"):
                ret.result = reply["data"]  # at least return some data
        elif queries or query_string:
            ret.result = reply["data"]
        else:
            ret.result = reply["data"][obj]

        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def rest(
        self,
        job: Job,
        instance: Union[None, str] = None,
        method: str = "get",
        api: str = "",
        **kwargs: Any,
    ) -> Result:
        """
        Sends a request to the Netbox REST API.

        Args:
            instance (str, optional): The Netbox instance name to get parameters for.
            method (str, optional): The HTTP method to use for the request (e.g., 'get', 'post'). Defaults to "get".
            api (str, optional): The API endpoint to send the request to. Defaults to "".
            **kwargs: Additional arguments to pass to the request (e.g., params, data, json).

        Returns:
            Union[dict, list]: The JSON response from the API, parsed into a dictionary or list.

        Raises:
            requests.exceptions.HTTPError: If the HTTP request returned an unsuccessful status code.
        """
        ret = Result(task=f"{self.name}:rest", result={})
        nb_params = self._get_instance_params(instance)
        api = api.strip("/")

        # send request to Netbox REST API
        response = getattr(requests, method)(
            url=f"{nb_params['url']}/api/{api}/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {nb_params['token']}",
            },
            verify=nb_params.get("ssl_verify", True),
            **kwargs,
        )

        try:
            response.raise_for_status()
        except Exception as e:
            log.error(f"REST API request failed, error: {e}")
            ret.result = response.status_code
            return ret

        try:
            ret.result = response.json()
        except Exception as e:
            log.debug(f"Failed to decode json, error: {e}")
            ret.result = response.text if response.text else response.status_code

        return ret

    def expand_alphanumeric_range(self, range_pattern: str) -> list:
        """
        Expand alphanumeric ranges.

        Examples:
            - Ethernet[1-3] -> ['Ethernet1', 'Ethernet2', 'Ethernet3']
            - [ge,xe]-0/0/[0-9] -> ['ge-0/0/0', 'ge-0/0/1', ..., 'xe-0/0/9']
        """
        # Find all bracketed patterns
        bracket_pattern = r"\[([^\]]+)\]"
        matches = list(re.finditer(bracket_pattern, range_pattern))

        if not matches:
            # No ranges found, return as-is
            return [range_pattern]

        # Start with a single template
        templates = [range_pattern]

        # Process each bracket from left to right
        for match in matches:
            bracket_content = match.group(1)
            new_templates = []

            # Check if it's a comma-separated list
            if "," in bracket_content:
                options = [opt.strip() for opt in bracket_content.split(",")]
                for template in templates:
                    for option in options:
                        new_templates.append(
                            template.replace(f"[{bracket_content}]", option, 1)
                        )

            # Check if it's a numeric range
            elif (
                "-" in bracket_content
                and bracket_content.replace("-", "").replace(" ", "").isdigit()
            ):
                parts = bracket_content.split("-")
                if len(parts) == 2:
                    try:
                        start = int(parts[0].strip())
                        end = int(parts[1].strip())
                        for template in templates:
                            for num in range(start, end + 1):
                                new_templates.append(
                                    template.replace(
                                        f"[{bracket_content}]", str(num), 1
                                    )
                                )
                    except ValueError:
                        # If conversion fails, treat as literal
                        for template in templates:
                            new_templates.append(
                                template.replace(
                                    f"[{bracket_content}]", bracket_content, 1
                                )
                            )
            else:
                # Treat as literal
                for template in templates:
                    new_templates.append(
                        template.replace(f"[{bracket_content}]", bracket_content, 1)
                    )

            templates = new_templates

        return templates

    def compare_netbox_object_state(
        self,
        desired_state: dict,
        current_state: dict,
        ignore_fields: Union[list, None] = None,
        ignore_if_not_empty: Union[list, None] = None,
        diff: dict = None,
    ) -> tuple:
        """
        Compare desired state with current NetBox object state and return fields that need updating.

        Args:
            desired_state (dict): Dictionary with desired field values.
            current_state (dict): Dictionary with current NetBox object field values.
            ignore_fields (list, optional): List of field names to ignore completely.
            ignore_if_not_empty (list, optional): List of field names to ignore if they have
                non-empty values in current_state (won't overwrite existing data).
            diff (dict, optional): Dictionary to accumulate field differences. If not provided,
                a new dictionary will be created.

        Returns:
            tuple: A tuple containing:
                - updates (dict): Dictionary containing only fields that need to be updated with their new values.
                - diff (dict): Dictionary containing the differences with '+' (new value) and '-' (old value) keys.

        Example:
            >>> desired = {"serial": "ABC123", "asset_tag": "TAG001", "comments": "New comment"}
            >>> current = {"serial": "OLD123", "asset_tag": "TAG001", "comments": "Existing"}
            >>> ignore_fields = ["comments"]
            >>> ignore_if_not_empty = []
            >>> updates, diff = compare_netbox_object_state(desired, current, ignore_fields, ignore_if_not_empty)
            >>> updates
            {"serial": "ABC123"}

            >>> desired = {"serial": "ABC123", "asset_tag": "TAG001", "comments": "New comment"}
            >>> current = {"serial": "OLD123", "asset_tag": "", "comments": "Existing"}
            >>> ignore_fields = []
            >>> ignore_if_not_empty = ["comments"]
            >>> updates, diff = compare_netbox_object_state(desired, current, ignore_fields, ignore_if_not_empty)
            >>> updates
            {"serial": "ABC123", "asset_tag": "TAG001"}
        """
        ignore_fields = ignore_fields or []
        ignore_if_not_empty = ignore_if_not_empty or []
        updates = {}
        diff = diff or {}

        for field, desired_value in desired_state.items():
            # Skip if field is in ignore list
            if field in ignore_fields:
                continue

            # Get current value, default to None if field doesn't exist
            current_value = current_state.get(field)

            # Skip if field is in ignore_if_not_empty and current value is not empty
            if field in ignore_if_not_empty and current_value:
                continue

            # Compare values and add to updates if different
            if current_value != desired_value:
                updates[field] = desired_value
                diff[field] = {
                    "-": current_value,
                    "+": desired_value,
                }

        return updates, diff
