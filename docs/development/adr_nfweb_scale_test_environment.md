# ADR: NFWeb Scale-Test Environment

- **Status:** Accepted
- **Date:** 6 September 2026
- **Decision owners:** NORFAB maintainers
- **Scope:** Dedicated NORFAB inventory and deterministic data fixtures for NFWeb topology scale testing

## Context

The NFWeb topology application must support thousands of displayed devices and
links, but current Nornir and NetBox test inventories do not contain enough data
to exercise that scale. Testing only with generated browser payloads would bypass
the broker, workers, Nornir inventory adaptation, live CLI collection, parsing,
source merging, persistence, and WebSocket delivery that materially affect
performance and correctness.

The repository already uses FakeNOS to provide deterministic network-device CLI
responses to Nornir. A dedicated NORFAB environment can extend that approach and
exercise the same interfaces used by NFWeb without adding test behavior to the
production application.

This ADR owns the scale-test environment. The topology source, merge, API, and UI
contracts remain defined by
[ADR: NFWeb Local Application Platform and 3D Topology Architecture](adr_web_ui_topology_architecture.md).

## Decision

Create a complete, independent NORFAB environment at:

```text
tests/nf_inventory_scale/
```

The directory is a normal inventory-driven NORFAB environment dedicated to NFWeb
development, integration testing, and profiling. NFWeb receives no special scale
mode, mock data source, mock route, or UI control. Tests start NFWeb against this
environment and use the production collection path.

### Environment Layout

Use the following logical layout, adjusting individual filenames only when the
existing inventory loader requires it:

```text
tests/nf_inventory_scale/
|-- inventory.yaml
|-- README.md
|-- fakenos/
|   |-- common.yaml
|   |-- network.yaml
|   `-- nos/
|       `-- <one small predefined YAML profile per FakeNOS device>
|-- netbox/
|   `-- common.yaml
`-- nornir/
    |-- common.yaml
    |-- hosts.yaml
    |-- interfaces.yaml
    |-- connections.yaml
    |-- circuits.yaml
    `-- bgp_peerings.yaml
```

Keep this directory limited to committed NORFAB inventory configuration and data.
The topology is a fixed test environment and has no retained generator.
Functional NFWeb tests exercise the environment through the normal collection and
parsing paths; no dedicated fixture-validation test is maintained.

The top-level `inventory.yaml` assembles the broker and required workers and merges
the committed Nornir inventory fragments. The data remains deterministic across
runs.

The environment is self-contained and must not alter the existing focused test
inventory under `tests/nf_tests_inventory`.

Allow up to ten minutes for worker initialization. A cold start transfers all 100
per-device NOS profiles through the normal NORFAB file-sharing path before
FakeNOS opens its listeners; this cost is part of the environment being profiled,
not a reason to bypass production file retrieval.

### FakeNOS Devices and Live Output

Start 100 FakeNOS devices on a dedicated consecutive port range. The inventory is
intentionally multi-vendor: 34 Arista EOS devices, 33 Cisco IOS XR devices, and 33
Juniper Junos devices. The 100-device budget is divided into 8 spines, 24 leaves,
4 data-center PE routers, 6 MPLS P routers, 2 route reflectors, 6 edge routers, 14
aggregation routers, and 36 access routers. Every role spans multiple platforms.

Device names use the `<device_type><number>.<sitename>` convention, such as
`spine01.site1`, `dcpe01.site1`, `pcore01.site3`, and `access01.site5`.
`site1` and `site2` contain the data-center fabrics, `site3` contains the MPLS
core and route reflectors, `site4` contains provider-facing edge routers, and
`site5` and `site6` contain metro aggregation and access networks. All managed
devices remain part of the `norfab-scale` tenant.

Each device uses a small YAML NOS plugin containing predefined output for the
platform-native commands selected by the `ttp_templates` getters:

| Platform | LLDP | BGP | Interfaces |
| --- | --- | --- | --- |
| Arista EOS | `show lldp neighbors detail \| json` | `show ip bgp neighbors vrf all \| json` | `show interfaces` |
| Cisco IOS XR | `show lldp neighbors detail` | `show bgp neighbors` | `show interfaces` |
| Juniper Junos | `show lldp neighbors detail \| display json` | `show bgp neighbor \| display json` | `show interfaces` |

Synthetic outputs follow the platform fixture shapes published by the
MIT-licensed `ttp_templates` repository. The committed inventory owns all local
names, addressing, counters, adjacency, and session values; upstream fixtures are
used as format references rather than copied as an opaque data dependency.

The profiles provide deterministic:

- LLDP neighbors and endpoint interfaces;
- BGP session addresses, state, and peer groups;
- interface operational state;
- traffic counters;
- input, output, and CRC error counters;
- interface transition counters.

The physical topology deliberately combines several network designs:

- two regular leaf-spine fabrics connected to redundant data-center PE routers;
- an irregular MPLS core interconnecting P, DCPE, edge, and aggregation routers;
- provider-facing edge NNIs and circuits for Internet transit and cloud services;
- aggregation rings in two metro sites;
- closed access rings and branched access trees connected to aggregation routers.

DCPE routers connect to MPLS P routers over both direct links and circuits. Edge
routers connect to external Internet and cloud-provider nodes over NNI circuits.
LLDP output also references adjacent nodes that are not FakeNOS devices. These
one-hop nodes allow the rendered graph to reach the scale target without starting
thousands of SSH endpoints.

BGP follows the network design rather than blindly following every physical
link. Leaf-spine sessions follow all fabric links. The two core route reflectors
peer with each other and with all P, DCPE, edge, and aggregation routers. In each
metro site, two aggregation routers peer with every access router. Provider-facing
BGP sessions retain peer-group and peer-IP labels for external-node resolution.

Seed controlled unhealthy states, including down interfaces, non-zero error
counters, and transition values covering all NFWeb flap bands: 0 through 10, 11
through 100, and greater than 100.

### Nornir Inventory Data

Nornir is the authoritative device list for NFWeb, split across two workers with
no duplicated managed hosts:

- `nornir-static` loads the even-ordinal 50 hosts from the committed Nornir YAML;
- `nornir-netbox` loads the odd-ordinal 50 hosts from `netbox-scale`, filtered by
  tenant `norfab-scale`.

The NetBox-backed worker depends on `netbox-scale`, not on `fakenos-scale`. The
static worker has no source-worker dependency. FakeNOS remains an independent live
CLI endpoint service for both sets of hosts.

Both workers expose the host attributes needed by topology, including host name,
hostname, platform, groups, role, site, status, manufacturer, device type, tags,
and primary IP. The static fragments contain interfaces, addressing, connections,
circuits, and BGP peerings for the static half. The NetBox worker requests the same
categories through `get_nornir_inventory` with interfaces, connections, circuits,
and BGP peerings enabled.

Topology ownership is complementary. The static worker owns every physical link
or circuit with at least one static endpoint. NetBox owns links and circuits whose
managed endpoints are entirely in the NetBox half, plus provider-facing circuits
from NetBox-backed edge routers. Managed BGP peerings follow the same design in
both halves. Combining both worker inventories reconstructs the complete fixed
topology without duplicate hosts or links.

### NetBox Fixture Data

Extend `tests/netbox_data.py` to create the NetBox portion of the scale topology.
The fixture creates:

- a tenant named `norfab-scale` with slug `norfab-scale`;
- 50 NetBox devices matching 50 Nornir/FakeNOS devices;
- six sites, eight device roles, three platforms, manufacturers, and device types;
- physical interfaces and interface IP addresses;
- cables that form NetBox topology links;
- BGP and supporting records needed for topology and peer resolution;
- MPLS, Internet-transit, and cloud-provider circuits with their providers,
  provider networks, types, and terminations;
- deterministic cleanup coverage for every object created by the fixture.

NetBox fixture setup runs before the NetBox-backed Nornir worker. `netbox_data.py`
owns generation of its 50 devices and all related interface, addressing,
connection, circuit, and BGP objects. It uses the same fixed naming, interface,
and IP plan as the committed static inventory and FakeNOS profiles.

NetBox physical links match cached Nornir connections and FakeNOS LLDP neighbors
for the selected 50 devices, apart from a small set of deliberate discrepancies:

- a mismatched interface endpoint;
- Nornir/LLDP links involving devices outside the 50-device NetBox subset;
- reciprocal RR-to-DCPE links present only in live LLDP output and absent from
  Nornir connections and NetBox cables;
- an inventory BGP session absent from live state;
- a live BGP session absent from inventory.

These records verify that NFWeb exposes the union of topology data and tracks its
origins instead of silently forcing all sources to agree.

### Scale Target

The initial environment targets approximately:

- 100 live FakeNOS/Nornir devices;
- 50 matching NetBox devices;
- 2,000 displayed nodes after one-hop adjacent nodes are included;
- 10,000 combined topology, circuit, LLDP, and BGP links.

Exact graph totals may vary slightly as parsers and deduplication improve, but the
fixture inputs remain fixed. Performance results must record the actual input and
normalized graph counts so comparisons remain meaningful.

### Profiling Coverage

Exercise the complete NFWeb path and record at least:

- worker collection duration by source;
- normalization, merge, and Pydantic validation duration;
- normalized node and link counts by type and origin;
- serialized snapshot size;
- SQLite insert and history-read duration;
- initial API and WebSocket delivery duration;
- browser parsing and ForceGraph3D layout convergence;
- NFWeb and browser memory consumption.

Measurements should distinguish cold startup from subsequent refreshes. A refresh
re-fetches Nornir inventory data and live state but does not refresh the Nornir
worker's underlying inventory.

No fixed pass/fail latency budget is established by this ADR. Record a baseline
before optimization and add enforceable thresholds only after results are stable
in the intended test environment.

## Implementation Plan

1. Add `tests/nf_inventory_scale` with a complete broker and worker inventory.
2. Extend `tests/netbox_data.py` with the `norfab-scale` tenant and deterministic
   50-device topology, including cleanup.
3. Commit the 50-host static Nornir inventory fragments and configure a second
   50-host Nornir worker to load from NetBox.
4. Add 100 per-device FakeNOS YAML profiles for NFWeb's LLDP, BGP, and interface
   commands.
5. Add deliberate source discrepancies, adjacent-only nodes, and unhealthy state.
6. Add an internal test or profiling entry point that starts the normal environment
   and exercises NFWeb without exposing scale controls in the web UI.
7. Capture the first end-to-end baseline at approximately 2,000 nodes and 10,000
   links.

## Alternatives Considered

### Generate Mock Topology Inside NFWeb

Rejected because it would add non-operational code and configuration to the
production application and would not validate worker calls or parsers.

### Run a Mock HTTP Server

Rejected because it bypasses the NORFAB broker, Nornir and NetBox workers, live CLI
collection, TTP parsing, persistence, and WebSocket path.

### Expand the Existing General Test Inventory

Rejected because 100 device servers and large fixtures increase startup time,
resource use, and maintenance cost for focused service tests. A separate inventory
keeps scale work opt-in and confined.

### Start Thousands of FakeNOS Devices

Rejected for the initial environment because it consumes unnecessary ports and
process resources. One-hop adjacent nodes in deterministic LLDP and BGP output
exercise browser graph scale while 100 live devices retain realistic collection
coverage.

## Consequences

Benefits:

- profiling covers the real broker, worker, parser, API, persistence, and browser
  path;
- deterministic source overlap and discrepancies exercise topology merge rules;
- the production NFWeb contract remains free of mock behavior;
- the environment can be run independently from focused service tests;
- live device count and rendered graph size can be tuned separately.

Costs:

- 100 per-device FakeNOS YAML profiles and expanded NetBox fixtures require
  maintenance;
- the environment consumes substantially more CPU, memory, ports, and startup time
  than focused tests;
- committed naming and addressing must remain synchronized across static Nornir,
  NetBox seed, and FakeNOS data;
- browser profiling may require a stable host and documented measurement method to
  produce comparable results.

## Acceptance Criteria

- `tests/nf_inventory_scale` is a complete NORFAB environment with no dependency
  on `tests/nf_tests_inventory`;
- it starts 100 FakeNOS devices across Arista EOS, Cisco IOS XR, and Juniper Junos,
  backed by small per-device YAML NOS profiles;
- device names follow `<device_type><number>.<sitename>`, sites are named `site1`
  through `site6`, and all managed objects belong to tenant `norfab-scale`;
- the topology contains two leaf-spine fabrics, an irregular MPLS core, redundant
  route reflectors, provider-facing edge circuits, aggregation rings, closed
  access rings, and branched access trees;
- BGP follows fabric links, uses both route reflectors for core-facing roles, and
  connects the designated aggregation routers to all access nodes in each metro
  site;
- all platform-native LLDP, BGP, and interface commands selected by the NFWeb
  getters return parseable deterministic output;
- Nornir inventory provides interfaces, addressing, connections, circuits, BGP
  peerings, and safe host attributes;
- two Nornir workers expose disjoint 50-host inventories; the NetBox-backed worker
  depends on `netbox-scale` and the combined inventories reconstruct the complete
  topology;
- `tests/netbox_data.py` creates 50 matching multi-vendor devices owned by the
  `norfab-scale` tenant,
  their interfaces, IP assignments, connections, circuits, BGP peerings, and
  deterministic cleanup data;
- the environment includes the documented source discrepancies and unhealthy
  operational values;
- an end-to-end run produces approximately 2,000 nodes and 10,000 links and records
  the exact normalized totals;
- profiling traverses the normal NFWeb production interfaces;
- no mock or scale-only data source, route, configuration, or control is exposed in
  the NFWeb UI;
- focused existing test environments do not start the scale topology implicitly.

## References

- [ADR: NFWeb Local Application Platform and 3D Topology Architecture](adr_web_ui_topology_architecture.md)
- [NFWeb developer guide](nfweb_developer_guide.md)
- [NORFAB testing framework](../testing/norfab_testing_framework.md)
- [NFWeb topology user guide](../clients_nfweb_topology.md)
- [ttp_templates platform fixtures](https://github.com/dmulyalin/ttp_templates/tree/master/test/platform)
