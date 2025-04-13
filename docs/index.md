> **Through lifting others we rise** :rocket:

---

# Network Automations Fabric (NorFab)

Welcome to NorFab, a platform designed to simplify and enhance network automation. 

---

## Why NorFab? :book:

Without automation, network engineers face a relentless cycle of manual configurations and troubleshooting. Hours are spent accessing devices, patching systems, and resolving outages. This repetitive work stifles innovation and leads to burnout.

NorFab changes this by introducing a framework that empowers engineers with automation capabilities, freeing them from mundane tasks and enabling them to focus on innovation.

---

## What is NorFab? :bulb:

NorFab is a task execution framework built for network automation. It bridges the gap between heavyweight platforms requiring dedicated infrastructure and lightweight scripts run locally. NorFab is:

- **Flexible**: Run it on a laptop, server, container, or in the cloud—centralized or distributed.
- **Feature-Rich**: Lightweight yet powerful, capable of handling diverse use cases without excessive costs or complexity.
- **Empowering**: Designed to unlock engineers' potential by automating modern network management.

---

## How NorFab Works :gear:

- **Run Anywhere**: Operates on Windows, macOS, Linux, containers, VMs, or in the cloud—centralized or distributed.
- **Extend Anything**: Built with extensibility at its core, allowing you to adapt it to your needs.
- **Integrate Everything**: Offers Python API, REST API, and CLI interfaces for seamless integration.
- **Manage Anything**: Use built-in services or create your own to manage network infrastructure.
- **Model and Data-Driven**: Leverages Pydantic models for API validation and documentation.
- **Automate Anything**: From simple tasks to complex workflows, NorFab is built to handle it all.

---

## Architecture

NorFab's architecture consists of the following key components:

- **Clients**: Processes running on client machines that connect to the broker to consume services.
- **Broker**: Acts as the central hub, providing access to services for clients.
- **Services**: Collections of workers managing specific resources.
- **Workers**: Processes that act as resource proxies, running anywhere to form services.
- **Resources**: Entities managed by workers, such as network devices, databases, or file systems.

### How It Works:
1. Clients submit jobs to the broker.
2. The broker distributes jobs to workers within the relevant service.
3. Workers execute the jobs and return results to the clients.

In essence, *Services* are hosted by *Workers* and accessed by *Clients* via the *Broker*.

![Network Automations Fabric Architecture](images/Overview_Architecture.jpg)

---

## Next Steps

Continue to [getting started tutorial](norfab_getting_started.md) or read [why to use NorFab](norfab_why_use_norfab.md)

For more information or to schedule a demo, [contact us](mailto:dmulyalin@gmail.com).