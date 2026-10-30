# ACME North Quay distribution centre: network low-level design

ACME Logistics is opening a distribution centre with warehouse scanners, packing
stations and a small operations office. This fictional design records the branch
routing, access switching, management addressing and rack support equipment in
Netbox. Names and address space are lab values; the site remains `NORFAB ACME TEST`
so the design can be exercised without using a production inventory.

The branch has two edge routers, two aggregation switches and three access
switches. Each router connects to both aggregation switches; each access switch
has an uplink to each aggregation switch. A terminal server and remotely managed
PDU support recovery when normal network access is unavailable.

## Physical topology

The diagram summarises connectivity. The interface definitions and cable records
below provide the port-level detail; `R1`, `A1` and `S1` abbreviate the corresponding
`acme-branch-rtr-1`, `acme-branch-agg-1` and `acme-branch-access-1` names.

```text
                       Upstream network
                              |
                    +---------+---------+
                    |                   |
                +---+---+           +---+---+
                |  R1   |           |  R2   |
                +---+---+           +---+---+
                    | \               / |
                    |  \             /  |
                    |   \           /   |
                    |    \         /    |
                    |     \       /     |
                    |      \     /      |
                    |       \   /       |
                    |        \ /        |
                +---+---+     X     +---+---+
                |  A1   +-----------+  A2   |
                +---+---+           +---+---+
                    |                   |
                    +-- dual uplinks ---+
                         to each switch
                       /      |      \
                   +--+--+ +--+--+ +--+--+
                   | S1  | | S2  | | S3  |
                   +-----+ +-----+ +-----+

         Terminal server: console recovery for network equipment
         Managed PDU:     remote power control for rack equipment
```

The crossed router links are independent cables, not a shared junction. Physical
redundancy alone does not establish convergence time or application availability;
those depend on the device configuration and acceptance testing.

## Deployment boundary

This document models inventory and relationships in Netbox. It does not push
switch or router configuration. Preview it with `design_deploy` and `dry_run_render=True`, review
the returned source and context, then use `design_deploy` for a preview or approved
Netbox update. The deployment input schema is deliberately kept at the end.

## Site parameters and reference schedules

The site identifier and parent allocation pool are deployment parameters. The
VLAN schedule records intended service separation: user access is enabled for
this phase, while management VLAN 200 is reserved for a later phase. It does not
create VLAN 200. The authoritative deployed VLAN and interface records appear
below; these reference schedules do not generate additional objects.

YAML keeps numeric and boolean types. CSV and Markdown table cells remain strings.
All reference fields are accepted by the input schema at the end.

```yaml context.site
NORFAB ACME TEST
```

```yaml context.parent_prefix
"198.19.224.0/20"
```

### Service VLAN schedule (YAML)

```yaml context.vlans
- name: USERS
  vid: 100
  enabled: true
- name: MANAGEMENT
  vid: 200
  enabled: false
```

### Edge link annotation schedule (CSV)

```csv context.links
port,description
Ethernet1,"uplink, primary"
Ethernet2,backup uplink
```

### Site VLAN assignments (Markdown)

This schedule maps the branch site to its planned VLANs. Conversion returns a
list of dictionaries. VIDs remain strings, just like CSV cells.

<!-- context.site_vlans -->

| site | name | vid | status |
| --- | --- | --- | --- |
| NORFAB ACME TEST | USERS | 100 | active |
| NORFAB ACME TEST | MANAGEMENT | 200 | planned |

## Review notes and excluded examples

The following scratch examples are retained for the design review. They are
unmarked, do not form part of the deployment, and intentionally include an
unfinished template expression to check that reference material is ignored:

```yaml
unknown_reference_only:
  - name: DO NOT DEPLOY
    description: "{{ ignored Jinja"
```

```json
{"context.site": "THIS IS NOT CONTEXT"}
```

| Device | Purpose |
| --- | --- |
| R1 | Edge router; see its authoritative device definition below |

## Shared deployment functions

The site description follows ACME naming conventions. Device-local context and
an allocated route target are provided by the referenced functions during the
later deployment workflow. Conversion preserves these URLs without downloading
or executing their contents.

```yaml design
jinja_functions:
  acme_site_description: nf://netbox/designs/acme_site_description.py
custom_functions:
  calculate_acme_device_context: nf://netbox/designs/calculate_acme_device_context.py
  allocate_bgp_route_target: nf://netbox/designs/allocate_bgp_route_target.py
# Version 1 of the task-oriented NetBox design DSL.
#
# Every top-level collection is a list of object records, equivalent to CSV rows.
# Record fields map directly to the corresponding NetBox worker task arguments.
# Device-owned objects use dictionaries where the key supplies the child name.

```

## Inventory ownership and hardware standards

All branch objects belong to the ACME tenant. The region, manufacturer and
platform establish shared references used by the hardware definitions below.

```yaml design
tenants:
  - name: ACME
    description: ACME branch network design

regions:
  - name: ACME REGION

manufacturers:
  - name: ACME NETWORKS

platforms:
  - name: ACME OS
    manufacturer: ACME NETWORKS

```

## Device roles

Roles separate edge, aggregation, access and recovery equipment for inventory filtering and operational ownership.

```yaml design
device_roles:
  - name: ACME ROUTER
    color: f44336
  - name: ACME AGGREGATION SWITCH
    color: ff9800
  - name: ACME ACCESS SWITCH
    color: 4caf50
  - name: ACME TERMINAL SERVER
    color: 607d8b
  - name: ACME PDU
    color: 795548

```

## Device types

The fictional ACME hardware catalogue identifies each chassis model and its default software platform.

```yaml design
device_types:
  - model: ACME BRANCH ROUTER
    manufacturer: ACME NETWORKS
    default_platform: ACME OS
  - model: ACME AGG SWITCH
    manufacturer: ACME NETWORKS
    default_platform: ACME OS
  - model: ACME ACCESS SWITCH
    manufacturer: ACME NETWORKS
    default_platform: ACME OS
  - model: ACME TERMINAL SERVER
    manufacturer: ACME NETWORKS
  - model: ACME PDU
    manufacturer: ACME NETWORKS

```

## Sites

The site record groups this branch under ACME ownership and supplies the shared location reference.

```yaml design
sites:
  - name: "{{ context.site }}"
    description: |-
      {{ context.site | acme_site_description }}
    tenant: ACME
    region: ACME REGION
    status: active

```

## Config context

The baseline marks the branch as managed. It records automation context; it does not configure devices.

```yaml design
config_context:
  - name: ACME BRANCH BASELINE
    description: ACME site-wide configuration defaults
    is_active: true
    weight: 1000
    sites: ["{{ context.site }}"]
    data:
      acme:
        managed: true

```

## Addressing roles

LAN pools and loopback pools carry different roles so allocation requests can
select the intended pool. The upstream ASN role distinguishes provider-facing
records from the branch's internal ASNs.

```yaml design
roles:
  - name: ACME-BRANCH-LAN
    color: 4caf50
roles:
  - name: ACME-BRANCH-LOOPBACK
    color: 2196f3
```

```yaml design
roles:
  - name: ACME UPSTREAM ASN
    color: 9c27b0

```

## RIRs

Private ASN resources are tracked under the ACME private registry.

```yaml design
rirs:
  - name: ACME PRIVATE
    is_private: true

```

## ASN ranges

Reserve 4200650100 through 4200650109 for branch allocations. Allocation requests below select from this named range.

```yaml design
asn_ranges:
  - name: ACME BRANCH ALLOCATED ASNS
    rir: ACME PRIVATE
    start: 4200650100
    end: 4200650109

```

## ASNs

Explicit ASNs identify known peers; allocation wrappers request branch ASNs whose values are assigned during deployment.

```yaml design
asns:
  - asn: 4200650000
    tenant: ACME
    rir: ACME PRIVATE
    role: ACME UPSTREAM ASN
    sites: ["{{ context.site }}"]
    description: ACME external upstream ASN
  - asn: 4200650001
    tenant: ACME
    rir: ACME PRIVATE
    role: ACME-BRANCH-LAN
    sites: ["{{ context.site }}"]
    description: ACME core routers ASN
    custom_fields:
      norfab_acme_site: "{{ context.site }}"
      norfab_acme_sites: ["{{ context.site }}"]

  - asn: 4200650002
    tenant: ACME
    rir: ACME PRIVATE
    role: ACME-BRANCH-LAN
    sites: ["{{ context.site }}"]
    description: ACME aggregation ASN
  - asn: 4200650003
    tenant: ACME
    rir: ACME PRIVATE
    role: ACME-BRANCH-LAN
    sites: ["{{ context.site }}"]
    description: ACME access ASN
  - create_asn:
      asn_range: ACME BRANCH ALLOCATED ASNS
      description: ACME allocated branch ASN
      tenant: ACME
      role: ACME-BRANCH-LAN
      sites: ["{{ context.site }}"]
  - create_asn:
      asn_range: ACME BRANCH ALLOCATED ASNS
      description: ACME allocated aggregation ASN
      tenant: ACME
      role: ACME-BRANCH-LAN
      sites: ["{{ context.site }}"]

```

## BGP communities

The community record gives routing policy a named reference for branch traffic classification.

```yaml design
bgp_communities:
  - value: "4200650001:100"
    tenant: ACME
    description: ACME branch routes

```

## Routing policies

The export policy is registered for use by the peering definitions. Device-side policy enforcement belongs to configuration delivery.

```yaml design
routing_policies:
  - name: ACME EXPORT
    description: ACME branch export policy

```

## Peer groups

Group upstream peers under one operational label so sessions can be managed consistently.

```yaml design
peer_groups:
  - name: ACME UPSTREAM PEERS
    description: ACME external upstream sessions

```

## VLAN groups

Keep branch VLAN allocation within the site-scoped group and its reserved VID range.

```yaml design
vlan_groups:
  - name: "{{ context.site }} VLANS"
    description: ACME branch VLAN group
    site: "{{ context.site }}"
    vid_ranges:
      - [100, 199]

```

## VLANs

Request the next available guest VLAN from the branch group. The resulting VID must be read from allocation output rather than inferred from ordering.

```yaml design
vlans:
  - create_vlan:
      vlan_group: "{{ context.site }} VLANS"
      name: ACME GUEST
      tenant: ACME
      description: ACME Allocate the next available branch VLAN ID
      status: active

```

## Route targets

Record the known branch import target and allocate an additional target through the shared deployment function.

```yaml design
route_targets:
  - name: "4200650001:100"
    tenant: ACME
    description: ACME branch import target
  - custom_function: allocate_bgp_route_target
    tenant: ACME
    description: ACME allocated route target

```

## VRFs

The ACME BRANCH routing domain uses explicit route-target relationships. The associated VXLAN L2VPN uses identifier 10100 and records its VLAN and router attachment.

```yaml design
vrfs:
  - name: ACME BRANCH
    tenant: ACME
    rd: "4200650001:100"
    import_route_targets:
      - query:
          name: "4200650001:100"
    export_route_targets:
      - name: "4200650001:200"
        tenant: ACME
        description: ACME branch export target

l2vpns:
  - name: ACME BRANCH EVPN
    type: vxlan
    identifier: 10100
    tenant: ACME
    import_route_targets:
      - query:
          name: "4200650001:100"
    export_route_targets:
      - name: "4200650001:100"
    terminations:
      - group: "{{ context.site }} VLANS"
        name: ACME USERS
        tenant: ACME
        vid: 100
        status: active
        description: ACME branch user access
        role: ACME-BRANCH-LAN
        custom_fields:
          norfab_acme_site: "{{ context.site }}"
          norfab_acme_sites: ["{{ context.site }}"]
      - device: acme-branch-rtr-1
        interface: Ethernet2.100

```

## Prefixes

The parent pool supplies dynamically allocated user and loopback prefixes. Fixed management and transit subnets remain explicit; the example addresses are reserved for lab use.

```yaml design
prefixes:
  - prefix: "{{ context.parent_prefix }}"
    tenant: ACME
    description: "ACME {{ context.site }} allocation pool"
    status: active
  - prefix: 198.51.100.0/30
    tenant: ACME
    description: ACME upstream peering subnet
    status: active
  - prefix: 198.51.100.4/31
    tenant: ACME
    description: ACME aggregation interconnect subnet
    status: active
  - prefix: 192.0.2.0/24
    tenant: ACME
    description: ACME explicit management prefix
    status: active
    region: ACME REGION
    site: "{{ context.site }}"
    vlan: {group: "{{ context.site }} VLANS", vid: 100}
    custom_fields:
      norfab_acme_site: "{{ context.site }}"
      norfab_acme_sites: ["{{ context.site }}"]
  - prefix: 198.19.230.0/24
    vrf: ACME BRANCH
    tenant: ACME
    site: "{{ context.site }}"
    description: ACME tenant VRF subnet
  - create_prefix:
      tenant: ACME
      parent: "{{ context.parent_prefix }}"
      description: "ACME {{ context.site }} user prefix"
      prefixlen: 24
      site: "{{ context.site }}"
      role: ACME-BRANCH-LAN
      vlan: 100
      vlan_group: "{{ context.site }} VLANS"
      status: active
  - create_prefix:
      tenant: ACME
      parent: "{{ context.parent_prefix }}"
      description: "ACME {{ context.site }} loopback prefix"
      prefixlen: 24
      site: "{{ context.site }}"
      role: ACME-BRANCH-LOOPBACK
      status: active

```

## IP addresses

Record fixed management and transit addresses alongside allocation requests. Interface assignments and VRF references determine where each address belongs.

```yaml design
ip_addresses:
  - create_ip:
      prefix: 192.0.2.0/24
      tenant: ACME
      description: ACME allocated management VIP
      vrrp_group: ACME MANAGEMENT GATEWAY
  - address: 198.19.230.1/24
    vrf: ACME BRANCH
    tenant: ACME
    description: ACME tenant VRF gateway
  - address: 198.51.100.2/30
    tenant: ACME
    description: ACME Upstream BGP peer
    status: active
  - address: 192.0.2.20/32
    tenant: ACME
    description: ACME Reserved monitoring address
    status: reserved

# Query the two dedicated BGP loopback interfaces for an iBGP session.
# Loopback-based BGP requires underlay reachability; access eBGP also requires
# multihop configuration. This design models NetBox objects, not device config.
# Both session directions are explicit; create_reverse remains false.
```

## BGP peerings

Peering records describe the intended control-plane relationships. They do not establish live BGP sessions on the equipment.

```yaml design
bgp_peerings:
  - device: acme-branch-rtr-1
    local_ip_query: {device: acme-branch-rtr-1, interface: Loopback100}
    remote_ip_query: {device: acme-branch-rtr-2, interface: Loopback100}
    local_as_query: {description: ACME allocated branch ASN}
    remote_as_query: {description: ACME allocated branch ASN}
    peer_group:
      name: ACME LOOPBACK PEERS
      description: ACME same-tier loopback sessions
    status: active
    description: ACME same-tier iBGP
    create_reverse: false

```

## Device and interface schedules

Each equipment item is listed separately for review. Repeated `devices:` sections
form one deployment collection, preserving the order of the individual schedules.
Router subinterfaces, aggregation gateways, access uplinks and recovery ports are
recorded with their parent devices.

### Edge router R1

```yaml design
devices:
{% for copy in [1] %}
  - name: acme-branch-rtr-1
    # Requires the dcim.device custom field supplied by the test inventory.
    custom_fields:
      norfab_crud_test_text: ACME core router
      # These dedicated reference IPs and device custom fields are seeded by netbox_data.py.
      norfab_design_device_ip: "198.19.243.10/32"
      norfab_design_device_ips: ["198.19.243.10/32", "198.19.243.11/32"]
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 1"
          label: ACME-CONSOLE-acme-branch-rtr-1
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 1"
          label: ACME-POWER-acme-branch-rtr-1
    role: ACME ROUTER
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME BRANCH ROUTER
    platform: ACME OS
    status: active
    local_context_data:
      acme:
        profile: core-router
        managed: true

    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.101/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-rtr-1
            status: active
      Ethernet1:
        type: 1000base-t
        description: ACME Branch LAN gateway
        enabled: true
        mode: access
        untagged_vlan:
          group: "{{ context.site }} VLANS"
          vid: 100
        ip_addresses:
          - create_ip:
              tenant: ACME
              prefix:
                description: "ACME {{ context.site }} user prefix"
                site: "{{ context.site }}"
              description: acme-branch-rtr-1 Ethernet1
              status: active
              create_peer_ip: false

      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Core uplink to aggregation switch 1
        enabled: true
      Ethernet2.100:
        type: virtual
        parent: {device: acme-branch-rtr-1, name: Ethernet2}
        description: ACME core tagged subinterface
        enabled: true

      Ethernet3:
        type: 10gbase-x-sfpp
        description: ACME Core uplink to aggregation switch 2
        enabled: true

      Loopback0:
        type: virtual
        description: ACME Router loopback
        enabled: true
        ip_addresses:
          - create_ip:
              tenant: ACME
              prefix:
                description: "ACME {{ context.site }} loopback prefix"
                site: "{{ context.site }}"
              description: acme-branch-rtr-1 Loopback0
              status: active
              is_primary: true
              create_peer_ip: false

      Ethernet4:
        type: 1000base-t
        description: ACME Upstream BGP peering
        enabled: true
        ip_addresses:
          - address: 198.51.100.1/30
            tenant: ACME
            description: ACME interface address
            status: active

    bgp_peerings:
      - name: acme-branch-rtr-1-to-acme-branch-agg-1
        local_address: 192.0.2.101
        remote_address: 192.0.2.103
        # Resolve both ASNs allocated above without assuming their range positions.
        local_as_query: {description: ACME allocated branch ASN}
        remote_as_query: {description: ACME allocated aggregation ASN}
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-rtr-1-to-acme-branch-agg-2
        local_address: 192.0.2.101
        remote_address: 192.0.2.104
        local_as:
          create_asn:
            asn_range: ACME BRANCH ALLOCATED ASNS
            description: ACME allocated branch ASN
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-rtr-1-upstream
        # Ethernet4's /30 supplies both the local and peer addresses.
        local_interface: Ethernet4
        local_as: 4200650001
        remote_as_query: {site: "{{ context.site | lower | replace(' ', '-') }}", role: ACME UPSTREAM ASN}
        peer_group: ACME UPSTREAM PEERS
        import_policies:
          - name: ACME IMPORT
            description: ACME branch import policy
        export_policies:
          - name: ACME EXPORT
            description: ACME branch export policy
        status: active
        description: ACME branch upstream
        create_reverse: false
{% endfor %}
```

### Edge router R2

```yaml design
devices:
  - name: acme-branch-rtr-2
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 2"
          label: ACME-CONSOLE-acme-branch-rtr-2
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 2"
          label: ACME-POWER-acme-branch-rtr-2
    role: ACME ROUTER
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME BRANCH ROUTER
    platform: ACME OS
    status: active
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.102/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-rtr-2
            status: active
      Ethernet1:
        type: 1000base-t
        description: ACME Branch LAN gateway
        enabled: true
        mode: access
        untagged_vlan:
          group: "{{ context.site }} VLANS"
          vid: 100
        ip_addresses:
          - create_ip:
              tenant: ACME
              prefix:
                description: "ACME {{ context.site }} user prefix"
                site: "{{ context.site }}"
              description: acme-branch-rtr-2 Ethernet1
              status: active
              create_peer_ip: false
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Core uplink to aggregation switch 1
        enabled: true
      Ethernet3:
        type: 10gbase-x-sfpp
        description: ACME Core uplink to aggregation switch 2
        enabled: true
      Loopback0:
        type: virtual
        description: ACME Router loopback
        enabled: true
        ip_addresses:
          - create_ip:
              tenant: ACME
              prefix:
                description: "ACME {{ context.site }} loopback prefix"
                site: "{{ context.site }}"
              description: acme-branch-rtr-2 Loopback0
              status: active
              is_primary: true
              create_peer_ip: false

    bgp_peerings:
      - name: acme-branch-rtr-2-to-acme-branch-rtr-1
        local_address: 192.0.2.102
        remote_address: 192.0.2.101
        local_as: 4200650001
        remote_as: 4200650001
        status: active
        description: ACME same-tier iBGP
        create_reverse: false
      - name: acme-branch-rtr-2-to-acme-branch-agg-1
        local_address: 192.0.2.102
        remote_address: 192.0.2.103
        local_as: 4200650001
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-rtr-2-to-acme-branch-agg-2
        local_address: 192.0.2.102
        remote_address: 192.0.2.104
        local_as: 4200650001
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false

```

### Aggregation switch A1

```yaml design
devices:
  - name: acme-branch-agg-1
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 3"
          label: ACME-CONSOLE-acme-branch-agg-1
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 3"
          label: ACME-POWER-acme-branch-agg-1
    role: ACME AGGREGATION SWITCH
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME AGG SWITCH
    platform: ACME OS
    status: active
    local_context_data:
      custom_function: calculate_acme_device_context
      profile: aggregation
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.103/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-agg-1
            status: active
      Loopback0:
        type: virtual
        description: ACME Explicit management address
        ip_addresses:
          - address: 192.0.2.10/32
            tenant: ACME
            description: acme-branch-agg-1 Loopback0
            status: active
      Ethernet1:
        type: 10gbase-x-sfpp
        description: ACME Uplink to router 1
        enabled: true
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Uplink to router 2
        enabled: true
      Ethernet3:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 1
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-1
          interface: Ethernet1
          type: smf-os2
          status: connected
      Ethernet4:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 2
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-2
          interface: Ethernet1
          type: smf-os2
          status: connected
      Ethernet5:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 3
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-3
          interface: Ethernet1
          type: smf-os2
          status: connected
      Port-Channel1:
        type: lag
        description: ACME aggregation interconnect LAG
        ip_addresses:
          - address: 198.51.100.4/31
            tenant: ACME
            description: ACME aggregation 1 interconnect address
            status: active
        # Flattening supplies device and local_interface; the create task
        # derives both addresses and the session name from the interface.
        bgp_peerings:
          - local_as_query: {description: ACME allocated aggregation ASN}
            remote_as_query: {description: ACME allocated aggregation ASN}
            status: active
            description: ACME same-tier iBGP
            create_reverse: false
      Ethernet6:
        type: 10gbase-x-sfpp
        lag: {device: acme-branch-agg-1, name: Port-Channel1}
        description: ACME aggregation interconnect member 1
        connection:
          device: acme-branch-agg-2
          interface: Ethernet6
          type: smf-os2
          status: connected
      Ethernet7:
        type: 10gbase-x-sfpp
        lag: {device: acme-branch-agg-1, name: Port-Channel1}
        description: ACME aggregation interconnect member 2
        connection:
          device: acme-branch-agg-2
          interface: Ethernet7
          type: smf-os2
          status: connected
      Vlan100:
        type: virtual
        description: ACME aggregation user gateway
        mode: access
        untagged_vlan: {group: "{{ context.site }} VLANS", vid: 100}
        ip_addresses:
          - address: 192.0.2.21/24
            tenant: ACME
          - address: 192.0.2.23/24
            role: vip
            tenant: ACME
            description: ACME shared user VIP
        vrrp:
          group_id: 10
          name: ACME USER GATEWAY
          vip: 192.0.2.1/24
          priority: 200

    bgp_peerings:
      - name: acme-branch-agg-1-to-acme-branch-rtr-1
        local_address: 192.0.2.103
        remote_address: 192.0.2.101
        local_as: 4200650002
        remote_as: 4200650001
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-1-to-acme-branch-rtr-2
        local_address: 192.0.2.103
        remote_address: 192.0.2.102
        local_as: 4200650002
        remote_as: 4200650001
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-1-to-acme-branch-access-1
        local_address: 192.0.2.103
        remote_address: 192.0.2.105
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-1-to-acme-branch-access-2
        local_address: 192.0.2.103
        remote_address: 192.0.2.106
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-1-to-acme-branch-access-3
        local_address: 192.0.2.103
        remote_address: 192.0.2.107
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false

```

### Aggregation switch A2

```yaml design
devices:
  - name: acme-branch-agg-2
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 4"
          label: ACME-CONSOLE-acme-branch-agg-2
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 4"
          label: ACME-POWER-acme-branch-agg-2
    role: ACME AGGREGATION SWITCH
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME AGG SWITCH
    platform: ACME OS
    status: active
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.104/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-agg-2
            status: active
      Loopback0:
        type: virtual
        description: ACME Explicit management address
        ip_addresses:
          - address: 192.0.2.11/32
            tenant: ACME
            description: acme-branch-agg-2 Loopback0
            status: active
      Ethernet1:
        type: 10gbase-x-sfpp
        description: ACME Uplink to router 1
        enabled: true
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Uplink to router 2
        enabled: true
      Ethernet3:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 1
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-1
          interface: Ethernet2
          type: smf-os2
          status: connected
      Ethernet4:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 2
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-2
          interface: Ethernet2
          type: smf-os2
          status: connected
      Ethernet5:
        type: 10gbase-x-sfpp
        description: ACME Downlink to access switch 3
        enabled: true
        connection:
          description: ACME access uplink
          device: acme-branch-access-3
          interface: Ethernet2
          type: smf-os2
          status: connected
      Port-Channel1:
        type: lag
        description: ACME aggregation interconnect LAG
        ip_addresses:
          - address: 198.51.100.5/31
            tenant: ACME
            description: ACME aggregation 2 interconnect address
            status: active
      Ethernet6:
        type: 10gbase-x-sfpp
        lag: {device: acme-branch-agg-2, name: Port-Channel1}
        description: ACME aggregation interconnect member 1
      Ethernet7:
        type: 10gbase-x-sfpp
        lag: {device: acme-branch-agg-2, name: Port-Channel1}
        description: ACME aggregation interconnect member 2
      Vlan100:
        type: virtual
        description: ACME aggregation user gateway
        mode: access
        untagged_vlan: {group: "{{ context.site }} VLANS", vid: 100}
        ip_addresses:
          - address: 192.0.2.22/24
            tenant: ACME
          - address: 192.0.2.23/24
            role: vip
            tenant: ACME
            description: ACME shared user VIP
        vrrp:
          group_id: 10
          name: ACME USER GATEWAY
          vip: 192.0.2.1/24
          priority: 100

    bgp_peerings:
      - name: acme-branch-agg-2-to-acme-branch-rtr-1
        local_address: 192.0.2.104
        remote_address: 192.0.2.101
        local_as: 4200650002
        remote_as: 4200650001
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-2-to-acme-branch-rtr-2
        local_address: 192.0.2.104
        remote_address: 192.0.2.102
        local_as: 4200650002
        remote_as: 4200650001
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-2-to-acme-branch-agg-1
        local_address: 198.51.100.5
        remote_address: 198.51.100.4
        local_as: 4200650002
        remote_as: 4200650002
        status: active
        description: ACME same-tier iBGP
        create_reverse: false
      - name: acme-branch-agg-2-to-acme-branch-access-1
        local_address: 192.0.2.104
        remote_address: 192.0.2.105
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-2-to-acme-branch-access-2
        local_address: 192.0.2.104
        remote_address: 192.0.2.106
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-agg-2-to-acme-branch-access-3
        local_address: 192.0.2.104
        remote_address: 192.0.2.107
        local_as: 4200650002
        remote_as: 4200650003
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false

```

### Warehouse access switch S1

```yaml design
devices:
  - name: acme-branch-access-1
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 5"
          label: ACME-CONSOLE-acme-branch-access-1
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 5"
          label: ACME-POWER-acme-branch-access-1
    role: ACME ACCESS SWITCH
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME ACCESS SWITCH
    platform: ACME OS
    status: active
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.105/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-access-1
            status: active
      Ethernet1:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 1
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 2
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet3:
        type: 1000base-t
        description: ACME User access port
        enabled: true
        mode: access
        untagged_vlan:
          group: "{{ context.site }} VLANS"
          vid: 100

    bgp_peerings:
      - name: acme-branch-access-1-to-acme-branch-agg-1
        local_address: 192.0.2.105
        remote_address: 192.0.2.103
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-access-1-to-acme-branch-agg-2
        local_address: 192.0.2.105
        remote_address: 192.0.2.104
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false

```

### Packing-area access switch S2

```yaml design
devices:
  - name: acme-branch-access-2
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 6"
          label: ACME-CONSOLE-acme-branch-access-2
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 6"
          label: ACME-POWER-acme-branch-access-2
    role: ACME ACCESS SWITCH
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME ACCESS SWITCH
    platform: ACME OS
    status: active
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.106/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-access-2
            status: active
      Ethernet1:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 1
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 2
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet3:
        type: 1000base-t
        description: ACME User access port
        enabled: true
        mode: access
        untagged_vlan:
          group: "{{ context.site }} VLANS"
          vid: 100

    bgp_peerings:
      - name: acme-branch-access-2-to-acme-branch-agg-1
        local_address: 192.0.2.106
        remote_address: 192.0.2.103
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-access-2-to-acme-branch-agg-2
        local_address: 192.0.2.106
        remote_address: 192.0.2.104
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false

```

### Office access switch S3

```yaml design
devices:
  - name: acme-branch-access-3
    tenant: ACME
    site: "{{ context.site }}"
    console_ports:
      Console:
        type: rj-45
        connection:
          device: acme-branch-terminal-server
          console_server_port: "Line 7"
          label: ACME-CONSOLE-acme-branch-access-3
    power_ports:
      PSU1:
        type: iec-60320-c14
        connection:
          device: acme-branch-pdu
          power_outlet: "Outlet 7"
          label: ACME-POWER-acme-branch-access-3
    role: ACME ACCESS SWITCH
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME ACCESS SWITCH
    platform: ACME OS
    status: active
    interfaces:
      Loopback100:
        type: virtual
        enabled: true
        description: ACME dedicated BGP loopback
        ip_addresses:
          - address: 192.0.2.107/32
            tenant: ACME
            description: ACME BGP loopback acme-branch-access-3
            status: active
      Ethernet1:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 1
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet2:
        type: 10gbase-x-sfpp
        description: ACME Uplink to aggregation switch 2
        enabled: true
        mode: tagged
        tagged_vlans:
          - group: "{{ context.site }} VLANS"
            vid: 100
          - name: ACME VOICE
            tenant: ACME
            vid: 110
            group: "{{ context.site }} VLANS"
            status: active
          - name: ACME MANAGEMENT
            tenant: ACME
            vid: 120
            group: "{{ context.site }} VLANS"
            status: active
      Ethernet3:
        type: 1000base-t
        description: ACME User access port
        enabled: true
        mode: access
        untagged_vlan:
          group: "{{ context.site }} VLANS"
          vid: 100

    bgp_peerings:
      - name: acme-branch-access-3-to-acme-branch-agg-1
        local_address: 192.0.2.107
        remote_address: 192.0.2.103
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false
      - name: acme-branch-access-3-to-acme-branch-agg-2
        local_address: 192.0.2.107
        remote_address: 192.0.2.104
        local_as: 4200650003
        remote_as: 4200650002
        status: active
        description: ACME inter-tier eBGP
        create_reverse: false


```

### Out-of-band terminal server

```yaml design
devices:
  - name: acme-branch-terminal-server
    tenant: ACME
    site: "{{ context.site }}"
    role: ACME TERMINAL SERVER
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME TERMINAL SERVER
    status: active
    console_server_ports:
      Line 1: {type: rj-45}
      Line 2: {type: rj-45}
      Line 3: {type: rj-45}
      Line 4: {type: rj-45}
      Line 5: {type: rj-45}
      Line 6: {type: rj-45}
      Line 7: {type: rj-45}

```

### Rack power distribution

```yaml design
devices:
  - name: acme-branch-pdu
    tenant: ACME
    site: "{{ context.site }}"
    role: ACME PDU
    device_type:
      manufacturer: ACME NETWORKS
      model: ACME PDU
    status: active
    power_outlets:
      Outlet 1: {type: iec-60320-c13}
      Outlet 2: {type: iec-60320-c13}
      Outlet 3: {type: iec-60320-c13}
      Outlet 4: {type: iec-60320-c13}
      Outlet 5: {type: iec-60320-c13}
      Outlet 6: {type: iec-60320-c13}
      Outlet 7: {type: iec-60320-c13}

```

## VRRP groups

Aggregation switch A1 is preferred for management gateway group 20 with priority 200; A2 uses priority 100. Live VRRP behaviour requires matching device configuration.

```yaml design
vrrp_groups:
  - protocol: vrrp2
    group_id: 20
    name: ACME MANAGEMENT GATEWAY
    assignments:
      - device: acme-branch-agg-1
        interface: Vlan100
        priority: 200
      - device: acme-branch-agg-2
        interface: Vlan100
        priority: 100

```

## Primary IP

Use aggregation loopbacks 192.0.2.10 and 192.0.2.11 as the primary inventory addresses.

```yaml design
primary_ip:
  - device: acme-branch-agg-1
    site: "{{ context.site }}"
    tenant: ACME
    address: 192.0.2.10/32
  - device: acme-branch-agg-2
    site: "{{ context.site }}"
    tenant: ACME
    address: 192.0.2.11/32

```

## Connections

Four OS2 single-mode fibre cables connect every edge router to both aggregation switches. Access and recovery connections are also recorded within device schedules.

```yaml design
connections:
  - label: ACME-RTR-1-AGG-1
    type: smf-os2
    status: connected
    a_terminations:
      - device: acme-branch-rtr-1
        interface: Ethernet2
    b_terminations:
      - device: acme-branch-agg-1
        interface: Ethernet1
  - label: ACME-RTR-1-AGG-2
    type: smf-os2
    status: connected
    a_terminations:
      - device: acme-branch-rtr-1
        interface: Ethernet3
    b_terminations:
      - device: acme-branch-agg-2
        interface: Ethernet1
  - label: ACME-RTR-2-AGG-1
    type: smf-os2
    status: connected
    a_terminations:
      - device: acme-branch-rtr-2
        interface: Ethernet2
    b_terminations:
      - device: acme-branch-agg-1
        interface: Ethernet2
  - label: ACME-RTR-2-AGG-2
    type: smf-os2
    status: connected
    a_terminations:
      - device: acme-branch-rtr-2
        interface: Ethernet3
    b_terminations:
      - device: acme-branch-agg-2
        interface: Ethernet2
```

## Deployment parameter contract

A site name and parent prefix are required for each deployment. The optional
reference schedules accompany the design review and do not alter the network
object definitions. Conversion moves this final metadata block to the beginning
of the generated YAML, ahead of function registrations and collections.

```yaml design
design_input_schema:
  type: object
  additionalProperties: false
  properties:
    site:
      type: string
      minLength: 1
    parent_prefix:
      type: string
      minLength: 1
    links:
      type: array
    vlans:
      type: array
    site_vlans:
      type: array
  required:
    - site
    - parent_prefix
```
