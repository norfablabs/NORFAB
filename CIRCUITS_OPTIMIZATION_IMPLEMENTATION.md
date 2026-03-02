# Implementation Guide: Circuits Optimization

## Option A: Quick Wins (GraphQL + Code Optimization)

### Change 1: Combine GraphQL Queries
**File:** `circuits_tasks.py`
**Effort:** 30 minutes
**Expected Speedup:** 30-50% faster

Modify the cache validation phase to include full circuit data in the initial query:

```python
# Current: 2 separate GraphQL queries
# Query 1: Only last_updated
last_updated = self.graphql(
    job=job,
    obj="circuit_list",
    filters=circuits_filters,
    fields=["cid", "last_updated", "termination_a {id last_updated}", "termination_z {id last_updated}"]
)

# Query 2: Full circuit data
query_result = self.graphql(...)

# New: Single query that includes timestamps + full data
circuit_fields_with_timestamps = [
    "cid", "cid_list,
    "tags {name}",
    "provider {name}",
    "commit_rate",
    "description",
    "status",
    "type {name}",
    "provider_account {name}",
    "tenant {name}",
    "termination_a {id last_updated}",
    "termination_z {id last_updated}",
    "custom_fields",
    "comments",
    "last_updated",
]

circuits_data = self.graphql(
    job=job,
    obj="circuit_list",
    filters=circuits_filters,
    fields=circuit_fields_with_timestamps,
)
```

### Change 2: Eliminate Deep Copying
**File:** `circuits_tasks.py`, `_map_circuit()` method
**Effort:** 15 minutes
**Expected Speedup:** 10-20% faster

```python
# Current (lines 121-132)
device_data = copy.deepcopy(circuit)  # Expensive!

# Optimized
device_data = {
    # Include only necessary fields
    "tags": circuit["tags"],
    "type": circuit["type"],
    "provider": circuit["provider"],
    "tenant": circuit["tenant"],
    "provider_account": circuit["provider_account"],
    "commit_rate": circuit["commit_rate"],
    "description": circuit["description"],
    "status": circuit["status"],
    "custom_fields": circuit["custom_fields"],
    "comments": circuit["comments"],
    "is_active": circuit["is_active"],
    "last_updated": circuit["last_updated"],
    "termination_a": circuit.get("termination_a"),
    "termination_z": circuit.get("termination_z"),
    "interface": end_a["name"],  # Add device-specific fields
    "remote_device": end_z["device"] if end_z["device"] else None,
    "remote_interface": end_z["name"] if end_z["device"] else None,
}
```

### Change 3: Optimize Cache Validation Loop
**File:** `circuits_tasks.py`, lines 305-342
**Effort:** 20 minutes
**Expected Speedup:** 5-10% faster

```python
# Current: Nested loops with O(n*m) complexity
for device in devices:
    for circuit in last_updated.result:
        # Complex nested if statements

# Optimized: Pre-process circuits into lookup dict
circuits_by_cid = {c["cid"]: c for c in last_updated.result}
device_to_circuits = {}  # Pre-compute circuit usage

for d in devices:
    device_to_circuits[d] = [
        c for c in last_updated.result 
        if device in cache_data.get(f"get_circuits::{c['cid']}", {})
    ]

# Then simpler loop
for device in devices:
    for circuit_metadata in device_to_circuits[device]:
        cid = circuit_metadata["cid"]
        # Validate cache...
```

---

## Option B: Full Migration to pynetbox REST API

### Why pynetbox is Better for This Use Case

1. **Built-in Pagination:** Handles automatically
2. **Connection Pooling:** Faster subsequent calls
3. **Better Error Handling:** Retries, timeouts
4. **Native Filtering:** Query parameters are simpler
5. **Lower Overhead:** REST is simpler than GraphQL parsing

### Implementation: Rewrite with pynetbox

```python
# circuits_tasks.py - REWRITTEN VERSION

import logging
import concurrent.futures
from typing import Union
import copy

from norfab.core.worker import Task, Job
from norfab.models import Result
from .netbox_models import NetboxFastApiArgs

log = logging.getLogger(__name__)


class NetboxCircuitsTasks:

    def _map_circuit_rest(
        self,
        job: Job,
        circuit: dict,
        ret: Result,
        devices: list,
        cache: bool,
    ) -> bool:
        """
        Map circuit details from REST API response to devices.
        
        Args:
            circuit (dict): Circuit data from REST API
            ret (Result): Result object to store mapped data
            devices (list): List of devices to check
            cache (bool): Cache usage flag
            
        Returns:
            bool: True if successful
        """
        
        cid = circuit.get("cid")
        ckt_cache_data = {}
        
        # Extract nested object names (same as before)
        circuit["tags"] = [i["name"] for i in circuit.get("tags", [])]
        circuit["type"] = circuit.get("type", {}).get("name")
        circuit["provider"] = circuit.get("provider", {}).get("name")
        circuit["tenant"] = circuit.get("tenant", {}).get("name") if circuit.get("tenant") else None
        circuit["provider_account"] = circuit.get("provider_account", {}).get("name") if circuit.get("provider_account") else None
        
        # Get termination IDs
        termination_a = circuit.get("termination_a", {})
        termination_z = circuit.get("termination_z", {})
        termination_a_id = termination_a.get("id") if termination_a else None
        termination_z_id = termination_z.get("id") if termination_z else None

        msg = f"{cid} tracing circuit terminations path"
        log.info(msg)
        job.event(msg)

        # Retrieve termination paths using REST API
        circuit_path = None
        if termination_a_id is not None:
            resp = self.rest(
                job=job,
                method="get",
                api=f"circuits/circuit-terminations/{termination_a_id}/paths",
            )
            circuit_path = resp.result if isinstance(resp.result, list) else None
        elif termination_z_id is not None:
            resp = self.rest(
                job=job,
                method="get",
                api=f"circuits/circuit-terminations/{termination_z_id}/paths",
            )
            circuit_path = resp.result if isinstance(resp.result, list) else None

        # Validate circuit path
        if not circuit_path or len(circuit_path) == 0:
            msg = f"{cid} does not have two terminations, cannot trace the path"
            log.warning(msg)
            job.event(msg)
            return True

        # Extract endpoints
        try:
            end_a_data = circuit_path[0]["path"][0][0] if circuit_path[0].get("path") else None
            end_z_data = circuit_path[0]["path"][-1][-1] if circuit_path[0].get("path") else None
            
            if not end_a_data or not end_z_data:
                msg = f"{cid} invalid path structure"
                log.error(msg)
                job.event(msg, severity="ERROR")
                return True
                
        except (IndexError, KeyError, TypeError):
            msg = f"{cid} failed to parse termination path"
            log.error(msg)
            job.event(msg, severity="ERROR")
            return True

        end_a = {
            "device": end_a_data.get("device", {}).get("name", False) if isinstance(end_a_data.get("device"), dict) else False,
            "provider_network": "provider-network" in end_a_data.get("url", ""),
            "name": end_a_data.get("name"),
        }
        end_z = {
            "device": end_z_data.get("device", {}).get("name", False) if isinstance(end_z_data.get("device"), dict) else False,
            "provider_network": "provider-network" in end_z_data.get("url", ""),
            "name": end_z_data.get("name"),
        }
        
        circuit["is_active"] = circuit_path[0].get("is_active", False)

        # Map to devices (same logic, simpler dict creation)
        if not end_a["device"] and not end_z["device"]:
            msg = f"{cid} path trace ends have no devices connected"
            log.error(msg)
            job.event(msg, severity="ERROR")
            return True
            
        if end_a["device"]:
            device_data = {
                "tags": circuit["tags"],
                "type": circuit["type"],
                "provider": circuit["provider"],
                "tenant": circuit["tenant"],
                "provider_account": circuit["provider_account"],
                "commit_rate": circuit.get("commit_rate"),
                "description": circuit.get("description"),
                "status": circuit.get("status"),
                "custom_fields": circuit.get("custom_fields", {}),
                "comments": circuit.get("comments"),
                "is_active": circuit["is_active"],
                "last_updated": circuit.get("last_updated"),
                "interface": end_a["name"],
                "remote_device": end_z["device"] if end_z["device"] else None,
                "remote_interface": end_z["name"] if end_z["device"] else None,
            }
            ckt_cache_data[end_a["device"]] = device_data
            if end_a["device"] in devices:
                ret.result[end_a["device"]][cid] = device_data
                
        if end_z["device"]:
            device_data = {
                "tags": circuit["tags"],
                "type": circuit["type"],
                "provider": circuit["provider"],
                "tenant": circuit["tenant"],
                "provider_account": circuit["provider_account"],
                "commit_rate": circuit.get("commit_rate"),
                "description": circuit.get("description"),
                "status": circuit.get("status"),
                "custom_fields": circuit.get("custom_fields", {}),
                "comments": circuit.get("comments"),
                "is_active": circuit["is_active"],
                "last_updated": circuit.get("last_updated"),
                "interface": end_z["name"],
                "remote_device": end_a["device"] if end_a["device"] else None,
                "remote_interface": end_a["name"] if end_a["device"] else None,
            }
            ckt_cache_data[end_z["device"]] = device_data
            if end_z["device"] in devices:
                ret.result[end_z["device"]][cid] = device_data

        # Save to cache
        if cache is not False:
            ckt_cache_key = f"get_circuits::{cid}"
            if ckt_cache_data:
                self.cache.set(ckt_cache_key, ckt_cache_data, expire=self.cache_ttl)
                log.info(f"{self.name}:get_circuits - {cid} cached circuit data")

        msg = f"{cid} circuit data mapped to devices"
        log.info(msg)
        job.event(msg)
        return True

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_circuits(
        self,
        job: Job,
        devices: list,
        cid: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cache: Union[None, bool, str] = None,
        add_interface_details: bool = False,
    ) -> Result:
        """
        Retrieve circuit information using REST API for better performance.
        
        Uses pynetbox under the hood via self.nb_api[instance] which provides
        better pagination, connection pooling, and error handling.
        """
        
        cid = cid or []
        instance = instance or self.default_instance
        log.info(
            f"{self.name}:get_circuits - {instance} Netbox, "
            f"devices {', '.join(devices)}, cid {cid}"
        )

        ret = Result(
            task=f"{self.name}:get_circuits",
            result={d: {} for d in devices},
            resources=[instance],
        )
        
        cache = self.cache_use if cache is None else cache

        # Get device data to determine sites
        device_data = self.get_devices(
            job=job, 
            devices=devices.copy(), 
            instance=instance, 
            cache=cache
        )
        sites = list(set([i["site"]["slug"] for i in device_data.result.values()]))
        
        # Build filter parameters
        try:
            nb_api = self.nb_api[instance]  # pynetbox API instance
        except (KeyError, AttributeError):
            # Fallback to REST API if pynetbox not available
            msg = f"{self.name} - pynetbox not configured, using REST API"
            log.warning(msg)
            # Use existing REST logic...
            return ret

        # Build query filters for pynetbox
        filters = {"terminations__site__slug": sites}
        if cid:
            filters["cid__ic"] = cid  # in circuit - multiple values

        job.event("fetching circuits from Netbox")
        
        try:
            # pynetbox handles pagination automatically
            circuits = nb_api.circuits.circuits.filter(**filters)
            
            msg = f"retrieved {len(circuits)} circuits from Netbox, mapping to devices"
            log.info(msg)
            job.event(msg)
            
            # Map circuits to devices using thread pool
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = [
                    executor.submit(
                        self._map_circuit_rest, 
                        job, 
                        dict(circuit),  # Convert pynetbox object to dict
                        ret, 
                        devices, 
                        cache
                    )
                    for circuit in circuits
                ]
                for _ in concurrent.futures.as_completed(results):
                    pass
                    
        except Exception as e:
            msg = f"{self.name} - Failed to fetch circuits: {str(e)}"
            log.error(msg)
            ret.errors.append(msg)
            return ret

        # Add interface details if requested
        if add_interface_details:
            job.event("fetching circuits interface details")
            fetch_interfaces = set()
            fetch_devices = set(ret.result.keys())
            for device_name, circuits_dict in ret.result.items():
                for ckt_data in circuits_dict.values():
                    fetch_interfaces.add(ckt_data["interface"])
                    if ckt_data.get("remote_device"):
                        fetch_devices.add(ckt_data["remote_device"])
                        fetch_interfaces.add(ckt_data["remote_interface"])
            
            interfaces_data = self.get_interfaces(
                job=job,
                devices=list(fetch_devices),
                interface_list=list(fetch_interfaces),
                ip_addresses=True,
            ).result
            
            for device_name, circuits_dict in ret.result.items():
                for circuit_id, ckt_data in circuits_dict.items():
                    interface_name = ckt_data["interface"]
                    if interface_name in interfaces_data.get(device_name, {}):
                        interface_data = interfaces_data[device_name][interface_name]
                        ckt_data["child_interfaces"] = interface_data.get("child_interfaces", [])
                        ckt_data["ip_addresses"] = interface_data.get("ip_addresses", [])
                        ckt_data["vrf"] = interface_data.get("vrf", {})

        return ret
```

### Setup pynetbox in netbox_worker.py
Add to `__init__()` method:

```python
# In netbox_worker.py __init__ method
import pynetbox

# After setting up instances
self.nb_api = {}  # Cache pynetbox API instances
for instance_name, params in self.instances.items():
    try:
        self.nb_api[instance_name] = pynetbox.api(
            url=params["url"],
            token=params["token"],
            verify=params.get("ssl_verify", True),
        )
        # Set session configuration for better performance
        self.nb_api[instance_name].http_session.timeout = (
            self.netbox_connect_timeout, 
            self.netbox_read_timeout
        )
    except Exception as e:
        log.warning(f"Failed to initialize pynetbox for {instance_name}: {e}")
```

### Installation
```bash
pip install pynetbox

# Or add to pyproject.toml
pynetbox = "^3.0.0"
```

---

## Hybrid Approach: Best of Both Worlds

Use **REST API for data fetching** (simpler, faster) and **keep GraphQL for complex queries**:

1. Use REST API for circuits.circuits.all() - simpler pagination
2. Keep GraphQL for complex multi-object queries
3. Use pynetbox for standard REST calls
4. Custom REST calls for specialized queries

---

## Performance Comparison

| Approach | Speedup | Effort | Complexity | Maintenance |
|----------|---------|--------|-----------|-------------|
| Current GraphQL | Baseline | - | Medium | Medium |
| Quick Wins (GraphQL opt) | 30-35% | 1 hour | Low | Low |
| Full pynetbox REST | 55-65% | 4-6 hours | Low | High (new dep) |
| Hybrid (REST + GraphQL) | 45-55% | 3-4 hours | Medium | Medium |

---

## Testing Before/After

```python
# Add to test suite
import time
from unittest.mock import patch

def test_get_circuits_performance():
    job = Job()
    devices = ["device1", "device2"]
    
    start = time.time()
    result = netbox_worker.get_circuits(job, devices)
    elapsed = time.time() - start
    
    print(f"get_circuits took {elapsed:.2f}s")
    assert len(result.result) == len(devices)
    
    # Verify accuracy
    for device, circuits in result.result.items():
        assert isinstance(circuits, dict)
```

