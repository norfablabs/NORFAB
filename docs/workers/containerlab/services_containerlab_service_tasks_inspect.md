---
tags:
  - containerlab
---

# Containerlab Service Inspect Task

> task api name: `inspect`

The Containerlab service `inspect` task is designed to inspect the configuration and status of container lab containers. This task provides detailed information about running labs, including their topology, container details, and status.

## Containerlab Inspect Task Overview

The `inspect` task provides the following features:

- **Lab Inspection**: Retrieves information about a specific lab or all labs.
- **Detailed View**: Optionally includes detailed information about the lab's containers.

## Containerlab Inspect Task Sample Usage

Below is an example of how to use the Containerlab inspect task to inspect a lab.

!!! example

    === "CLI"

        ```
        nf#show containerlab containers lab-name three-routers-lab
        containerlab-worker-1:
            ----------
            containers:
                |_
                  ----------
                  lab_name:
                      three-routers-lab
                  labPath:
                      __norfab__/files/worker/containerlab-worker-1/topologies/containerlab/three-routers-topology.yaml
                  name:
                      clab-three-routers-lab-r1
                  container_id:
                      4f7836a4d1ac
                  image:
                      ceosimage:4.30.0F
                  kind:
                      ceos
                  state:
                      running
                  ipv4_address:
                      172.100.101.12/24
                  ipv6_address:
                      N/A
                  owner:
                      norfabuser
                |_
                  ----------
                  lab_name:
                      three-routers-lab
                  labPath:
                      __norfab__/files/worker/containerlab-worker-1/topologies/containerlab/three-routers-topology.yaml
                  name:
                      clab-three-routers-lab-r2
                  container_id:
                      6ea7120965b1
                  image:
                      ceosimage:4.30.0F
                  kind:
                      ceos
                  state:
                      running
                  ipv4_address:
                      172.100.101.13/24
                  ipv6_address:
                      N/A
                  owner:
                      norfabuser
                |_
                  ----------
                  lab_name:
                      three-routers-lab
                      __norfab__/files/worker/containerlab-worker-1/topologies/containerlab/three-routers-topology.yaml
                  name:
                      clab-three-routers-lab-r3
                  container_id:
                      63ee900fde76
                  image:
                      ceosimage:4.30.0F
                  kind:
                      ceos
                  state:
                      running
                  ipv4_address:
                      172.100.101.14/24
                  ipv6_address:
                      N/A
                  owner:
                      norfabuser
        nf#
        ```

    === "CLI with Details"

        ```
        nf#show containerlab containers lab-name three-routers-lab details
        containerlab-worker-1:
            |_
              ----------
              Names:
                  - clab-three-routers-lab-r2
              ID:
                  6ea7120965b142c397bab0c1a40550e00e967b8ae6031f7f66561f8decc0b45a
              ShortID:
                  6ea7120965b1
              Image:
                  ceosimage:4.30.0F
              State:
                  running
              Status:
                  Up 14 minutes
              Labels:
                  ----------
                  clab-mgmt-net-bridge:
                      br-f71d180c51e5
                  clab-node-group:
                  clab-node-kind:
                      ceos
                  clab-node-lab-dir:
                      /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/clab-three-routers-lab/r2
                  clab-node-longname:
                      clab-three-routers-lab-r2
                  clab-node-name:
                      r2
                  clab-node-type:
                  clab-owner:
                      norfabuser
                  clab-topo-file:
                      /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/three-routers-topology.yaml
                  containerlab:
                      three-routers-lab
              Pid:
                  7083
              NetworkSettings:
                  ----------
                  IPv4addr:
                      172.100.101.13
                  IPv4pLen:
                      24
                  IPv4Gw:
                      172.100.101.1
                  IPv6addr:
                  IPv6pLen:
                      0
                  IPv6Gw:
              Mounts:
                  |_
                    ----------
                    Source:
                        /home/norfabuser/norfab/tests/nf_containerlab/__norfab__/files/worker/containerlab-worker-1/topologies/containerlab/clab-three-routers-lab/r2/flash
                    Destination:
                        /mnt/flash
              Ports:
                  |_
                    ----------
                    host_ip:
                        0.0.0.0
                    host_port:
                        12203
                    port:
                        22
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        ::
                    host_port:
                        12203
                    port:
                        22
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        0.0.0.0
                    host_port:
                        14403
                    port:
                        443
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        ::
                    host_port:
                        14403
                    port:
                        443
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        0.0.0.0
                    host_port:
                        18803
                    port:
                        80
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        ::
                    host_port:
                        18803
                    port:
                        80
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        0.0.0.0
                    host_port:
                        18303
                    port:
                        830
                    protocol:
                        tcp
                  |_
                    ----------
                    host_ip:
                        ::
                    host_port:
                        18303
                    port:
                        830
                    protocol:
                        tcp
                        
        <...omitted for brevity...>
        
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
                task="inspect",
                kwargs={
                    "lab_name": "three-routers-lab",
                }
            )

            pprint.pprint(res)

            nf.destroy()
        ```

## NORFAB Containerlab CLI Shell Reference

Below are the commands supported by the `inspect` task:

```
nf#man tree show.containerlab.containers
root
└── show:    NorFab show commands
    └── containerlab:    Show Containerlab service
        └── containers:    show containerlab containers
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── details:    Show container labs details
            └── lab-name:    Show container for given lab only
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.containerlab_worker.ContainerlabWorker.inspect