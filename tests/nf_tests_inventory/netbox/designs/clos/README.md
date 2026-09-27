# Compact Arista cEOS CLOS

`design.yaml` accepts only `site` (an alphanumeric name with hyphens or
underscores) and `prefix` (an aligned IPv4 `/20`). `addressing.py` validates the
pool and supplies address arithmetic; all topology repetition stays in Jinja2.

The design creates two spines and three leaves using the **Arista cEOS** device
type, `arista_eos` platform, ASNs 65001–65005 in device order, an ASN range named
`<site>-asns` encompassing those five ASNs, and a site-scoped
VLAN group permitting IDs 100–200. VLANs are 100/mgmt, 110/data, and 120/control.
Each leaf has one access port per VLAN (Ethernet3–5).

Six `/31` spine–leaf links have cables and twelve explicit directional eBGP
sessions. Spine Ethernet1–3 connect to leaves 1–3; leaf Ethernet1–2 connect to
spines 1–2. Leaf 1 and leaf 2 also connect through Ethernet6, a trunk carrying
the three VLANs so VRRP advertisements can pass between them. This is a routed
CLOS with a local redundancy trunk, without an EVPN overlay or MLAG.

| Allocation relative to the supplied /20 | Purpose |
| --- | --- |
| Offsets 0–31 (`/27`) | P2P pool; six `/31`s start at offsets 0, 2, 4, 6, 8, 10 |
| Offsets 32–63 (`/27`) | Loopback pool; five `/32`s at offsets 33–37 |
| `/24` blocks 1, 2, 3 (zero-based) | Leaf 1/2 mgmt, data, control subnets |
| `/24` blocks 4, 5, 6 | Leaf 3 mgmt, data, control subnets |
| All remaining space | Unallocated capacity inside the parent `/20` |

Leaf 1/2 use `.2`/`.3`, VRRP VIP `.1`, and priorities 200/100 respectively in
each shared subnet. Leaf 3 uses `.1` without VRRP in each of its separate
subnets. The same VLAN IDs on leaf 3 do not imply shared Layer 2 connectivity.
Management is in-band. Loopbacks are the devices' primary IPv4 addresses.

Device-local context records IP routing, BGP ASN/router ID, two ECMP paths,
multipath relaxation for distinct neighbor ASNs, and exact loopback/access
prefixes to originate. These are configuration intentions, not EOS commands:
deploying this design populates NetBox; it does not start or configure cEOS.
A configuration renderer must consume these values plus NetBox interfaces,
VLANs, BGP sessions, and VRRP assignments. Real operation also needs connected
access hosts and EOS configuration for routing, VLANs, VRRP, and BGP.

## Preview through NorFab

Requires the NetBox BGP plugin and a worker running this repository's design
engine. The design creates its manufacturer, device type, platform, roles, RIR,
site, and IPAM prerequisites. Matching pre-existing objects receive updates.
Choose the intended instance and review branch when invoking the task.
The ASN range is named for the site; NetBox ASN ranges are not site-scoped.

The files are stored under the requested **`tests/nf_test_inventory`** path
(singular `test`), distinct from the repository's usual `tests/nf_tests_inventory`.
Expose that directory as the broker's file-sharing root, or copy `netbox/design/clos_v1`
into the active inventory root. Both YAML and Python must be accessible at the
`nf://` URLs below.

```python
result = client.run_job(
    "netbox", "design_deploy", workers="any",
    kwargs={
        "design": "nf://netbox/design/clos_v1/design.yaml",
        "context": {"site": "LAB1", "prefix": "10.64.0.0/20"},
        "instance": "YOUR_INSTANCE",
        "branch": "YOUR_REVIEW_BRANCH",
        "dry_run": True,
    },
)
```

The prefix above is illustrative; supply your allocated `/20`. Inspect worker
`failed` and `errors` fields. A dry run cannot resolve every planned object before
it exists. Set `dry_run=False` only for an intended deployment.

## Reuse limits

Use an unused pool and device-name prefix. ASNs are globally matched by number;
their descriptions and site assignments will be updated on reuse. The current
design engine also identifies VRRP groups globally by `(protocol, group_id)`,
not by site or name. Groups `vrrp2/100`, `vrrp2/110`, and `vrrp2/120` must be
unused or already owned by this fabric. Do not deploy another site's copy into
the same NetBox data set with these IDs: change the three VRRP IDs to unused
values in 1–255 first, or use a separate NetBox instance. A site-scoped VLAN
group alone does not isolate VRRP groups. Repeated deployment of the same
site/prefix reuses the explicit identities; changing the pool does not remove
old objects.

VRRP protects a gateway device failure while the peer trunk is operational;
the single trunk is not redundant. Uplink isolation and trunk failure need
an EOS failure policy (for example, tracking loss of both uplinks) before
production use. No external/default-route connectivity is modeled.

This is an authored design only. It has not been rendered, run, or deployed
against NetBox.
