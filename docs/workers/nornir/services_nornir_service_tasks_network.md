---
tags:
  - nornir
---

# Nornir Service Network Task

> task api name: `network`

The Nornir Service Network Task is a component of NorFab's Nornir service designed to facilitate various network-related operations. This task suite provides network professionals with essential tools for managing, troubleshooting, and monitoring network infrastructure. By leveraging the capabilities of the Nornir service, users can perform critical network functions such as ICMP echo requests (ping) and DNS resolution checks, ensuring the reliability and performance of their network devices and services.

Key features of the Nornir Service Network Task include:

- **Network Ping**: This task allows you to perform ICMP echo requests to verify the reachability of network devices. 

- **DNS Testing**: This task enables you to perform DNS resolution checks to ensure that domain names are correctly mapped to their respective IP addresses. 

The document also includes a reference for the NorFab shell commands related to the Nornir `network` task, detailing the available options and parameters. These commands provide granular control over the execution of network tasks, enabling users to tailor the behavior of the tasks to meet specific network management needs.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `fun` | Yes | Network utility function to run. Supported values include `ping` and `dns`. |
| `workers` | No | Nornir workers to target. Defaults to all workers. |
| `use_host_name` | No | Use the Nornir host name instead of the host hostname value. |
| `count` | No | Number of ICMP echo requests for `ping`. |
| `ping_timeout` | No | Timeout for each ping reply. |
| `size`, `interval`, `payload`, `sweep_start`, `sweep_end`, `df`, `match`, `source` | No | Additional ping options. |
| `servers` | No | DNS servers to use for `dns`. |
| `dns_timeout` | No | DNS query timeout. |
| `ipv4`, `ipv6` | No | Resolve A or AAAA records for `dns`. |
| `FC`, `FB`, `FH`, `FL`, `FM`, `FG`, `FR`, `FO`, `FP`, `FX`, `FN`, `hosts` | No | Host filters. |

## Output

The task returns per-host results for the selected utility function. Ping results include reachability statistics. DNS results include resolved addresses or lookup errors.

## Examples

!!! example

    === "CLI"

        Ping devices whose hostnames contain `spine`:

        ```bash
        nf# nornir network ping FC spine count 3
        ```

        Resolve DNS names using selected DNS servers:

        ```bash
        nf# nornir network dns FC spine servers 8.8.8.8 1.1.1.1 ipv4
        ```

    === "Python"

        Context manager - ping selected devices:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        with NorFab(inventory="inventory.yaml") as nf:
            client = nf.make_client()

            result = client.run_job(
                service="nornir",
                task="network",
                kwargs={
                    "fun": "ping",
                    "FC": "spine",
                    "count": 3,
                    "ping_timeout": 2,
                },
            )

            pprint.pprint(result)
        ```

        Direct lifecycle - run DNS checks:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="inventory.yaml")
        try:
            nf.start()
            client = nf.make_client()

            result = client.run_job(
                service="nornir",
                task="network",
                kwargs={
                    "fun": "dns",
                    "FC": "spine",
                    "servers": ["8.8.8.8", "1.1.1.1"],
                    "ipv4": True,
                },
            )

            pprint.pprint(result)
        finally:
            nf.destroy()
        ```

## Network Ping

The Network Ping task in NorFab's Nornir service allows you to perform ICMP echo requests (pings) to verify the reachability of network devices. This task is essential for network troubleshooting and monitoring, as it helps you determine if a device is online and responsive. The ping task can be customized with various parameters such as timeout, number of retries, payload size and others. By using the ping task, you can quickly identify connectivity issues and ensure that your network devices are functioning correctly.

## DNS Testing

The DNS Testing task in NorFab's Nornir service enables you to perform DNS resolution checks to verify that domain names are correctly mapped to their respective IP addresses. This task is crucial for ensuring that your DNS infrastructure is working as expected and that your network services are accessible via their domain names. The DNS testing task can be configured with different parameters to control the behavior of the DNS queries, such as specifying the DNS server to use, query timeout, and the type of DNS record to query. By performing DNS tests, you can proactively identify and resolve DNS-related issues, ensuring seamless network operations.

## NORFAB Nornir Network Shell Reference

NorFab shell supports these command options for Nornir `network` task:

```bash
nf# man tree nornir.network
root
└── nornir:    Nornir service
    └── network:    Network utility functions - ping, dns etc.
        ├── ping:    Ping devices
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── add-details:    Add task details to results, default 'False'
        │   ├── num-workers:    RetryRunner number of threads for tasks execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run task
        │   ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
        │   ├── connect-check:    RetryRunner test TCP connection before opening actual connection
        │   ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        │   ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results to on worker file system
        │   ├── tf-skip-failed:    Save results to file for failed tasks
        │   ├── diff:    File group name to run the diff for
        │   ├── diff-last:    File version number to diff, default is 1 (last)
        │   ├── progress:    Display progress events, default 'True'
        │   ├── table:    Table format (brief, terse, extend) or parameters or True
        │   ├── headers:    Table headers
        │   ├── headers-exclude:    Table headers to exclude
        │   ├── sortby:    Table header column to sort by
        │   ├── reverse:    Table reverse the sort by order
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Filter hosts excluding them by name
        │   ├── FN:    Negate the match
        │   ├── hosts:    Filter hosts to target
        │   ├── use-host-name:    Ping host's name instead of host's hostname
        │   ├── count:    Number of pings to run
        │   ├── ping-timeout:    Time in seconds before considering each non-arrived reply permanently lost
        │   ├── size:    Size of the entire packet to send
        │   ├── interval:    Interval to wait between pings
        │   ├── payload:    Payload content if size is not set
        │   ├── sweep-start:    If size is not set, initial size in a sweep of sizes
        │   ├── sweep-end:    If size is not set, final size in a sweep of sizes
        │   ├── df:    Don't Fragment flag value for IP Header
        │   ├── match:    Do payload matching between request and reply
        │   └── source:    Source IP address
        └── dns:    Resolve DNS
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            ├── add-details:    Add task details to results, default 'False'
            ├── num-workers:    RetryRunner number of threads for tasks execution
            ├── num-connectors:    RetryRunner number of threads for device connections
            ├── connect-retry:    RetryRunner number of connection attempts
            ├── task-retry:    RetryRunner number of attempts to run task
            ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
            ├── connect-check:    RetryRunner test TCP connection before opening actual connection
            ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
            ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
            ├── tf:    File group name to save task results to on worker file system
            ├── tf-skip-failed:    Save results to file for failed tasks
            ├── diff:    File group name to run the diff for
            ├── progress:    Display progress events, default 'True'
            ├── table:    Table format (brief, terse, extend) or parameters or True
            ├── headers:    Table headers
            ├── headers-exclude:    Table headers to exclude
            ├── sortby:    Table header column to sort by
            ├── reverse:    Table reverse the sort by order
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
            ├── use-host-name:    Ping host's name instead of host's hostname
            ├── servers:    List of DNS servers to use
            ├── dns-timeout:    Time in seconds before considering request lost
            ├── ipv4:    Resolve 'A' record
            └── ipv6:    Resolve 'AAAA' record
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.network
