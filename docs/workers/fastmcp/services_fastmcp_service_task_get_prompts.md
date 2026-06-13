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

## FastMCP Get Prompts Sample Usage

!!! example

    === "CLI"

        List all prompts:

        ```
        nf#show fastmcp prompts
        ```

        The detailed output includes each prompt's `messages` list and its
        Jinja2 template text.

        List prompt names for a specific service:

        ```
        nf#show fastmcp prompts service nornir brief
        ```

        Filter prompts by name using glob patterns:

        ```
        nf#show fastmcp prompts name "*troubleshoot" brief
        ```

    === "Python"

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        if __name__ == "__main__":
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            nfclient = nf.make_client()

            result = nfclient.run_job(
                "fastmcp",
                "get_prompts",
                kwargs={"brief": True, "service": "nornir"},
                workers="any",
            )
            pprint.pprint(result)

            nf.destroy()
        ```

## NORFAB FastMCP Get Prompts Command Shell Reference

NorFab shell supports these command options for FastMCP `get_prompts` task:

```
nf#man tree show.fastmcp.prompts
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
