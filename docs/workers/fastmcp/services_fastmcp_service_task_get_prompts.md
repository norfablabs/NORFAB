---
tags:
  - fastmcp
  - mcp
---

# FastMCP Service Get Prompts Task

> task api name: `get_prompts`

FastMCP service `get_prompts` task returns MCP prompts discovered from NorFab
task metadata. A task can publish multiple prompts by defining a list under
`mcp["prompts"]` in its `Task` decorator.

The detailed response includes the prompt name, title, description, arguments,
and unrendered message templates. Use `brief` to return prompt names only.

Published prompts follow this naming convention:

```
service_<service_name>__task_<task_name>__prompt_<prompt_name>
```

Retrieving a prompt through MCP returns rendered messages. It does not execute
the related NorFab task.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `brief` | No | Return prompt names only. |
| `service` | No | Filter prompts by NorFab service name. |
| `name` | No | Filter prompts by glob pattern. |
| `workers` | No | FastMCP workers to target. Defaults to any worker. |

## Output

The task returns MCP prompt definitions with prompt name, title, description, arguments, and unrendered message templates. With `brief=True`, it returns prompt names only.

## Examples

!!! example

    === "CLI"

        List all prompts:

        ```bash
        nf# show fastmcp prompts
        ```

        The detailed output includes each prompt's `messages` list and its
        Jinja2 template text.

        List prompt names for a specific service:

        ```bash
        nf# show fastmcp prompts service nornir brief
        ```

        Filter prompts by name using glob patterns:

        ```bash
        nf# show fastmcp prompts name "*troubleshoot" brief
        ```

    === "Python"

        Context manager - list Nornir prompt names:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        with NorFab(inventory="inventory.yaml") as nf:
            client = nf.make_client()

            result = client.run_job(
                service="fastmcp",
                task="get_prompts",
                kwargs={"brief": True, "service": "nornir"},
                workers="any",
            )
            pprint.pprint(result)
        ```

        Direct lifecycle - filter prompts by name:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="inventory.yaml")
        try:
            nf.start()
            client = nf.make_client()

            result = client.run_job(
                service="fastmcp",
                task="get_prompts",
                kwargs={"brief": True, "name": "*troubleshoot"},
                workers="any",
            )
            pprint.pprint(result)
        finally:
            nf.destroy()
        ```

## NORFAB FastMCP Get Prompts Command Shell Reference

NorFab shell supports these command options for FastMCP `get_prompts` task:

```bash
nf# man tree show.fastmcp.prompts
root
└── show:    NorFab show commands
    └── fastmcp:    Show FastMCP service
        └── prompts:    show FastMCP server prompts
            ├── brief:    show prompt names only
            ├── service:    filter prompts by service name
            ├── name:    filter prompts by name using glob pattern
            ├── workers:    Filter worker to target, default 'any'
            └── timeout:    Job timeout
nf#
```

## Python API Reference

::: norfab.workers.fastmcp_worker.fastmcp_worker.FastMCPWorker.get_prompts
