---
tags:
  - fastmcp
  - mcp
---

# FastMCP Service

FastMCP Service exposes NorFab service tasks as MCP tools via an HTTP endpoint.
It is designed to integrate NorFab with MCP-capable clients (e.g. VS Code MCP).

FastMCP worker periodically discovers NorFab services and their tasks, and auto-generates
MCP tools following this naming convention:

```
service_<service_name>__task_<task_name>
```

By default, FastMCP server listens on `0.0.0.0:8001` and serves MCP at `/mcp/`.

# Installation

FastMCP uses [Python SDK MCP](https://github.com/modelcontextprotocol/python-sdk) library. Required dependencies can be installed using `fastmcpservice` extras:

```
pip install norfab[fastmcpservice]
```

> [!NOTE]
> There is no dependency on name-twin [FastMCP project](https://github.com/PrefectHQ/fastmcp) that uses similar name and Python API, `mcp` library above is the only dependency.

## FastMCP Service Tasks

FastMCP Service supports a small set of tasks to manage MCP exposure.

| Task | Description | Use Cases |
|------|-------------|-----------|
| **[get_tools](services_fastmcp_service_task_get_tools.md)** | Return tools exposed by FastMCP worker (optionally filtered). | Tool discovery, debugging integrations, building MCP allow-lists. |
| **[auth](services_fastmcp_service_task_auth.md)** | Store, list, delete, and check bearer tokens for optional MCP authentication. | Securing MCP access, rotating client tokens, auditing active tokens. |

## FastMCP Service Show Commands

FastMCP service shell comes with a set of show commands to query service details:

```
nf#man tree show.fastmcp
root
└── show:    NorFab show commands
    └── fastmcp:    Show FastMCP service
        ├── inventory:    show FastMCP inventory data
        │   ├── timeout:    Job timeout
        │   └── workers:    Filter worker to target, default 'all'
        ├── version:    show FastMCP service version report
        ├── status:    show FastMCP server status
        │   ├── timeout:    Job timeout
        │   └── workers:    Filter worker to target, default 'all'
        └── tools:    show FastMCP server tools
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── brief:    show tools names only
            ├── service:    filter tools by service name
            └── name:    filter tools by name using glob pattern
nf#
```

## FastMCP Service Auth Commands

FastMCP service shell supports bearer token management commands:

```
nf#man tree fastmcp.auth
root
└── fastmcp:    FastMCP service
    └── auth:    Manage auth tokens
        ├── create-token:    Create authentication token
        ├── list-tokens:    Retrieve authentication tokens
        ├── delete-token:    Delete existing authentication token
        └── check-token:    Check if given token valid
nf#
```

## VS Code MCP Integration

Refer to [VSCode MCP integration](../../tutorials/norfab_vscode_mcp_integration.md) tutorial for a minimal,
end-to-end example of running FastMCP worker and connecting it as an MCP server in VS Code.
