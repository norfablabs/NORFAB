---
tags:
  - netbox
---

# Netbox GraphQL Task

> task api name: `graphql`

Runs GraphQL queries against a NetBox instance. The task can build a query from `obj`, `filters`, and `fields`, run multiple aliased queries from `queries`, or send a complete `query_string`.

!!! warning
    The `graphql` task is marked deprecated in code in favour of the lower-level `netbox_graphql` helper. Existing callers can still use `graphql`, but new internal code should prefer `netbox_graphql` where appropriate.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `obj` | Conditional | NetBox GraphQL object name, used with `filters` and `fields` |
| `filters` | Conditional | GraphQL filters as a dictionary or raw filter string |
| `fields` | Conditional | GraphQL fields to return |
| `queries` | Conditional | Dictionary of query definitions keyed by alias |
| `query_string` | Conditional | Complete GraphQL query string to send as-is |
| `instance` | No | NetBox instance name to target |
| `dry_run` | No | Return the generated query payload without executing it |

Provide one of these input forms:

- `obj`, `filters`, and `fields`
- `queries`
- `query_string`

## Output

Normal mode returns the GraphQL response payload from NetBox. Dry-run mode returns the HTTP payload that would be sent:

```python
{
    "url": "https://netbox.example/graphql/",
    "data": "{\"query\": \"query {...}\"}",
    "headers": {"Authorization": "Token ...123456"},
    "verify": True,
}
```

## Notes / Gotchas

- For generated queries, NetBox version must be `4.4.0` or newer.
- `fields` is a comma-separated string in NFCLI and a list in the Python API.
- Use `query_string` when you need full control over the GraphQL document.

## Examples

=== "CLI"

    Query devices by generated object, filter, and fields:

    ```bash
    nf#netbox graphql obj devices filters '{"name": {"exact": "ceos-leaf-1"}}' fields name,status,platform
    ```

    Preview the generated GraphQL payload:

    ```bash
    nf#netbox graphql obj devices filters '{"name": {"exact": "ceos-leaf-1"}}' fields name,status dry-run
    ```

    Run multiple aliased queries:

    ```bash
    nf#netbox graphql queries '{"leafs": {"obj": "devices", "filters": {"role": {"exact": "leaf"}}, "fields": ["name", "status"]}}'
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "obj": "devices",
                "filters": {"name": {"exact": "ceos-leaf-1"}},
                "fields": ["name", "status", "platform"],
            },
        )
    ```

    Direct lifecycle:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        preview = client.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "obj": "devices",
                "filters": {"name": {"exact": "ceos-leaf-1"}},
                "fields": ["name", "status"],
                "dry_run": True,
            },
        )

        result = client.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query { devices { name status } }",
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB Netbox GraphQL Command Shell Reference

NorFab shell supports these command options for Netbox `graphql` task:

```bash
nf# man tree netbox.graphql
root
└── netbox:    Netbox service
    └── graphql:    Query Netbox GraphQL API
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'any'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        ├── instance:    Netbox instance name to target
        ├── dry-run:    Return query payload without executing it
        ├── obj:    NetBox GraphQL object name or query object
        ├── filters:    JSON dictionary or raw filter string to filter by
        ├── fields:    Comma-separated GraphQL fields to return
        ├── queries:    JSON dictionary keyed by GraphQL aliases
        └── query-string:    Complete GraphQL query string to send as is
nf#
```

## Python API Reference

### graphql

::: norfab.workers.netbox_worker.graphql_tasks.NetboxGraphqlTasks.graphql

### netbox_graphql

::: norfab.workers.netbox_worker.graphql_tasks.NetboxGraphqlTasks.netbox_graphql
