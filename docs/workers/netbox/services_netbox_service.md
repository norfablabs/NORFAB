---
tags:
  - NetBox
---

# NetBox Service

The NetBox service integrates NorFab with [NetBox](https://github.com/netbox-community/netbox), an open-source tool for documenting networks. This integration helps network engineers and administrators manage and automate infrastructure using the data stored in NetBox.

![Nornir Service Architecture](../../images/Netbox_Service.jpg)

## Overview

NetBox is a comprehensive network documentation and management tool that includes IP address management (IPAM), data center infrastructure management (DCIM), and more. By integrating NetBox with NorFab, you can use detailed source-of-truth data to automate network tasks and keep operations consistent.

## NetBox Compatibility

NorFab supports these versions of NetBox:

1. NetBox 3.6.x
2. NetBox 4.0.x and 4.1.x
3. NetBox 4.2.x starting with NorFab 0.8.0

## NorFab NetBox Service Key Features

### Multi-Instance Support

Each NorFab NetBox worker can work with multiple NetBox instances. This makes it practical to automate tasks across large environments with multiple data centers or network segments.

### Device and Interface Management

The NetBox service can retrieve and manage detailed information about network devices and interfaces, including configuration contexts, interface status, and IP addresses. This helps keep network state accurate and up to date.

### GraphQL and REST API Integration

The NetBox service uses the REST and GraphQL APIs provided by NetBox to run complex queries and retrieve specific data sets. You can use this data for inventory updates, configuration audits, and compliance checks.

### Customizable Filters and Queries

You can define custom filters and queries to retrieve specific data from NetBox. This lets you tailor each request to the information required by your automation task.

### Caching and Performance Optimization

The NetBox service includes caching mechanisms to improve performance and reduce load on NetBox instances. Caching frequently accessed data can make automation workflows faster and more efficient.

## Use Cases

### Automated Inventory Management

By integrating NetBox with NorFab, you can automate network inventory updates and maintenance. This keeps inventory data accurate and reduces the risk of configuration errors.

### Configuration, Compliance and Auditing

The NetBox service can automate configuration compliance checks and audits through integrations with services such as Nornir. By comparing NetBox inventory data with live network state, you can identify and remediate drift quickly.

## Getting Started

To get started with the NetBox service, configure your NetBox instances and define the required connection parameters in your NorFab inventory. See [NetBox Inventory](services_netbox_service_inventory.md) for setup details.

## Conclusion

The NetBox service connects NorFab automation with NetBox source-of-truth data. Use it to improve network management workflows, accuracy, and consistency across operations.
