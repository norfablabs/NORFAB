# NorFab four-router demo

Deploy R1-R4 from NetBox, configure the lab, run validation, and sync changes.
Run commands from this folder. NorFab serves its files through `nf://` URLs.

## Overview

This guide walks through the following steps:

1. **Set up NorFab:** Prepare the lab host, NetBox access, and workers.
2. **Deploy the NetBox design:** Create four routers, ring links, IP addresses, and iBGP peerings in branch `demo`.
3. **Deploy the lab:** Build the Containerlab network from the NetBox design.
4. **Load Nornir inventory:** Import device connection settings and NetBox data into Nornir hosts.
5. **Apply IOS configuration:** Render and deploy routing, LLDP, logging, and customer VRF configuration.
6. **Check the routers:** Inspect live OSPF, BGP, and LLDP output.
7. **Run validation:** Compare live device output with inventory expectations and demonstrate deliberate failures.
8. **Sync customer configuration:** Record the additional device configuration in NetBox.
9. **Check synchronization:** Review differences between the devices and NetBox.
10. **Clean up:** Destroy the lab and optionally remove the demo branch.

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

Preview and deploy the four-router Containerlab network from branch `demo`.

```text
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1 dry-run
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1
```

### 3. Load Nornir hosts and NetBox data

```text
nornir inventory load containerlab lab-name demo-4-routers clab-workers containerlab-worker-1 load-netbox-branch demo workers nornir-worker-1
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

Inspect OSPF adjacencies, BGP sessions, and LLDP neighbors on all four routers.

```text
nornir cli commands "show ip ospf neighbor" 
nornir cli commands "show ip bgp summary"
nornir cli commands "show lldp neighbors" 
```

### 6. Run the validation suite

```text
nornir test suite nf://tests/four_routers_suite.yaml dry-run
nornir test suite nf://tests/four_routers_suite.yaml
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

Sync the customer VRF, interfaces, addresses, and BGP configuration into branch `demo`, leaving device inventory unchanged.

```text
netbox sync all FL R1 R2 R3 R4 branch demo sync-kwargs {"sync_device_inventory": false, "sync_bgp_peerings": {"rir": "DEMO PRIVATE"}}
```

### 8. Check synchronization

Compare the live configuration with NetBox and review any remaining differences, excluding device inventory.

```text
netbox check-sync devices FL R1 R2 R3 R4 branch demo check-inventory false
```

## Cleanup

Destroy the lab before exiting NFCLI:

```text
containerlab destroy lab-name demo-4-routers
```

Optionally delete branch `demo` through the NetBox UI. Exit NFCLI to stop the
local broker and workers.

## Conclusion

After completing this guide, you have:

1. **Set up NorFab:** Prepared the lab host, NetBox access, and workers.
2. **Deployed the NetBox design:** Created the four-router topology and core routing records in a branch.
3. **Deployed the lab:** Started the routers and links through Containerlab.
4. **Loaded Nornir inventory:** Combined lab connection settings with NetBox host data.
5. **Applied IOS configuration:** Configured core routing, LLDP, logging, and the customer VRF.
6. **Checked the routers:** Inspected live routing and neighbor status.
7. **Run validation:** Checked inventory expectations and reviewed deliberate description and MTU failures.
8. **Synced customer configuration:** Added the device-side customer configuration to NetBox.
9. **Checked synchronization:** Reviewed remaining differences against NetBox.
10. **Cleaned up:** Destroyed the lab and stopped the local NorFab processes.
