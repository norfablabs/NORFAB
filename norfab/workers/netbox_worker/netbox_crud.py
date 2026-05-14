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
    limit: StrictInt = Field(
        10, ge=1, le=100, description="Max results per object type"
    )
    instance: Optional[StrictStr] = Field(None, description="NetBox instance name")


class CrudReadArgs(BaseModel):
    object_type: StrictStr = Field(
        ..., description='"app.resource" e.g. "dcim.devices"'
    )
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
    object_type: StrictStr = Field(
        ..., description='"app.resource" e.g. "dcim.interfaces"'
    )
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
    partial: StrictBool = Field(
        True, description="True=PATCH (partial); False=PUT (full replace)"
    )
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

        job.event(f"searching '{query}' across {len(object_types)} object type(s)")

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
            if "id" not in fields:
                fields.append("id")
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
                job.event(f"retrieving {object_type} with {len(filters)} filter(s)")
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

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
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

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
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

    @Task(
        fastapi={"methods": ["DELETE"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
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

        filter_count = (
            1 if isinstance(filters, dict) else (len(filters) if filters else 0)
        )
        job.event(f"retrieving changelogs with {filter_count} filter(s)")

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
        log.info(f"{self.name} - crud_get_changelogs: retrieved {len(results)} entries")

        ret.result = {
            "count": len(results),
            "next": None,
            "previous": None,
            "results": results,
        }
        return ret
