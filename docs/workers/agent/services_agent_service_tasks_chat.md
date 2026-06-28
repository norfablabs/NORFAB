---
tags:
  - agent
---

# Agent Service Chat Task

> task api name: `invoke`

Invokes an Agent worker with user instructions. The task is commonly used as an interactive chat surface, but the API task name is `invoke`.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `instructions` | Yes | User instructions to send to the agent |
| `name` | No | Agent name to invoke, default `NorFab` |
| `verbose_result` | No | Return the full message payload instead of only the final response |

## Output

By default, returns the final agent response text. With `verbose_result=True`, returns the full agent invocation payload.

## Examples

=== "CLI"

    Ask the default agent a question:

    ```bash
    nf#agent invoke instructions "Summarize the current NorFab inventory"
    ```

    Invoke a named agent:

    ```bash
    nf#agent invoke name NorFab instructions "Check whether any workers are unhealthy"
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="agent",
            task="invoke",
            workers="any",
            kwargs={
                "instructions": "Summarize the current NorFab inventory",
            },
        )
        print(result)
    ```

    Direct lifecycle with a named agent:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            service="agent",
            task="invoke",
            workers="any",
            kwargs={
                "name": "NorFab",
                "instructions": "Check whether any workers are unhealthy",
                "verbose_result": True,
            },
        )
        print(result)
    finally:
        nf.destroy()
    ```

## NORFAB Agent Chat Command Shell Reference

NorFab shell supports these command options for Agent `invoke` task:

```bash
nf# man tree agent
root
└── agent:    AI Agent service
    ├── timeout:    Job timeout
    ├── workers:    Filter worker to target, default 'all'
    ├── show:    Show Agent service parameters
    │   ├── inventory:    show agent inventory data
    │   ├── version:    show agent service version report
    │   └── status:    show agent status
    ├── invoke:    Invoke an agent to chat or run a task
    │   ├── instructions:    Provide instructions
    │   ├── name:    Agent name to interact with
    │   └── progress:    Emit execution progress, default 'True'
    └── progress:    Emit execution progress, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.agent_worker.agent_worker.AgentWorker.invoke
