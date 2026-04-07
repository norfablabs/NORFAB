---
tags:
  - netbox
---

# Netbox CRUD Tasks

> task api names: `crud_list_objects`, `crud_search`, `crud_read`, `crud_create`, `crud_update`, `crud_delete`, `crud_get_changelogs`

Seven generic CRUD tasks for any NetBox object type. Designed for AI agents, CLI automation,
and programmatic workflows where the full flexibility of the NetBox REST API is needed without
hard-coding object-type-specific helper tasks.

Typical workflow:

1. `crud_list_objects` — discover what object types exist
2. `crud_search` — free-text search to locate objects by name or description
3. `crud_read` — fetch full objects by ID or filter
4. `crud_create` / `crud_update` / `crud_delete` — mutate objects (`dry_run=True` first)
5. `crud_get_changelogs` — verify what changed and when

---

## List Objects

> task api name: `crud_list_objects`

Lists all available NetBox object types extracted from the OpenAPI schema.
Results are cached for 24 hours (key `netbox_{instance}_openapi_objects`).

### Outputs

When `include_metadata=True` (default):

```json
{
  "dcim": {
    "devices": {
      "path": "/api/dcim/devices/",
      "object_type": "devices",
      "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
      "schema_name": "WritableDevice",
      "description": "..."
    }
  }
}
```

When `include_metadata=False`:

```json
{
  "dcim": ["cables", "devices", "interfaces", "sites"],
  "ipam": ["ip-addresses", "prefixes"]
}
```

### NORFAB Netbox CRUD List Objects Command Shell Reference

NorFab shell supports these command options for Netbox `crud_list_objects` task:

```
nf#man tree netbox.crud.list-objects
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── list-objects:    List available NetBox object types from OpenAPI schema
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── app-filter:    Filter by app(s) e.g. dcim or dcim,ipam (comma-separated)
            └── no-include-metadata:    Return object names only (omit path/methods/schema)
nf#
```

### Examples

=== "CLI"

    List all object types with full metadata:

    ```
    nf#netbox crud list-objects
    ```

    List object names only (no metadata), filtered to dcim and ipam apps:

    ```
    nf#netbox crud list-objects no-include-metadata app-filter dcim,ipam
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # all object types with metadata
    result = client.run_job(
        "netbox",
        "crud_list_objects",
        workers="any",
    )

    # names only, filtered to dcim app
    result = client.run_job(
        "netbox",
        "crud_list_objects",
        workers="any",
        kwargs={
            "app_filter": ["dcim"],
            "include_metadata": False,
        },
    )

    nf.destroy()
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_list_objects

---

## Search

> task api name: `crud_search`

Free-text search using the `q` parameter across multiple object types simultaneously.
Results are grouped by object type. Per-type errors are logged as warnings and the
search continues — the task is error-resilient across object types.

Default object types searched when `object_types` is omitted:
`dcim.devices`, `dcim.sites`, `ipam.ip-addresses`, `ipam.prefixes`,
`dcim.interfaces`, `circuits.circuits`, `tenancy.tenants`,
`virtualization.virtual-machines`.

### Outputs

```json
{
  "dcim.devices": [
    {"id": 1, "name": "ceos1", "status": {"value": "active"}}
  ],
  "ipam.prefixes": []
}
```

### NORFAB Netbox CRUD Search Command Shell Reference

NorFab shell supports these command options for Netbox `crud_search` task:

```
nf#man tree netbox.crud.search
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── search:    Free-text search across NetBox object types
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *query:    Search term
            ├── object-types:    Comma-separated app.resource types to search e.g. dcim.devices,ipam.prefixes
            ├── fields:    Comma-separated fields to return
            ├── brief:    Return brief representation
            └── limit:    Max results per object type, default 10
nf#
```

### Examples

=== "CLI"

    Search for "ceos" across default object types:

    ```
    nf#netbox crud search ceos
    ```

    Search within specific object types and return selected fields:

    ```
    nf#netbox crud search ceos object-types dcim.devices,dcim.interfaces fields id,name limit 5
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # search across default object types
    result = client.run_job(
        "netbox",
        "crud_search",
        workers="any",
        kwargs={"query": "ceos"},
    )

    # search in specific types, restrict fields and limit results
    result = client.run_job(
        "netbox",
        "crud_search",
        workers="any",
        kwargs={
            "query": "ceos",
            "object_types": ["dcim.devices", "dcim.interfaces"],
            "fields": ["id", "name"],
            "limit": 5,
        },
    )

    nf.destroy()
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_search

---

## Get (Read)

> task api name: `crud_read`

Retrieve NetBox objects by ID(s) or filter dict(s). When multiple filter dicts are
provided, results are merged and de-duplicated by `id`.

### Outputs

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {"id": 1, "name": "ceos1", "status": {"value": "active"}},
    {"id": 2, "name": "ceos2", "status": {"value": "active"}}
  ]
}
```

### NORFAB Netbox CRUD Get Command Shell Reference

NorFab shell supports these command options for Netbox `crud_read` task:

```
nf#man tree netbox.crud.get
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── get:    Retrieve NetBox objects by ID or filter
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *object-type:    Object type e.g. "dcim.devices"
            ├── object-id:    Comma-separated integer ID(s)
            ├── filters:    JSON filter dict or list of dicts e.g. '{"name":"ceos1"}'
            ├── fields:    Comma-separated fields to return
            ├── brief:    Return brief representation
            ├── limit:    Page size, default 50
            ├── offset:    Pagination skip count, default 0
            └── ordering:    Comma-separated ordering fields, prefix "-" for descending
nf#
```

### Examples

=== "CLI"

    Retrieve a single device by name filter:

    ```
    nf#netbox crud get object-type dcim.devices filters '{"name":"ceos1"}' fields id,name,status
    ```

    Retrieve multiple devices by ID:

    ```
    nf#netbox crud get object-type dcim.devices object-id 1,2,3
    ```

    Paginate through all devices sorted by name:

    ```
    nf#netbox crud get object-type dcim.devices limit 50 offset 0 ordering name
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # single filter dict
    result = client.run_job(
        "netbox",
        "crud_read",
        workers="any",
        kwargs={
            "object_type": "dcim.devices",
            "filters": {"name": "ceos1"},
            "fields": ["id", "name", "status", "site"],
        },
    )

    # multiple IDs
    result = client.run_job(
        "netbox",
        "crud_read",
        workers="any",
        kwargs={
            "object_type": "dcim.devices",
            "object_id": [1, 2, 3],
        },
    )

    nf.destroy()
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_read

---

## Create

> task api name: `crud_create`

Create one or multiple NetBox objects in a single request. Pass a single dict for one
object or a list of dicts for bulk creation. Use `dry_run=True` to preview the payload
without writing to NetBox.

### Outputs

Normal:

```json
{
  "created": 2,
  "objects": [
    {"id": 10, "name": "Acme", "slug": "acme"},
    {"id": 11, "name": "Initech", "slug": "initech"}
  ]
}
```

Dry run:

```json
{
  "dry_run": true,
  "count": 2,
  "preview": [
    {"name": "Acme", "slug": "acme"},
    {"name": "Initech", "slug": "initech"}
  ]
}
```

### NORFAB Netbox CRUD Create Command Shell Reference

NorFab shell supports these command options for Netbox `crud_create` task:

```
nf#man tree netbox.crud.create
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── create:    Create one or multiple NetBox objects
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *object-type:    Object type e.g. "dcim.manufacturers"
            ├── *data:    JSON dict or list of dicts with object field values
            └── dry-run:    Preview without creating
nf#
```

### Examples

=== "CLI"

    Create a single manufacturer (dry run first):

    ```
    nf#netbox crud create object-type dcim.manufacturers data '{"name":"Acme","slug":"acme"}' dry-run
    nf#netbox crud create object-type dcim.manufacturers data '{"name":"Acme","slug":"acme"}'
    ```

    Bulk-create interfaces:

    ```
    nf#netbox crud create object-type dcim.interfaces data '[{"device":1,"name":"eth0","type":"1000base-t"},{"device":1,"name":"eth1","type":"1000base-t"}]'
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "crud_create",
        workers="any",
        kwargs={
            "object_type": "dcim.manufacturers",
            "data": {"name": "Acme", "slug": "acme"},
            "dry_run": True,
        },
    )
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_create

---

## Update

> task api name: `crud_update`

Update one or multiple NetBox objects. Each item in `data` must contain an `"id"` field.
By default uses PATCH (partial update — only specified fields are changed). Set
`partial=False` to use PUT (full replace — omitted fields revert to their defaults).

Use `dry_run=True` to compute field-level diffs without modifying anything.

### Outputs

Normal:

```json
{
  "updated": 1,
  "objects": [
    {"id": 10, "name": "Acme Corp", "slug": "acme"}
  ]
}
```

Dry run:

```json
{
  "dry_run": true,
  "count": 1,
  "changes": [
    {
      "id": 10,
      "changes": {
        "name": {"old": "Acme", "new": "Acme Corp"}
      }
    }
  ]
}
```

### NORFAB Netbox CRUD Update Command Shell Reference

NorFab shell supports these command options for Netbox `crud_update` task:

```
nf#man tree netbox.crud.update
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── update:    Update one or multiple NetBox objects
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *object-type:    Object type e.g. "dcim.manufacturers"
            ├── *data:    JSON dict or list of dicts; each must contain "id"
            ├── no-partial:    Use PUT (full replace) instead of PATCH (partial update)
            └── dry-run:    Show diffs without updating
nf#
```

### Examples

=== "CLI"

    Preview changes before applying:

    ```
    nf#netbox crud update object-type dcim.manufacturers data '{"id":10,"name":"Acme Corp"}' dry-run
    nf#netbox crud update object-type dcim.manufacturers data '{"id":10,"name":"Acme Corp"}'
    ```

=== "Python"

    ```python
    # dry run first
    result = client.run_job(
        "netbox",
        "crud_update",
        workers="any",
        kwargs={
            "object_type": "dcim.manufacturers",
            "data": {"id": 10, "name": "Acme Corp"},
            "dry_run": True,
        },
    )

    # apply
    result = client.run_job(
        "netbox",
        "crud_update",
        workers="any",
        kwargs={
            "object_type": "dcim.manufacturers",
            "data": {"id": 10, "name": "Acme Corp"},
        },
    )
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_update

---

## Delete

> task api name: `crud_delete`

Delete one or multiple NetBox objects by ID. Use `dry_run=True` to preview which
objects would be deleted without removing them.

### Outputs

Normal:

```json
{
  "deleted": 2,
  "deleted_ids": [10, 11]
}
```

Dry run:

```json
{
  "dry_run": true,
  "count": 2,
  "would_delete": [
    {"id": 10, "name": "Acme", "slug": "acme"},
    {"id": 11, "name": "Initech", "slug": "initech"}
  ]
}
```

### NORFAB Netbox CRUD Delete Command Shell Reference

NorFab shell supports these command options for Netbox `crud_delete` task:

```
nf#man tree netbox.crud.delete
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── delete:    Delete one or multiple NetBox objects by ID
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *object-type:    Object type e.g. "dcim.manufacturers"
            ├── *object-id:    Comma-separated integer ID(s) to delete
            └── dry-run:    Preview objects that would be deleted
nf#
```

### Examples

=== "CLI"

    Preview then delete:

    ```
    nf#netbox crud delete object-type dcim.manufacturers object-id 10,11 dry-run
    nf#netbox crud delete object-type dcim.manufacturers object-id 10,11
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "crud_delete",
        workers="any",
        kwargs={
            "object_type": "dcim.manufacturers",
            "object_id": [10, 11],
            "dry_run": True,
        },
    )
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_delete

---

## Get Changelogs

> task api name: `crud_get_changelogs`

Retrieve NetBox change history from the object-changes endpoint.
Supports NetBox 4.0+ (endpoint moved from `extras` to `core`) with automatic
fallback to older versions.

### Outputs

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 42,
      "user_name": "admin",
      "request_id": "abc-123",
      "action": {"value": "create", "label": "Created"},
      "changed_object_type": "dcim.manufacturer",
      "changed_object_id": 10,
      "object_repr": "Acme",
      "time": "2026-04-06T12:00:00Z",
      "prechange_data": null,
      "postchange_data": {"name": "Acme", "slug": "acme"}
    }
  ]
}
```

### NORFAB Netbox CRUD Changelogs Command Shell Reference

NorFab shell supports these command options for Netbox `crud_get_changelogs` task:

```
nf#man tree netbox.crud.changelogs
root
└── netbox:    Netbox service
    └── crud:    Generic CRUD operations on NetBox objects
        └── changelogs:    Retrieve NetBox change history
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── filters:    JSON filter dict or list of dicts
            ├── fields:    Comma-separated fields to return
            ├── limit:    Page size, default 50
            └── offset:    Pagination skip count, default 0
nf#
```

### Examples

=== "CLI"

    Recent create actions:

    ```
    nf#netbox crud changelogs filters '{"action":"create"}' limit 20
    ```

    Changes to a specific object:

    ```
    nf#netbox crud changelogs filters '{"changed_object_id":10}' fields id,action,time,object_repr
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "crud_get_changelogs",
        workers="any",
        kwargs={
            "filters": {"action": "create"},
            "fields": ["id", "action", "time", "object_repr", "user_name"],
            "limit": 20,
        },
    )
    ```

### Python API Reference

::: norfab.workers.netbox_worker.netbox_crud.NetboxCrudTasks.crud_get_changelogs
