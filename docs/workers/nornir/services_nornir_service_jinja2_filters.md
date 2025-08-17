---
tags:
  - nornir
---

# Nornir Service Jinja2 Templates Filters

Below listed additional Jinja2 filters that supported by Nornir service for templates rendering by all service tasks such as ``cfg``, ``cli``, ``tests`` etc.

## network_hosts

Returns a list of hosts for given network.

Arguments:

- ``pfxlen`` - boolean, default is True, if False skips prefix length for IP addresses 

Example:

``` jinja2
{{ '192.168.1.0/30' | network_hosts }}

{{ '192.168.2.0/30' | network_hosts(pfxlen=False) }}
```

Returns:

``` python
["192.168.1.1/30", "192.168.1.2/30"]

["192.168.2.1", "192.168.2.2"]
```

## nb_create_ip

This Jinja2 filter queries Netbox to get existing or create next available IP in prefix.

`nb_create_ip` can be invoked using Jinja2 filter syntax where value it is applied against must be 
a prefix recorded in Netbox:

```
{% for interface in host.interfaces %}
interface {{ interface }}
  ip address {{ "10.0.0.0/24" | nb_create_ip(host.name, interface) }}
!
{% endfor %}
```

Alternatively, `nb_create_ip` can be called within `set` block to assign result to a variable:

```
{% for interface in host.interfaces %}
{% set ip = nb_create_ip("10.0.0.0/24", host.name, interface, description="Primary interface ip") %}
interface {{ interface }}
  ip address {{ ip }}
!
{% endfor %}
```

All the same arguments supported by [Netbox service create_ip](../netbox/services_netbox_service_tasks_create_ip.md) task can be passed onto `nb_create_ip` call:

::: norfab.workers.netbox_worker.NetboxWorker.create_ip

## nb_create_prefix

This Jinja2 filter queries Netbox to get existing or create next available prefix within parent prefix. The intention is to use `nb_create_prefix` together with `nb_create_ip` function to automate the process of IP addressing devices interfaces and Netbox updates.

`nb_create_prefix` can be invoked using Jinja2 filter syntax where value it is applied against must be 
a parent prefix recorded in Netbox:

```
{% for interface in host.interfaces %}
{% set subnet_description = host.name + ":" + interface  + ":ptp" %}
interface {{ interface }}
  ip address {{ "10.0.0.0/24" | nb_create_prefix(subnet_description) | nb_create_ip(host.name, interface) }}
!
{% endfor %}
```

above Jinja2 template will first invoke `nb_create_prefix` to allocate next available `/30` subnet in 10.0.0.0/24 prefix with `nb_create_ip` subsequently allocating next available IP address within newely allocated `/30` subnet.

Alternatively, `nb_create_prefix` can be called within `set` block to assign result to a variable:

```
{% for interface in host.interfaces %}
{% set subnet_description = host.name + ":" + interface  + ":ptp" %}
{% set subnet = nb_create_prefix(parent="10.0.0.0/24", description=subnet_description, prefixlen=30) %}
{% set ip = nb_create_ip(subnet, host.name, interface, description="Primary interface ip") %}
interface {{ interface }}
  ip address {{ ip }}
!
{% endfor %}
```

All the same arguments supported by [Netbox service create_prefix](../netbox/services_netbox_service_tasks_create_prefix.md) task can be passed onto `nb_create_prefix` call:

::: norfab.workers.netbox_worker.NetboxWorker.create_prefix