---
tags:
  - FastAPI
---

# FastAPI Auth Tasks

> task api names: `bearer_token_store`, `bearer_token_list`, `bearer_token_delete`, `bearer_token_check`

FastAPI service supports bearer token REST API authentication. To handle tokens lifecycle a number of FastAPI Service methods created allowing to store, delete, list and check API tokens.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `username` | Required for create and username-scoped delete/list | User name associated with one or more bearer tokens. |
| `token` | Required for check and token-scoped delete | Bearer token value. If omitted on create, the worker generates one. |
| `expire` | No | Token expiration time in seconds. If omitted, the token does not expire. |
| `workers` | No | FastAPI workers to target. Defaults to all workers. |

## Output

Create, delete, and check tasks return booleans per worker. List tasks return stored token records with username, token, age, creation time, and expiration time.

## Examples

!!! example

    === "CLI"

        Store authentication token in FastAPI service database:

        ```bash
        nf# fastapi auth create-token username foobar token f343ff34r3fg4g5g34gf34g34g3g34g4 expire 3600
        {
            "fastapi-worker-1": true
        }
        nf#
        ```

        `expire` is optional and indicates token expiration time in seconds. If no `expire` argument is provided, the token does not expire. Multiple tokens can be stored for any given user.

        List stored tokens for a specific user:

        ```bash
        nf# fastapi auth list-tokens username foobar
         worker            username  token                             age             creation                    expires
         fastapi-worker-1  foobar    f343ff34r3fg4g5g34gf34g34g3g34g4  0:01:29.688340  2025-02-16 20:08:51.914919  2025-02-16 21:08:51.914919
         fastapi-worker-1  foobar    888945f96b824bf1b4358de790c452b6  8:08:51.548662  2025-02-16 12:01:30.054597  None
        nf#
        ```

        List all stored tokens:

        ```bash
        nf# fastapi auth list-tokens
         worker            username  token                             age             creation                    expires
         fastapi-worker-1  pytest    11111111111111111111111111111111  1:26:18.492274  2025-02-16 18:44:18.124019  None
         fastapi-worker-1  foobar    f343ff34r3fg4g5g34gf34g34g3g34g4  0:01:44.701374  2025-02-16 20:08:51.914919  2025-02-16 21:08:51.914919
        nf#
        ```

        Delete a specific token:

        ```bash
        nf# fastapi auth delete-token token 888945f96b824bf1b4358de790c452b6
        {
            "fastapi-worker-1": true
        }
        nf#
        ```

        Delete all tokens for a given user:

        ```bash
        nf# fastapi auth delete-token username foo
        {
            "fastapi-worker-1": true
        }
        nf#
        ```

        Check if a token is valid:

        ```bash
        nf# fastapi auth check-token token 888945f96b824bf1b4358de790c452b6
        {
            "fastapi-worker-1": false
        }
        nf# fastapi auth check-token token f343ff34r3fg4g5g34gf34g34g3g34g4
        {
            "fastapi-worker-1": true
        }
        nf#
        ```

    === "Python"

        Context manager - create and list tokens:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        with NorFab(inventory="inventory.yaml") as nf:
            client = nf.make_client()

            client.run_job(
                service="fastapi",
                task="bearer_token_store",
                kwargs={
                    "username": "foobar",
                    "token": "secret-token",
                    "expire": 3600,
                },
                workers="all",
            )

            result = client.run_job(
                service="fastapi",
                task="bearer_token_list",
                kwargs={"username": "foobar"},
                workers="all",
            )

            pprint.pprint(result)
        ```

        Direct lifecycle - check and delete a token:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="inventory.yaml")
        try:
            nf.start()
            client = nf.make_client()

            check_result = client.run_job(
                service="fastapi",
                task="bearer_token_check",
                kwargs={"token": "secret-token"},
                workers="all",
            )
            delete_result = client.run_job(
                service="fastapi",
                task="bearer_token_delete",
                kwargs={"token": "secret-token"},
                workers="all",
            )

            pprint.pprint(check_result)
            pprint.pprint(delete_result)
        finally:
            nf.destroy()
        ```

## NORFAB FastAPI Service Auth Tasks Command Shell Reference

NorFab shell supports these command options for FastAPI `auth` tasks:

```bash
nf# man tree fastapi.auth
root
└── fastapi:    FastAPI service
    └── auth:    Manage auth tokens
        ├── create-token:    Create authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── token:    Token string to store, autogenerate if not given
        │   ├── *username:    Name of the user to store token for
        │   └── expire:    Seconds before token expire
        ├── list-tokens:    Retrieve authentication tokens
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   └── username:    Name of the user to list tokens for
        ├── delete-token:    Delete existing authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── username:    Name of the user to delete tokens for
        │   └── token:    Token string to delete
        └── check-token:    Check if given token valid
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            └── *token:    Token string to check
nf#
```

## Python API Reference

### bearer_token_store

::: norfab.workers.fastapi_worker.fastapi_worker.FastAPIWorker.bearer_token_store

### bearer_token_delete

::: norfab.workers.fastapi_worker.fastapi_worker.FastAPIWorker.bearer_token_delete

### bearer_token_list

::: norfab.workers.fastapi_worker.fastapi_worker.FastAPIWorker.bearer_token_list

### bearer_token_check

::: norfab.workers.fastapi_worker.fastapi_worker.FastAPIWorker.bearer_token_check
