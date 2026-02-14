# VSCode MCP integration (NORFAB)

This tutorial shows a minimal, end-to-end setup: start NORFAB with the FastMCP worker, connect it as an MCP server in VS Code, and create a small Copilot agent that can run NORFAB tools.

## Prerequisites

You need VS Code with GitHub Copilot, a working NORFAB environment (see [Installation Guide](../norfab_installation.md) and [Getting Started](../norfab_getting_started.md)), adjust Nornir worker devices inventory to match your use case.

## 1) Start NORFAB with the FastMCP worker

Add a FastMCP worker into `inventory.yaml` and include it in topology.

```yaml title="inventory.yaml"
workers:
  fastmcp-worker-1:
    - fastmcp/common.yaml

topology:
  workers:
    - fastmcp-worker-1
```

Create the worker inventory file:

```yaml title="fastmcp/common.yaml"
service: fastmcp
```

Start NORFAB from the same folder:

```bash
nfcli
```

By default, the MCP endpoint is available at `http://127.0.0.1:8001/mcp`. To verify the worker is up and serving tools:

```
nf#show workers
nf#show fastmcp status
```

!!! tip
    To see which tools are exposed by a service, use:

    ```bash
    nf#show fastmcp tools service nornir brief
    ```

## 2) Configure the MCP server in VS Code

Follow online VScode instruction how to add MCP servers, but at the time of writing this tutorial need to create or update `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "norfab": {
      "type": "http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

!!! note
    If your FastMCP worker uses a different host/port, update the `url` to match.

## 3) Create a small custom agent

Follow VScode documentation guidelines on how to add custom agents. At the time of writing this tutorial need to in VS Code need open Copilot Chat and use **Configure Custom Agents** → **Create New Agent**. Create a file named `norfab.agent.md` (in the folder VS Code suggests) with the content below.

```markdown title="norfab.agent.md"
---
description: 'Run read-only network commands via NORFAB'
tools:
  - 'norfab/service_nornir__task_get_nornir_hosts'
  - 'norfab/service_nornir__task_cli'
---

Your name is 'NorFab Agent'. You help users query network devices through NORFAB.

Use 'norfab/service_nornir__task_get_nornir_hosts' to discover available devices.
Use 'norfab/service_nornir__task_cli' to run show commands.

When passing tool arguments, replace hyphens with underscores (example: add-details -> add_details).
```

## 4) Use the agent

Open Copilot Chat, select your agent, then try prompts like:

```
List available devices.
Run "show version" on router1.
Run "show interfaces" on router1.
```

## Troubleshooting

If VS Code cannot connect, confirm the FastMCP worker is running (nfcli `show workers`, `show fastmcp status`) and that `.vscode/mcp.json` points at the correct URL.

If the agent does not show up, double-check the file ends with `.agent.md`, then restart VS Code.

If a tool is missing, confirm the exact tool name (use nfcli `show fastmcp tools ...`) and that the required service worker is present in your inventory.

## Security note

!!! warning
    The MCP server can execute real automation tasks. For development, prefer binding to localhost, use least-privilege credentials, and only grant the agent the tools it actually needs.

## Additional resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [NORFAB API Reference](../api_reference_core_norfab_nfapi.md)
