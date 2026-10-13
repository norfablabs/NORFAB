# NorFab four-router demo

Deploy R1-R4 from NetBox, configure the lab, run validation, and sync changes.
Run commands from this folder. NorFab serves its files through `nf://` URLs.

## Setup

1. Install Docker and Containerlab on the lab host and make the image
   `vrnetlab/cisco_iol:17.16.1a` available.
2. Configure NetBox with the Branching and BGP plugins and the BGP session
   `vrf` custom field. Set the URL and token in `.env`; the token needs
   permissions to create records and branches.
3. Set the broker endpoint in `inventory.yaml`. For a local deployment, include
   `containerlab-worker-1` in `topology.workers`. For a remote worker, start it
   separately against the same broker and omit it from the local worker list.
   Nornir must be able to reach the lab's published SSH ports.
4. Install NorFab and start NFCLI:

```bash
cd /path/to/norfab_demo
python3 -m venv .venv
source .venv/bin/activate
pip install "norfab[full]"
nfcli
```

## Run the demo

Use branch `demo`, NetBox instance `prod`, and lab `demo-4-routers` throughout.

### 1. Deploy the NetBox design

```text
netbox design deploy design nf://netbox/designs/four_routers_design.yaml branch demo dry-run
netbox design deploy design nf://netbox/designs/four_routers_design.yaml branch demo
```

The design creates the routers, ring links, addresses, and full-mesh iBGP.
Edit its Containerlab image if your tag differs. A first dry run may fail on
lookups for devices or pools that have not been created yet.

### 2. Deploy the lab

```text
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1 dry-run
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1
```

### 3. Load Nornir hosts and NetBox data

```text
nornir inventory load containerlab lab-name demo-4-routers clab-workers containerlab-worker-1 workers nornir-worker-1 load-netbox-branch demo load-netbox-instance prod
```

This loads lab connection settings and NetBox interfaces, connections, and BGP
peerings into host data.

### 4. Render and apply IOS configuration

```text
nornir cfg config nf://nornir/four_routers_ios_base.j2 workers nornir-worker-1 FL R1 R2 R3 R4 dry-run
nornir cfg config nf://nornir/four_routers_ios_base.j2 workers nornir-worker-1 FL R1 R2 R3 R4
```

Review addresses before applying, especially when reusing an existing lab.
The template configures core OSPF, iBGP, LLDP, and logging, plus a static
`CUSTOMER-A` VRF. Customer peers are placeholders and are not deployed.

### 5. Check the routers

```text
nornir cli commands "show ip ospf neighbor" workers nornir-worker-1 FL R1 R2 R3 R4
nornir cli commands "show ip bgp summary" workers nornir-worker-1 FL R1 R2 R3 R4
nornir cli commands "show lldp neighbors" workers nornir-worker-1 FL R1 R2 R3 R4
```

Optionally save the configuration:

```text
nornir cli commands "write memory" workers nornir-worker-1 FL R1 R2 R3 R4
```

### 6. Run the validation suite

```text
nornir test suite nf://tests/four_routers_suite.yaml workers nornir-worker-1 FL R1 R2 R3 R4 dry-run
nornir test suite nf://tests/four_routers_suite.yaml workers nornir-worker-1 FL R1 R2 R3 R4
```

The suite checks core BGP and OSPF, LLDP connections, interface state and
descriptions, MTU when supplied, and logging. It uses loaded host data without
calling NetBox. Customer peers and management LLDP neighbors are excluded.

Expect two deliberate failures per router: an absent Ethernet0/1 description
and MTU 9000. To run only baseline checks or show only failures:

```text
nornir test suite nf://tests/four_routers_suite.yaml workers nornir-worker-1 FL R1 R2 R3 R4 groups baseline
nornir test suite nf://tests/four_routers_suite.yaml workers nornir-worker-1 FL R1 R2 R3 R4 failed-only
```

### 7. Sync customer configuration into NetBox

```text
netbox sync all FL R1 R2 R3 R4 branch demo instance prod workers netbox-worker-1
```

### 8. Check synchronization

```text
netbox check-sync devices FL R1 R2 R3 R4 branch demo instance prod workers netbox-worker-1 check-bgp-communities false
```

Review the differences. Community checking is disabled because `sync_all`
does not synchronize BGP community records.

## Cleanup

Destroy the lab before exiting NFCLI:

```text
containerlab destroy lab-name demo-4-routers workers containerlab-worker-1
```

Optionally delete branch `demo` through the NetBox UI. Exit NFCLI to stop the
local broker and workers.
