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

### Load Nornir Inventory from Containerlab

Nornir Service supports loading hosts inventory from running Containerlab labs. This is useful to easily onboard Containerlab environments into Nornir and helps with automation. Internally Nornir service uses Containerlab Service to fetch running containers details and construct Nornir inventory.

!!! example

    === "CLI"
    
        ```
		C:\nf>nfcli
		Welcome to NorFab Interactive Shell.
		nf#
		nf#nornir inventory load containerlab 
		ceos-spine-1:
			show clock:
				Sun Dec  1 10:49:58 2024
				Timezone: UTC
				Clock source: local
			show hostname:
				Hostname: ceos-spine-1
				FQDN:     ceos-spine-1
		ceos-spine-2:
			show clock:
				Sun Dec  1 10:49:58 2024
				Timezone: UTC
				Clock source: local
			show hostname:
				Hostname: ceos-spine-2
				FQDN:     ceos-spine-2
		nf[nornir-cli]#
        ```
        
        Demo
		
		![Nornir Cli Demo](../../images/nornir_cli_demo.gif)
    
        In this example:

        - `nfcli` command starts the NorFab Interactive Shell.
        - `nornir` command switches to the Nornir sub-shell.
        - `cli` command switches to the CLI task sub-shell.
        - `commands` command retrieves the output of "show clock" and "show hostname" from the devices  that contain `ceos-spine` in their hostname as we use `FC` - "Filter Contains" Nornir hosts targeting filter.
		
		`inventory.yaml` should be located in same folder where we start nfcli, unless `nfcli -i path_to_inventory.yaml` flag used. Refer to [Getting Started](../../norfab_getting_started.md) section on how to construct  `inventory.yaml` file
		
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
                task="cli",
                kwargs={
                    "commands": ["show clock", "show hostname"],
                    "FC": "ceos-spine"              
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

		Once executed, above code should produce this output:
		
		```
        C:\nf>python nornir_cli.py
        {'nornir-worker-1': {'errors': [],
                             'failed': False,
                             'messages': [],
                             'result': {'ceos-spine-1': {'show clock': 'Sun Dec  1 '
                                                                       '11:10:53 2024\n'
                                                                       'Timezone: UTC\n'
                                                                       'Clock source: '
                                                                       'local',
                                                         'show hostname': 'Hostname: '
                                                                          'ceos-spine-1\n'
                                                                          'FQDN:     '
                                                                          'ceos-spine-1'},
                                        'ceos-spine-2': {'show clock': 'Sun Dec  1 '
                                                                       '11:10:53 2024\n'
                                                                       'Timezone: UTC\n'
                                                                       'Clock source: '
                                                                       'local',
                                                         'show hostname': 'Hostname: '
                                                                          'ceos-spine-2\n'
                                                                          'FQDN:     '
                                                                          'ceos-spine-2'}},
                             'task': 'nornir-worker-1:cli'}}
        C:\nf>					 
		```
		
		Refer to [Getting Started](../../norfab_getting_started.md) section on 
		how to construct  `inventory.yaml` file.

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
        │   ├── *name:    Name of the host
        │   ├── username:    Host connections username
        │   ├── password:    Host connections password
        │   ├── platform:    Host platform recognized by connection plugin
        │   ├── hostname:    Hostname of the host to initiate connection with, IP address or FQDN
        │   ├── port:    TCP port to initiate connection with, default '22'
        │   ├── connection-options:    JSON string with connection options
        │   ├── groups:    List of groups to associate with this host
        │   ├── groups-action:    Action to perform with groups, default 'append'
        │   └── progress:    Display progress events, default 'True'
        ├── delete-host:    Delete host from inventory
        │   ├── timeout:    Job timeout
        │   ├── workers:    Nornir workers to target, default 'all'
        │   ├── *name:    Name of the host
        │   └── progress:    Display progress events, default 'True'
        └── read-host-data:    Return host data at given dor-separated key path
            ├── timeout:    Job timeout
            ├── workers:    Nornir workers to target, default 'all'
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            ├── FN:    Negate the match
            ├── hosts:    Filter hosts to target
            ├── *keys:    Dot separated path within host data, examples: config.interfaces.Lo0
            └── progress:    Display progress events, default 'True'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.runtime_inventory