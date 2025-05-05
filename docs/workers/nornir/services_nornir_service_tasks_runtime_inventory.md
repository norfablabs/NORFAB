---
tags:
  - nornir
---

# Nornir Service Runtime Inventory Task

> task api name: `runtime_inventory`

The Nornir Service `runtime_inventory` task designed to work with Nornir inventory content at a runtime. This task uses nornir-salt `InventoryFun` functions to create, read, update or delete hosts.

## Sample Usage

Sample NorFab client call to invoke inventory host creation:

``` python
result = nfclient.run_job(
    "nornir",
    "runtime_inventory",
    workers=["nornir-worker-1"],
    kwargs={
        "action": "create_host",
        "name": "foobar"
    },
)
```

Supported actions are:

- `create_host` or `create` - creates new host or replaces existing host object
- `read_host` or `read` - read host inventory content
- `update_host` or `update` - non recursively update host attributes if host exists in Nornir inventory, do not create host if it does not exist
- `delete_host` or `delete` - deletes host object from Nornir Inventory
- `load` - to simplify calling multiple functions
- `read_inventory` - read inventory content for groups, default and hosts
- `read_host_data` - to return host's data under provided path keys
- `list_hosts` - return a list of inventory's host names
- `list_hosts_platforms` - return a dictionary of hosts' platforms
- `update_defaults` - non recursively update defaults attributes
- `load` - load Nornir inventory from external sources

### Create Host Example

```
nf#nornir inventory create-host name foobar
--------------------------------------------- Job Events -----------------------------------------------
15-Feb-2025 11:12:38.908 d42e073070b94d408225af2a880d1d26 job started
15-Feb-2025 11:12:38.939 INFO nornir-worker-5 running nornir.runtime_inventory  - Performing 'create_host' action
15-Feb-2025 11:12:39.162 d42e073070b94d408225af2a880d1d26 job completed in 0.254 seconds

--------------------------------------------- Job Results --------------------------------------------

{
    "nornir-worker-5": {
        "foobar": true
    }
}
nf#
```

## Nornir and Containerlab Services Integration

Nornir Service supports loading hosts inventory from running Containerlab labs using `nornir_inventory_load_containerlab` task. This is useful to easily onboard Containerlab environments into Nornir and helps with automation. Internally Nornir service uses Containerlab Service to fetch running containers details and construct Nornir inventory.

!!! example

    === "CLI"
    
        ```
        nf#nornir inventory load containerlab clab-workers containerlab-worker-1 workers nornir-worker-1 lab-name three-routers-lab
        --------------------------------------------- Job Events -----------------------------------------------
        05-May-2025 21:32:07.155 ed210f6c91ac40ada02149118eede2c9 job started
        05-May-2025 21:32:07.172 INFO nornir-worker-1 running nornir.nornir_inventory_load_containerlab  - Pulling Containerlab 'three-routers-lab' lab inventory from 'containerlab-worker-1' workers
        05-May-2025 21:32:07.393 INFO nornir-worker-1 running nornir.nornir_inventory_load_containerlab  - Pulled Containerlab 'three-routers-lab' lab inventory
        05-May-2025 21:32:07.399 INFO nornir-worker-1 running nornir.nornir_inventory_load_containerlab  - Merged Containerlab 'three-routers-lab' lab inventory with Nornir runtime inventory
        05-May-2025 21:32:07.916 ed210f6c91ac40ada02149118eede2c9 job completed in 0.76 seconds

        --------------------------------------------- Job Results --------------------------------------------

        nornir-worker-1:
            True
        nf#
        ```
		
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
                service="nornir",
                workers=["nornir-worker-1"],
                task="nornir_inventory_load_containerlab",
                kwargs={
                    "lab_name": "three-routers-lab",
                    "clab_workers": ["containerlab-worker-1"],
                    "lab_name": "three-routers-lab"
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

## NORFAB Nornir Runtime Inventory Shell Reference

NorFab shell supports these command options for Nornir `runtime_inventory` task:

```
nf#man tree nornir.inventory
root
└── nornir:    Nornir service
    └── inventory:    Work with Nornir inventory
        ├── create-host:    Create new host
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'any'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── *name:    Name of the host
        │   ├── username:    Host connections username
        │   ├── password:    Host connections password
        │   ├── platform:    Host platform recognized by connection plugin
        │   ├── hostname:    Hostname of the host to initiate connection with, IP address or FQDN
        │   ├── port:    TCP port to initiate connection with, default '22'
        │   ├── connection-options:    JSON string with connection options
        │   ├── groups:    List of groups to associate with this host
        │   ├── data:    JSON string with arbitrary host data
        │   └── progress:    Display progress events, default 'True'
        ├── update-host:    Update existing host details
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── *name:    Name of the host
        │   ├── username:    Host connections username
        │   ├── password:    Host connections password
        │   ├── platform:    Host platform recognized by connection plugin
        │   ├── hostname:    Hostname of the host to initiate connection with, IP address or FQDN
        │   ├── port:    TCP port to initiate connection with, default '22'
        │   ├── connection-options:    JSON string with connection options
        │   ├── groups:    List of groups to associate with this host
        │   ├── groups-action:    Action to perform with groups, default 'append'
        │   ├── data:    JSON string with arbitrary host data
        │   └── progress:    Display progress events, default 'True'
        ├── delete-host:    Delete host from inventory
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── *name:    Name of the host
        │   └── progress:    Display progress events, default 'True'
        ├── read-host-data:    Return host data at given dor-separated key path
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FX:    Filter hosts excluding them by name
        │   ├── FN:    Negate the match
        │   ├── *keys:    Dot separated path within host data, examples: config.interfaces.Lo0
        │   └── progress:    Display progress events, default 'True'
        └── load:    Load inventory from external source
            └── containerlab:    Load inventory from running Containerlab lab(s)
                ├── timeout:    Job timeout
                ├── *workers:    Nornir workers to load inventory into
                ├── verbose-result:    Control output details, default 'False'
                ├── clab-workers:    Containerlab workers to load inventory from
                ├── progress:    Display progress events, default 'True'
                ├── lab-name:    Name of Containerlab lab to load hosts' inventory
                ├── groups:    List of Nornir groups to associate with hosts
                ├── use-default-credentials:    Use Containerlab default credentials for all hosts
                └── dry-run:    Do not refresh Nornir, only return pulled inventory
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.runtime_inventory