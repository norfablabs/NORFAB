# NorFab four-router demo

Standalone inventory for a Linux machine with one local broker and one worker
each for Nornir, NetBox, and Containerlab. The broker listens on
`tcp://127.0.0.1:5555`.
NorFab also starts its built-in file-sharing worker, which serves this folder
through `nf://` URLs. Service folders follow the Docker development inventory
layout. Copy this folder to the Linux machine; the repository is not needed
to run it.

```text
norfab_demo/
  inventory.yaml
  .env
  nornir/
    nornir.common.yaml
    nornir-worker-1.yaml
    four_routers_ios_base.j2
  netbox/
    netbox.common.yaml
    designs/four_routers_design.yaml
  containerlab/
    containerlab.common.yaml
```

## Setup

Run on a Linux host with Containerlab, Docker, and the IOS image
`vrnetlab/cisco_iol:17.16.1a` available. The user running NFCLI needs permission
to deploy Containerlab labs and manage Docker networking. NetBox needs the
Branching and BGP plugins, including the BGP session `vrf` custom field used
by the NetBox service. Use a token with permissions to create the design's
records and branches.

Install NorFab's full dependency set in a Python virtual environment:

```bash
cd /path/to/norfab_demo
python3 -m venv .venv
source .venv/bin/activate
pip install "norfab[full]"
docker info
containerlab version
```

Docker and Containerlab must already be installed and usable by this Linux
user. The pip install supplies NorFab and its Python dependencies.

The private `.env` is initialized from the local test NetBox settings. Check
the URL and token before starting. For another installation, copy `.env.example`
to `.env` and edit it. NorFab loads `.env` automatically. Start this inventory
with a NorFab version supporting `load-netbox-branch` and
`load-netbox-instance` on the Containerlab inventory loader.

From the demo folder, with the virtual environment active:

```bash
nfcli
```

## Run the demo

Enter these commands in NFCLI. Use the same branch, instance, and lab names
throughout.

### 1. Deploy the NetBox design

Preview the changes, then create the four routers in branch `demo`:

```text
netbox design deploy design nf://netbox/designs/four_routers_design.yaml branch demo dry-run
netbox design deploy design nf://netbox/designs/four_routers_design.yaml branch demo
```

The design creates the `demo` tenant, `DEMO` site, R1–R4, core interfaces and
addresses, ring connections, and full-mesh iBGP sessions. Its site config
context selects the Cisco IOL kind and image for Containerlab. Edit the copied
design's image if your local tag differs.

### 2. Deploy the lab

```text
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1 dry-run
containerlab deploy-netbox lab-name demo-4-routers tenant demo branch demo netbox-instance prod workers containerlab-worker-1
```

### 3. Load Nornir hosts and NetBox data

```text
nornir inventory load containerlab lab-name demo-4-routers clab-workers containerlab-worker-1 workers nornir-worker-1 load-netbox-branch demo load-netbox-instance prod
```

This retains the lab's published SSH ports and default device credentials, and
loads NetBox interfaces, IPs, connections, circuits, and BGP peerings into host
data. No separate static host inventory is needed.

### 4. Render and apply IOS configuration

```text
nornir cfg config nf://nornir/four_routers_ios_base.j2 workers nornir-worker-1 FL R1 R2 R3 R4 dry-run
nornir cfg config nf://nornir/four_routers_ios_base.j2 workers nornir-worker-1 FL R1 R2 R3 R4
```

The base configuration uses loaded host data for interface addresses and global
iBGP sessions. It enables OSPF area 0, uses Loopback0 as the router ID, and
enables LLDP on physical ports. Review the rendered link addresses before
applying configuration; both endpoints must share a subnet for OSPF to form.

Each router also has a hardcoded `CUSTOMER-A` block: VRF, Loopback100,
Ethernet0/3.100, OSPF process 100, export community `65222:100`, and customer
eBGP to AS 65001. Customer peers are external placeholders and are not deployed
by this design. Core address masks supported by the template are /30 and /32.

### 5. Check the routers

```text
nornir cli commands "show ip ospf neighbor" workers nornir-worker-1 FL R1 R2 R3 R4
nornir cli commands "show ip bgp summary" workers nornir-worker-1 FL R1 R2 R3 R4
nornir cli commands "show lldp neighbors" workers nornir-worker-1 FL R1 R2 R3 R4
```

Optionally save the running configuration:

```text
nornir cli commands "write memory" workers nornir-worker-1 FL R1 R2 R3 R4
```

### 6. Sync the additional customer configuration into NetBox

Read the running devices and sync their customer VRF, loopback, subinterface,
IP address, and BGP configuration into the same NetBox branch:

```text
netbox sync all FL R1 R2 R3 R4 branch demo instance prod workers netbox-worker-1
```

### 7. Check synchronization

Compare the running configuration with NetBox after synchronization:

```text
netbox check-sync devices FL R1 R2 R3 R4 branch demo instance prod workers netbox-worker-1 check-bgp-communities false
```

Review the returned per-device differences. BGP community checking is disabled
here because `sync_all` does not synchronize BGP community records.

## Cleanup

Destroy the lab:

```text
containerlab destroy lab-name demo-4-routers workers containerlab-worker-1
```

Optionally delete the `demo` branch through the NetBox UI to discard its changes.
Exit NFCLI to stop the local broker and workers. Destroy the lab first, because
stopping NorFab does not remove its Docker containers.
