---
tags:
  - containerlab
---

# Containerlab Service Restart Task

> task api name: `restart_lab`

The Containerlab service `restart_lab` task is designed to restart a specified lab. This task destroys the existing lab and redeploys it using the same topology file, ensuring a clean and consistent lab environment.

!!! warning
  
    Invoking restart task involves calling Containerlab deploy command with `--reconfigure` flag. Any non saved state will be lost.

## Containerlab Restart Task Overview

The `restart_lab` task provides the following features:

- **Lab Restart**: Destroys the current lab and redeploys it using the original topology file.
- **Error Handling**: Provides detailed error messages if the lab cannot be found or restarted.

## Containerlab Restart Task Sample Usage

Below is an example of how to use the Containerlab restart task to restart a lab.

!!! example

    === "CLI"

        ```
        nf#containerlab restart lab-name three-routers-lab
        --------------------------------------------- Job Events -----------------------------------------------
        05-May-2025 20:51:33.947 ee23b3ec4bfb474fac0a7e87e910862b job started
        05-May-2025 20:51:34.011 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:34 INFO Containerlab started version=0.67.0
        05-May-2025 20:51:34.022 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:34 INFO Parsing & checking topology file=three-routers-topology.yaml
        05-May-2025 20:51:34.034 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:34 INFO Destroying lab name=three-routers-lab
        05-May-2025 20:51:35.527 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Removed container name=clab-three-routers-lab-r2
        05-May-2025 20:51:35.614 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Removed container name=clab-three-routers-lab-r3
        05-May-2025 20:51:35.659 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Removed container name=clab-three-routers-lab-r1
        05-May-2025 20:51:35.670 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Removing host entries path=/etc/hosts
        05-May-2025 20:51:35.681 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Removing SSH config path=/etc/ssh/ssh_config.d/clab-three-routers-lab.conf
        05-May-2025 20:51:35.790 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Creating container name=r1
        05-May-2025 20:51:35.813 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:35 INFO Creating container name=r3
        05-May-2025 20:51:36.402 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Running postdeploy actions for Arista cEOS 'r3' node
        05-May-2025 20:51:36.658 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Created link: r3:eth3 ▪┄┄▪ r1:eth3
        05-May-2025 20:51:36.669 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Running postdeploy actions for Arista cEOS 'r1' node
        05-May-2025 20:51:36.779 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Created link: r1:eth1 ▪┄┄▪ r2:eth1
        05-May-2025 20:51:36.821 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Created link: r2:eth2 ▪┄┄▪ r3:eth2
        05-May-2025 20:51:36.832 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:51:36 INFO Running postdeploy actions for Arista cEOS 'r2' node
        05-May-2025 20:52:03.895 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:52:03 INFO Adding host entries path=/etc/hosts
        05-May-2025 20:52:03.906 INFO containerlab-worker-1 running containerlab.restart_lab  - 20:52:03 INFO Adding SSH config for nodes path=/etc/ssh/ssh_config.d/clab-three-routers-lab.conf
        05-May-2025 20:52:04.142 ee23b3ec4bfb474fac0a7e87e910862b job completed in 30.195 seconds

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
                task="restart_lab",
                kwargs={
                    "lab_name": "three-routers-lab",
                }
            )

            pprint.pprint(res)

            nf.destroy()
        ```

## NORFAB Containerlab CLI Shell Reference

Below are the commands supported by the `restart_lab` task:

```
nf#man tree containerlab.restart
root
└── containerlab:    Containerlab service
    └── restart:    Restart lab devices
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── lab-name:    Lab name to restart
        └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.containerlab_worker.ContainerlabWorker.restart_lab