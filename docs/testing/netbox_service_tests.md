# Netbox Service Tests

## Overview

The Netbox Service Tests (`test_netbox_service.py`) provide comprehensive testing coverage for NORFAB's Netbox integration service. These tests validate the Netbox worker's ability to interact with Netbox instances.

## Test Summary

The test suite is organized into 17 test classes:

| Test Class | Purpose | Documentation |
|-----------|---------|---------------|
| TestNetboxWorker | Core service discovery and version checks | [Details](#testnetboxworker) |
| TestNetboxGrapQL | GraphQL query operations | [Details](#testnetboxgrapql) |
| TestGetInterfaces | Interface retrieval and filtering | [Details](#testgetinterfaces) |
| TestGetDevices | Device retrieval and filtering | [Details](#testgetdevices) |
| TestGetConnections | Device connection queries | [Details](#testgetconnections) |
| TestGetNornirInventory | Nornir inventory generation from Netbox | [Details](#testgetnornirInventory) |
| TestGetCircuits | Circuit information retrieval | [Details](#testgetcircuits) |
| TestGetBgpPeerings | BGP peering data | [Details](#testgetbgppeerings) |
| TestSyncDeviceFacts | Device fact synchronization | [Details](#testsyncdevicefacts) |
| TestSyncDeviceInterfaces | Device interface synchronization | [Details](#testsyncdeviceinterfaces) |
| TestCreateDeviceInterfaces | Device interface creation | [Details](#testcreatedeviceinterfaces) |
| TestSyncDeviceIP | IP address synchronization | [Details](#testsyncdeviceip) |
| TestCreateIP | IP address creation | [Details](#testcreateip) |
| TestNetboxCache | Caching functionality | [Details](#testnetboxcache) |
| TestGetContainerlabInventory | Containerlab inventory generation | [Details](#testgetcontainerlabinventory) |
| TestCreatePrefix | IP prefix creation | [Details](#testcreateprefix) |
| TestCreateIPBulk | Bulk IP address creation | [Details](#testcreateipbulk) |

## Test Classes

### TestNetboxWorker

Core Netbox service functionality and health checks.

**Purpose**: Validate basic service operations, version compatibility, and status monitoring.

#### Test Get Netbox Inventory

::: tests.test_netbox_service.TestNetboxWorker.test_get_netbox_inventory

#### Test Get Netbox Version

::: tests.test_netbox_service.TestNetboxWorker.test_get_netbox_version

#### Test Get Netbox Status

::: tests.test_netbox_service.TestNetboxWorker.test_get_netbox_status

#### Test Get Netbox Compatibility

::: tests.test_netbox_service.TestNetboxWorker.test_get_netbox_compatibility

### TestNetboxGrapQL

GraphQL query operations against Netbox instances.

**Purpose**: Validate GraphQL query execution, dry-run mode, and error handling.

#### Test Graphql Query String

::: tests.test_netbox_service.TestNetboxGrapQL.test_graphql_query_string

#### Test Graphql Query String With Instance

::: tests.test_netbox_service.TestNetboxGrapQL.test_graphql_query_string_with_instance

#### Test Graphql Query String Dry Run

::: tests.test_netbox_service.TestNetboxGrapQL.test_graphql_query_string_dry_run

#### Test Graphql Query String Error

::: tests.test_netbox_service.TestNetboxGrapQL.test_graphql_query_string_error

#### Test Form Graphql Query Dry Run

::: tests.test_netbox_service.TestNetboxGrapQL.test_form_graphql_query_dry_run

### TestGetInterfaces

Interface retrieval and filtering operations.

**Purpose**: Validate device interface queries with various filters and parameters.

#### Test Get Interfaces

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces

#### Test Get Interfaces With Instance

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces_with_instance

#### Test Get Interfaces Dry Run

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces_dry_run

#### Test Get Interfaces Add Ip

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces_add_ip

#### Test Get Interfaces Add Inventory Items

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces_add_inventory_items

#### Test Get Interfaces With Interface Regex

::: tests.test_netbox_service.TestGetInterfaces.test_get_interfaces_with_interface_regex

### TestGetDevices

Device retrieval and advanced filtering.

**Purpose**: Validate comprehensive device queries with filtering, selection, and data structure validation.

#### Test With Devices List

::: tests.test_netbox_service.TestGetDevices.test_with_devices_list

#### Test With Filters

::: tests.test_netbox_service.TestGetDevices.test_with_filters

#### Test With Filters Dry Run

::: tests.test_netbox_service.TestGetDevices.test_with_filters_dry_run

#### Test Get Devices Cache

::: tests.test_netbox_service.TestGetDevices.test_get_devices_cache

### TestGetConnections

Device connection and cable management queries.

**Purpose**: Validate device connection retrieval and relationship mapping.

#### Test Get Connections

::: tests.test_netbox_service.TestGetConnections.test_get_connections

#### Test Get Connections Physical Interface Regex

::: tests.test_netbox_service.TestGetConnections.test_get_connections_physical_interface_regex

#### Test Get Connections Virtual Interface Regex

::: tests.test_netbox_service.TestGetConnections.test_get_connections_virtual_interface_regex

#### Test Get Connections Dry Run

::: tests.test_netbox_service.TestGetConnections.test_get_connections_dry_run

#### Test Get Connections And Cables

::: tests.test_netbox_service.TestGetConnections.test_get_connections_and_cables

### TestGetNornirInventory

Nornir inventory generation from Netbox data.

**Purpose**: Validate conversion of Netbox data into Nornir-compatible inventory format.

#### Test With Devices

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices

#### Test With Filters

::: tests.test_netbox_service.TestGetNornirInventory.test_with_filters

#### Test Source Platform From Config Context

::: tests.test_netbox_service.TestGetNornirInventory.test_source_platform_from_config_context

#### Test With Devices Nbdata Is True

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices_nbdata_is_true

#### Test With Devices Add Interfaces

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices_add_interfaces

#### Test With Devices Add Interfaces With Ip And Inventory

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices_add_interfaces_with_ip_and_inventory

#### Test With Devices Add Connections

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices_add_connections

#### Test With Devices Add Bgp Peerings

::: tests.test_netbox_service.TestGetNornirInventory.test_with_devices_add_bgp_peerings

### TestGetCircuits

Circuit information retrieval from Netbox.

**Purpose**: Validate circuit data queries and filtering.

#### Test Get Circuits Dry Run

::: tests.test_netbox_service.TestGetCircuits.test_get_circuits_dry_run

#### Test Get Circuits

::: tests.test_netbox_service.TestGetCircuits.test_get_circuits

#### Test Get Circuits By Cid

::: tests.test_netbox_service.TestGetCircuits.test_get_circuits_by_cid

#### Test Get Circuits Cache

::: tests.test_netbox_service.TestGetCircuits.test_get_circuits_cache

#### Test Get Circuits Cache Content

::: tests.test_netbox_service.TestGetCircuits.test_get_circuits_cache_content

### TestGetBgpPeerings

BGP peering information retrieval.

**Purpose**: Validate BGP peering data extraction and filtering.

#### Test Get Bgp Peerings

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings

#### Test Get Bgp Peerings With Instance

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_with_instance

#### Test Get Bgp Peerings Nonexistent Device

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_nonexistent_device

#### Test Get Bgp Peerings Empty Devices List

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_empty_devices_list

#### Test Get Bgp Peerings Cache True

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_cache_true

#### Test Get Bgp Peerings Cache Refresh

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_cache_refresh

#### Test Get Bgp Peerings Cache Force

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_cache_force

#### Test Get Bgp Peerings Cache False

::: tests.test_netbox_service.TestGetBgpPeerings.test_get_bgp_peerings_cache_false

### TestSyncDeviceFacts

Device fact synchronization from external sources to Netbox.

**Purpose**: Validate pushing collected device facts (from Nornir) back to Netbox.

#### Test Sync Device Facts Basic Update

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_basic_update

#### Test Sync Device Facts Already In Sync

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_already_in_sync

#### Test Sync Device Facts With Filters

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_filters

#### Test Sync Device Facts Dry Run

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_dry_run

#### Test Sync Device Facts With Diff

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_diff

#### Test Sync Device Facts With Branch

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_branch

#### Test Sync Device Facts With Custom Instance

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_custom_instance

#### Test Sync Device Facts With Batch Size

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_batch_size

#### Test Sync Device Facts With Timeout

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_with_timeout

#### Test Sync Device Facts Non Existing Device

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_non_existing_device

#### Test Sync Device Facts Empty Device List

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_empty_device_list

#### Test Sync Device Facts Single Device

::: tests.test_netbox_service.TestSyncDeviceFacts.test_sync_device_facts_single_device

### TestSyncDeviceInterfaces

Interface status and configuration synchronization.

**Purpose**: Validate pushing interface data from network devices to Netbox.

#### Test Sync Device Interfaces

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces

#### Test Sync Device Interfaces Dry Run

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces_dry_run

#### Test Sync Device Interfaces Create

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces_create

#### Test Sync Device Interfaces Update

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces_update

#### Test Sync Device Interfaces Non Existing Device

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces_non_existing_device

#### Test Sync Device Interfaces With Branch

::: tests.test_netbox_service.TestSyncDeviceInterfaces.test_sync_device_interfaces_with_branch

### TestCreateDeviceInterfaces

Device interface creation in Netbox.

**Purpose**: Validate programmatic interface creation and configuration.

#### Test Create Device Interfaces Single

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_single

#### Test Create Device Interfaces Multiple Devices

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_multiple_devices

#### Test Create Device Interfaces With Range Numeric

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_with_range_numeric

#### Test Create Device Interfaces With Range List

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_with_range_list

#### Test Create Device Interfaces With Multiple Ranges

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_with_multiple_ranges

#### Test Create Device Interfaces Multiple Names List

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_multiple_names_list

#### Test Create Device Interfaces Skip Existing

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_skip_existing

#### Test Create Device Interfaces Dry Run

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_dry_run

#### Test Create Device Interfaces With Branch

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_with_branch

#### Test Create Device Interfaces Non Existing Device

::: tests.test_netbox_service.TestCreateDeviceInterfaces.test_create_device_interfaces_non_existing_device

### TestSyncDeviceIP

IP address and interface IP synchronization.

**Purpose**: Validate IP address assignment and synchronization to device interfaces.

#### Test Sync Device Ip

::: tests.test_netbox_service.TestSyncDeviceIP.test_sync_device_ip

#### Test Sync Device Ip Dry Run

::: tests.test_netbox_service.TestSyncDeviceIP.test_sync_device_ip_dry_run

#### Test Sync Device Ip With Branch

::: tests.test_netbox_service.TestSyncDeviceIP.test_sync_device_ip_with_branch

### TestCreateIP

IP address creation in Netbox.

**Purpose**: Validate IP address allocation and creation.

#### Test Create Ip By Prefix

::: tests.test_netbox_service.TestCreateIP.test_create_ip_by_prefix

#### Test Create Ip By Prefix Description

::: tests.test_netbox_service.TestCreateIP.test_create_ip_by_prefix_description

#### Test Create Ip By Prefix Multiple

::: tests.test_netbox_service.TestCreateIP.test_create_ip_by_prefix_multiple

#### Test Create Ip Nonexist Prefix

::: tests.test_netbox_service.TestCreateIP.test_create_ip_nonexist_prefix

#### Test Create Ip By Prefix Device Interface

::: tests.test_netbox_service.TestCreateIP.test_create_ip_by_prefix_device_interface

#### Test Create Ip By Prefix Description Device Interface

::: tests.test_netbox_service.TestCreateIP.test_create_ip_by_prefix_description_device_interface

#### Test Create Ip With Vrf Tags Tenant Role Dnsname Comments

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_vrf_tags_tenant_role_dnsname_comments

#### Test Create Ip Non Existing Device

::: tests.test_netbox_service.TestCreateIP.test_create_ip_non_existing_device

#### Test Create Ip Non Existing Interface

::: tests.test_netbox_service.TestCreateIP.test_create_ip_non_existing_interface

#### Test Create Ip Is Primary

::: tests.test_netbox_service.TestCreateIP.test_create_ip_is_primary

#### Test Create Ip Dry Run New Ip

::: tests.test_netbox_service.TestCreateIP.test_create_ip_dry_run_new_ip

#### Test Create Ip Dry Run Existing Ip

::: tests.test_netbox_service.TestCreateIP.test_create_ip_dry_run_existing_ip

#### Test Create Ip With Nb Instance

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_nb_instance

#### Test Create Ip With Branch

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_branch

#### Test Create Ip With Mask Len

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_mask_len

#### Test Create Ip With Mask Len Dry Run

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_mask_len_dry_run

#### Test Create Ip Check Create Peer Ip

::: tests.test_netbox_service.TestCreateIP.test_create_ip_check_create_peer_ip

#### Test Create Ip Check Create Peer Ip With Branch

::: tests.test_netbox_service.TestCreateIP.test_create_ip_check_create_peer_ip_with_branch

#### Test Create Ip Check Skip Create Peer Ip

::: tests.test_netbox_service.TestCreateIP.test_create_ip_check_skip_create_peer_ip

#### Test Create Ip Use Peer Ip

::: tests.test_netbox_service.TestCreateIP.test_create_ip_use_peer_ip

#### Test Create Ip With Link Peer Dry Run

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_link_peer_dry_run

#### Test Create Ip With Link Peer Within Parent

::: tests.test_netbox_service.TestCreateIP.test_create_ip_with_link_peer_within_parent

### TestNetboxCache

Caching functionality and cache management.

**Purpose**: Validate cache operations for improved query performance.

#### Test Cache List

::: tests.test_netbox_service.TestNetboxCache.test_cache_list

#### Test Cache List Details

::: tests.test_netbox_service.TestNetboxCache.test_cache_list_details

#### Test Cache List Filter

::: tests.test_netbox_service.TestNetboxCache.test_cache_list_filter

#### Test Cache Clear All

::: tests.test_netbox_service.TestNetboxCache.test_cache_clear_all

#### Test Cache Clear Key

::: tests.test_netbox_service.TestNetboxCache.test_cache_clear_key

#### Test Cache Get Key

::: tests.test_netbox_service.TestNetboxCache.test_cache_get_key

#### Test Cache Get Keys

::: tests.test_netbox_service.TestNetboxCache.test_cache_get_keys

#### Test Cache False

::: tests.test_netbox_service.TestNetboxCache.test_cache_false

#### Test Cache Refresh

::: tests.test_netbox_service.TestNetboxCache.test_cache_refresh

### TestGetContainerlabInventory

Containerlab topology generation from Netbox.

**Purpose**: Validate containerlab topology file generation from Netbox inventory.

#### Test Get Containerlab Inventory Devices

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_devices

#### Test Get Containerlab Inventory Non Existing Devices

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_non_existing_devices

#### Test Get Containerlab Inventory By Tenant

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_by_tenant

#### Test Get Containerlab Inventory By Filters

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_by_filters

#### Test Get Containerlab Inventory With Nb Instance

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_with_nb_instance

#### Test Get Containerlab Inventory With Image

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_with_image

#### Test Get Containerlab Inventory Run Out Of Ports

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_run_out_of_ports

#### Test Get Containerlab Inventory Run Out Of Ips

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_run_out_of_ips

#### Test Get Containerlab Inventory With Ports Map

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_with_ports_map

#### Test Get Containerlab Inventory With Cache

::: tests.test_netbox_service.TestGetContainerlabInventory.test_get_containerlab_inventory_with_cache

### TestCreatePrefix

IP prefix creation and management.

**Purpose**: Validate IP prefix allocation and creation.

#### Test Create Prefix

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix

#### Test Create Prefix Multiple

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_multiple

#### Test Create Prefix Non Exist Parent

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_non_exist_parent

#### Test Create Prefix With Vrf

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_with_vrf

#### Test Create Prefix With Parent Vrf Mismatch

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_with_parent_vrf_mismatch

#### Test Create Prefix By Parent Prefix Name

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_by_parent_prefix_name

#### Test Create Prefix Within Vrf By Parent Prefix Name

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_within_vrf_by_parent_prefix_name

#### Test Create Prefix Dry Run Empty Parent

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_dry_run_empty_parent

#### Test Create Prefix Dry Run Parent Has Children

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_dry_run_parent_has_children

#### Test Create Prefix Dry Run Prefix Exists

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_dry_run_prefix_exists

#### Test Create Prefix Test Length Mismatch

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_test_length_mismatch

#### Test Create Prefix With Attributes

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_with_attributes

#### Test Create Prefix With Attributes Updates

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_with_attributes_updates

#### Test Create Prefix With Branch

::: tests.test_netbox_service.TestCreatePrefix.test_create_prefix_with_branch

### TestCreateIPBulk

Bulk IP address creation operations.

**Purpose**: Validate efficient bulk IP creation for large datasets.

#### Test Create Ip Bulk

::: tests.test_netbox_service.TestCreateIPBulk.test_create_ip_bulk

## Test Execution

### Configuration

Netbox tests require configuration in `netbox_data.py`:

```python
NB_URL = "http://netbox-instance:8000"
NB_API_TOKEN = "your-api-token"
```

Tests operate against three Netbox instances configured in inventory: **dev**, **preprod**, and **prod**.

### Running Tests

```bash
# Run all Netbox tests
pytest tests/test_netbox_service.py -v

# Run specific test class
pytest tests/test_netbox_service.py::TestGetDevices -v

# Run specific test method
pytest tests/test_netbox_service.py::TestGetDevices::test_get_devices_with_filters -v
```

## Test Utilities

Helper functions available in test file:

- `get_nb_version(nfclient, instance=None)` - Get Netbox version
- `delete_branch(branch, nfclient)` - Delete transaction branch
- `delete_interfaces(nfclient, device, interface)` - Delete interface
- `delete_prefixes_within(prefix, nfclient)` - Delete prefix subtree
- `delete_ips(prefix, nfclient)` - Delete IPs in prefix
- `get_pynetbox(nfclient)` - Get pynetbox API instance

## Troubleshooting

- **Connection errors**: Verify Netbox is running and `netbox_data.py` is configured correctly
- **Fixture timeout**: Increase sleep time in fixture if workers need more time to start
- **Cache issues**: Clear cache between test runs if stale data is observed
- **Branch isolation**: Always delete test branches after use to prevent state pollution

## Related Documentation

- [Netbox Service Overview](../workers/netbox/services_netbox_service.md)
- [Netbox Service Tasks](../workers/netbox/services_netbox_service_tasks_rest.md)
- [NORFAB Testing Framework](norfab_testing_framework.md)
- [Netbox Worker API Reference](../workers/netbox/api_reference_workers_netbox_worker.md)
