"""NetBox generic CRUD task module — implementation.

Spec reference kept below.

---

NetBox generic CRUD task module. Provides seven tasks for any NetBox object type via the NFP
protocol. Designed primarily for AI Agents (MCP server, NorFab Agent), CLI, and automation.

Implements NetBox Performance Handbook recommendations:
- Use `fields` parameter on all reads (80-90% payload reduction)
- Use `brief=True` for list/search when full objects not needed
- Use server-side `filters` rather than client-side filtering
- Use smart `limit` values: higher with brief/few fields, lower with complex relations
- Bulk create/update/delete in single requests instead of per-object calls
- Cache OpenAPI schema (crud_list_objects) for 24h; rarely changes

Recommended field presets:
- Minimal:    ["id", "name"]
- Devices:    ["id", "name", "site", "device_type", "status", "serial"]
- Interfaces: ["id", "name", "type", "device", "mtu", "status"]
- IPs:        ["id", "address", "dns_name", "device", "interface", "status"]
- Sites:      ["id", "name", "slug", "status", "region", "group"]

Typical agent workflow: crud_list_objects → crud_search → crud_read →
crud_create/crud_update/crud_delete (dry_run=True first) → crud_get_changelogs


TASKS
=====

crud_list_objects(job, instance=None, app_filter=None, include_metadata=True)
    List all available NetBox object types extracted from OpenAPI schema.
    - instance: NetBox instance name; uses default if omitted
    - app_filter: str or list to filter by app(s) e.g. "dcim" or ["dcim", "ipam"]
    - include_metadata: if False returns object names only; if True includes path,
      methods (GET/POST/PATCH/PUT/DELETE), schema_name, description

    Implementation:
    1. nb.openapi() → fetch schema
    2. Iterate schema['paths'], match '/api/{app}/{object_type}/' pattern
    3. Extract app, object_type, methods, description per matching path
    4. Apply app_filter if provided; sort alphabetically by app then object_type
    5. Cache result in diskcache 24h TTL; key "netbox_{instance}_openapi_objects"

    Return: dict keyed by app → object_type → {path, object_type, methods, schema_name, description}

    Job events:
    - "extracting object types from OpenAPI schema for instance '{instance}'"
    - "retrieved {count} object types"


crud_search(job, query, object_types=None, fields=None, brief=False, limit=10, instance=None)
    Free-text search using the 'q' parameter across multiple object types simultaneously.
    Returns results grouped by object_type; continues on per-type errors (error-resilient).
    - query: search term; NetBox searches across all indexed fields
    - object_types: list of "app.resource" strings to search; default set:
      dcim.devices, dcim.sites, ipam.ip-addresses, ipam.prefixes,
      dcim.interfaces, circuits.circuits, tenancy.tenants, virtualization.virtual-machines
    - fields: list of specific fields to return; ignored when brief=True
    - brief: if True adds brief=1 to request (id, url, display, name, slug, description only)
    - limit: max results per object type (1-100)

    Implementation:
    1. _get_pynetbox(instance)
    2. Normalize object_types to list; validate each against crud_list_objects cache
    3. For each object_type: build params {'q': query, 'limit': limit}; add 'fields' or 'brief'
    4. Call pynetbox filter(**params); catch exceptions per type, log warning, continue
    5. Collect results; empty list for failed or no-match types

    Return: dict keyed by "app.resource" → list of matching objects

    Job events:
    - "searching '{query}' across {count} object type(s)"
    - "search completed: {total} matches found"


crud_read(job, object_type, object_id=None, filters=None, fields=None, brief=False,
          limit=50, offset=0, ordering=None, instance=None)
    Retrieve objects by ID(s) or filter dict(s).
    - object_type: "app.resource" e.g. "dcim.devices"
    - object_id: int or list[int]; when set, filters is ignored
    - filters: dict or list[dict]; list runs multiple queries merged into one result set
    - fields: list of specific fields to return; ignored when brief=True
    - brief: if True adds brief=1 (id, url, display, name, slug, description only)
    - limit: page size (1-1000); lower for complex relational queries, higher for brief/few fields
    - offset: pagination skip count
    - ordering: str or list[str]; prefix with '-' for descending e.g. ["-id", "name"]

    Implementation:
    1. Validate object_type; _get_pynetbox(instance)
    2. Resolve pynetbox accessor: getattr(getattr(nb, app), obj_type)
    3. Build params: add fields or brief; add ordering; add limit, offset
    4. If object_id int → .get(object_id); if list → filter(id__in=[...], **params)
    5. If filters dict → filter(**filters, **params)
    6. If filters list → run filter per dict, merge results, de-duplicate by id
    7. Return results with count, next, previous pagination metadata

    Return: {count, next, previous, results: [...]}

    Job events:
    - "retrieving {object_type} by ID(s)" or "retrieving {object_type} with {count} filter(s)"
    - "retrieved {count} total objects"


crud_create(job, object_type, data, instance=None, dry_run=False)
    Create one or multiple NetBox objects in a single request.
    - object_type: "app.resource" e.g. "dcim.interfaces"
    - data: dict (single) or list[dict] (bulk); normalized to list internally
    - dry_run: if True returns input data without calling NetBox (safe preview)

    Implementation:
    1. Validate object_type; _get_pynetbox(instance)
    2. Normalize data → list
    3. If dry_run: return {"dry_run": True, "count": len(data), "preview": data}
    4. Resolve accessor; call .create(data) (pynetbox accepts list for bulk)
    5. Return created objects with their new IDs

    Return:
    - Normal: {created: N, objects: [...full created objects...]}
    - dry_run: {dry_run: True, count: N, preview: [...input data...]}

    Job events:
    - "creating {count} {object_type}(s)"
    - "dry-run: would create {count} {object_type}(s)"


crud_update(job, object_type, data, partial=True, instance=None, dry_run=False)
    Update one or multiple NetBox objects. Each item in data MUST include "id".
    - object_type: "app.resource"
    - data: dict (single) or list[dict]; each must contain "id" field
    - partial: True → PATCH (only specified fields changed); False → PUT (full replace, destructive)
    - dry_run: if True fetches current state, computes diffs, returns without modifying

    Implementation:
    1. Validate object_type; normalize data → list; verify each item has "id"
    2. _get_pynetbox(instance); resolve accessor
    3. If dry_run:
       a. For each item: .get(id) to fetch current state
       b. Compute diff: {field: {old: current[field], new: item[field]}} for changed fields
       c. Return diffs without modifying
    4. If not dry_run: for each item call pynetbox obj.update(data) with partial flag
    5. Return updated objects

    Return:
    - Normal: {updated: N, objects: [...full updated objects...]}
    - dry_run: {dry_run: True, count: N, changes: [{id, changes: {field: {old, new}}}]}

    Job events:
    - "updating {count} {object_type}(s)"
    - "dry-run: computing diffs for {count} {object_type}(s)"


crud_delete(job, object_type, object_id, instance=None, dry_run=False)
    Delete one or multiple NetBox objects by ID.
    - object_type: "app.resource"
    - object_id: int (single) or list[int] (bulk)
    - dry_run: if True fetches and returns objects that would be deleted without removing them

    Implementation:
    1. Validate object_type; normalize object_id → list; _get_pynetbox(instance)
    2. Resolve accessor
    3. If dry_run: fetch each object by ID; return as preview without deleting
    4. If not dry_run: for each id call .get(id).delete(); track deleted count

    Return:
    - Normal: {deleted: N, deleted_ids: [...]}
    - dry_run: {dry_run: True, count: N, would_delete: [...objects...]}

    Job events:
    - "deleting {count} {object_type}(s)"
    - "dry-run: would delete {count} {object_type}(s)"


crud_get_changelogs(job, filters=None, fields=None, limit=50, offset=0, instance=None)
    Retrieve NetBox change history from the extras/object-changes endpoint.
    - filters: dict or list[dict]; supported filter keys:
        user_id, user, changed_object_id, changed_object_type_id,
        object_repr, action ("created"/"updated"/"deleted"),
        time_before, time_after (ISO-8601), q
    - fields: list of fields to return; prechange_data/postchange_data are large—
      only request when diffs are needed
    - limit: page size (1-1000)
    - offset: pagination skip count

    Implementation:
    1. _get_pynetbox(instance)
    2. Build params from filters dict; add fields, limit, offset
    3. If filters list: run multiple queries, merge results
    4. Call nb.extras.object_changes.filter(**params)
    5. Return paginated results

    Return: {count, next, previous, results: [{id, user, user_name, request_id, action,
             changed_object_type, changed_object_id, object_repr, time,
             prechange_data, postchange_data}]}

    Job events:
    - "retrieving changelogs with {count} filter(s)"
    - "retrieved {count} changelog entries"


PYDANTIC INPUT MODELS
======================

CrudListObjectsArgs:
    instance: Optional[str]
    app_filter: Union[None, str, List[str]]
    include_metadata: bool = True

CrudSearchArgs:
    query: str
    object_types: Optional[List[str]]
    fields: Optional[List[str]]
    brief: bool = False
    limit: int = 10  # 1-100
    instance: Optional[str]

CrudReadArgs:
    object_type: str
    object_id: Union[None, int, List[int]]
    filters: Union[None, Dict, List[Dict]]
    fields: Optional[List[str]]
    brief: bool = False
    limit: int = 50  # 1-1000
    offset: int = 0
    ordering: Union[None, str, List[str]]
    instance: Optional[str]

CrudCreateArgs:
    object_type: str
    data: Union[Dict, List[Dict]]
    instance: Optional[str]
    dry_run: bool = False

CrudUpdateArgs:
    object_type: str
    data: Union[Dict, List[Dict]]  # each item must have "id"
    partial: bool = True
    instance: Optional[str]
    dry_run: bool = False

CrudDeleteArgs:
    object_type: str
    object_id: Union[int, List[int]]
    instance: Optional[str]
    dry_run: bool = False

CrudChangelogArgs:
    filters: Union[None, Dict, List[Dict]]
    fields: Optional[List[str]]
    limit: int = 50  # 1-1000
    offset: int = 0
    instance: Optional[str]


INTEGRATION
===========

In netbox_worker.py add import and mixin:

    from .netbox_crud import NetboxCrudTasks

    class NetboxWorker(
        NFPWorker,
        ...,
        NetboxCrudTasks,
    ):
        pass

Helper methods available via inheritance from NetboxWorker:
    _get_pynetbox(instance, branch=None)  → pynetbox.api object
    _get_instance_params(instance)         → {url, token, ssl_verify}
    cache                                  → DiskCache (FanoutCache) instance


TESTS (test_netbox_service_crud_tasks.py)
=========================================

Naming convention: test_{task}_{scenario}

crud_list_objects: all_apps, app_filter_str, app_filter_list, include_metadata_false,
                   cache_hit, cache_miss
crud_search:       single_type, multiple_types, brief_mode, fields_filter,
                   error_resilient_partial_failure, no_results
crud_read:         by_id_single, by_id_list, filters_dict, filters_list, brief_mode,
                   fields_filter, pagination, ordering, invalid_object_type
crud_create:       single_object, bulk_objects, dry_run, invalid_data
crud_update:       single_object, bulk_objects, partial_patch, full_put,
                   dry_run_diffs, missing_id_field
crud_delete:       single_id, multiple_ids, dry_run, nonexistent_id
crud_get_changelogs: by_object_id, by_user, by_action, time_range,
                     fields_filter, pagination
common:            multi_instance, network_timeout, api_auth_failure
"""

import itertools
import logging
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxFastApiArgs

log = logging.getLogger(__name__)

# Matches only top-level collection paths: /api/{app}/{object_type}/
_OPENAPI_PATH_RE = re.compile(r"^/api/([^/]+)/([^/]+)/$")

OPENAPI_CACHE_TTL = 86400  # 24 hours


# ------------------------------------------------------------------------------
# PYDANTIC INPUT MODELS
# ------------------------------------------------------------------------------


class CrudListObjectsArgs(BaseModel):
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")
    app_filter: Union[None, StrictStr, List[StrictStr]] = Field(
        None, description='Filter by app(s) e.g. "dcim" or ["dcim", "ipam"]'
    )
    include_metadata: StrictBool = Field(
        True,
        description=(
            "If False returns object names only; "
            "if True includes path, methods, schema_name, description"
        ),
    )


class CrudSearchArgs(BaseModel):
    query: StrictStr = Field(..., description="Search term")
    object_types: Optional[List[StrictStr]] = Field(
        None, description='List of "app.resource" strings to search'
    )
    fields: Optional[List[StrictStr]] = Field(
        None, description="Specific fields to return; ignored when brief=True"
    )
    brief: StrictBool = Field(False, description="Return brief representation")
    limit: StrictInt = Field(10, ge=1, le=100, description="Max results per object type")
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")


class CrudReadArgs(BaseModel):
    object_type: StrictStr = Field(..., description='"app.resource" e.g. "dcim.devices"')
    object_id: Union[None, StrictInt, List[StrictInt]] = Field(
        None, description="Object ID(s); when set, filters is ignored"
    )
    filters: Union[None, Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        None, description="Filter dict(s)"
    )
    fields: Optional[List[StrictStr]] = Field(
        None, description="Specific fields to return; ignored when brief=True"
    )
    brief: StrictBool = Field(False, description="Return brief representation")
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")
    ordering: Union[None, StrictStr, List[StrictStr]] = Field(
        None, description="Ordering field(s); prefix with '-' for descending"
    )
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")


class CrudCreateArgs(BaseModel):
    object_type: StrictStr = Field(..., description='"app.resource" e.g. "dcim.interfaces"')
    data: Union[Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        ..., description="Object data; dict for single, list for bulk"
    )
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")
    dry_run: StrictBool = Field(False, description="Preview without creating")


class CrudUpdateArgs(BaseModel):
    object_type: StrictStr = Field(..., description='"app.resource"')
    data: Union[Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        ..., description="Object data; each item must contain 'id'"
    )
    partial: StrictBool = Field(True, description="True=PATCH (partial); False=PUT (full replace)")
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")
    dry_run: StrictBool = Field(False, description="Compute diffs without updating")


class CrudDeleteArgs(BaseModel):
    object_type: StrictStr = Field(..., description='"app.resource"')
    object_id: Union[StrictInt, List[StrictInt]] = Field(
        ..., description="Object ID(s) to delete"
    )
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")
    dry_run: StrictBool = Field(False, description="Preview without deleting")


class CrudChangelogArgs(BaseModel):
    filters: Union[None, Dict[StrictStr, Any], List[Dict[StrictStr, Any]]] = Field(
        None, description="Filter dict(s)"
    )
    fields: Optional[List[StrictStr]] = Field(
        None, description="Specific fields to return"
    )
    limit: StrictInt = Field(50, ge=1, le=1000, description="Page size")
    offset: StrictInt = Field(0, ge=0, description="Pagination skip count")
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")


# ------------------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------------------


def _get_pynetbox_accessor(nb: Any, object_type: str) -> Any:
    """Resolve pynetbox accessor from 'app.resource' string.

    Converts dashes to underscores in the resource name so that
    e.g. ``ipam.ip-addresses`` → ``nb.ipam.ip_addresses``.
    """
    app, resource = object_type.split(".", 1)
    resource_attr = resource.replace("-", "_")
    return getattr(getattr(nb, app), resource_attr)


def _schema_name_from_path_spec(path_spec: dict) -> Optional[str]:
    """Extract the write-model schema name from the POST requestBody of a path spec."""
    schema_ref = (
        path_spec.get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    for source in [schema_ref] + schema_ref.get("oneOf", []):
        if "$ref" in source:
            return source["$ref"].split("/")[-1]
        if source.get("type") == "array" and "$ref" in source.get("items", {}):
            return source["items"]["$ref"].split("/")[-1]
    return None


# ------------------------------------------------------------------------------
# CRUD TASKS MIXIN
# ------------------------------------------------------------------------------


class NetboxCrudTasks:

    # default object types searched by crud_search when none are provided
    _CRUD_SEARCH_DEFAULT_OBJECT_TYPES = [
        "dcim.devices",
        "dcim.sites",
        "ipam.ip-addresses",
        "ipam.prefixes",
        "dcim.interfaces",
        "circuits.circuits",
        "tenancy.tenants",
        "virtualization.virtual-machines",
    ]
    
    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_list_objects(
        self,
        job: Job,
        instance: Union[None, str] = None,
        app_filter: Union[None, str, list] = None,
        include_metadata: bool = True,
    ) -> Result:
        """
        List all available NetBox object types extracted from OpenAPI schema.

        Args:
            job: NorFab Job object
            instance: NetBox instance name; uses default if omitted
            app_filter: str or list to filter by app(s) e.g. "dcim" or ["dcim", "ipam"]
            include_metadata: if False returns object names only; if True includes path,
                methods (GET/POST/PATCH/PUT/DELETE), schema_name, description

        Returns:
            dict keyed by app → object_type → {path, object_type, methods, schema_name, description}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_list_objects",
            result={},
            resources=[instance],
        )
        cache_key = f"netbox_{instance}_openapi_objects"

        # return cached result if available
        if cache_key in self.cache:
            schema_data = self.cache[cache_key]
            log.info(
                f"{self.name} - Serving OpenAPI objects list from cache for '{instance}'"
            )
        else:
            job.event(
                f"extracting object types from OpenAPI schema for instance '{instance}'"
            )
            nb = self._get_pynetbox(instance)
            schema = nb.openapi()
            schema_data: Dict[str, Dict[str, Any]] = {}

            for path, path_spec in schema.get("paths", {}).items():
                match = _OPENAPI_PATH_RE.match(path)
                if not match:
                    continue

                app = match.group(1)
                object_type = match.group(2)
                methods = [
                    m.upper()
                    for m in ("get", "post", "put", "patch", "delete")
                    if m in path_spec
                ]
                schema_name = _schema_name_from_path_spec(path_spec)
                description = path_spec.get("get", {}).get("description", "")

                schema_data.setdefault(app, {})[object_type] = {
                    "path": path,
                    "object_type": object_type,
                    "methods": methods,
                    "schema_name": schema_name,
                    "description": description,
                }

            count = sum(len(obj_types) for obj_types in schema_data.values())
            job.event(f"retrieved {count} object types")
            log.info(
                f"{self.name} - Retrieved {count} object types from OpenAPI schema"
                f" for '{instance}'"
            )

            # cache for 24 hours
            self.cache.set(cache_key, schema_data, expire=OPENAPI_CACHE_TTL)

        # apply app_filter
        if app_filter:
            if isinstance(app_filter, str):
                app_filter = [app_filter]
            schema_data = {
                app: obj_types
                for app, obj_types in schema_data.items()
                if app in app_filter
            }

        # sort alphabetically by app then object_type
        result: Dict[str, Any] = {}
        for app in sorted(schema_data.keys()):
            result[app] = dict(sorted(schema_data[app].items()))

        # strip metadata if not requested
        if not include_metadata:
            for app in result:
                result[app] = list(result[app].keys())

        ret.result = result
        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_search(
        self,
        job: Job,
        query: str,
        object_types: Union[None, list] = None,
        fields: Union[None, list] = None,
        brief: bool = False,
        limit: int = 10,
        instance: Union[None, str] = None,
    ) -> Result:
        """
        Free-text search using the 'q' parameter across multiple object types.

        Results are grouped by object_type.  Per-type errors are logged as
        warnings and the search continues (error-resilient).

        Args:
            job: NorFab Job object
            query: search term; NetBox searches across all indexed fields
            object_types: list of "app.resource" strings to search; uses a
                sensible default set when omitted
            fields: list of specific fields to return; ignored when brief=True
            brief: if True adds brief=1 to request
            limit: max results per object type (1-100)
            instance: NetBox instance name; uses default if omitted

        Returns:
            dict keyed by "app.resource" → list of matching objects
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_search",
            result={},
            resources=[instance],
        )

        if object_types is None:
            object_types = list(self._CRUD_SEARCH_DEFAULT_OBJECT_TYPES)

        job.event(
            f"searching '{query}' across {len(object_types)} object type(s)"
        )

        nb = self._get_pynetbox(instance)

        for object_type in object_types:
            try:
                accessor = _get_pynetbox_accessor(nb, object_type)
                params: Dict[str, Any] = {"q": query, "limit": limit}
                if brief:
                    params["brief"] = 1
                elif fields:
                    params["fields"] = ",".join(fields)

                found = list(itertools.islice(accessor.filter(**params), limit))
                ret.result[object_type] = [dict(obj) for obj in found]
            except Exception as exc:
                log.warning(
                    f"{self.name} - crud_search: failed to search '{object_type}':"
                    f" {exc}"
                )
                ret.result[object_type] = []

        total = sum(len(v) for v in ret.result.values())
        job.event(f"search completed: {total} matches found")
        log.info(f"{self.name} - crud_search '{query}' completed: {total} matches")

        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_read(
        self,
        job: Job,
        object_type: str,
        object_id: Union[None, int, list] = None,
        filters: Union[None, dict, list] = None,
        fields: Union[None, list] = None,
        brief: bool = False,
        limit: int = 50,
        offset: int = 0,
        ordering: Union[None, str, list] = None,
        instance: Union[None, str] = None,
    ) -> Result:
        """
        Retrieve NetBox objects by ID(s) or filter dict(s).

        Args:
            job: NorFab Job object
            object_type: "app.resource" e.g. "dcim.devices"
            object_id: int or list[int]; when set, filters is ignored
            filters: dict or list[dict]; list runs multiple queries merged into one result set
            fields: list of specific fields to return; ignored when brief=True
            brief: if True adds brief=1
            limit: page size (1-1000)
            offset: pagination skip count
            ordering: str or list[str]; prefix with '-' for descending

        Returns:
            {count, next, previous, results: [...]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_read",
            result={},
            resources=[instance],
        )

        nb = self._get_pynetbox(instance)
        accessor = _get_pynetbox_accessor(nb, object_type)

        # build common params
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if brief:
            params["brief"] = 1
        elif fields:
            params["fields"] = ",".join(fields)
        if ordering:
            if isinstance(ordering, list):
                params["ordering"] = ",".join(ordering)
            else:
                params["ordering"] = ordering

        results = []

        if object_id is not None:
            if isinstance(object_id, int):
                job.event(f"retrieving {object_type} by ID(s)")
                obj = accessor.get(object_id)
                results = [dict(obj)] if obj else []
            else:
                job.event(f"retrieving {object_type} by ID(s)")
                found = list(accessor.filter(id=list(object_id), **params))
                results = [dict(o) for o in found]
        elif filters is not None:
            if isinstance(filters, dict):
                job.event(f"retrieving {object_type} with 1 filter(s)")
                found = list(accessor.filter(**filters, **params))
                results = [dict(o) for o in found]
            else:
                # list of dicts — run one filter per dict and merge
                job.event(
                    f"retrieving {object_type} with {len(filters)} filter(s)"
                )
                seen_ids: set = set()
                for flt in filters:
                    for obj in accessor.filter(**flt, **params):
                        obj_dict = dict(obj)
                        obj_id_ = obj_dict.get("id")
                        if obj_id_ not in seen_ids:
                            seen_ids.add(obj_id_)
                            results.append(obj_dict)
        else:
            job.event(f"retrieving {object_type} with 0 filter(s)")
            found = list(accessor.filter(**params))
            results = [dict(o) for o in found]

        job.event(f"retrieved {len(results)} total objects")
        log.info(
            f"{self.name} - crud_read '{object_type}': retrieved {len(results)} objects"
        )

        ret.result = {
            "count": len(results),
            "next": None,
            "previous": None,
            "results": results,
        }
        return ret

    @Task(fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_create(
        self,
        job: Job,
        object_type: str,
        data: Union[dict, list],
        instance: Union[None, str] = None,
        dry_run: bool = False,
    ) -> Result:
        """
        Create one or multiple NetBox objects in a single request.

        Args:
            job: NorFab Job object
            object_type: "app.resource" e.g. "dcim.interfaces"
            data: dict (single) or list[dict] (bulk); normalized to list internally
            instance: NetBox instance name; uses default if omitted
            dry_run: if True returns input data without calling NetBox

        Returns:
            - Normal: {created: N, objects: [...]}
            - dry_run: {dry_run: True, count: N, preview: [...input data...]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_create",
            result={},
            resources=[instance],
        )

        # normalise to list
        if isinstance(data, dict):
            data_list = [data]
        else:
            data_list = list(data)

        if dry_run:
            job.event(f"dry-run: would create {len(data_list)} {object_type}(s)")
            log.info(
                f"{self.name} - crud_create dry-run: {len(data_list)}"
                f" {object_type}(s) would be created"
            )
            ret.result = {
                "dry_run": True,
                "count": len(data_list),
                "preview": data_list,
            }
            return ret

        job.event(f"creating {len(data_list)} {object_type}(s)")

        nb = self._get_pynetbox(instance)
        accessor = _get_pynetbox_accessor(nb, object_type)

        created = accessor.create(data_list)
        # pynetbox returns a Record for single or list for bulk
        if not isinstance(created, list):
            created = [created]

        created_dicts = [dict(obj) for obj in created]
        log.info(
            f"{self.name} - crud_create '{object_type}':"
            f" created {len(created_dicts)} object(s)"
        )

        ret.result = {"created": len(created_dicts), "objects": created_dicts}
        return ret

    @Task(fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_update(
        self,
        job: Job,
        object_type: str,
        data: Union[dict, list],
        partial: bool = True,
        instance: Union[None, str] = None,
        dry_run: bool = False,
    ) -> Result:
        """
        Update one or multiple NetBox objects. Each item in data MUST include "id".

        Args:
            job: NorFab Job object
            object_type: "app.resource"
            data: dict (single) or list[dict]; each must contain "id" field
            partial: True → PATCH (only specified fields); False → PUT (full replace)
            instance: NetBox instance name; uses default if omitted
            dry_run: if True fetches current state, computes diffs, returns without modifying

        Returns:
            - Normal: {updated: N, objects: [...]}
            - dry_run: {dry_run: True, count: N, changes: [{id, changes: {field: {old, new}}}]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_update",
            result={},
            resources=[instance],
        )

        # normalise to list
        if isinstance(data, dict):
            data_list = [data]
        else:
            data_list = list(data)

        # validate that each item has an "id"
        for item in data_list:
            if "id" not in item:
                raise ValueError(
                    f"crud_update: each data item must contain 'id', got: {item}"
                )

        nb = self._get_pynetbox(instance)
        accessor = _get_pynetbox_accessor(nb, object_type)

        if dry_run:
            job.event(f"dry-run: computing diffs for {len(data_list)} {object_type}(s)")
            diffs = []
            for item in data_list:
                obj_id = item["id"]
                current = accessor.get(obj_id)
                current_dict = dict(current) if current else {}
                changes: Dict[str, Any] = {}
                for field, new_val in item.items():
                    if field == "id":
                        continue
                    old_val = current_dict.get(field)
                    if old_val != new_val:
                        changes[field] = {"old": old_val, "new": new_val}
                diffs.append({"id": obj_id, "changes": changes})
            log.info(
                f"{self.name} - crud_update dry-run '{object_type}':"
                f" computed diffs for {len(diffs)} object(s)"
            )
            ret.result = {
                "dry_run": True,
                "count": len(diffs),
                "changes": diffs,
            }
            return ret

        job.event(f"updating {len(data_list)} {object_type}(s)")

        updated_dicts = []
        for item in data_list:
            obj_id = item["id"]
            obj = accessor.get(obj_id)
            if obj:
                if partial:
                    obj.update(item)
                else:
                    # full PUT: save the entire item dict
                    obj.update(item)
                    obj.save()
                updated_dicts.append(dict(obj))

        log.info(
            f"{self.name} - crud_update '{object_type}':"
            f" updated {len(updated_dicts)} object(s)"
        )

        ret.result = {"updated": len(updated_dicts), "objects": updated_dicts}
        return ret

    @Task(fastapi={"methods": ["DELETE"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_delete(
        self,
        job: Job,
        object_type: str,
        object_id: Union[int, list],
        instance: Union[None, str] = None,
        dry_run: bool = False,
    ) -> Result:
        """
        Delete one or multiple NetBox objects by ID.

        Args:
            job: NorFab Job object
            object_type: "app.resource"
            object_id: int (single) or list[int] (bulk)
            instance: NetBox instance name; uses default if omitted
            dry_run: if True fetches and returns objects that would be deleted

        Returns:
            - Normal: {deleted: N, deleted_ids: [...]}
            - dry_run: {dry_run: True, count: N, would_delete: [...objects...]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_delete",
            result={},
            resources=[instance],
        )

        # normalise to list
        if isinstance(object_id, int):
            id_list = [object_id]
        else:
            id_list = list(object_id)

        nb = self._get_pynetbox(instance)
        accessor = _get_pynetbox_accessor(nb, object_type)

        if dry_run:
            job.event(f"dry-run: would delete {len(id_list)} {object_type}(s)")
            preview = []
            for oid in id_list:
                obj = accessor.get(oid)
                if obj:
                    preview.append(dict(obj))
            log.info(
                f"{self.name} - crud_delete dry-run '{object_type}':"
                f" would delete {len(id_list)} object(s)"
            )
            ret.result = {
                "dry_run": True,
                "count": len(preview),
                "would_delete": preview,
            }
            return ret

        job.event(f"deleting {len(id_list)} {object_type}(s)")

        deleted_ids = []
        for oid in id_list:
            obj = accessor.get(oid)
            if obj:
                obj.delete()
                deleted_ids.append(oid)

        log.info(
            f"{self.name} - crud_delete '{object_type}':"
            f" deleted {len(deleted_ids)} object(s)"
        )

        ret.result = {"deleted": len(deleted_ids), "deleted_ids": deleted_ids}
        return ret

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def crud_get_changelogs(
        self,
        job: Job,
        filters: Union[None, dict, list] = None,
        fields: Union[None, list] = None,
        limit: int = 50,
        offset: int = 0,
        instance: Union[None, str] = None,
    ) -> Result:
        """
        Retrieve NetBox change history from the extras/object-changes endpoint.

        Args:
            job: NorFab Job object
            filters: dict or list[dict]; supported filter keys include user_id, user,
                changed_object_id, changed_object_type_id, object_repr, action,
                time_before, time_after (ISO-8601), q
            fields: list of fields to return
            limit: page size (1-1000)
            offset: pagination skip count
            instance: NetBox instance name; uses default if omitted

        Returns:
            {count, next, previous, results: [{id, user, user_name, request_id, action,
             changed_object_type, changed_object_id, object_repr, time,
             prechange_data, postchange_data}]}
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:crud_get_changelogs",
            result={},
            resources=[instance],
        )

        filter_count = 1 if isinstance(filters, dict) else (len(filters) if filters else 0)
        job.event(
            f"retrieving changelogs with {filter_count} filter(s)"
        )

        nb = self._get_pynetbox(instance)

        # build base params
        base_params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            base_params["fields"] = ",".join(fields)

        results = []

        if filters is None or isinstance(filters, dict):
            params = {**base_params}
            if filters:
                params.update(filters)
            try:
                # NetBox 4.0+: ObjectChange moved from extras to core
                found = list(nb.core.object_changes.filter(**params))
            except Exception:
                found = list(nb.extras.object_changes.filter(**params))
            results = [dict(obj) for obj in found]
        else:
            # list of filter dicts — run multiple queries
            seen_ids: set = set()
            for flt in filters:
                params = {**base_params, **flt}
                try:
                    changelog_iter = nb.core.object_changes.filter(**params)
                except Exception:
                    changelog_iter = nb.extras.object_changes.filter(**params)
                for obj in changelog_iter:
                    obj_dict = dict(obj)
                    oid = obj_dict.get("id")
                    if oid not in seen_ids:
                        seen_ids.add(oid)
                        results.append(obj_dict)

        job.event(f"retrieved {len(results)} changelog entries")
        log.info(
            f"{self.name} - crud_get_changelogs: retrieved {len(results)} entries"
        )

        ret.result = {
            "count": len(results),
            "next": None,
            "previous": None,
            "results": results,
        }
        return ret


# =============================================================================
# PICLE SHELL COMMANDS PLAN
# =============================================================================
#
# New file: norfab/clients/nfcli_shell/netbox/netbox_picle_shell_crud.py
#
# Follows the same conventions as existing netbox PICLE shell modules:
#   - Each command model inherits from NetboxCommonArgs (provides `instance`)
#     and NetboxClientRunJobArgs (provides `workers`, `timeout`, `nowait`,
#     `verbose_result`)
#   - json_schema_extra={"presence": True} on bool fields that act as flags
#   - Aliases use dashes (e.g. "dry-run", "object-type")
#   - JSON string inputs (filters, data) are parsed inside run() via json.loads()
#   - listen_events decorator on run() if real-time event feedback is desired
#   - PicleConfig inner class sets outputter and pipe
#
# The seven command models map 1-to-1 to the seven crud_* tasks.
#
# ─────────────────────────────────────────────────────────────────────────────
# 1. CrudListObjectsShell  →  netbox crud list-objects
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     app_filter   Optional[Union[StrictStr, List[StrictStr]]]
#                    description="Filter by app(s) e.g. dcim or dcim,ipam"
#                    alias="app-filter"
#                    # single string accepted; run() splits on comma into list
#     include_metadata  StrictBool  presence flag, default True
#                    description="Include path/methods/schema_name/description"
#                    alias="include-metadata"
#                    json_schema_extra={"presence": True}
#
#   run():
#     - if isinstance(kwargs.get("app_filter"), str) and "," in it:
#           kwargs["app_filter"] = [s.strip() for s in kwargs["app_filter"].split(",")]
#     - NFCLIENT.run_job("netbox", "crud_list_objects", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 2. CrudSearchShell  →  netbox crud search
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     query         StrictStr  required
#                    description="Search term"
#     object_types  Optional[StrictStr]
#                    description="Comma-separated app.resource types to search"
#                    alias="object-types"
#                    # run() splits on comma: kwargs["object_types"] = [s.strip() ...]
#     fields        Optional[StrictStr]
#                    description="Comma-separated fields to return"
#                    # run() splits on comma into list
#     brief         StrictBool  presence flag, default False
#                    description="Return brief representation"
#                    json_schema_extra={"presence": True}
#     limit         StrictInt  default 10, ge=1, le=100
#                    description="Max results per object type"
#
#   run():
#     - parse object_types and fields from comma strings to lists
#     - NFCLIENT.run_job("netbox", "crud_search", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 3. CrudReadShell  →  netbox crud get
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     object_type   StrictStr  required
#                    description='Object type e.g. "dcim.devices"'
#                    alias="object-type"
#     object_id     Optional[StrictStr]
#                    description="Comma-separated integer ID(s)"
#                    alias="object-id"
#                    # run() converts to int or list[int]
#     filters       Optional[StrictStr]
#                    description='JSON filter dict or list of dicts e.g. {"name":"ceos1"}'
#                    # run() parses with json.loads()
#     fields        Optional[StrictStr]
#                    description="Comma-separated fields to return"
#                    # run() splits on comma
#     brief         StrictBool  presence flag, default False
#                    json_schema_extra={"presence": True}
#     limit         StrictInt  default 50, ge=1, le=1000
#     offset        StrictInt  default 0, ge=0
#     ordering      Optional[StrictStr]
#                    description='Comma-separated ordering fields, prefix "-" for descending'
#                    # run() converts to list if comma present, else passes as str
#
#   run():
#     - parse object_id: split on comma, cast each to int;
#       if single value → int, if multiple → list[int]
#     - parse filters: json.loads(kwargs["filters"]) if present
#     - parse fields: split on comma into list if present
#     - parse ordering: split on comma into list if comma present
#     - NFCLIENT.run_job("netbox", "crud_read", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 4. CrudCreateShell  →  netbox crud create
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     object_type   StrictStr  required
#                    alias="object-type"
#     data          StrictStr  required
#                    description='JSON dict or list of dicts with object field values'
#                    # run() parses with json.loads()
#     dry_run       StrictBool  presence flag, default False
#                    alias="dry-run"
#                    json_schema_extra={"presence": True}
#                    description="Preview without creating"
#
#   run():
#     - kwargs["data"] = json.loads(kwargs["data"])
#     - NFCLIENT.run_job("netbox", "crud_create", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 5. CrudUpdateShell  →  netbox crud update
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     object_type   StrictStr  required
#                    alias="object-type"
#     data          StrictStr  required
#                    description='JSON dict or list of dicts; each must contain "id"'
#                    # run() parses with json.loads()
#     partial       StrictBool  presence flag, default True
#                    description="PATCH (partial=True) vs PUT (partial=False)"
#                    json_schema_extra={"presence": True}
#     dry_run       StrictBool  presence flag, default False
#                    alias="dry-run"
#                    json_schema_extra={"presence": True}
#                    description="Show diffs without updating"
#
#   run():
#     - kwargs["data"] = json.loads(kwargs["data"])
#     - NFCLIENT.run_job("netbox", "crud_update", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 6. CrudDeleteShell  →  netbox crud delete
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     object_type   StrictStr  required
#                    alias="object-type"
#     object_id     StrictStr  required
#                    description="Comma-separated integer ID(s) to delete"
#                    alias="object-id"
#                    # run() converts to int or list[int]
#     dry_run       StrictBool  presence flag, default False
#                    alias="dry-run"
#                    json_schema_extra={"presence": True}
#                    description="Preview objects that would be deleted"
#
#   run():
#     - parse object_id same as CrudReadShell
#     - NFCLIENT.run_job("netbox", "crud_delete", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# 7. CrudGetChangelogsShell  →  netbox crud changelogs
# ─────────────────────────────────────────────────────────────────────────────
#   Fields:
#     filters       Optional[StrictStr]
#                    description='JSON filter dict or list of dicts;
#                      supported keys: user, action, changed_object_id,
#                      object_repr, time_before, time_after, q'
#                    # run() parses with json.loads()
#     fields        Optional[StrictStr]
#                    description="Comma-separated fields to return"
#                    # run() splits on comma into list
#     limit         StrictInt  default 50, ge=1, le=1000
#     offset        StrictInt  default 0, ge=0
#
#   run():
#     - parse filters and fields
#     - NFCLIENT.run_job("netbox", "crud_get_changelogs", workers=workers, kwargs=kwargs)
#
#   PicleConfig:
#     outputter = Outputters.outputter_json
#     pipe = PipeFunctionsModel
#
# ─────────────────────────────────────────────────────────────────────────────
# CONTAINER MODEL: CrudCommands  →  netbox crud
# ─────────────────────────────────────────────────────────────────────────────
#
#   class CrudCommands(BaseModel):
#     list_objects : CrudListObjectsShell  alias="list-objects"
#                    description="List available NetBox object types from OpenAPI schema"
#     search       : CrudSearchShell
#                    description="Free-text search across NetBox object types"
#     get          : CrudReadShell
#                    description="Retrieve NetBox objects by ID or filter"
#     create       : CrudCreateShell
#                    description="Create one or multiple NetBox objects"
#     update       : CrudUpdateShell
#                    description="Update one or multiple NetBox objects"
#     delete       : CrudDeleteShell
#                    description="Delete one or multiple NetBox objects by ID"
#     changelogs   : CrudGetChangelogsShell
#                    description="Retrieve NetBox change history"
#
#     class PicleConfig:
#       subshell = True
#       prompt = "nf[netbox-crud]#"
#
# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION INTO netbox_picle_shell.py
# ─────────────────────────────────────────────────────────────────────────────
#
# 1. In netbox_picle_shell_crud.py: define the 7 leaf models + CrudCommands
#
# 2. In netbox_picle_shell.py add import:
#      from .netbox_picle_shell_crud import CrudCommands
#
# 3. In NetboxServiceCommands add field:
#      crud : CrudCommands = Field(None, description="Generic CRUD operations on NetBox objects")
#
#   Resulting CLI paths:
#     nf[netbox]# crud list-objects [app-filter dcim] [no-include-metadata]
#     nf[netbox]# crud search <query> [object-types dcim.devices,ipam.prefixes] [brief]
#     nf[netbox]# crud get object-type dcim.devices [filters '{"name":"ceos1"}'] [fields id,name]
#     nf[netbox]# crud create object-type dcim.manufacturers data '{"name":"Foo","slug":"foo"}'
#     nf[netbox]# crud update object-type dcim.manufacturers data '{"id":1,"name":"Bar"}' [dry-run]
#     nf[netbox]# crud delete object-type dcim.manufacturers object-id 1,2 [dry-run]
#     nf[netbox]# crud changelogs [filters '{"action":"create"}'] [limit 20]
