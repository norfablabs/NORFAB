---
tags:
  - containerlab
---

# Containerlab Service Nornir Inventory Task

> task api name: `get_nornir_inventory`

The Containerlab service `get_nornir_inventory` task is designed to generate a Nornir-compatible inventory for a specified lab. This task inspects the container lab environment and maps container details to Nornir inventory format, enabling seamless integration with network automation workflows.

## Containerlab Nornir Inventory Task Overview

The `get_nornir_inventory` task provides the following features:

- **Inventory Generation**: Creates a Nornir-compatible inventory for a specified lab or all labs.
- **Platform Mapping**: Maps containerlab node kinds to Netmiko SSH platform types.
- **Default Credentials**: Optionally includes default credentials for containerlab nodes.

## Containerlab Nornir Inventory Task Sample Usage

Below is an example of how to use the Containerlab `get_nornir_inventory` task to generate an inventory.

!!! example

    === "CLI"

        ```
        nf#containerlab get-nornir-inventory lab-name three-routers-lab
        --------------------------------------------- Job Events -----------------------------------------------
        05-May-2025 21:14:09.594 fc13d3b11ad54c2fb2330af20a7ceacd job started
        05-May-2025 21:14:09.926 fc13d3b11ad54c2fb2330af20a7ceacd job completed in 0.332 seconds
        
        --------------------------------------------- Job Results --------------------------------------------
        
        containerlab-worker-1:
            ----------
            hosts:
                ----------
                r2:
                    ----------
                    hostname:
                        192.168.1.130
                    port:
                        12203
                    groups:
                    platform:
                        arista_eos
                    username:
                        admin
                    password:
                        admin
                r3:
                    ----------
                    hostname:
                        192.168.1.130
                    port:
                        12204
                    groups:
                    platform:
                    username:
                        admin
                    password:
                        admin
                r1:
                    ----------
                    hostname:
                        192.168.1.130
                    port:
                        12202
                    groups:
                    platform:
                        arista_eos
                    username:
                        admin
                    password:
                        admin
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
                task="get_nornir_inventory",
                kwargs={
                    "lab_name": "three-routers-lab",
                }
            )

            pprint.pprint(res)

            nf.destroy()
        ```

## NORFAB Containerlab CLI Shell Reference

Below are the commands supported by the `get_nornir_inventory` task:

```
nf#man tree containerlab.get-nornir-inventory
root
└── containerlab:    Containerlab service
    └── get-nornir-inventory:    Get nornir inventory for a given lab
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── lab-name:    Lab name to get Nornir inventory for
        ├── progress:    Display progress events, default 'True'
        └── groups:    List of groups to include in host's inventory
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.containerlab_worker.ContainerlabWorker.get_nornir_inventory