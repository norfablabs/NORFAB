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

## FastMCP Service Tasks

FastMCP Service supports a small set of tasks to manage MCP exposure.

| Task | Description | Use Cases |
|------|-------------|-----------|
| **[get_tools](services_fastmcp_service_task_get_tools.md)** | Return tools exposed by FastMCP worker (optionally filtered). | Tool discovery, debugging integrations, building MCP allow-lists. |

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

## VS Code MCP Integration

Refer to [VSCode MCP integration](../../tutorials/norfab_vscode_mcp_integration.md) tutorial for a minimal,
end-to-end example of running FastMCP worker and connecting it as an MCP server in VS Code.
