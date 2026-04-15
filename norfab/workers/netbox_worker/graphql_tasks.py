import json
import logging
import concurrent.futures
from typing import Any, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_exceptions import UnsupportedNetboxVersion
from .netbox_models import NetboxFastApiArgs

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


def graphql_fetch_page(
    token: str,
    nb_url: str,
    ssl_verify: bool,
    query: str,
    variables: dict,
    connect_timeout: int,
    read_timeout: int,
    worker_name: str,
) -> dict[str, Any]:
    """Execute a single paginated GraphQL POST request and return the ``data`` payload.

    Each call creates its own :class:`requests.Session` so it is safe to call
    concurrently from multiple threads.

    Args:
        token: NetBox API token used in the ``Authorization`` header.
        nb_url: Base URL of the NetBox instance (e.g. ``https://netbox.example.com``).
        ssl_verify: Whether to verify TLS certificates.
        query: GraphQL query string.
        variables: Variable mapping sent with the query (must include ``offset`` and ``limit``).
        connect_timeout: Connection timeout in seconds.
        read_timeout: Read timeout in seconds.
        worker_name: Worker name used in error messages.

    Returns:
        The ``data`` section of the GraphQL JSON response.

    Raises:
        requests.HTTPError: If the HTTP response status indicates an error.
        RuntimeError: If the GraphQL response body contains an ``errors`` field.
    """
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"POST"},
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }
    )
    try:
        response = session.post(
            url=f"{nb_url}/graphql/",
            json={"query": query, "variables": variables},
            verify=ssl_verify,
            timeout=(connect_timeout, read_timeout),
        )
        response.raise_for_status()
        response_payload = response.json()
        if response_payload.get("errors"):
            raise RuntimeError(
                f"{worker_name} - GraphQL query returned errors: {response_payload['errors']}"
            )
        return response_payload.get("data", {})
    finally:
        session.close()


class NetboxGraphqlTasks:
    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def netbox_graphql(
        self,
        job: Job,
        instance: str,
        query: str,
        variables: Union[None, dict] = None,
        dry_run: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> Result:
        """
        Execute a paginated GraphQL query against a NetBox instance, fetching all pages in parallel.

        Pages are fetched in parallel batches of up to ``grapqhl_max_workers`` concurrent requests.
        Results across all pages are merged into a single ``aggregated_data`` dict where list
        fields are extended and scalar fields are overwritten.

        Args:
            job: NorFab job context.
            instance: Name of the NetBox instance to query.
            query: GraphQL query string. Must accept ``$offset: Int!`` and ``$limit: Int!``
                variables to support automatic pagination.
            variables: Optional extra GraphQL variables forwarded verbatim to the GraphQL query.
            dry_run: When ``True``, return the request parameters without executing any HTTP calls.
            offset: Starting pagination offset (number of records to skip before the first page).
            limit: Number of records per page fetched from NetBox.

        Returns:
            :class:`Result` whose ``result`` field holds the merged GraphQL ``data`` dict.
            On failure ``failed`` is ``True`` and ``errors`` lists the exception messages.
        """
        nb_params = self._get_instance_params(instance)
        ret = Result(task=f"{self.name}:graphql", resources=[instance])

        if dry_run:
            ret.dry_run = True
            ret.result = {
                "url": f"{nb_params['url']}/graphql/",
                "data": json.dumps({"query": query, "variables": variables or {}}),
                "verify": nb_params.get("ssl_verify", True),
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token ...{nb_params['token'][-6:]}",
                },
            }
            return ret

        aggregated_data: dict[str, Any] = {}
        ssl_verify = nb_params.get("ssl_verify", True)
        nb_url = nb_params["url"]

        # paginate through all results, fetching grapqhl_max_workers pages per iteration
        while True:
            batch_offsets = [
                offset + (i * limit) for i in range(self.grapqhl_max_workers)
            ]
            pages: list[tuple[int, dict[str, Any]]] = []

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.grapqhl_max_workers
            ) as pool:
                futures: dict[concurrent.futures.Future, int] = {
                    pool.submit(
                        graphql_fetch_page,
                        nb_params["token"],
                        nb_url,
                        ssl_verify,
                        query,
                        {**variables, "offset": page_offset, "limit": limit},
                        self.netbox_connect_timeout,
                        self.netbox_read_timeout,
                        self.name,
                    ): page_offset
                    for page_offset in batch_offsets
                }
                for future in concurrent.futures.as_completed(futures):
                    page_offset = futures[future]
                    try:
                        pages.append((page_offset, future.result()))
                    except Exception as exc:
                        error_msg = (
                            f"Failed to fetch page at offset {page_offset}: {exc}"
                        )
                        log.error(f"{self.name} - {error_msg}")
                        ret.errors.append(error_msg)
                        ret.failed = True

            # stop immediately if any page fetch failed — results would be incomplete
            if ret.failed:
                break

            any_data_returned = False
            has_full_page = False

            # merge pages in offset order to maintain consistent result ordering
            for _, data in sorted(pages, key=lambda item: item[0]):
                page_sizes: list[int] = []
                for key, value in data.items():
                    if isinstance(value, list):
                        if value:
                            any_data_returned = True
                        aggregated_data.setdefault(key, [])
                        aggregated_data[key].extend(value)
                        page_sizes.append(len(value))
                    else:
                        aggregated_data[key] = value
                # a full page means there may be more data to fetch
                if page_sizes and any(size == limit for size in page_sizes):
                    has_full_page = True

            # stop when no data was returned or no page was fully filled
            if not any_data_returned or not has_full_page:
                break

            offset += self.grapqhl_max_workers * limit

        if not ret.failed:
            ret.result = aggregated_data

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
            log.info(
                f"{self.name} - GraphQL dry run, returning query payload without executing"
            )
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
