---
tags:
  - agent
---

# Agent Service

Ask an agent to investigate network state, collect task results and explain its
findings. The agent runs on a NorFab worker and can call tasks from running
services, such as Nornir for device commands and Netbox for inventory.

Use it to check interface health, investigate a reported fault or summarize
verification results. Include device names, the checks you want and the evidence
you expect in the answer.

## Get started

Install the service on the agent worker host:

```bash
pip install "norfab[agentservice]"
```

Choose a model that supports tool calls and configure an
[agent worker](services_agent_service_inventory.md#worker-configuration).
The service includes the Ollama provider; other
[providers](../../clients/clients_agent.md#profile-settings) need their package
and credentials. Interface examples also need a running Nornir service with the
target devices in its inventory.

## Investigate a device

=== "CLI"

    ```bash
    nf# agent invoke workers agent-worker-1 instructions "Inspect interfaces on r1. Report down interfaces and error counters, include the commands and evidence, and do not change configuration."
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        results = client.run_job(
            service="agent",
            task="invoke",
            workers="agent-worker-1",
            kwargs={
                "instructions": (
                    "Inspect interfaces on r1. Report down interfaces and error "
                    "counters, include the commands and evidence, and do not "
                    "change configuration."
                ),
            },
        )
        for worker, response in results.items():
            print(worker, response["result"])
    ```

`workers` selects the agent worker. Device names and the requested network scope
belong in the instructions. The answer depends on the tools and data available;
ask the agent to state which checks it could not complete.

## Get useful answers

| Goal | What to include in the request |
| --- | --- |
| Investigate an interface fault | Device and interface names, symptoms, and a request for link state and error counters. |
| Verify a change | Devices, expected state and checks to run; ask for pass/fail findings with evidence. |
| Compare devices | Exact device names, the settings or state to compare, and the differences that matter. |
| Prepare a handover | Scope, collected findings and a request for unresolved issues and next checks. |

Each worker invocation starts a fresh conversation. Include the full context in
each request. For follow-up chat that remembers earlier questions, use the
[client agent](../../clients/clients_agent.md).

Use a [custom definition](services_agent_service_inventory.md#custom-agent-definitions)
when you want a repeatable prompt and a focused set of tools. See
[Invoke](services_agent_service_tasks_chat.md) for custom-agent examples and
result details.
