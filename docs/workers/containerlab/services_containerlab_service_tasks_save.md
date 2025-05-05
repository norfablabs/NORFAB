---
tags:
  - containerlab
---

# Containerlab Service Save Task

> task api name: `save`

The Containerlab service `save` task is used to save the configuration of devices in a specified lab. This task ensures that the current state of the lab is preserved, allowing users to back up configurations for future use or restoration.

## Containerlab Save Task Overview

The `save` task provides the following features:

- **Configuration Backup**: Saves the current configuration of all devices in the lab.
- **Lab-Specific**: Operates on a specified lab, ensuring targeted configuration management.

## Containerlab Save Task Sample Usage

Below is an example of how to use the Containerlab save task to back up a lab's configuration.

!!! example

    === "CLI"

        ```
        nf#containerlab save lab-name three-routers-lab
        --------------------------------------------- Job Events -----------------------------------------------
        05-May-2025 20:48:25.322 7ffd783a18ee4db7b92d1643ef8b3390 job started
        05-May-2025 20:48:25.391 INFO containerlab-worker-1 running containerlab.save  - 20:48:25 INFO Parsing & checking topology file=three-routers-topology.yaml
        05-May-2025 20:48:25.551 INFO containerlab-worker-1 running containerlab.save  - 20:48:25 INFO saved cEOS configuration from r2 node to
        /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/clab-three-routers-lab/r2/flash/startup-config
        05-May-2025 20:48:25.905 INFO containerlab-worker-1 running containerlab.save  - 20:48:25 INFO saved cEOS configuration from r3 node to
        /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/clab-three-routers-lab/r3/flash/startup-config
        05-May-2025 20:48:26.285 INFO containerlab-worker-1 running containerlab.save  - 20:48:26 INFO saved cEOS configuration from r1 node to
        /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/clab-three-routers-lab/r1/flash/startup-config
        05-May-2025 20:48:26.510 7ffd783a18ee4db7b92d1643ef8b3390 job completed in 1.188 seconds

        --------------------------------------------- Job Results --------------------------------------------

        containerlab-worker-1:
            ----------
            three-routers-lab:
                True
        nf#
        ```

    === "Python"

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()

            client = nf.make_client()

            res = client.run_job(
                service="containerlab",
                task="save",
                kwargs={
                    "lab_name": "three-routers-lab",
                }
            )

            pprint.pprint(res)

            nf.destroy()
        ```

## NORFAB Containerlab CLI Shell Reference

Below are the commands supported by the `save` task:

```
nf# man tree containerlab.save
root
└── containerlab:    Containerlab service
    └── save:    Perform configuration save for all containers running in a lab
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── lab-name:    Lab name to save configurations for
        └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.containerlab_worker.ContainerlabWorker.save