"""
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
