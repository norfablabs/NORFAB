---
tags:
  - netbox
---

# Netbox Get Containerlab Inventory Task

> task api name: `get_containerlab_inventory`

This task designed to provide Containerlab workers with inventory data sourced from Netbox to deploy lab topologies.

## Get Containerlab Inventory Sample Usage

Below is an example of how to fetch Containerlab topology inventory data from Netbox for two devices named `fceos4` and `fceos5`.

```
nf#netbox get containerlab-inventory devices fceos4 fceos5 lab-name foobar
--------------------------------------------- Job Events -----------------------------------------------
31-May-2025 13:10:14.477 7d434ed4e24c4a69af5d52797d7a187e job started
31-May-2025 13:10:14.525 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Fetching devices data from Netbox
31-May-2025 13:10:14.594 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Node added fceos4
31-May-2025 13:10:14.600 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Node added fceos5
31-May-2025 13:10:14.606 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Fetching connections data from Netbox
31-May-2025 13:10:15.211 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth1 - fceos4:eth1
31-May-2025 13:10:15.217 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth2 - fceos4:eth2
31-May-2025 13:10:15.225 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth3 - fceos4:eth3
31-May-2025 13:10:15.232 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth4 - fceos4:eth4
31-May-2025 13:10:15.238 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth6 - fceos4:eth6
31-May-2025 13:10:15.244 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth7 - fceos4:eth7
31-May-2025 13:10:15.250 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth8 - fceos4:eth101
31-May-2025 13:10:15.257 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Link added fceos5:eth11 - fceos4:eth11
31-May-2025 13:10:15.580 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Renaming fceos4 interfaces
31-May-2025 13:10:15.587 INFO netbox-worker-1.1 running netbox.get_containerlab_inventory  - Renaming fceos5 interfaces
31-May-2025 13:10:15.808 7d434ed4e24c4a69af5d52797d7a187e job completed in 1.331 seconds

--------------------------------------------- Job Results --------------------------------------------

netbox-worker-1.1:
  mgmt:
    ipv4-subnet: 172.100.100.0/24
    network: br-foobar
  name: foobar
  topology:
    links:
    - endpoints:
      - interface: eth1
        node: fceos5
      - interface: eth1
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth2
        node: fceos5
      - interface: eth2
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth3
        node: fceos5
      - interface: eth3
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth4
        node: fceos5
      - interface: eth4
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth6
        node: fceos5
      - interface: eth6
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth7
        node: fceos5
      - interface: eth7
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth8
        node: fceos5
      - interface: eth101
        node: fceos4
      type: veth
    - endpoints:
      - interface: eth11
        node: fceos5
      - interface: eth11
        node: fceos4
      type: veth
    nodes:
      fceos4:
        image: ceosimage:4.30.0F
        kind: ceos
        mgmt-ipv4: 172.100.100.2
        ports:
        - 12000:22/tcp
        - 12001:23/tcp
        - 12002:80/tcp
        - 12003:161/udp
        - 12005:830/tcp
        - 12006:8080/tcp
      fceos5:
        image: ceosimage:4.30.0F
        kind: ceos
        mgmt-ipv4: 172.100.100.3
        ports:
        - 12007:22/tcp
        - 12008:23/tcp
        - 12009:80/tcp
        - 12010:161/udp
        - 12011:443/tcp
        - 12012:830/tcp
        - 12013:8080/tcp

nf#
```

## NORFAB Netbox Get Containerlab Inventory Command Shell Reference

NorFab shell supports these command options for Netbox `get_containerlab_inventory` task:

```
nf#man tree netbox.get.containerlab-inventory
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── containerlab-inventory:    Query Netbox and construct Containerlab inventory
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── lab-name:    Lab name to generate lab inventory for
            ├── tenant:    Tenant name to generate lab inventory for
            │   ├── tenant:    Filter devices by tenants
            │   ├── device-name-contains:    Filter devices by name pattern
            │   ├── model:    Filter devices by models
            │   ├── platform:    Filter devices by platforms
            │   ├── region:    Filter devices by regions
            │   ├── role:    Filter devices by roles
            │   ├── site:    Filter devices by sites
            │   ├── status:    Filter devices by statuses
            │   └── tag:    Filter devices by tags
            ├── devices:    List of devices to generate lab inventory for
            ├── progress:    Display progress events, default 'True'
            ├── netbox-instance:    Name of Netbox instance to pull inventory from
            ├── ipv4-subnet:    IPv4 management subnet to use for lab, default '172.100.100.0/24'
            ├── image:    Docker image to use for all nodes
            └── ports:    Range of TCP/UDP ports to use for nodes, default '[12000, 13000]'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.get_containerlab_inventory