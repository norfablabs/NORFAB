---
tags:
  - agent
---

# Invoke an Agent

> task api name: `invoke`

Give an agent a network question or a check to perform. The default `NorFab`
agent can call tasks from running services. A custom definition supplies a
repeatable prompt and selected tools; see
[worker configuration and definitions](services_agent_service_inventory.md).

Each call starts a fresh conversation. Include the device scope, expected state
and evidence you want in every request. Use the
[client agent](../../clients/clients_agent.md) for ongoing chat.

## Output

The default result is the agent's final answer. Python calls return it under
`result` for each agent worker, alongside `failed` and `errors`.

For example, these are the relevant fields of a successful response; the wording
of the answer varies with the model and task results:

```json
{
  "agent-worker-1": {
    "result": "r1: one interface is down. Review Ethernet2 and its peer.",
    "failed": false,
    "errors": []
  }
}
```

Request `verbose_result=True` to include the conversation and tool results when
you need to inspect the evidence behind an answer.

## Check network state

=== "CLI"

    ```bash
    nf# agent invoke workers agent-worker-1 instructions "Check interfaces on r1. List down interfaces and error counters. Include the commands used and any checks that could not be completed."
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
                    "Check interfaces on r1. List down interfaces and error "
                    "counters. Include the commands used and any checks that "
                    "could not be completed."
                ),
            },
        )
        for worker, response in results.items():
            if response["failed"]:
                print(worker, response["errors"])
            else:
                print(worker, response["result"])
    ```

Interface examples require a running Nornir service with `r1` in its inventory.
A completed agent request does not mean every network check passed: read the
findings and any reported task failures in the answer.

## Follow progress

Workers send progress events while the model responds and tools run. These show
activity and tool names, without exposing model reasoning or full tool data.

=== "CLI"

    Progress is displayed by default:

    ```bash
    nf# agent invoke workers agent-worker-1 instructions "Check interfaces on r1" progress true
    ```

=== "Python"

    Use the client from the previous example to read events as they arrive:

    ```python
    future = client.submit_job(
        service="agent",
        task="invoke",
        workers="agent-worker-1",
        kwargs={"instructions": "Check interfaces on r1", "progress": True},
    )
    for event in future.events():
        print(event["message"])
    print(future.result())
    ```

## Run a focused agent

This uses the [interface-check definition](services_agent_service_inventory.md#custom-agent-definitions).

=== "CLI"

    ```bash
    nf# agent invoke workers agent-worker-1 name nf://agents/interface_check.yaml instructions "Check interfaces on r1 and r2. Report only problems and their evidence."
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()
        results = client.run_job(
            service="agent",
            task="invoke",
            workers="agent-worker-1",
            kwargs={
                "name": "nf://agents/interface_check.yaml",
                "instructions": (
                    "Check interfaces on r1 and r2. Report only problems "
                    "and their evidence."
                ),
            },
        )
        for worker, response in results.items():
            print(worker, response["result"])
    finally:
        nf.destroy()
    ```

## Inspect tool results

=== "CLI"

    ```bash
    nf# agent invoke workers agent-worker-1 verbose-result instructions "Check interfaces on r1 and include the evidence."
    ```

=== "Python"

    ```python
    results = client.run_job(
        service="agent",
        task="invoke",
        workers="agent-worker-1",
        kwargs={
            "instructions": "Check interfaces on r1 and include the evidence.",
            "verbose_result": True,
        },
    )
    for response in results.values():
        print(response["result"])
    ```

Use the `client` created in the examples above. `workers` selects the agent host;
network devices are selected through your instructions and the tools it calls.

## Task Command Shell Reference

```bash
nf# man tree agent invoke
```

## Python API Reference

::: norfab.workers.agent_worker.agent_worker.AgentWorker.invoke
