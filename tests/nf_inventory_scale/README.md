# NFWeb Scale-Test Environment

This is a dedicated, opt-in NORFAB environment for NFWeb topology integration
testing and profiling. It starts 100 FakeNOS devices across Arista EOS, Cisco IOS
XR, and Juniper Junos platforms on ports 6400 through 6499.

The inventory models two leaf-spine data centers, an MPLS core with route
reflectors, provider-facing edge routers, metro aggregation rings, and both ring
and branched-tree access networks. Managed hostnames follow
`<device_type><number>.site<number>` and all NetBox-backed objects belong to the
`norfab-scale` tenant.

The topology and per-device NOS profiles are committed fixtures. They are treated
as a fixed test environment and are not generated at runtime.

Populate NetBox with `tests/netbox_data.py` before starting the environment. The
scale objects use tenant name and slug `norfab-scale`.

The environment runs two disjoint Nornir workers. `nornir-static` loads 50 hosts
and their topology data from the committed files under `nornir/`.
`nornir-netbox` loads the other 50 hosts, interfaces, connections, circuits, and
BGP peerings from the NetBox worker using the `norfab-scale` tenant filter. The
NetBox-backed worker depends on `netbox-scale`; neither Nornir worker has a
FakeNOS startup dependency.

Start NFWeb from the repository root:

```shell
poetry run nfcli -i tests/nf_inventory_scale/inventory.yaml --web-ui
```

The first environment start fetches approximately 16 MB across 100 NOS profiles
through the normal file-sharing path and can take several minutes. The inventory
allows up to ten minutes for worker initialization; subsequent collection uses the
normal NFWeb refresh behavior.

The synthetic command formats were designed and validated against the MIT-licensed
[ttp_templates platform test fixtures](https://github.com/dmulyalin/ttp_templates/tree/master/test/platform).
No scale-only source or control is exposed by NFWeb.
