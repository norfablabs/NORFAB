# Containerlab Worker Inventory

Content of `inventory.yaml` need to be updated to include Containerlab worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  containerlab-worker-1: 
    - containerlab/containerlab-worker-1.yaml

topology: 
  workers: 
    - containerlab-worker-1
```

Sample Containerlab worker inventory file content:

``` yaml title="containerlab/containerlab-worker-1.yaml"
service: containerlab
```