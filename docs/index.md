> **Through lifting others we rise** :rocket:

---

# Network Automations Fabric (NorFab)

NorFab is the platform that unifies, simplifies, and accelerates network automation. Designed for engineers who want to move fast and deliver results, NorFab eliminates the friction of integrating disparate tools and empowers you to automate with confidence.

---

## Why NorFab? :star:

Network automation is essential, but the landscape is fragmented. Too many tools, too much glue code, and not enough time. NorFab solves this by providing a cohesive automation fabric—integrating best-in-class tools, delivering ready-to-use solutions, and letting you focus on outcomes, not plumbing.

- **No more glue code:** Integrate tools and workflows seamlessly.
- **Accelerate delivery:** Use batteries-included, use-case-driven implementations.
- **Future-proof:** Adapt and scale as your network evolves.

---

## What is NorFab? :bulb:

NorFab is a distributed task automation and orchestration framework built for real-world network operations.

- **Run Anywhere:** Laptop, server, container, or cloud—centralized or distributed.
- **Feature-Rich:** Lightweight, powerful, and cost-effective.
- **Empowering:** Unlock your potential to automate and manage modern networks.
- **Integrate Everything:** Python API, REST API, and CLI for seamless integration.
- **Model-Driven:** Pydantic models ensure robust validation and documentation.
- **Automate Anything:** From simple tasks to complex workflows—NorFab handles it all.

---

## How NorFab Works :gear:

- **Universal Deployment:** Windows, macOS, Linux, containers, VMs, on-prem or cloud.
- **Extensible Core:** Adapt NorFab to your needs with pluggable services and APIs.
- **Unified Management:** Use built-in or custom services to manage any network resource.
- **Data-Driven:** Structured models and inventory for reliable automation.
- **Seamless Integration:** Connect NorFab to your existing ecosystem with minimal effort.

---

## Architecture Overview

NorFab’s architecture is designed for flexibility, scalability, and reliability:

- **Clients:** Submit jobs and consume services.
- **Broker:** Central hub that routes jobs and manages services.
- **Services:** Logical groupings of workers managing specific resources.
- **Workers:** Resource proxies that execute tasks anywhere.
- **Resources:** Devices, databases, filesystems—anything you need to manage.

**Workflow:**
1. Clients submit jobs to the broker.
2. Broker distributes jobs to the appropriate service workers.
3. Workers execute tasks and return results.

*Services are hosted by Workers and accessed by Clients via the Broker.*

![Network Automations Fabric Architecture](images/Overview_Architecture.jpg)

---

## Get Started

- Jump into the [Getting Started Tutorial](norfab_getting_started.md)
- Discover [Why NorFab is Different](norfab_why_use_norfab.md)

Ready to transform your network automation? [Contact us](mailto:dmulyalin@gmail.com) for more information or a demo.