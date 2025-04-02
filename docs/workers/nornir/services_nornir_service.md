---
tags:
  - nornir
---

# Nornir Service

Nornir Service is based on [Nornir](https://github.com/nornir-automation/nornir)
library - a well adopted open-source tool for automating network devices operations.
 
![Nornir Service Architecture](../../images/Nornir_Service.jpg) 

With each Nornir worker capable of handling multiple devices simultaneously, 
Nornir Service offers high scalability, allowing efficient management of 
large device fleets. By optimizing compute resources such as CPU, RAM, and 
storage, it delivers cost-effective performance.

Additionally, Nornir Service supports various interfaces and libraries for 
seamless integration. For instance, the `cli` task can interact with devices 
via the SSH Command Line Interface (CLI) using popular libraries like Netmiko, 
Scrapli or NAPALM, providing flexibility for diverse network environments.

## Nornir Service Tasks

Nornir Service supports a number of tasks to interact with network devices using 
some of the most popular open source libraries such as Netmiko, NAPALM, Scrapli, 
Ncclient, Scrapli NETCONF, pygnmi, puresnmp, TextFSM, TTP etc.

| Task          | Description  | Use Cases |
|---------------|--------------|-----------|
| **[task](services_nornir_service_tasks_task.md)** | Run Nornir custom tasks | Pure Python per device workflows, do anything you want, it is pure python |
| **[cli](services_nornir_service_tasks_cli.md)** | Executes CLI commands on network devices using libraries like Netmiko, Scrapli or NAPALM. | Device diagnostics, retrieving device information. |
| **[cfg](services_nornir_service_tasks_cfg.md)** | Manages device configurations, including pushing configurations. | Automated configuration management. |
| **[test](services_nornir_service_tasks_test.md)** | Run test suites against network devices. | Network testing, troubleshooting, device compliance, configuration verification. |
| **[network](services_nornir_service_tasks_network.md)** | A collection of network utilities such as ping and DNS. | Check device connectivity, verify and resolve DNS records. |
| **[parse](services_nornir_service_tasks_parse.md)** | Parses command outputs using TextFSM, NAPALM getters or TTP to extract structured data. | Data extraction from CLI outputs, automated report generation, configuration validation. |
| **[diagram](services_nornir_service_tasks_diagram.md)** | Produce Network L2,  L3, OSPF or ISIS routing diagrams in DrawIO or yED formats. | Automated network documentation, network validation. |
| **[file_copy](services_nornir_service_tasks_file_copy.md)** | Copy files to network devices over SCP. | Device software upgrades, certificates or license renewal. |
| **[runtime_inventory](services_nornir_service_tasks_runtime_inventory.md)** | Modify Nornir service runtime inventory. | Add, update or remove Nornir hosts at a runtime. |

## Nornir Service Shell Show Commands

Nornir service shell comes with this set of show commands to query various information:

```
nf#man tree show.nornir
root
└── show:    NorFab show commands
    └── nornir:    Show Nornir service
        ├── inventory:    show Nornir inventory data
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
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
        │   └── hosts:    Filter hosts to target
        ├── hosts:    show Nornir hosts
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
        │   ├── workers:    Filter worker to target, default 'all'
        │   └── details:    show hosts details
        ├── version:    show Nornir service version report
        ├── watchdog:    show Nornir service version report
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FN:    Negate the match
        │   ├── hosts:    Filter hosts to target
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── statistics:    show Nornir watchdog statistics
        │   ├── configuration:    show Nornir watchdog configuration
        │   └── connections:    show Nornir watchdog connections monitoring data
        └── jobs:    Show Nornir Jobs
            ├── summary:    List jobs
            │   ├── timeout:    Job timeout
            │   ├── workers:    Workers to return jobs for, default 'all'
            │   ├── last:    Return last N completed and last N pending jobs
            │   ├── pending:    Return pending jobs, default 'True'
            │   ├── completed:    Return completed jobs, default 'True'
            │   ├── client:    Client name to return jobs for
            │   ├── uuid:    Job UUID to return
            │   └── task:    Task name to return jobs for
            └── details:    Show job details
                ├── timeout:    Job timeout
                ├── workers:    Workers to return jobs for, default 'all'
                ├── *uuid:    Job UUID
                ├── data:    Return job data received from client, default 'True'
                ├── result:    Return job result, default 'True'
                └── events:    Return job events, default 'True'
nf# 
```