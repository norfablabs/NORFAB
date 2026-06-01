---
tags:
  - fastmcp
  - mcp
  - auth
---

# FastMCP Service Auth Tasks

FastMCP service supports optional bearer token authentication for the MCP
streamable HTTP endpoint. To manage token lifecycle, FastMCP provides tasks to
store, delete, list, and check bearer tokens in the worker diskcache database.

These tasks are available through NorFab client jobs and the NFCLI shell. They
are not exposed as MCP tools.

## Task API Names

| Task | Description |
| --- | --- |
| `bearer_token_store` | Store a bearer token for a username. |
| `bearer_token_list` | List stored bearer tokens, optionally filtered by username. |
| `bearer_token_delete` | Delete one token or all tokens for a username. |
| `bearer_token_check` | Check whether a token exists and is still active. |

## FastMCP Auth Tasks Sample Usage

!!! example

    === "CLI"

        Store an explicit token:

        ```
        nf#fastmcp auth create-token username automation token secret-token expire 3600
        {
            "fastmcp-worker-1": true
        }
        nf#
        ```

        Generate and store a token automatically:

        ```
        nf#fastmcp auth create-token username automation
        {
            "fastmcp-worker-1": true
        }
        nf#
        ```

        List tokens for a specific user:

        ```
        nf#fastmcp auth list-tokens username automation
         worker              username    token         age             creation                    expires
         fastmcp-worker-1    automation  secret-token  0:01:29.688340  2026-05-31 12:08:51.914919  2026-05-31 13:08:51.914919
        nf#
        ```

        List all tokens:

        ```
        nf#fastmcp auth list-tokens
         worker              username    token                             age             creation                    expires
         fastmcp-worker-1    automation  secret-token                      0:01:44.701374  2026-05-31 12:08:51.914919  2026-05-31 13:08:51.914919
         fastmcp-worker-1    vscode      888945f96b824bf1b4358de790c452b6  0:10:06.561696  2026-05-31 12:00:30.054597  None
        nf#
        ```

        Delete a specific token:

        ```
        nf#fastmcp auth delete-token token secret-token
        {
            "fastmcp-worker-1": true
        }
        nf#
        ```

        Delete all tokens for a user:

        ```
        nf#fastmcp auth delete-token username automation
        {
            "fastmcp-worker-1": true
        }
        nf#
        ```

        Check whether a token is valid:

        ```
        nf#fastmcp auth check-token token secret-token
        {
            "fastmcp-worker-1": true
        }
        nf#
        ```

    === "Python"

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        if __name__ == "__main__":
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            nfclient = nf.make_client()

            nfclient.run_job(
                "fastmcp",
                "bearer_token_store",
                kwargs={
                    "username": "automation",
                    "token": "secret-token",
                    "expire": 3600,
                },
                workers="all",
            )

            result = nfclient.run_job(
                "fastmcp",
                "bearer_token_list",
                kwargs={"username": "automation"},
                workers="all",
            )
            pprint.pprint(result)

            nf.destroy()
        ```

## Using Tokens With MCP Clients

When `authentication_enabled: true` is configured in FastMCP inventory, MCP
clients must send the stored token in the HTTP authorization header:

```http
Authorization: Bearer secret-token
```

For example, VS Code MCP configuration can include the bearer header in the MCP
server definition if the client supports custom headers.

## NORFAB FastMCP Service Auth Tasks Command Shell Reference

NorFab shell supports these command options for FastMCP `auth` tasks:

```
nf#man tree fastmcp.auth
root
└── fastmcp:    FastMCP service
    └── auth:    Manage auth tokens
        ├── create-token:    Create authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── token:    Token string to store, autogenerate if not given
        │   ├── *username:    User name to store the token for
        │   └── expire:    Token expiration time in seconds
        ├── list-tokens:    Retrieve authentication tokens
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   └── username:    User name to list tokens for
        ├── delete-token:    Delete existing authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── username:    User name whose tokens should be deleted
        │   └── token:    Bearer token string to delete
        └── check-token:    Check if given token valid
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            └── *token:    Bearer token string to check
nf#
```

## Python API Reference

### bearer_token_store

::: norfab.workers.fastmcp_worker.fastmcp_worker.FastMCPWorker.bearer_token_store

### bearer_token_delete

::: norfab.workers.fastmcp_worker.fastmcp_worker.FastMCPWorker.bearer_token_delete

### bearer_token_list

::: norfab.workers.fastmcp_worker.fastmcp_worker.FastMCPWorker.bearer_token_list

### bearer_token_check

::: norfab.workers.fastmcp_worker.fastmcp_worker.FastMCPWorker.bearer_token_check
