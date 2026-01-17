# Filesharing Worker Inventory

When you start NORFAB via `NorFab` (NFAPI) **with the broker enabled**, NFAPI injects a filesharing worker:

- Worker name: `filesharing-worker-1`
- Service: `filesharing`
- Base directory: `base_dir = <inventory.base_dir>`

That means you usually do not need to add a File Sharing worker manually.

If you do want to define it explicitly (or point it at a different directory), add it to inventory:

```yaml title="inventory.yaml"
workers:
  filesharing-worker-1:
    - service: filesharing
      base_dir: ./

topology:
  broker: true
  workers:
    - filesharing-worker-1
```