import json
import logging
import sys
import importlib.metadata
import requests
import copy
import os
import concurrent.futures
import pynetbox
import ipaddress
import re
import time

from fnmatch import fnmatchcase
from datetime import datetime, timedelta
from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from typing import Union
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from norfab.core.exceptions import UnsupportedServiceError
from norfab.models.netbox import CreatePrefixInput, NetboxFastApiArgs
from diskcache import FanoutCache

SERVICE = "netbox"

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# EXCEPTIONS
# ----------------------------------------------------------------------


class NetboxAllocationError(Exception):
    """
    Raised when there is an error in allocating resource in Netbox
    """


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


def _form_query_v3(obj, filters, fields, alias=None) -> str:
    """
    Helper function to form graphql query for Netbox version 3.

    Args:
        obj (str): The object to return data for, e.g., 'device', 'interface', 'ip_address'.
        filters (dict): A dictionary of key-value pairs to filter by.
        fields (list): A list of data fields to return.
        alias (str, optional): An alias value for the requested object.

    Returns:
        str: A formatted GraphQL query string.
    """
    filters_list = []
    for k, v in filters.items():
        if isinstance(v, (list, set, tuple)):
            items = ", ".join(f'"{i}"' for i in v)
            filters_list.append(f"{k}: [{items}]")
        else:
            filters_list.append(f'{k}: "{v}"')
    filters_string = ", ".join(filters_list)
    fields = " ".join(fields)
    if alias:
        query = f"{alias}: {obj}({filters_string}) {{{fields}}}"
    else:
        query = f"{obj}({filters_string}) {{{fields}}}"

    return query


class NetboxWorker(NFPWorker):
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
        compatible_ge_v3 (tuple): Minimum supported Netbox v3 version.
        compatible_ge_v4 (tuple): Minimum supported Netbox v4 version.
    """

    default_instance = None
    inventory = None
    nb_version = {}  # dict keyed by instance name and version
    compatible_ge_v3 = (
        3,
        6,
        0,
    )  # 3.6.0 - minimum supported Netbox v3
    compatible_ge_v4 = (
        4,
        0,
        5,
    )  # 4.0.5 - minimum supported Netbox v4

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

        Args:
            job: NorFab Job object containing relevant metadata

        Returns:
            dict: A dictionary containing the NetBox inventory.
        """
        return Result(
            task=f"{self.name}:get_inventory", result=dict(self.netbox_inventory)
        )

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_version(self, **kwargs) -> Result:
        """
        Retrieves the version information of Netbox instances.

        Args:
            job: NorFab Job object containing relevant metadata

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
            job: NorFab Job object containing relevant metadata
            instance (str, optional): The name of the specific NetBox instance
                                      to query.

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
                if self.nb_version[instance][0] == 3:  # check Netbox 3 compatibility
                    ret.result[instance] = (
                        self.nb_version[instance] >= self.compatible_ge_v3
                    )
                elif self.nb_version[instance][0] == 4:  # check Netbox 4 compatibility
                    ret.result[instance] = (
                        self.nb_version[instance] >= self.compatible_ge_v4
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
        params = self.netbox_inventory["instances"][name]
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

    def _get_instance_params(self, name: str) -> dict:
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

        if name:
            ret = self.netbox_inventory["instances"][name]
        else:
            ret = self.netbox_inventory["instances"][self.default_instance]

        # check if need to disable SSL warnings
        if ret.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        else:
            requests.packages.urllib3.enable_warnings(InsecureRequestWarning)

        return ret

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

        if params.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            nb = pynetbox.api(url=params["url"], token=params["token"])
            nb.http_session.verify = False
        else:
            nb = pynetbox.api(url=params["url"], token=params["token"])

        # add branch
        if branch is not None and self.has_plugin(
            "netbox_branching", instance, strict=True
        ):
            try:
                nb_branch = nb.plugins.branching.branches.get(name=branch)
            except Exception as e:
                msg = "Failed to retrieve branch '{branch}' from Netbox"
                raise RuntimeError(msg)

            # create new branch
            if not nb_branch:
                nb_branch = nb.plugins.branching.branches.create(name=branch)

            # wait for branch provisioning to complete
            if not nb_branch.status.value.lower() == "ready":
                retries = 0
                while retries < 60:
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
            job: NorFab Job object containing relevant metadata
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
        if key == keys == None:
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
                if self.nb_version[instance][0] == 4:
                    queries_list.append(_form_query_v4(**query_data))
                elif self.nb_version[instance][0] == 3:
                    queries_list.append(_form_query_v3(**query_data))
            queries_strings = "    ".join(queries_list)
            query = f"query {{{queries_strings}}}"
        elif obj and filters and fields:
            if self.nb_version[instance][0] == 4:
                query = _form_query_v4(obj, filters, fields)
            elif self.nb_version[instance][0] == 3:
                query = _form_query_v3(obj, filters, fields)
            query = f"query {{{query}}}"
        elif query_string:
            query = query_string
        else:
            raise RuntimeError(
                f"{self.name} - graphql method expects quieries argument or obj, filters, "
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
        except Exception as e:
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
        **kwargs,
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

        response.raise_for_status()
        try:
            ret.result = response.json()
        except Exception as e:
            log.debug(f"Failed to decode json, error: {e}")
            ret.result = response.text if response.text else response.status_code

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_devices(
        self,
        job: Job,
        filters: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        devices: Union[None, list] = None,
        cache: Union[bool, str] = None,
    ) -> Result:
        """
        Retrieves device data from Netbox using the GraphQL API.

        Args:
            job: NorFab Job object containing relevant metadata
            filters (list, optional): A list of filter dictionaries to filter devices.
            instance (str, optional): The Netbox instance name.
            dry_run (bool, optional): If True, only returns the query content without executing it. Defaults to False.
            devices (list, optional): A list of device names to query data for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: A dictionary keyed by device name with device data.

        Raises:
            Exception: If the GraphQL query fails or if there are errors in the query result.
        """
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:get_devices", result={}, resources=[instance])
        cache = self.cache_use if cache is None else cache
        filters = filters or []
        devices = devices or []
        queries = {}  # devices queries
        device_fields = [
            "name",
            "last_updated",
            "custom_field_data",
            "tags {name}",
            "device_type {model}",
            "role {name}",
            "config_context",
            "tenant {name}",
            "platform {name}",
            "serial",
            "asset_tag",
            "site {name slug tags{name} }",
            "location {name}",
            "rack {name}",
            "status",
            "primary_ip4 {address}",
            "primary_ip6 {address}",
            "airflow",
            "position",
        ]

        if cache == True or cache == "force":
            # retrieve last updated data from Netbox for devices
            last_updated_query = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": ["name", "last_updated"],
                }
                for index, filter_item in enumerate(filters)
            }
            if devices:
                # use cache data without checking if it is up to date for cached devices
                if cache == "force":
                    for device_name in list(devices):
                        device_cache_key = f"get_devices::{device_name}"
                        if device_cache_key in self.cache:
                            devices.remove(device_name)
                            ret.result[device_name] = self.cache[device_cache_key]
                # query netbox last updated data for devices
                if self.nb_version[instance][0] == 4:
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                elif self.nb_version[instance][0] == 3:
                    filters_dict = {"name": devices}
                last_updated_query["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": ["name", "last_updated"],
                }
            last_updated = self.graphql(
                job=job,
                queries=last_updated_query,
                instance=instance,
                dry_run=dry_run,
            )
            last_updated.raise_for_status(f"{self.name} - get devices query failed")

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = last_updated.result
                return ret

            # try to retrieve device data from cache
            self.cache.expire()  # remove expired items from cache
            for devices_list in last_updated.result.values():
                for device in devices_list:
                    device_cache_key = f"get_devices::{device['name']}"
                    # check if cache is up to date and use it if so
                    if device_cache_key in self.cache and (
                        self.cache[device_cache_key]["last_updated"]
                        == device["last_updated"]
                        or cache == "force"
                    ):
                        ret.result[device["name"]] = self.cache[device_cache_key]
                        # remove device from list of devices to retrieve
                        if device["name"] in devices:
                            devices.remove(device["name"])
                    # cache old or no cache, fetch device data
                    elif device["name"] not in devices:
                        devices.append(device["name"])
        # ignore cache data, fetch data from netbox
        elif cache == False or cache == "refresh":
            queries = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": device_fields,
                }
                for index, filter_item in enumerate(filters)
            }

        # fetch devices data from Netbox
        if devices or queries:
            if devices:
                if self.nb_version[instance][0] == 4:
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                elif self.nb_version[instance][0] == 3:
                    filters_dict = {"name": devices}
                queries["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": device_fields,
                }

            # send queries
            query_result = self.graphql(
                job=job, queries=queries, instance=instance, dry_run=dry_run
            )

            # check for errors
            if query_result.errors:
                msg = f"{self.name} - get devices query failed with errors:\n{query_result.errors}"
                raise Exception(msg)

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = query_result.result
                return ret

            # process devices data
            devices_data = query_result.result
            for devices_list in devices_data.values():
                for device in devices_list:
                    if device["name"] not in ret.result:
                        device_name = device.pop("name")
                        # cache device data
                        if cache != False:
                            cache_key = f"get_devices::{device_name}"
                            self.cache.set(cache_key, device, expire=self.cache_ttl)
                        # add device data to return result
                        ret.result[device_name] = device

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        ip_addresses: bool = False,
        inventory_items: bool = False,
        dry_run: bool = False,
        cache: Union[bool, str] = None,
    ) -> Result:
        """
        Retrieve device interfaces from Netbox using GraphQL API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve interfaces for.
            ip_addresses (bool, optional): If True, retrieves interface IPs. Defaults to False.
            inventory_items (bool, optional): If True, retrieves interface inventory items. Defaults to False.
            dry_run (bool, optional): If True, only return query content, do not run it. Defaults to False.

        Returns:
            dict: Dictionary keyed by device name with interface details.

        Raises:
            Exception: If no interfaces data is returned for the specified devices.
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:get_interfaces",
            result={d: {} for d in devices},
            resources=[instance],
        )

        intf_fields = [
            "name",
            "enabled",
            "description",
            "mtu",
            "parent {name}",
            "mode",
            "untagged_vlan {vid name}",
            "vrf {name}",
            "tagged_vlans {vid name}",
            "tags {name}",
            "custom_fields",
            "last_updated",
            "bridge {name}",
            "child_interfaces {name}",
            "bridge_interfaces {name}",
            "member_interfaces {name}",
            "wwn",
            "duplex",
            "speed",
            "id",
            "device {name}",
        ]
        if self.nb_version[instance] >= (4, 2, 0):
            intf_fields.append("mac_addresses {mac_address}")
        else:
            intf_fields.append("mac_address")

        # add IP addresses to interfaces fields
        if ip_addresses:
            intf_fields.append(
                "ip_addresses {address status role dns_name description custom_fields last_updated tenant {name} tags {name}}"
            )

        # form interfaces query dictionary
        if self.nb_version[instance] >= (4, 3, 0):
            dlist = str(devices).replace("'", '"')  # swap quotes
            dfilt = "{device: {name: {in_list: " + dlist + "}}}"
        else:
            dfilt = {"device": devices}
        queries = {
            "interfaces": {
                "obj": "interface_list",
                "filters": dfilt,
                "fields": intf_fields,
            }
        }

        # add query to retrieve inventory items
        if inventory_items:
            if self.nb_version[instance] >= (4, 3, 0):
                dlist = str(devices).replace("'", '"')  # swap quotes
                inv_filters = (
                    "{device: {name: {in_list: "
                    + dlist
                    + '}}, component_type: {app_label: {exact: "dcim"}}}'
                )
            else:
                inv_filters = {"device": devices, "component_type": "dcim.interface"}
            inv_fields = [
                "name",
                "component {... on InterfaceType {id}}",
                "role {name}",
                "manufacturer {name}",
                "custom_fields",
                "label",
                "description",
                "tags {name}",
                "asset_tag",
                "serial",
                "part_id",
            ]
            queries["inventor_items"] = {
                "obj": "inventory_item_list",
                "filters": inv_filters,
                "fields": inv_fields,
            }

        query_result = self.graphql(
            job=job, instance=instance, queries=queries, dry_run=dry_run
        )

        # return dry run result
        if dry_run:
            return query_result

        interfaces_data = query_result.result

        # exit if no Interfaces returned
        if interfaces_data is None or not interfaces_data.get("interfaces"):
            raise Exception(
                f"{self.name} - no interfaces data in '{interfaces_data}' returned by '{instance}' "
                f"for devices {', '.join(devices)}"
            )

        # process query results
        interfaces = interfaces_data.pop("interfaces")

        # process inventory items
        if inventory_items:
            inventory_items_list = interfaces_data.pop("inventor_items")
            # transform inventory items list to a dictionary keyed by intf_id
            inventory_items_dict = {}
            while inventory_items_list:
                inv_item = inventory_items_list.pop()
                # skip inventory items that does not assigned to components
                if inv_item.get("component") is None:
                    continue
                intf_id = str(inv_item.pop("component").pop("id"))
                inventory_items_dict.setdefault(intf_id, [])
                inventory_items_dict[intf_id].append(inv_item)
            # iterate over interfaces and add inventory items
            for intf in interfaces:
                intf["inventory_items"] = inventory_items_dict.pop(intf["id"], [])

        # transform interfaces list to dictionary keyed by device and interfaces names
        while interfaces:
            intf = interfaces.pop()
            _ = intf.pop("id")
            device_name = intf.pop("device").pop("name")
            intf_name = intf.pop("name")
            if device_name in ret.result:  # Netbox issue #16299
                ret.result[device_name][intf_name] = intf

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_connections(
        self,
        job: Job,
        devices: list,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cables: bool = False,
        cache: Union[bool, str] = None,
    ) -> Result:
        """
        Retrieve interface connection details for specified devices from Netbox.

        Args:
            job: NorFab Job object containing relevant metadata
            devices (list): List of device names to retrieve connections for.
            instance (str, optional): Netbox instance name for the GraphQL query.
            dry_run (bool, optional): If True, perform a dry run without making actual changes.
            cables (bool, optional): if True includes interfaces' directly attached cables details

        Returns:
            dict: A dictionary containing connection details for each device:

                ```
                {
                    "netbox-worker-1.2": {
                        "r1": {
                            "Console": {
                                "breakout": false,
                                "remote_device": "termserv1",
                                "remote_interface": "ConsoleServerPort1",
                                "remote_termination_type": "consoleserverport",
                                "termination_type": "consoleport"
                            },
                            "eth1": {
                                "breakout": false,
                                "remote_device": "r2",
                                "remote_interface": "eth8",
                                "remote_termination_type": "interface",
                                "termination_type": "interface"
                            }
                        }
                    }
                }
                ```

        Raises:
            Exception: If there is an error in the GraphQL query or data retrieval process.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:get_connections",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # form lists of fields to request from netbox
        cable_fields = """
            cable {
                type
                status
                tenant {name}
                label
                tags {name}
                length
                length_unit
                custom_fields
            }
        """
        if self.nb_version[instance][0] == 4:
            interfaces_fields = [
                "name",
                "device {name}",
                """connected_endpoints {
                __typename 
                ... on InterfaceType {name device {name}}
                ... on ProviderNetworkType {name}
                }""",
            ]
        elif self.nb_version[instance][0] == 3:
            interfaces_fields = [
                "name",
                "device {name}",
                """connected_endpoints {
                __typename 
                ... on InterfaceType {name device {name}}
                }""",
            ]
        interfaces_fields.append(
            """
            link_peers {
                __typename
                ... on InterfaceType {name device {name}}
                ... on FrontPortType {name device {name}}
                ... on RearPortType {name device {name}}
            }
        """
        )
        console_ports_fields = [
            "name",
            "device {name}",
            """connected_endpoints {
              __typename 
              ... on ConsoleServerPortType {name device {name}}
            }""",
            """link_peers {
              __typename
              ... on ConsoleServerPortType {name device {name}}
              ... on FrontPortType {name device {name}}
              ... on RearPortType {name device {name}}
            }""",
        ]
        console_server_ports_fields = [
            "name",
            "device {name}",
            """connected_endpoints {
              __typename 
              ... on ConsolePortType {name device {name}}
            }""",
            """link_peers {
              __typename
              ... on ConsolePortType {name device {name}}
              ... on FrontPortType {name device {name}}
              ... on RearPortType {name device {name}}
            }""",
        ]

        # check if need to include cables info
        if cables is True:
            interfaces_fields.append(cable_fields)
            console_ports_fields.append(cable_fields)
            console_server_ports_fields.append(cable_fields)

        # form query dictionary with aliases to get data from Netbox
        if self.nb_version[instance] >= (4, 3, 0):
            dlist = str(devices).replace("'", '"')  # swap quotes
            dfilt = "{device: {name: {in_list: " + dlist + "}}}"
        else:
            dfilt = {"device": devices}
        queries = {
            "interface": {
                "obj": "interface_list",
                "filters": dfilt,
                "fields": interfaces_fields,
            },
            "consoleport": {
                "obj": "console_port_list",
                "filters": dfilt,
                "fields": console_ports_fields,
            },
            "consoleserverport": {
                "obj": "console_server_port_list",
                "filters": dfilt,
                "fields": console_server_ports_fields,
            },
        }

        # retrieve full list of devices interface with all cables
        query_result = self.graphql(
            job=job, queries=queries, instance=instance, dry_run=dry_run
        )

        # return dry run result
        if dry_run:
            return query_result

        all_ports = query_result.result

        # extract interfaces
        for port_type, ports in all_ports.items():
            for port in ports:
                endpoints = port["connected_endpoints"]
                # skip ports that have no remote device connected
                if not endpoints or not all(i for i in endpoints):
                    continue

                # extract required parameters
                cable = port.get("cable", {})
                device_name = port["device"]["name"]
                port_name = port["name"]
                link_peers = port["link_peers"]
                remote_termination_type = endpoints[0]["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")

                # form initial connection dictionary
                connection = {
                    "breakout": len(endpoints) > 1,
                    "remote_termination_type": remote_termination_type,
                    "termination_type": port_type,
                }

                # add remote connection details
                if remote_termination_type == "providernetwork":
                    connection["remote_device"] = None
                    connection["remote_interface"] = None
                    connection["provider"] = endpoints[0]["name"]
                else:
                    remote_interface = endpoints[0]["name"]
                    if len(endpoints) > 1:
                        remote_interface = list(sorted([i["name"] for i in endpoints]))
                    connection["remote_interface"] = remote_interface
                    connection["remote_device"] = endpoints[0]["device"]["name"]

                # add cable and its peer details
                if cables:
                    peer_termination_type = link_peers[0]["__typename"].lower()
                    peer_termination_type = peer_termination_type.replace("type", "")
                    cable["peer_termination_type"] = peer_termination_type
                    cable["peer_device"] = link_peers[0].get("device", {}).get("name")
                    cable["peer_interface"] = link_peers[0].get("name")
                    if len(link_peers) > 1:  # handle breakout cable
                        cable["peer_interface"] = [i["name"] for i in link_peers]
                    connection["cable"] = cable

                ret.result[device_name][port_name] = connection

        return ret

    def _map_circuit(
        self, circuit: dict, ret: Result, instance: str, devices: list, cache: bool
    ) -> bool:
        """
        ThreadPoolExecutor target function to retrieve circuit details from Netbox

        Args:
            circuit (dict): The circuit data to be mapped.
            ret (Result): The result object to store the mapped data.
            instance (str): The instance of the Netbox API to use.
            devices (list): List of devices to check against the circuit endpoints.
            cache (bool): Flag to determine if the data should be cached.

        Returns:
            bool: True if the mapping is successful, False otherwise.
        """
        cid = circuit.pop("cid")
        ckt_cache_data = {}  # ckt data dictionary to save in cache
        circuit["tags"] = [i["name"] for i in circuit["tags"]]
        circuit["type"] = circuit["type"]["name"]
        circuit["provider"] = circuit["provider"]["name"]
        circuit["tenant"] = circuit["tenant"]["name"] if circuit["tenant"] else None
        circuit["provider_account"] = (
            circuit["provider_account"]["name"] if circuit["provider_account"] else None
        )
        termination_a = circuit["termination_a"]
        termination_z = circuit["termination_z"]
        termination_a = termination_a["id"] if termination_a else None
        termination_z = termination_z["id"] if termination_z else None

        log.info(f"{self.name}:get_circuits - {cid} tracing circuit terminations path")

        # retrieve A or Z termination path using Netbox REST API
        if termination_a is not None:
            circuit_path = self.rest(
                instance=instance,
                method="get",
                api=f"/circuits/circuit-terminations/{termination_a}/paths/",
            )["result"]
        elif termination_z is not None:
            circuit_path = self.rest(
                instance=instance,
                method="get",
                api=f"/circuits/circuit-terminations/{termination_z}/paths/",
            )["result"]
        else:
            return True

        # check if circuit ends connect to device or provider network
        if (
            not circuit_path
            or "name" not in circuit_path[0]["path"][0][0]
            or "name" not in circuit_path[0]["path"][-1][-1]
        ):
            return True

        # form A and Z connection endpoints
        end_a = {
            "device": circuit_path[0]["path"][0][0]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][0][0]["url"],
            "name": circuit_path[0]["path"][0][0]["name"],
        }
        end_z = {
            "device": circuit_path[0]["path"][-1][-1]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][-1][-1]["url"],
            "name": circuit_path[0]["path"][-1][-1]["name"],
        }
        circuit["is_active"] = circuit_path[0]["is_active"]

        # map path ends to devices
        if end_a["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_a["name"]
            if end_z["device"]:
                device_data["remote_device"] = end_z["device"]
                device_data["remote_interface"] = end_z["name"]
            elif end_z["provider_network"]:
                device_data["provider_network"] = end_z["name"]
            # save device data in cache
            ckt_cache_data[end_a["device"]] = device_data
            # include device data in result
            if end_a["device"] in devices:
                ret.result[end_a["device"]][cid] = device_data
        if end_z["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_z["name"]
            if end_a["device"]:
                device_data["remote_device"] = end_a["device"]
                device_data["remote_interface"] = end_a["name"]
            elif end_a["provider_network"]:
                device_data["provider_network"] = end_a["name"]
            # save device data in cache
            ckt_cache_data[end_z["device"]] = device_data
            # include device data in result
            if end_z["device"] in devices:
                ret.result[end_z["device"]][cid] = device_data

        # save data to cache
        if cache != False:
            ckt_cache_key = f"get_circuits::{cid}"
            if ckt_cache_data:
                self.cache.set(ckt_cache_key, ckt_cache_data, expire=self.cache_ttl)
                log.info(
                    f"{self.name}:get_circuits - {cid} cached circuit data for future use"
                )

        log.info(
            f"{self.name}:get_circuits - {cid} circuit data mapped to devices using data from Netbox"
        )
        return True

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_circuits(
        self,
        job: Job,
        devices: list,
        cid: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cache: Union[bool, str] = True,
    ) -> Result:
        """
        Retrieve circuit information for specified devices from Netbox.

        Args:
            job: NorFab Job object containing relevant metadata
            devices (list): List of device names to retrieve circuits for.
            cid (list, optional): List of circuit IDs to filter by.
            instance (str, optional): Netbox instance to query.
            dry_run (bool, optional): If True, perform a dry run without making changes. Defaults to False.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: dictionary keyed by device names with circuits data.

        Task to retrieve device's circuits data from Netbox.
        """
        cid = cid or []
        log.info(
            f"{self.name}:get_circuits - {instance or self.default_instance} Netbox, "
            f"devices {', '.join(devices)}, cid {cid}"
        )
        instance = instance or self.default_instance

        # form final result object
        ret = Result(
            task=f"{self.name}:get_circuits",
            result={d: {} for d in devices},
            resources=[instance],
        )
        cache = self.cache_use if cache is None else cache
        cid = cid or []
        circuit_fields = [
            "cid",
            "tags {name}",
            "provider {name}",
            "commit_rate",
            "description",
            "status",
            "type {name}",
            "provider_account {name}",
            "tenant {name}",
            "termination_a {id last_updated}",
            "termination_z {id last_updated}",
            "custom_fields",
            "comments",
            "last_updated",
        ]

        # form initial circuits filters based on devices' sites and cid list
        circuits_filters = {}
        device_data = self.get_devices(
            job=job, devices=copy.deepcopy(devices), instance=instance, cache=cache
        )
        sites = list(set([i["site"]["slug"] for i in device_data.result.values()]))
        if (4, 0, 0) <= self.nb_version[instance] < (4, 3, 0):
            circuits_filters = {"site": sites}
            if cid:
                cid_list = '["{cl}"]'.format(cl='", "'.join(cid))
                circuits_filters["cid"] = f"{{in_list: {cid_list}}}"
        elif self.nb_version[instance] >= (4, 3, 0):
            slist = str(sites).replace("'", '"')  # swap quotes
            if cid:
                clist = str(cid).replace("'", '"')  # swap quotes
                circuits_filters = "{terminations: {site: {slug: {in_list: slist}}}, cid: {in_list: clist}}"
                circuits_filters = circuits_filters.replace("slist", slist).replace(
                    "clist", clist
                )
            else:
                circuits_filters = "{terminations: {site: {slug: {in_list: slist }}}}"
                circuits_filters = circuits_filters.replace("slist", slist)
        elif self.nb_version[instance][0] == 3:
            circuits_filters = {"site": sites}
            if cid:
                cid_list = '["{cl}"]'.format(cl='", "'.join(cid))
                circuits_filters["cid"] = cid_list

        log.info(
            f"{self.name}:get_circuits - constructed circuits filters: '{circuits_filters}'"
        )

        if cache == True or cache == "force":
            log.info(f"{self.name}:get_circuits - retrieving circuits data from cache")
            cid_list = []  #  new cid list for follow up query
            # retrieve last updated data from Netbox for circuits and their terminations
            last_updated = self.graphql(
                job=job,
                obj="circuit_list",
                filters=circuits_filters,
                fields=[
                    "cid",
                    "last_updated",
                    "termination_a {id last_updated}",
                    "termination_z {id last_updated}",
                ],
                dry_run=dry_run,
                instance=instance,
            )
            last_updated.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run:
                ret.result["get_circuits_dry_run"] = last_updated.result
                return ret

            # retrieve circuits data from cache
            self.cache.expire()  # remove expired items from cache
            for device in devices:
                for circuit in last_updated.result:
                    circuit_cache_key = f"get_circuits::{circuit['cid']}"
                    log.info(
                        f"{self.name}:get_circuits - searching cache for key {circuit_cache_key}"
                    )
                    # check if cache is up to date and use it if so
                    if circuit_cache_key in self.cache:
                        cache_ckt = self.cache[circuit_cache_key]
                        # check if device uses this circuit
                        if device not in cache_ckt:
                            continue
                        # use cache forcefully
                        if cache == "force":
                            ret.result[device][circuit["cid"]] = cache_ckt[device]
                        # check circuit cache is up to date
                        if cache_ckt[device]["last_updated"] != circuit["last_updated"]:
                            continue
                        if (
                            cache_ckt[device]["termination_a"]
                            and circuit["termination_a"]
                            and cache_ckt[device]["termination_a"]["last_updated"]
                            != circuit["termination_a"]["last_updated"]
                        ):
                            continue
                        if (
                            cache_ckt[device]["termination_z"]
                            and circuit["termination_z"]
                            and cache_ckt[device]["termination_z"]["last_updated"]
                            != circuit["termination_z"]["last_updated"]
                        ):
                            continue
                        ret.result[device][circuit["cid"]] = cache_ckt[device]
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} retrieved data from cache"
                        )
                    elif circuit["cid"] not in cid_list:
                        cid_list.append(circuit["cid"])
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} no cache data found, fetching from Netbox"
                        )
            # form new filters dictionary to fetch remaining circuits data
            circuits_filters = {}
            if cid_list:
                cid_list = str(cid_list).replace("'", '"')  # swap quotes
                if (4, 0, 0) <= self.nb_version[instance] < (4, 3, 0):
                    circuits_filters["cid"] = f"{{in_list: {cid_list}}}"
                elif self.nb_version[instance] >= (4, 3, 0):
                    circuits_filters = "{cid: {in_list: cid_list}}"
                    circuits_filters = circuits_filters.replace("cid_list", cid_list)
                elif self.nb_version[instance][0] == 3:
                    circuits_filters["cid"] = cid_list
        # ignore cache data, fetch circuits from netbox
        elif cache == False or cache == "refresh":
            pass

        if circuits_filters:
            query_result = self.graphql(
                job=job,
                obj="circuit_list",
                filters=circuits_filters,
                fields=circuit_fields,
                dry_run=dry_run,
                instance=instance,
            )
            query_result.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run is True:
                return query_result

            all_circuits = query_result.result

            # iterate over circuits and map them to devices
            log.info(
                f"{self.name}:get_circuits - retrieved data for {len(all_circuits)} "
                f"circuits from netbox, mapping circuits to devices"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = [
                    executor.submit(
                        self._map_circuit, circuit, ret, instance, devices, cache
                    )
                    for circuit in all_circuits
                ]
                for _ in concurrent.futures.as_completed(results):
                    continue

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_nornir_inventory(
        self,
        job: Job,
        filters: Union[None, list] = None,
        devices: Union[None, list] = None,
        instance: Union[None, str] = None,
        interfaces: Union[dict, bool] = False,
        connections: Union[dict, bool] = False,
        circuits: Union[dict, bool] = False,
        nbdata: bool = True,
        primary_ip: str = "ip4",
    ) -> Result:
        """
        Retrieve and construct Nornir inventory from NetBox data.

        Args:
            job: NorFab Job object containing relevant metadata
            filters (list, optional): List of filters to apply when retrieving devices from NetBox.
            devices (list, optional): List of specific devices to retrieve from NetBox.
            instance (str, optional): NetBox instance to use.
            interfaces (Union[dict, bool], optional): If True, include interfaces data
                    in the inventory. If a dict, use it as arguments for the get_interfaces method.
            connections (Union[dict, bool], optional): If True, include connections data
                    in the inventory. If a dict, use it as arguments for the get_connections method.
            circuits (Union[dict, bool], optional): If True, include circuits data in the
                    inventory. If a dict, use it as arguments for the get_circuits method.
            nbdata (bool, optional): If True, include a copy of NetBox device's data in the host's data.
            primary_ip (str, optional): Specify whether to use 'ip4' or 'ip6' for the primary
                    IP address. Defaults to 'ip4'.

        Returns:
            dict: Nornir inventory dictionary containing hosts and their respective data.
        """
        hosts = {}
        filters = filters or []
        devices = devices or []
        inventory = {"hosts": hosts}
        ret = Result(task=f"{self.name}:get_nornir_inventory", result=inventory)

        # check Netbox status
        netbox_status = self.get_netbox_status(job=job, instance=instance)
        if netbox_status.result[instance or self.default_instance]["status"] is False:
            return ret

        # retrieve devices data
        nb_devices = self.get_devices(
            job=job, filters=filters, devices=devices, instance=instance
        )

        # form Nornir hosts inventory
        for device_name, device in nb_devices.result.items():
            host = device["config_context"].pop("nornir", {})
            host.setdefault("data", {})
            name = host.pop("name", device_name)
            hosts[name] = host
            # add platform if not provided in device config context
            if not host.get("platform"):
                if device["platform"]:
                    host["platform"] = device["platform"]["name"]
                else:
                    log.warning(f"{self.name} - no platform found for '{name}' device")
            # add hostname if not provided in config context
            if not host.get("hostname"):
                if device["primary_ip4"] and primary_ip in ["ip4", "ipv4"]:
                    host["hostname"] = device["primary_ip4"]["address"].split("/")[0]
                elif device["primary_ip6"] and primary_ip in ["ip6", "ipv6"]:
                    host["hostname"] = device["primary_ip6"]["address"].split("/")[0]
                else:
                    host["hostname"] = name
            # add netbox data to host's data
            if nbdata is True:
                host["data"].update(device)

        # return if no hosts found for provided parameters
        if not hosts:
            log.warning(f"{self.name} - no viable hosts returned by Netbox")
            return ret

        # add interfaces data
        if interfaces:
            # decide on get_interfaces arguments
            kwargs = interfaces if isinstance(interfaces, dict) else {}
            # add 'interfaces' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("interfaces", {})
            # query interfaces data from netbox
            nb_interfaces = self.get_interfaces(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save interfaces data to hosts' inventory
            while nb_interfaces.result:
                device, device_interfaces = nb_interfaces.result.popitem()
                hosts[device]["data"]["interfaces"] = device_interfaces

        # add connections data
        if connections:
            # decide on get_interfaces arguments
            kwargs = connections if isinstance(connections, dict) else {}
            # add 'connections' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("connections", {})
            # query connections data from netbox
            nb_connections = self.get_connections(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save connections data to hosts' inventory
            while nb_connections.result:
                device, device_connections = nb_connections.result.popitem()
                hosts[device]["data"]["connections"] = device_connections

        # add circuits data
        if circuits:
            # decide on get_interfaces arguments
            kwargs = circuits if isinstance(circuits, dict) else {}
            # add 'circuits' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("circuits", {})
            # query circuits data from netbox
            nb_circuits = self.get_circuits(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save circuits data to hosts' inventory
            while nb_circuits.result:
                device, device_circuits = nb_circuits.result.popitem()
                hosts[device]["data"]["circuits"] = device_circuits

        return ret

    def get_nornir_hosts(self, kwargs: dict, timeout: int):
        """
        Retrieves a list of unique Nornir hosts from Nornir service based on provided filter criteria.

        Args:
            kwargs (dict): Dictionary of keyword arguments, where keys starting with 'F' are used as filters.
            timeout (int): Timeout value (in seconds) for the job execution.

        Returns:
            list: Sorted list of unique Nornir host names that match the filter criteria.

        Notes:
            - Only filters with keys starting with 'F' are considered.
            - Hosts are collected from all workers where the job did not fail.
        """
        ret = []
        filters = {k: v for k, v in kwargs.items() if k.startswith("F")}
        if filters:
            nornir_hosts = self.client.run_job(
                "nornir",
                "get_nornir_hosts",
                kwargs=filters,
                workers="all",
                timeout=timeout,
            )
            for w, r in nornir_hosts.items():
                if r["failed"] is False:
                    ret.extend(r["result"])

        return list(sorted(set(ret)))

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def update_device_facts(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: Union[None, list] = None,
        batch_size: int = 10,
        branch: str = None,
        **kwargs,
    ) -> Result:
        """
        Updates the device facts in NetBox:

        - serial number

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, no changes will be made to NetBox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_facts getter

            timeout (int, optional): The timeout for the job execution. Defaults to 60.
            devices (list, optional): The list of devices to update.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments to pass to the job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in NetBox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:update_device_facts", result=result, resources=[instance]
        )
        nb = self._get_pynetbox(instance, branch=branch)
        kwargs["add_details"] = True

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_facts"
                job.event(
                    f"retrieving facts data for devices {', '.join(kwargs['FL'])}",
                    resource=instance,
                )
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_facts failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        if host_data["napalm_get"]["failed"]:
                            log.error(
                                f"{host} facts update failed: '{host_data['napalm_get']['exception']}'"
                            )
                            job.event(
                                f"{host} facts update failed",
                                resource=instance,
                                status="failed",
                                severity="WARNING",
                            )
                            continue
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        facts = host_data["napalm_get"]["result"]["get_facts"]
                        # update serial number
                        nb_device.serial = facts["serial_number"]
                        if not dry_run:
                            nb_device.save()
                        result[host] = {
                            (
                                "update_device_facts_dry_run"
                                if dry_run
                                else "update_device_facts"
                            ): {
                                "serial": facts["serial_number"],
                            }
                        }
                        if branch is not None:
                            result[host]["branch"] = branch
                        job.event(f"{host} facts updated", resource=instance)
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def update_device_interfaces(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: Union[None, list] = None,
        create: bool = True,
        batch_size: int = 10,
        branch: str = None,
        **kwargs,
    ) -> Result:
        """
        Update or create device interfaces in Netbox. Interface parameters updated:

        - interface name
        - interface description
        - mtu
        - mac address
        - admin status
        - speed

        Args:
            job: NorFab Job object containing relevant metadata.
            instance (str, optional): The Netbox instance name to use.
            dry_run (bool, optional): If True, no changes will be made to Netbox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces getter

            timeout (int, optional): The timeout for the job.
            devices (list, optional): List of devices to update.
            create (bool, optional): If True, new interfaces will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments to pass to the datasource job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:update_device_interfaces",
            result=result,
            resources=[instance],
        )
        nb = self._get_pynetbox(instance, branch=branch)

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces"
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_interfaces failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        updated, created = {}, {}
                        result[host] = {
                            (
                                "update_device_interfaces_dry_run"
                                if dry_run
                                else "update_device_interfaces"
                            ): updated,
                            (
                                "created_device_interfaces_dry_run"
                                if dry_run
                                else "created_device_interfaces"
                            ): created,
                        }
                        if branch is not None:
                            result[host]["branch"] = branch
                        interfaces = host_data["napalm_get"]["get_interfaces"]
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        nb_interfaces = nb.dcim.interfaces.filter(
                            device_id=nb_device.id
                        )
                        # update existing interfaces
                        for nb_interface in nb_interfaces:
                            if nb_interface.name not in interfaces:
                                continue
                            interface = interfaces.pop(nb_interface.name)
                            if dry_run is not True:
                                nb_interface.description = interface["description"]
                                if interface["mtu"] > 0:
                                    nb_interface.mtu = interface["mtu"]
                                if interface["speed"] > 0:
                                    nb_interface.speed = interface["speed"] * 1000
                                if interface["mac_address"].strip().lower() not in [
                                    "none",
                                    "",
                                ]:
                                    mac_address = interface["mac_address"]
                                    if self.nb_version[instance] >= (4, 2, 0):
                                        try:
                                            nb_mac_addr = nb.dcim.mac_addresses.get(
                                                mac_address=mac_address,
                                                interface_id=nb_interface.id,
                                            )
                                        except Exception as e:
                                            msg = f"{worker} failed to get {mac_address} mac-address from netbox: {e}"
                                            job.event(msg, severity="WARNING")
                                            ret.messages.append(msg)
                                            log.error(msg)
                                        else:
                                            if not nb_mac_addr:
                                                nb_mac_addr = nb.dcim.mac_addresses.create(
                                                    mac_address=mac_address,
                                                    assigned_object_type="dcim.interface",
                                                    assigned_object_id=nb_interface.id,
                                                )
                                            elif not nb_mac_addr.assigned_object_id:
                                                nb_mac_addr.assigned_object_type = (
                                                    "dcim.interface"
                                                )
                                                nb_mac_addr.assigned_object_id = (
                                                    nb_interface.id
                                                )
                                            if not nb_interface.primary_mac_address:
                                                nb_interface.primary_mac_address = (
                                                    nb_mac_addr.id
                                                )
                                                job.event(
                                                    f"{host} {mac_address} MAC associating with interface {nb_interface.name}",
                                                    resource=instance,
                                                )
                                        nb_interface.mac_address = mac_address
                                nb_interface.enabled = interface["is_enabled"]
                                nb_interface.save()
                            updated[nb_interface.name] = interface
                            job.event(
                                f"{host} updated interface {nb_interface.name}",
                                resource=instance,
                            )
                        # create new interfaces
                        if create is not True:
                            continue
                        for interface_name, interface in interfaces.items():
                            interface["type"] = "other"
                            if dry_run is not True:
                                nb_interface = nb.dcim.interfaces.create(
                                    name=interface_name,
                                    device={"name": nb_device.name},
                                    type=interface["type"],
                                )
                                nb_interface.description = interface["description"]
                                if interface["mtu"] > 0:
                                    nb_interface.mtu = interface["mtu"]
                                if interface["speed"] > 0:
                                    nb_interface.speed = interface["speed"] * 1000
                                # create MAC address
                                if interface["mac_address"].strip().lower() not in [
                                    "none",
                                    "",
                                ]:
                                    mac_address = interface["mac_address"]
                                    if self.nb_version[instance] >= (4, 2, 0):
                                        try:
                                            nb_mac_addr = nb.dcim.mac_addresses.create(
                                                mac_address=mac_address,
                                                assigned_object_type="dcim.interface",
                                                assigned_object_id=nb_interface.id,
                                            )
                                        except Exception as e:
                                            msg = f"{host} {mac_address} MAC failed to create, interface {nb_interface.name}: {e}"
                                            job.event(msg, severity="WARNING")
                                            ret.messages.append(msg)
                                            log.error(msg)
                                        else:
                                            nb_interface.primary_mac_address = (
                                                nb_mac_addr.id
                                            )
                                    else:
                                        nb_interface.mac_address = mac_address
                                    job.event(
                                        f"{host} {mac_address} MAC created, associating with interface {nb_interface.name}",
                                        resource=instance,
                                    )
                                nb_interface.enabled = interface["is_enabled"]
                                nb_interface.save()
                            created[interface_name] = interface
                            job.event(
                                f"{host} created interface {interface_name}",
                                resource=instance,
                            )
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def update_device_ip(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: Union[None, list] = None,
        create: bool = True,
        batch_size: int = 10,
        branch: str = None,
        **kwargs,
    ) -> Result:
        """
        Update the IP addresses of devices in Netbox.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): The Netbox instance name to use.
            dry_run (bool, optional): If True, no changes will be made.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces_ip getter

            timeout (int, optional): The timeout for the operation.
            devices (list, optional): The list of devices to update.
            create (bool, optional): If True, new IP addresses will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:update_device_ip", result=result, resources=[instance]
        )
        nb = self._get_pynetbox(instance, branch=branch)

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces_ip"
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_interfaces_ip failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        updated, created = {}, {}
                        result[host] = {
                            "updated_ip_dry_run" if dry_run else "updated_ip": updated,
                            "created_ip_dry_run" if dry_run else "created_ip": created,
                        }
                        if branch is not None:
                            result[host]["branch"] = branch
                        interfaces = host_data["napalm_get"]["get_interfaces_ip"]
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        nb_interfaces = nb.dcim.interfaces.filter(
                            device_id=nb_device.id
                        )
                        # update interface IP addresses
                        for nb_interface in nb_interfaces:
                            if nb_interface.name not in interfaces:
                                continue
                            interface = interfaces.pop(nb_interface.name)
                            # merge v6 into v4 addresses to save code repetition
                            ips = {
                                **interface.get("ipv4", {}),
                                **interface.get("ipv6", {}),
                            }
                            # update/create IP addresses
                            for ip, ip_data in ips.items():
                                prefix_length = ip_data["prefix_length"]
                                # get IP address info from Netbox
                                nb_ip = nb.ipam.ip_addresses.filter(
                                    address=f"{ip}/{prefix_length}"
                                )
                                if len(nb_ip) > 1:
                                    log.warning(
                                        f"{host} got multiple {ip}/{prefix_length} IP addresses from Netbox, "
                                        f"NorFab Netbox Service only supports handling of non-duplicate IPs."
                                    )
                                    continue
                                # decide what to do
                                if not nb_ip and create is False:
                                    continue
                                elif not nb_ip and create is True:
                                    if dry_run is not True:
                                        try:
                                            nb_ip = nb.ipam.ip_addresses.create(
                                                address=f"{ip}/{prefix_length}"
                                            )
                                        except Exception as e:
                                            msg = f"{host} failed to create {ip}/{prefix_length}, error: {e}"
                                            log.error(msg)
                                            job.event(msg, resource=instance)
                                            continue
                                        nb_ip.assigned_object_type = "dcim.interface"
                                        nb_ip.assigned_object_id = nb_interface.id
                                        nb_ip.status = "active"
                                        nb_ip.save()
                                    created[f"{ip}/{prefix_length}"] = nb_interface.name
                                    job.event(
                                        f"{host} created IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )
                                elif nb_ip:
                                    nb_ip = list(nb_ip)[0]
                                    if dry_run is not True:
                                        nb_ip.assigned_object_type = "dcim.interface"
                                        nb_ip.assigned_object_id = nb_interface.id
                                        nb_ip.status = "active"
                                        nb_ip.save()
                                    updated[nb_ip.address] = nb_interface.name
                                    job.event(
                                        f"{host} updated IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )

        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def create_ip(
        self,
        job: Job,
        prefix: Union[str, dict],
        device: str = None,
        interface: str = None,
        description: str = None,
        vrf: str = None,
        tags: Union[None, list] = None,
        dns_name: str = None,
        tenant: str = None,
        comments: str = None,
        role: str = None,
        is_primary: bool = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: str = None,
    ) -> Result:
        """
        Allocate the next available IP address from a given subnet.

        This task finds or creates an IP address in NetBox, updates its metadata,
        optionally links it to a device/interface, and supports a dry run mode for
        previewing changes.

        Args:
            prefix (str): The prefix from which to allocate the IP address, could be:

                - IPv4 prefix string e.g. 10.0.0.0/24
                - IPv6 prefix string e.g. 2001::/64
                - Prefix description string to filter by
                - Dictionary with prefix filters to feed `pynetbox` get method
                    e.g. `{"prefix": "10.0.0.0/24", "site__name": "foo"}`

            description (str, optional): A description for the allocated IP address.
            device (str, optional): The device associated with the IP address.
            interface (str, optional): The interface associated with the IP address.
            vrf (str, optional): The VRF (Virtual Routing and Forwarding) instance.
            tags (list, optional): A list of tags to associate with the IP address.
            dns_name (str, optional): The DNS name for the IP address.
            tenant (str, optional): The tenant associated with the IP address.
            comments (str, optional): Additional comments for the IP address.
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, do not actually allocate the IP address. Defaults to False.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.

        Returns:
            dict: A dictionary containing the result of the IP allocation.

        Tasks execution follow these steps:

        1. Tries to find an existing IP in NetBox matching the device/interface/description.
            If found, uses it; otherwise, proceeds to create a new IP.

        2. If prefix is a string, determines if it’s an IP network or a description.
            Builds a filter dictionary for NetBox queries, optionally including VRF.

        3. Queries NetBox for the prefix using the constructed filter.

        4. If dry_run is True, fetches the next available IP but doesn’t create it.

        5. If not a dry run, creates the next available IP in the prefix.

        6. Updates IP attributes (description, VRF, tenant, DNS name, comments, role, tags)
            if provided and different from current values. Handles interface assignment and
            can set the IP as primary for the device.

        7. If changes were made and not a dry run, saves the IP and device updates to NetBox.
        """
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:create_ip", result={}, resources=[instance])
        tags = tags or []
        has_changes = False
        nb_ip = None
        nb_device = None
        nb = self._get_pynetbox(instance, branch=branch)

        # try to source existing IP from netbox
        if device and interface and description:
            nb_ip = nb.ipam.ip_addresses.get(
                device=device, interface=interface, description=description
            )
        elif device and interface:
            nb_ip = nb.ipam.ip_addresses.get(device=device, interface=interface)
        elif description:
            nb_ip = nb.ipam.ip_addresses.get(description=description)

        # create new IP address
        if not nb_ip:
            job.event(f"Creating new IP address within prefix {prefix}")
            # source prefix from Netbox
            if isinstance(prefix, str):
                # try converting prefix to network, if fails prefix is not an IP network
                try:
                    network = ipaddress.ip_network(prefix)
                    is_network = True
                except:
                    is_network = False
                if is_network is True and vrf:
                    prefix = {"prefix": prefix, "vrf__name": vrf}
                elif is_network is True:
                    prefix = {"prefix": prefix}
                elif is_network is False and vrf:
                    prefix = {"description": prefix, "vrf__name": vrf}
                elif is_network is False:
                    prefix = {"description": prefix}
            nb_prefix = nb.ipam.prefixes.get(**prefix)
            if not nb_prefix:
                raise NetboxAllocationError(
                    f"Unable to source prefix from Netbox - {prefix}"
                )
            # execute dry run on new IP
            if dry_run is True:
                nb_ip = nb_prefix.available_ips.list()[0]
                ret.status = "unchanged"
                ret.dry_run = True
                ret.result = {
                    "address": str(nb_ip),
                    "description": description,
                    "vrf": vrf,
                    "device": device,
                    "interface": interface,
                }
                # add branch to results
                if branch is not None:
                    ret.result["branch"] = branch
                return ret
            # create new IP
            else:
                nb_ip = nb_prefix.available_ips.create()
            ret.status = "created"
        else:
            job.event(f"Using existing IP address {nb_ip}")
            ret.status = "updated"

        # update IP address parameters
        if description and description != nb_ip.description:
            nb_ip.description = description
            has_changes = True
        if vrf and vrf != nb_ip.vrf:
            nb_ip.vrf = {"name": vrf}
            has_changes = True
        if tenant and tenant != nb_ip.tenant:
            nb_ip.tenant = {"name": tenant}
            has_changes = True
        if dns_name and dns_name != nb_ip.dns_name:
            nb_ip.dns_name = dns_name
            has_changes = True
        if comments and comments != nb_ip.comments:
            nb_ip.comments = comments
            has_changes = True
        if role and role != nb_ip.role:
            nb_ip.role = role
            has_changes = True
        if tags and not any(t in nb_ip.tags for t in tags):
            for t in tags:
                if t not in nb_ip.tags:
                    nb_ip.tags.append({"name": t})
                    has_changes = True
        if device and interface:
            nb_interface = nb.dcim.interfaces.get(device=device, name=interface)
            if not nb_interface:
                raise NetboxAllocationError(
                    f"Unable to source '{device}:{interface}' interface from Netbox"
                )
            if (
                hasattr(nb_ip, "assigned_object")
                and nb_ip.assigned_object != nb_interface.id
            ):
                nb_ip.assigned_object_id = nb_interface.id
                nb_ip.assigned_object_type = "dcim.interface"
                if is_primary is not None:
                    nb_device = nb.dcim.devices.get(name=device)
                    nb_device.primary_ip4 = nb_ip.id
                has_changes = True

        # save IP address into Netbox
        if dry_run:
            ret.status = "unchanged"
            ret.dry_run = True
        elif has_changes:
            nb_ip.save()
            # make IP primary for device
            if is_primary is True and nb_device:
                nb_device.save()
        else:
            ret.status = "unchanged"

        # form and return results
        ret.result = {
            "address": str(nb_ip),
            "description": str(nb_ip.description),
            "vrf": str(nb_ip.vrf) if not vrf else nb_ip.vrf["name"],
            "device": device,
            "interface": interface,
        }
        # add branch to results
        if branch is not None:
            ret.result["branch"] = branch

        return ret

    @Task(
        input=CreatePrefixInput,
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
    )
    def create_prefix(
        self,
        job: Job,
        parent: Union[str, dict],
        description: str,
        prefixlen: int = 30,
        vrf: str = None,
        tags: Union[None, list] = None,
        tenant: str = None,
        comments: str = None,
        role: str = None,
        site: str = None,
        status: str = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: str = None,
    ) -> Result:
        """
        Creates a new IP prefix in NetBox or updates an existing one.

        Args:
            parent (Union[str, dict]): Parent prefix to allocate new prefix from, could be:

                - IPv4 prefix string e.g. 10.0.0.0/24
                - IPv6 prefix string e.g. 2001::/64
                - Prefix description string to filter by
                - Dictionary with prefix filters for `pynetbox` prefixes.get method
                    e.g. `{"prefix": "10.0.0.0/24", "site__name": "foo"}`

            description (str): Description for the new prefix, this is mandatory to have
                since prefix description used for deduplication to source existng prefixes.
            prefixlen (int, optional): The prefix length of the new prefix to create, by default
                allocates next availabe /30 point-to-point prefix.
            vrf (str, optional): Name of the VRF to associate with the prefix.
            tags (Union[None, list], optional): List of tags to assign to the prefix.
            tenant (str, optional): Name of the tenant to associate with the prefix.
            comments (str, optional): Comments for the prefix.
            role (str, optional): Role to assign to the prefix.
            site (str, optional): Name of the site to associate with the prefix.
            status (str, optional): Status of the prefix.
            instance (Union[None, str], optional): NetBox instance identifier.
            dry_run (bool, optional): If True, simulates the creation without making changes.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.

        Returns:
            Result: An object containing the outcome, including status, details of the prefix, and resources used.
        """
        instance = instance or self.default_instance
        changed = {}
        ret = Result(
            task=f"{self.name}:create_prefix",
            result={},
            resources=[instance],
            diff=changed,
        )
        tags = tags or []
        nb_prefix = None
        nb = self._get_pynetbox(instance, branch=branch)

        job.event(
            f"Processing create '/{prefixlen}' prefix request within '{parent}' parent prefix"
        )

        # source parent prefix from Netbox
        if isinstance(parent, str):
            # check if parent prefix is IP network or description
            try:
                _ = ipaddress.ip_network(parent)
                is_network = True
            except:
                is_network = False
            if is_network is True and vrf:
                parent_filters = {"prefix": parent, "vrf__name": vrf}
            elif is_network is True:
                parent_filters = {"prefix": parent}
            elif is_network is False and vrf:
                parent_filters = {"description": parent, "vrf__name": vrf}
            elif is_network is False:
                parent_filters = {"description": parent}
        nb_parent_prefix = nb.ipam.prefixes.get(**parent_filters)
        if not nb_parent_prefix:
            raise NetboxAllocationError(
                f"Unable to source parent prefix from Netbox - {parent}"
            )

        # check that parent vrf and new prefix vrf are same
        if vrf and str(nb_parent_prefix.vrf) != vrf:
            raise NetboxAllocationError(
                f"Parent prefix vrf '{nb_parent_prefix.vrf}' not same as requested child prefix vrf '{vrf}'"
            )

        # try to source existing prefix from netbox using its description
        prefix_filters = {"within": nb_parent_prefix.prefix, "description": description}
        if vrf:
            prefix_filters["vrf__name"] = vrf
        if site:
            prefix_filters["site__name"] = site
        try:
            nb_prefix = nb.ipam.prefixes.get(**prefix_filters)
        except Exception as e:
            raise NetboxAllocationError(
                f"Failed to source existing prefix from Netbox using filters '{prefix_filters}', error: {e}"
            )

        # create new prefix
        if not nb_prefix:
            job.event(f"Creating new '/{prefixlen}' prefix within '{parent}' prefix")
            # execute dry run on new prefix
            if dry_run is True:
                nb_prefixes = nb_parent_prefix.available_prefixes.list()
                if not nb_prefixes:
                    raise NetboxAllocationError(
                        f"Parent prefix '{parent}' has no child prefixes available"
                    )
                for pfx in nb_prefixes:
                    # parent prefix empty, can use first subnet as a child prefix
                    if pfx.prefix == nb_parent_prefix.prefix:
                        nb_prefix = (
                            nb_parent_prefix.prefix.split("/")[0] + f"/{prefixlen}"
                        )
                        break
                    # find child prefix by prefixlenght
                    elif str(pfx).endswith(f"/{prefixlen}"):
                        nb_prefix = str(pfx)
                        break
                else:
                    raise NetboxAllocationError(
                        f"Parent prefix '{parent}' has no child prefixes available with '/{prefixlen}' prefix length"
                    )
                ret.status = "unchanged"
                ret.dry_run = True
                ret.result = {
                    "prefix": nb_prefix,
                    "description": description,
                    "parent": nb_parent_prefix.prefix,
                    "vrf": vrf,
                    "site": site,
                }
                # add branch to results
                if branch is not None:
                    ret.result["branch"] = branch
                return ret
            # create new prefix
            else:
                try:
                    nb_prefix = nb_parent_prefix.available_prefixes.create(
                        {"prefix_length": prefixlen}
                    )
                except Exception as e:
                    raise NetboxAllocationError(
                        f"Failed creating child prefix of '/{prefixlen}' prefix length "
                        f"within parent prefix '{str(nb_parent_prefix)}', error: {e}"
                    )
            ret.status = "created"
        else:
            # check existing prefix length matching requested length
            if not nb_prefix.prefix.endswith(f"/{prefixlen}"):
                raise NetboxAllocationError(
                    f"Found existing child prefix '{nb_prefix.prefix}' with mismatch "
                    f"requested prefix length '/{prefixlen}'"
                )
            job.event(f"Using existing prefix {nb_prefix}")

        # update prefix parameters
        if description and description != nb_prefix.description:
            changed["description"] = {"-": str(nb_prefix.description), "+": description}
            nb_prefix.description = description
        if vrf and vrf != str(nb_prefix.vrf):
            changed["vrf"] = {"-": str(nb_prefix.vrf), "+": vrf}
            nb_prefix.vrf = {"name": vrf}
        if tenant and tenant != str(nb_prefix.tenant):
            changed["tenant"] = {
                "-": str(nb_prefix.tenant) if nb_prefix.tenant else None,
                "+": tenant,
            }
            nb_prefix.tenant = {"name": tenant}
        if site and str(nb_prefix.scope) != site:
            nb_site = nb.dcim.sites.get(name=site)
            if not nb_site:
                raise NetboxAllocationError(f"Failed to get '{site}' site from Netbox")
            changed["site"] = {
                "-": str(nb_prefix.scope) if nb_prefix.scope else None,
                "+": nb_site.name,
            }
            nb_prefix.scope_type = "dcim.site"
            nb_prefix.scope_id = nb_site.id
        if status and status.lower() != nb_prefix.status:
            changed["status"] = {"-": str(nb_prefix.status), "+": status.title()}
            nb_prefix.status = status.lower()
        if comments and comments != nb_prefix.comments:
            changed["comments"] = {"-": str(nb_prefix.comments), "+": comments}
            nb_prefix.comments = comments
        if role and role != nb_prefix.role:
            changed["role"] = {"-": str(nb_prefix.role), "+": role}
            nb_prefix.role = {"name": role}
        existing_tags = [str(t) for t in nb_prefix.tags]
        if tags and not any(t in existing_tags for t in tags):
            changed["tags"] = {
                "-": existing_tags,
                "+": [t for t in tags if t not in existing_tags] + existing_tags,
            }
            for t in tags:
                if t not in existing_tags:
                    nb_prefix.tags.append({"name": t})

        # save prefix into Netbox
        if dry_run:
            ret.status = "unchanged"
            ret.dry_run = True
            ret.diff = changed
        elif changed:
            ret.diff = changed
            nb_prefix.save()
            if ret.status != "created":
                ret.status = "updated"
        else:
            ret.status = "unchanged"

        # source vrf name
        vrf_name = None
        if nb_prefix.vrf:
            if isinstance(nb_prefix.vrf, dict):
                vrf_name = nb_prefix.vrf["name"]
            else:
                vrf_name = nb_prefix.vrf.name

        # form and return results
        ret.result = {
            "prefix": nb_prefix.prefix,
            "description": nb_prefix.description,
            "vrf": vrf_name,
            "site": str(nb_prefix.scope) if nb_prefix.scope else site,
            "parent": nb_parent_prefix.prefix,
        }
        # add branch to results
        if branch is not None:
            ret.result["branch"] = branch

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_containerlab_inventory(
        self,
        job: Job,
        lab_name: str = None,
        tenant: Union[None, str] = None,
        filters: Union[None, list] = None,
        devices: Union[None, list] = None,
        instance: Union[None, str] = None,
        image: Union[None, str] = None,
        ipv4_subnet: str = "172.100.100.0/24",
        ports: tuple = (12000, 15000),
        ports_map: Union[None, dict] = None,
        cache: Union[bool, str] = False,
    ) -> Result:
        """
        Retrieve and construct Containerlab inventory from NetBox data.

        Containerlab node details must be defined under device configuration
        context `norfab.containerlab` path, for example:

        ```
        {
            "norfab": {
                "containerlab": {
                    "kind": "ceos",
                    "image": "ceos:latest",
                    "mgmt-ipv4": "172.100.100.10/24",
                    "ports": [
                        {10000: 22},
                        {10001: 830}
                    ],

                    ... any other node parameters ...

                    "interfaces_rename": [
                        {
                            "find": "eth",
                            "replace": "Eth",
                            "use_regex": false
                        }
                    ]
                }
            }
        }
        ```

        For complete list of parameters refer to
        [Containerlab nodes definition](https://containerlab.dev/manual/nodes/).

        Special handling given to these parameters:

        - `lab_name` - if not provided uses `tenant` argument value as a lab name
        - `kind` - uses device platform field value by default
        - `image` - uses `image` value if provided, otherwise uses `{kind}:latest`
        - `interfaces_rename` - a list of one or more interface renaming instructions,
            each item must have `find` and `replace` defined, optional `use_regex`
            flag specifies whether to use regex based pattern substitution.

        To retrieve topology data from Netbox at least one of these arguments must be provided
        to identify a set of devices to include into Containerlab topology:

        - `tenant` - topology constructed using all devices and links that belong to this tenant
        - `devices` - creates topology only using devices in the lists
        - `filters` - list of device filters to retrieve from Netbox and add to topology

        If multiple of above arguments provided, resulting lab topology is a sum of all
        devices matched.

        Args:
            job: NorFab Job object containing relevant metadata
            lab_name (str, Mandatory): Name of containerlab to construct inventory for.
            tenant (str, optional): Construct topology using given tenant's devices
            filters (list, optional): List of filters to apply when retrieving devices from NetBox.
            devices (list, optional): List of specific devices to retrieve from NetBox.
            instance (str, optional): NetBox instance to use.
            image (str, optional): Default containerlab image to use,
            ipv4_subnet (str, Optional): Management subnet to use to IP number nodes
                starting with 2nd IP in the subnet, in assumption that 1st IP is a default gateway.
            ports (tuple, Optional): Ports range to use for nodes.
            ports_map (dict, Optional): dictionary keyed by node name with list of ports maps to use,
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: Containerlab inventory dictionary containing lab topology data
        """
        devices = devices or []
        filters = filters or []
        nodes, links = {}, []
        ports_map = ports_map or {}
        endpts_done = []  # to deduplicate links
        instance = instance or self.default_instance
        # handle lab name and tenant name with filters
        if lab_name is None and tenant:
            lab_name = tenant
        # add tenant filters
        if tenant:
            filters = filters or [{}]
            for filter in filters:
                if self.nb_version[instance] >= (4, 3, 0):
                    filter["tenant"] = f'{{name: {{exact: "{tenant}"}}}}'
                else:
                    filter["tenant"] = tenant

        # construct inventory
        inventory = {
            "name": lab_name,
            "topology": {"nodes": nodes, "links": links},
            "mgmt": {"ipv4-subnet": ipv4_subnet, "network": f"br-{lab_name}"},
        }
        ret = Result(
            task=f"{self.name}:get_containerlab_inventory",
            result=inventory,
            resources=[instance],
        )
        mgmt_net = ipaddress.ip_network(ipv4_subnet)
        available_ips = list(mgmt_net.hosts())[1:]

        # run checks
        if not available_ips:
            raise ValueError(f"Need IPs to allocate, but '{ipv4_subnet}' given")
        if ports:
            available_ports = list(range(ports[0], ports[1]))
        else:
            raise ValueError(f"Need ports to allocate, but '{ports}' given")

        # check Netbox status
        netbox_status = self.get_netbox_status(job=job, instance=instance)
        if netbox_status.result[instance]["status"] is False:
            ret.failed = True
            ret.messages = [f"Netbox status is no good: {netbox_status}"]
            return ret

        # retrieve devices data
        log.debug(
            f"Fetching devices from {instance} Netbox instance, devices '{devices}', filters '{filters}'"
        )
        job.event("Fetching devices data from Netbox")
        nb_devices = self.get_devices(
            job=job,
            filters=filters,
            devices=devices,
            instance=instance,
            cache=cache,
        )

        # form Containerlab nodes inventory
        for device_name, device in nb_devices.result.items():
            node = device["config_context"].get("norfab", {}).get("containerlab", {})
            # populate node parameters
            if not node.get("kind"):
                if device["platform"]:
                    node["kind"] = device["platform"]["name"]
                else:
                    msg = (
                        f"{device_name} - has no 'kind' of 'platform' defined, skipping"
                    )
                    log.warning(msg)
                    job.event(msg, severity="WARNING")
                    continue
            if not node.get("image"):
                if image:
                    node["image"] = image
                else:
                    node["image"] = f"{node['kind']}:latest"
            if not node.get("mgmt-ipv4"):
                if available_ips:
                    node["mgmt-ipv4"] = f"{available_ips.pop(0)}"
                else:
                    raise RuntimeError("Run out of IP addresses to allocate")
            if not node.get("ports"):
                node["ports"] = []
                # use ports map
                if ports_map.get(device_name):
                    node["ports"] = ports_map[device_name]
                # allocate next-available ports
                else:
                    for port in [
                        "22/tcp",
                        "23/tcp",
                        "80/tcp",
                        "161/udp",
                        "443/tcp",
                        "830/tcp",
                        "8080/tcp",
                    ]:
                        if available_ports:
                            node["ports"].append(f"{available_ports.pop(0)}:{port}")
                        else:
                            raise RuntimeError(
                                "Run out of TCP / UDP ports to allocate."
                            )

            # save node content
            nodes[device_name] = node
            job.event(f"Node added {device_name}")

        # return if no nodes found for provided parameters
        if not nodes:
            msg = f"{self.name} - no devices found in Netbox"
            log.error(msg)
            ret.failed = True
            ret.messages = [
                f"{self.name} - no devices found in Netbox, "
                f"devices - '{devices}', filters - '{filters}'"
            ]
            ret.errors = [msg]
            return ret

        job.event("Fetching connections data from Netbox")

        # query interface connections data from netbox
        nb_connections = self.get_connections(
            job=job, devices=list(nodes), instance=instance, cache=cache
        )
        # save connections data to links inventory
        while nb_connections.result:
            device, device_connections = nb_connections.result.popitem()
            for interface, connection in device_connections.items():
                # skip non ethernet links
                if connection.get("termination_type") != "interface":
                    continue
                # skip orphaned links
                if not connection.get("remote_interface"):
                    continue
                # skip connections to devices that are not part of lab
                if connection["remote_device"] not in nodes:
                    continue
                endpoints = []
                link = {
                    "type": "veth",
                    "endpoints": endpoints,
                }
                # add A node
                endpoints.append(
                    {
                        "node": device,
                        "interface": interface,
                    }
                )
                # add B node
                endpoints.append({"node": connection["remote_device"]})
                if connection.get("breakout") is True:
                    endpoints[-1]["interface"] = connection["remote_interface"][0]
                else:
                    endpoints[-1]["interface"] = connection["remote_interface"]
                # save the link
                a_end = (
                    endpoints[0]["node"],
                    endpoints[0]["interface"],
                )
                b_end = (
                    endpoints[1]["node"],
                    endpoints[1]["interface"],
                )
                if a_end not in endpts_done and b_end not in endpts_done:
                    endpts_done.append(a_end)
                    endpts_done.append(b_end)
                    links.append(link)
                    job.event(
                        f"Link added {endpoints[0]['node']}:{endpoints[0]['interface']}"
                        f" - {endpoints[1]['node']}:{endpoints[1]['interface']}"
                    )

        # query circuits connections data from netbox
        nb_circuits = self.get_circuits(
            job=job, devices=list(nodes), instance=instance, cache=cache
        )
        # save circuits data to hosts' inventory
        while nb_circuits.result:
            device, device_circuits = nb_circuits.result.popitem()
            for cid, circuit in device_circuits.items():
                # skip circuits not connected to devices
                if not circuit.get("remote_interface"):
                    continue
                # skip circuits to devices that are not part of lab
                if circuit["remote_device"] not in nodes:
                    continue
                endpoints = []
                link = {
                    "type": "veth",
                    "endpoints": endpoints,
                }
                # add A node
                endpoints.append(
                    {
                        "node": device,
                        "interface": circuit["interface"],
                    }
                )
                # add B node
                endpoints.append(
                    {
                        "node": circuit["remote_device"],
                        "interface": circuit["remote_interface"],
                    }
                )
                # save the link
                a_end = (
                    endpoints[0]["node"],
                    endpoints[0]["interface"],
                )
                b_end = (
                    endpoints[1]["node"],
                    endpoints[1]["interface"],
                )
                if a_end not in endpts_done and b_end not in endpts_done:
                    endpts_done.append(a_end)
                    endpts_done.append(b_end)
                    links.append(link)
                    job.event(
                        f"Link added {endpoints[0]['node']}:{endpoints[0]['interface']}"
                        f" - {endpoints[1]['node']}:{endpoints[1]['interface']}"
                    )

        # rename links' interfaces
        for node_name, node_data in nodes.items():
            interfaces_rename = node_data.pop("interfaces_rename", [])
            if interfaces_rename:
                job.event(f"Renaming {node_name} interfaces")
            for item in interfaces_rename:
                if not item.get("find") or not item.get("replace"):
                    log.error(
                        f"{self.name} - interface rename need to have"
                        f" 'find' and 'replace' defined, skipping: {item}"
                    )
                    continue
                pattern = item["find"]
                replace = item["replace"]
                use_regex = item.get("use_regex", False)
                # go over links one by one and rename interfaces
                for link in links:
                    for endpoint in link["endpoints"]:
                        if endpoint["node"] != node_name:
                            continue
                        if use_regex:
                            renamed = re.sub(
                                pattern,
                                replace,
                                endpoint["interface"],
                            )
                        else:
                            renamed = endpoint["interface"].replace(pattern, replace)
                        if endpoint["interface"] != renamed:
                            msg = f"{node_name} interface {endpoint['interface']} renamed to {renamed}"
                            log.debug(msg)
                            job.event(msg)
                            endpoint["interface"] = renamed

        return ret

    @Task(
        fastapi={"methods": ["DELETE"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def delete_branch(
        self,
        job: Job,
        branch: str = None,
        instance: str = None,
    ) -> Result:
        """
        Deletes a branch with the specified name from the NetBox instance.

        Args:
            job (Job): The job context for the operation.
            branch (str, optional): The name of the branch to delete.
            instance (str, optional): The NetBox instance name.

        Returns:
            Result: An object containing the outcome of the deletion operation,
                including whether the branch was found and deleted.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:delete_branch",
            result=None,
            resources=[instance],
        )
        nb = self._get_pynetbox(instance)

        job.event(f"Deleting branch '{branch}', Netbo instance '{instance}'")

        nb_branch = nb.plugins.branching.branches.get(name=branch)

        if nb_branch:
            nb_branch.delete()
            ret.result = True
            job.event(f"'{branch}' deleted from '{instance}' Netbox instance")
        else:
            msg = f"'{branch}' branch does not exist in '{instance}' Netbox instance"
            ret.result = None
            ret.messages.append(msg)
            job.event(msg)

        return ret
