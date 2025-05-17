---
tags:
  - containerlab
---

# Containerlab Service Destroy Task

> task api name: `destroy_lab`

The Containerlab service `destroy_lab` task is designed to destroy a specified lab. This task ensures that all resources associated with the lab are cleaned up, including containers, networks, and other artifacts created during the lab deployment.

## Containerlab Destroy Task Overview

The `destroy_lab` task provides the following features:

- **Lab Cleanup**: Removes all containers, networks, and other resources associated with the specified lab.
- **Error Handling**: Provides detailed error messages if the lab cannot be found or destroyed.

## Containerlab Destroy Task Sample Usage

Below is an example of how to use the Containerlab destroy task to clean up a lab.

!!! example

    === "Demo"

        ![Containerlab Destroy Demo](../../images/containerlab/containerlab_destroy_demo.gif)

    === "CLI"

        ```
        nf#containerlab destroy lab-name three-routers-lab
        --------------------------------------------- Job Events -----------------------------------------------
        05-May-2025 20:45:48.745 831d3d485489476c98159f8d4dbf7ec2 job started
        05-May-2025 20:45:48.805 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:48 INFO Parsing & checking topology file=three-routers-topology.yaml
        05-May-2025 20:45:48.818 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:48 INFO Parsing & checking topology file=three-routers-topology.yaml
        05-May-2025 20:45:48.831 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:48 INFO Destroying lab name=three-routers-lab
        05-May-2025 20:45:50.129 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:50 INFO Removed container name=clab-three-routers-lab-r2
        05-May-2025 20:45:50.348 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:50 INFO Removed container name=clab-three-routers-lab-r3
        05-May-2025 20:45:50.390 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:50 INFO Removed container name=clab-three-routers-lab-r1
        05-May-2025 20:45:50.401 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:50 INFO Removing host entries path=/etc/hosts
        05-May-2025 20:45:50.412 INFO containerlab-worker-1 running containerlab.destroy_lab  - 20:45:50 INFO Removing SSH config path=/etc/ssh/ssh_config.d/clab-three-routers-lab.conf
        05-May-2025 20:45:50.963 831d3d485489476c98159f8d4dbf7ec2 job completed in 2.218 seconds

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
                task="destroy_lab",
                kwargs={
                    "lab_name": "three-routers-lab",
                }
            )

            pprint.pprint(res)

            nf.destroy()
        ```

## NORFAB Containerlab CLI Shell Reference

Below are the commands supported by the `destroy_lab` task:

```
nf#man tree containerlab.destroy
root
└── containerlab:    Containerlab service
    └── destroy:    The destroy command destroys a lab referenced by its name
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── lab-name:    Lab name to destroy
        └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.containerlab_worker.ContainerlabWorker.destroy_lab