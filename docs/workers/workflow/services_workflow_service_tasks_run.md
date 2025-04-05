---
tags:
  - workflow
---

# Workflow Service Run Task

> task api name: `run`

Run workflow defined using YAML file.

## Workflow Sample Usage

Workflow service `run` task uses YAML formatted files to execute workflow steps:

``` yaml title="workflow-1.yaml"
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

File `workflow-1.yaml` stored on broker and downloaded by Workflow service prior to running steps, below is an example of how to run the the workflow.

!!! example

    === "CLI"
    
        ```
        C:\nf>nfcli
        Welcome to NorFab Interactive Shell.
        nf#
        nf#workflow run workflow nf://workflow/workflow-1.yaml
        --------------------------------------------- Job Events -----------------------------------------------
        05-Apr-2025 21:34:53.846 d1634ce3dc764f56ac00971950a033cc job started
        05-Apr-2025 21:34:53.883 INFO workflow-worker-1 running workflow.run  - Starting workflow 'workflow_1'
        05-Apr-2025 21:34:53.883 INFO workflow-worker-1 running workflow.run  - Doing workflow step 'step1'
        05-Apr-2025 21:34:55.008 INFO workflow-worker-1 running workflow.run  - Doing workflow step 'step2'
        05-Apr-2025 21:34:56.557 d1634ce3dc764f56ac00971950a033cc job completed in 2.711 seconds

        --------------------------------------------- Job Results --------------------------------------------

        workflow-worker-1:
            ----------
            workflow_1:
                ----------
                step1:
                    ----------
                    nornir-worker-1:
                        ----------
                        task:
                            nornir-worker-1:cli
                        failed:
                            False
                        errors:
                        result:
                            ----------
                            ceos-spine-2:
                                ----------
                                show version:
                                    Arista cEOSLab
                                    Hardware version:
                                    Serial number: 8B7EBC67A4FA6C48F1D1BCC5438866A7
                                    Hardware MAC address: 001c.73ab.5167
                                    System MAC address: 001c.73ab.5167

                                    Software image version: 4.30.0F-31408673.4300F (engineering build)
                                    Architecture: x86_64
                                    Internal build version: 4.30.0F-31408673.4300F
                                    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
                                    Image format version: 1.0
                                    Image optimization: None

                                    cEOS tools version: (unknown)
                                    Kernel version: 5.15.0-136-generic

                                    Uptime: 1 hour and 17 minutes
                                    Total memory: 32827264 kB
                                    Free memory: 19525528 kB
                                show ip int brief:
                                                                                                                      Address
                                    Interface         IP Address              Status       Protocol            MTU    Owner
                                    ----------------- ----------------------- ------------ -------------- ----------- -------
                                    Loopback0         unassigned              up           up                65535
                                    Loopback123       unassigned              up           up                65535
                                    Management0       172.100.100.11/24       up           up                 1500
                            ceos-spine-1:
                                ----------
                                show version:
                                    Arista cEOSLab
                                    Hardware version:
                                    Serial number: 7B5E3CF8CB9A6DE53FB8411896DE476F
                                    Hardware MAC address: 001c.730a.5369
                                    System MAC address: 001c.730a.5369

                                    Software image version: 4.30.0F-31408673.4300F (engineering build)
                                    Architecture: x86_64
                                    Internal build version: 4.30.0F-31408673.4300F
                                    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
                                    Image format version: 1.0
                                    Image optimization: None

                                    cEOS tools version: (unknown)
                                    Kernel version: 5.15.0-136-generic

                                    Uptime: 1 hour and 17 minutes
                                    Total memory: 32827264 kB
                                    Free memory: 19525528 kB
                                show ip int brief:
                                                                                                                      Address
                                    Interface         IP Address              Status       Protocol            MTU    Owner
                                    ----------------- ----------------------- ------------ -------------- ----------- -------
                                    Loopback0         unassigned              up           up                65535
                                    Loopback123       unassigned              up           up                65535
                                    Management0       172.100.100.10/24       up           up                 1500
                        messages:
                        juuid:
                            0bef61db66cf46318735e02bdb0389c0
                        status:
                            completed
                step2:
                    ----------
                    nornir-worker-2:
                        ----------
                        task:
                            nornir-worker-2:cli
                        failed:
                            False
                        errors:
                        result:
                            ----------
                            ceos-leaf-2:
                                ----------
                                show hostname:
                                    Hostname: ceos-leaf-2
                                    FQDN:     ceos-leaf-2
                                    unsynchronised
                                    poll interval unknown
                            ceos-leaf-1:
                                ----------
                                show hostname:
                                    Hostname: ceos-leaf-1
                                    FQDN:     ceos-leaf-1
                                show ntp status:
                                    unsynchronised
                                    poll interval unknown
                            ceos-leaf-3:
                                ----------
                                show hostname:
                                    Hostname: ceos-leaf-3
                                    FQDN:     ceos-leaf-3
                                show ntp status:
                                    unsynchronised
                                    poll interval unknown
                        messages:
                        juuid:
                            972287e3abc94e86acfff99b54940ef9
                        status:
                            completed
        nf#
        ```    
        In this example:

        - `nfcli` command starts the NorFab Interactive Shell.
        - `workflow run` command runs `workflow-1.yaml` workflow.
		
    === "Python"
    
        This code is complete and can run as is
		
        ```
        import pprint
        
        from norfab.core.nfapi import NorFab
        
        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            
            client = nf.make_client()
            
            res = client.run_job(
                service="workflow",
                task="run",
                kwargs={
                    "workflow": "nf://workflow/workflow-1.yaml",
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

## NORFAB Workflow Test Shell Reference

NorFab shell supports these command options for workflow `run` task:

```
nf#man tree workflow
root
└── workflow:    Workflow service
    └── run:    Run workflows
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── workflow:    Workflow to run
        └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.workflow_worker.WorkflowWorker.run