---
tags:
  - workflow
---

# Workflow Service Run Task

> task api name: `run`

Runs a workflow defined as a YAML file reference or an inline dictionary. Workflow steps call other NorFab services and collect the per-step job results under the workflow name.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `workflow` | Yes | Workflow definition dictionary or URL to a YAML workflow file |

## Output

Returns workflow execution results keyed by workflow name and step name:

```python
{
    "workflow_1": {
        "step1": {
            "nornir-worker-1": {
                "result": {"ceos-spine-1": {"show version": "..."}},
                "failed": False,
                "errors": [],
            },
        },
        "step2": {
            "nornir-worker-2": {
                "result": {"ceos-leaf-1": {"show hostname": "..."}},
                "failed": False,
                "errors": [],
            },
        },
    },
}
```

## Workflow File Example

Workflow service `run` task uses YAML files to execute workflow steps:

```yaml title="workflow-1.yaml"
name: workflow_1
description: Sample workflow with two steps.

step1:
  service: nornir
  task: cli
  kwargs:
    FC: spine
    commands:
      - show version
      - show ip int brief

step2:
  service: nornir
  task: cli
  kwargs:
    FC: leaf
    commands:
      - show hostname
      - show ntp status
```

Store the file on the broker, for example as `nf://workflow/workflow-1.yaml`, before running the workflow.

## Examples

=== "CLI"

    Run a workflow from a broker file:

    ```bash
    nf#workflow run workflow nf://workflow/workflow-1.yaml
    ```

    Run with a longer timeout:

    ```bash
    nf#workflow run workflow nf://workflow/workflow-1.yaml timeout 900
    ```

=== "Python"

    Context manager - run from a broker file:

    ```python
    import pprint

    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="workflow",
            task="run",
            workers="any",
            kwargs={
                "workflow": "nf://workflow/workflow-1.yaml",
            },
        )
        pprint.pprint(result)
    ```

    Direct lifecycle - run an inline workflow:

    ```python
    import pprint

    from norfab.core.nfapi import NorFab

    workflow = {
        "name": "inline_workflow",
        "description": "Collect basic command output from lab devices.",
        "show_version": {
            "service": "nornir",
            "task": "cli",
            "kwargs": {
                "FC": "spine",
                "commands": ["show version"],
            },
        },
        "show_hostname": {
            "service": "nornir",
            "task": "cli",
            "kwargs": {
                "FC": "leaf",
                "commands": ["show hostname"],
            },
        },
    }

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            service="workflow",
            task="run",
            workers="any",
            kwargs={"workflow": workflow},
        )
        pprint.pprint(result)
    finally:
        nf.destroy()
    ```

## NORFAB Workflow Run Command Shell Reference

NorFab shell supports these command options for Workflow `run` task:

```bash
nf# man tree workflow
root
└── workflow:    Workflow service
    └── run:    Run workflows
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── workflow:    Workflow to run
        └── progress:    Display progress events, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.workflow_worker.workflow_worker.WorkflowWorker.run
