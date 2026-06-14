---
tags:
  - nornir
---

# Nornir Service SNMP Tasks

> task api names: `snmp_get`, `snmp_getnext`, `snmp_multiget`, `snmp_walk`,
> `snmp_multiwalk`, `snmp_bulkget`, `snmp_bulkwalk`, `snmp_table`,
> `snmp_bulktable`, `snmp_set`, `snmp_multiset`

Nornir service SNMP tasks provide operation-specific interfaces to interact
with network devices using the SNMP protocol. All SNMP tasks are backed by
[Nornir-Salt](https://github.com/saltstack/nornir-salt)'s `puresnmp_call`
plugin, which uses the [puresnmp](https://github.com/exhuma/puresnmp)
library under the hood.

- **SNMPv1 / SNMPv2c**: Supported out of the box using community-based
  authentication.
- **SNMPv3**: Requires the puresnmp `crypto` extra (included with NorFab's
  Nornir service dependency).

Only numeric OIDs are supported. MIB name loading and symbolic OID resolution
are not provided by the installed puresnmp API.

## Nornir SNMP Sample Usage

Below is an example of how to use the Nornir SNMP tasks to retrieve and
set OID values on devices.

!!! example

    === "CLI"
    
        ```
		C:\nf>nfcli
		Welcome to NorFab Interactive Shell.
		nf#
		nf#nornir
		nf[nornir]#snmp
		nf[nornir-snmp]#
		nf[nornir-snmp]#get oid 1.3.6.1.2.1.1.5.0 FC spine
		ceos-spine-1:
		  get:
		    1.3.6.1.2.1.1.5.0: ceos-spine-1
		ceos-spine-2:
		  get:
		    1.3.6.1.2.1.1.5.0: ceos-spine-2
		nf[nornir-snmp]#
		nf[nornir-snmp]#walk oid 1.3.6.1.2.1.1
		ceos-spine-1:
		  walk:
		    1.3.6.1.2.1.1.1.0: Arista Networks EOS
		    1.3.6.1.2.1.1.2.0: 1.3.6.1.4.1.30065.1.3011.4352.2F
		    1.3.6.1.2.1.1.3.0: 6000000
		    1.3.6.1.2.1.1.4.0: ""
		    1.3.6.1.2.1.1.5.0: ceos-spine-1
		    1.3.6.1.2.1.1.6.0: ""
		    1.3.6.1.2.1.1.7.0: 72
		nf[nornir-snmp]#
		nf[nornir-snmp]#multi-get oids 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0
		ceos-spine-1:
		  multiget:
		    1.3.6.1.2.1.1.1.0: Arista Networks EOS
		    1.3.6.1.2.1.1.5.0: ceos-spine-1
		nf[nornir-snmp]#
		nf[nornir-snmp]#set oid 1.3.6.1.2.1.1.6.0 value "Brisbane lab"
		ceos-spine-1:
		  set:
		    1.3.6.1.2.1.1.6.0: Brisbane lab
		nf[nornir-snmp]#
        ```
    
        In this example:

        - `nfcli` command starts the NorFab Interactive Shell.
        - `nornir` command switches to the Nornir sub-shell.
        - `snmp` command switches to the SNMP task sub-shell.
        - `get` retrieves a single OID from devices that contain `spine` in
          their hostname using `FC` — "Filter Contains" Nornir hosts targeting
          filter.
        - `walk` walks an entire OID subtree, collecting all values beneath it.
        - `multi-get` retrieves multiple OIDs in a single request.
        - `set` writes a value to a writable OID on the targeted devices.
		
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
                task="snmp_get",
                kwargs={
                    "oid": "1.3.6.1.2.1.1.5.0",
                    "FC": "spine"              
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

		Once executed, above code should produce this output:
		
		```
        C:\nf>python nornir_snmp.py
        {'nornir-worker-1': {'errors': [],
                             'failed': False,
                             'messages': [],
                             'result': {'ceos-spine-1': {'get': {'1.3.6.1.2.1.1.5.0':
                                                                      'ceos-spine-1'}},
                                        'ceos-spine-2': {'get': {'1.3.6.1.2.1.1.5.0':
                                                                      'ceos-spine-2'}}},
                             'task': 'nornir-worker-1:snmp_get'}}
        C:\nf>					 
		```
		
		Refer to [Getting Started](../../norfab_getting_started.md) section on 
		how to construct  `inventory.yaml` file.

## SNMP Read Operations

Nornir SNMP tasks expose a full set of read operations, each with its own
task API name and validation. All read operations are annotated as read-only
and idempotent for MCP tool safety.

| Task | Required Argument | Optional Arguments | Description |
| --- | --- | --- | --- |
| `snmp_get` | `oid` | Common Nornir arguments | Retrieve a single OID value |
| `snmp_getnext` | `oid` | Common Nornir arguments | Retrieve the OID following the specified OID |
| `snmp_multiget` | `oids` | Common Nornir arguments | Retrieve multiple OIDs in a single request |
| `snmp_walk` | `oid` | `errors`, common arguments | Walk an OID subtree |
| `snmp_multiwalk` | `oids` | Common Nornir arguments | Walk multiple OID subtrees |
| `snmp_bulkget` | `repeating_oids` | `scalar_oids`, `max_list_size`, common arguments | Retrieve scalar and column OIDs using GETBULK |
| `snmp_bulkwalk` | `oids` | `bulk_size`, common arguments | Walk OID subtrees using GETBULK |
| `snmp_table` | `oid` | Common Nornir arguments | Retrieve a full SNMP table |
| `snmp_bulktable` | `oid` | `bulk_size`, common arguments | Retrieve a full SNMP table using GETBULK |

Argument names match the installed puresnmp methods. In particular,
`snmp_bulkget` uses `max_list_size`, while `snmp_bulkwalk` and
`snmp_bulktable` use `bulk_size`.

!!! example

    === "CLI"
    
        ```
		nf[nornir-snmp]#walk oid 1.3.6.1.2.1.2.2
		ceos-leaf-1:
		  walk:
		    1.3.6.1.2.1.2.2.1.1.1: 1
		    1.3.6.1.2.1.2.2.1.2.1: Ethernet1
		    1.3.6.1.2.1.2.2.1.2.2: Ethernet2
		    ...
		nf[nornir-snmp]#
		nf[nornir-snmp]#bulk-walk oids 1.3.6.1.2.1.2.2.1.2 bulk-size 20
		ceos-leaf-1:
		  bulkwalk:
		    1.3.6.1.2.1.2.2.1.2.1: Ethernet1
		    1.3.6.1.2.1.2.2.1.2.2: Ethernet2
		    ...
		nf[nornir-snmp]#
		nf[nornir-snmp]#table oid 1.3.6.1.2.1.2.2
		ceos-leaf-1:
		  table:
		    1.3.6.1.2.1.2.2:
		      - "1": "1"
		        "2": "Ethernet1"
		        ...
		nf[nornir-snmp]#
		nf[nornir-snmp]#bulk-get scalar-oids 1.3.6.1.2.1.1.5.0 repeating-oids 1.3.6.1.2.1.2.2.1.2
		ceos-leaf-1:
		  bulkget:
		    scalars:
		      1.3.6.1.2.1.1.5.0: ceos-leaf-1
		    listing:
		      1.3.6.1.2.1.2.2.1.2.1: Ethernet1
		      1.3.6.1.2.1.2.2.1.2.2: Ethernet2
		nf[nornir-snmp]#
        ```

        In this example:

        - `walk` retrieves the full interface table subtree from matched
          devices.
        - `bulk-walk` uses GETBULK for more efficient collection of large
          tables, with `bulk-size` controlling the number of OIDs per request.
        - `table` returns the interface table as normalized rows.
        - `bulk-get` retrieves scalar and column OIDs in one request,
          separating scalars and listing in the result.
		
    === "Python"
    
		This code is complete and can run as is
		
        ```
        import pprint
        
        from norfab.core.nfapi import NorFab
        
        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            
            client = nf.make_client()
            
            # SNMP WALK
            res = client.run_job(
                service="nornir",
                task="snmp_walk",
                kwargs={"oid": "1.3.6.1.2.1.2.2"}
            )
            pprint.pprint(res)
            
            # SNMP TABLE
            res = client.run_job(
                service="nornir",
                task="snmp_table",
                kwargs={"oid": "1.3.6.1.2.1.2.2"}
            )
            pprint.pprint(res)
            
            nf.destroy()
        ```

## SNMP Write Operations

`snmp_set` and `snmp_multiset` provide state-changing SNMP write capabilities.
Both operations are annotated as destructive for MCP tool safety.

!!! warning
    SNMP writes require a read-write community on the target device. The
    installed Nornir-Salt plugin converts all set values to SNMP
    `OctetString`. Integer, counter, gauge, IP address, and OID-typed
    writes are not supported by this API.

!!! example

    === "CLI"
    
        ```
		nf[nornir-snmp]#set oid 1.3.6.1.2.1.1.6.0 value "Brisbane lab" FC spine
		ceos-spine-1:
		  set:
		    1.3.6.1.2.1.1.6.0: Brisbane lab
		ceos-spine-2:
		  set:
		    1.3.6.1.2.1.1.6.0: Brisbane lab
		nf[nornir-snmp]#
		nf[nornir-snmp]#multi-set mappings '{"1.3.6.1.2.1.1.6.0":"NorFab HQ","1.3.6.1.2.1.1.4.0":"ops@norfab.local"}'
		ceos-spine-1:
		  multiset:
		    1.3.6.1.2.1.1.6.0: NorFab HQ
		    1.3.6.1.2.1.1.4.0: ops@norfab.local
		nf[nornir-snmp]#
        ```

        `multi-set` accepts a JSON object mapping OIDs to values and converts
        it to a dictionary before job submission.

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
                task="snmp_set",
                kwargs={
                    "oid": "1.3.6.1.2.1.1.6.0",
                    "value": "Brisbane lab",
                    "FC": "spine"
                }
            )
            pprint.pprint(res)
            
            nf.destroy()
        ```

## Nornir Inventory Configuration

SNMP connectivity requires the `puresnmp` connection plugin configured in
the Nornir inventory.

### SNMPv2c Community

```yaml
groups:
  eos_params:
    connection_options:
      puresnmp:
        extras:
          version: v2c
          community: norfab
```

Per-host UDP port overrides are needed when the default UDP/161 port is
mapped to a different host port, such as in containerlab setups:

```yaml
hosts:
  ceos-spine-1:
    hostname: 192.168.1.130
    connection_options:
      puresnmp:
        port: 11610
```

### SNMPv3

```yaml
connection_options:
  puresnmp:
    extras:
      version: v3
      community: ""  # must be empty for SNMPv3
      username: myuser
      auth_protocol: SHA
      auth_password: "{{ env.get('SNMP_AUTH') }}"
      priv_protocol: AES
      priv_password: "{{ env.get('SNMP_PRIV') }}"
```

!!! warning
    Community strings and SNMPv3 credentials should come from
    environment-backed or protected inventory, not committed production files.

## Using Host Filters

All SNMP tasks accept the common Nornir host filter arguments (`FC`, `FL`,
`FB`, `FG`, `FR`, `FM`, `FX`, `FN`, etc.) to control which devices are
targeted.

!!! example

    === "CLI"
    
        ```
		nf[nornir-snmp]#get oid 1.3.6.1.2.1.1.5.0 FC spine
		nf[nornir-snmp]#get oid 1.3.6.1.2.1.1.5.0 FL ceos-spine-1 ceos-leaf-1
		nf[nornir-snmp]#walk oid 1.3.6.1.2.1.1 FG eos_params
        ```

    === "Python"
    
        ```
        import pprint
        
        from norfab.core.nfapi import NorFab
        
        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            
            client = nf.make_client()
            
            # Filter by host name containment
            res = client.run_job(
                service="nornir",
                task="snmp_get",
                kwargs={"oid": "1.3.6.1.2.1.1.5.0", "FC": "spine"}
            )
            pprint.pprint(res)
            
            # Filter by explicit host list
            res = client.run_job(
                service="nornir",
                task="snmp_walk",
                kwargs={
                    "oid": "1.3.6.1.2.1.2.2",
                    "FL": ["ceos-leaf-1", "ceos-leaf-2"]
                }
            )
            pprint.pprint(res)
            
            nf.destroy()
        ```

When no hosts match the provided filters, the task returns `status="no_match"`
without failure.

## Using Processors

SNMP tasks support Nornir-Salt processors such as `dp` (DataProcessor),
`tests` (TestsProcessor), `diff` (DiffProcessor), and `tf` (ToFileProcessor).

```python
# Apply JMESPath expression to filter walk results
client.run_job("nornir", "snmp_walk", kwargs={
    "oid": "1.3.6.1.2.1.2.2",
    "dp": [{"fun": "jmespath", "expr": "walk"}],
})
```

## Troubleshooting

### SNMP timeout

Verify UDP port mapping and that the SNMP agent is running on the device:

```bash
snmpget -v2c -c norfab 192.168.1.130:11610 1.3.6.1.2.1.1.5.0
```

### Community mismatch

Ensure the community configured in the Nornir inventory matches the
community configured on the device.

### No reply / no devices matched

Verify the `puresnmp.port` is correct. When using containerlab, ensure the
UDP port mapping in the topology file publishes the correct port.

### Write operation fails

SNMP writes require a read-write community. The isolated test lab uses
`norfab rw`. Production environments should use least-privilege access.

## NORFAB Nornir SNMP Shell Reference

The NorFab shell provides a comprehensive set of commands for the Nornir
SNMP tasks, allowing you to perform various SNMP read and write operations.
These commands include options for setting job timeouts, specifying connection
parameters, applying host filters, and controlling the execution of SNMP
operations.

```
nf#man tree nornir.snmp

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── snmp:    Interact with devices using SNMP
        ├── get:    Perform an SNMP GET operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   └── oid (R):    Numeric OID to retrieve via SNMP GET, examples: 1.3.6.1.2.1.1.5.0
        ├── get-next:    Perform an SNMP GETNEXT operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   └── oid (R):    Numeric OID from which to retrieve the next OID via SNMP GETNEXT, examples: 1.3.6.1.2.1.1.5.0
        ├── multi-get:    Perform an SNMP MULTIGET operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   └── oids (R):    List of numeric OIDs to retrieve via SNMP MULTIGET
        ├── walk:    Perform an SNMP WALK operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   ├── oid (R):    Numeric OID at which to start the SNMP WALK, examples: 1.3.6.1.2.1.1
        │   └── errors:    Error handling mode: ``strict`` raises on error, ``warn`` continues, default 'SnmpErrors.strict'
        ├── multi-walk:    Perform an SNMP MULTIWALK operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   └── oids (R):    List of numeric OIDs at which to start each SNMP MULTIWALK
        ├── bulk-get:    Perform an SNMP BULKGET operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   ├── repeating_oids (R):    List of numeric OIDs for repeating (column) retrieval via SNMP BULKGET
        │   ├── scalar-oids:    Optional list of numeric OIDs for scalar retrieval
        │   └── max-list-size:    Maximum number of OIDs per GETBULK request, default '10'
        ├── bulk-walk:    Perform an SNMP BULKWALK operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   ├── oids (R):    List of numeric OIDs at which to start each SNMP BULKWALK
        │   └── bulk-size:    Maximum number of OIDs per GETBULK request, default '10'
        ├── table:    Perform an SNMP TABLE operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   └── oid (R):    Numeric OID at the root of the SNMP TABLE to retrieve, examples: 1.3.6.1.2.1.2.2
        ├── bulk-table:    Perform an SNMP BULKTABLE operation on network devices using GETBULK
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FR:    Filter hosts by name using regular expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   ├── oid (R):    Numeric OID at the root of the SNMP BULKTABLE to retrieve using GETBULK, examples: 1.3.6.1.2.1.2.2
        │   └── bulk-size:    Maximum number of OIDs per GETBULK request, default '10'
        ├── set:    Perform an SNMP SET operation on network devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── FO:    Filter hosts using a Nornir-Salt Filter Object
        │   ├── FB:    Filter hosts by name using glob patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts by name containment pattern
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Exclude hosts by name
        │   ├── FN:    Negate the host filter match
        │   ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
        │   ├── add-details:    Add Nornir task execution details to results, default 'False'
        │   ├── progress:    Emit progress events during task execution, default 'True'
        │   ├── num-workers:    RetryRunner number of threads for task execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run each task
        │   ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
        │   ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
        │   ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
        │   ├── creds-retry:    RetryRunner connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results on the worker
        │   ├── tf-skip-failed:    Skip failed task results when saving to file
        │   ├── diff:    File group name to diff task results against
        │   ├── diff-last:    Previous saved file version to diff against
        │   ├── dp:    Nornir-Salt DataProcessor pipeline definition
        │   ├── xml-flake:    XML flake pattern for DataProcessor
        │   ├── match:    Pattern to match in task output
        │   ├── before:    Number of lines before a match to include, default '0'
        │   ├── run-ttp:    TTP template to run with DataProcessor
        │   ├── ttp-structure:    TTP result structure for DataProcessor, default 'flat_list'
        │   ├── remove-tasks:    Remove task output when processors produce final results, default 'True'
        │   ├── tests:    Nornir-Salt TestsProcessor tests definition
        │   ├── subset:    Test subset name or glob pattern to execute
        │   ├── failed-only:    Return failed test results only, default 'False'
        │   ├── groups:    Test group names to execute
        │   ├── xpath:    XPath expression to run with DataProcessor
        │   ├── jmespath:    JMESPath expression to run with DataProcessor
        │   ├── iplkp:    IP lookup mode for DataProcessor
        │   ├── ntfsm:    Parse output with NTC TextFSM templates
        │   ├── oid (R):    Numeric OID to write via SNMP SET, examples: 1.3.6.1.2.1.1.6.0
        │   └── value (R):    String value to write at the OID, examples: Brisbane lab
        └── multi-set:    Perform an SNMP MULTISET operation on network devices
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
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
            └── mappings (R):    JSON object mapping numeric OIDs to values for SNMP MULTISET, examples: {"1.3.6.1.2.1.1.6.0": "Brisbane lab"}
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_get
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_getnext
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_multiget
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_walk
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_multiwalk
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_bulkget
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_bulkwalk
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_table
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_bulktable
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_set
::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_multiset