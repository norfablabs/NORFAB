# NORFAB Testing Framework

## Overview

NORFAB employs a comprehensive testing framework built on **pytest** to ensure code quality, functionality, and reliability across all components. The testing infrastructure includes unit tests, integration tests, and service-specific tests that validate the core framework, workers, and client implementations.

## Testing Architecture

### Test Organization

The NORFAB testing framework is organized as follows:

- **Core Tests** (`tests/core/`): Tests for fundamental NORFAB components
  - `test_nfapi.py` - NFAPI (Python API) tests
  - `test_client.py` - Client functionality tests
  - `test_worker.py` - Worker base class tests
  - `test_simple_inventory_datastore.py` - Inventory datastore tests

- **Service Tests** (root `tests/` directory): Tests for service workers
  - `test_containerlab_service.py` - Containerlab service tests
  - `test_nornir_service.py` - Nornir service tests
  - `test_netbox_service.py` - Netbox service tests
  - `test_fastapi_service.py` - FastAPI service tests
  - `test_fastmcp_service.py` - FastMCP service tests
  - `test_workflow_service.py` - Workflow service tests
  - `test_dummy_service_plugin.py` - Plugin service tests

### Test Support Files

- **`conftest.py`** - Pytest fixtures for test initialization and teardown
- **`netbox_data.py`** - Netbox instance configuration and test data
- **`nf_tests_inventory/`** - Test inventory files used across test suites

## Testing Framework

### pytest Fixtures

The testing framework uses pytest fixtures to manage test lifecycle:

#### NorFab Client Fixture (`nfclient`)

Creates a NorFab instance with test inventory, starts all workers, and provides a client object:

```python
@pytest.fixture(scope="class")
def nfclient():
    """Fixture to start NorFab and return client object"""
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)  # wait for workers to start
    yield nf.make_client()  # return nf client
    nf.destroy()  # teardown
```

**Scope**: Class-level (single instance per test class)
**Teardown**: Automatically destroys NorFab instance after tests complete

#### Dictionary-based Inventory Fixture (`nfclient_dict_inventory`)

Creates a NorFab instance using a programmatically defined inventory dictionary:

```python
@pytest.fixture(scope="class")
def nfclient_dict_inventory():
    """Fixture to start NorFab with dict inventory"""
    data = {
        "broker": {"endpoint": "tcp://127.0.0.1:5555", ...},
        "topology": {"broker": True, "workers": [...]},
        "workers": {...}
    }
    nf = NorFab(inventory_data=data, base_dir="./nf_tests_inventory/")
    nf.start()
    time.sleep(3)
    yield nf.make_client()
    nf.destroy()
```

**Use Case**: Testing with custom worker configurations and topology definitions

#### PICLE Shell Fixture (`picle_shell`)

Initializes the PICLE shell client for interactive testing:

```python
@pytest.fixture(scope="class")
def picle_shell():
    """Fixture for PICLE shell testing"""
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)
    NFCLIENT = nf.make_client()
    builtins.NFCLIENT = NFCLIENT
    shell = App(NorFabShell, stdin=mock_stdin, stdout=mock_stdout)
    mount_shell_plugins(shell, nf.inventory)
    yield shell, mock_stdout
    nf.destroy()
```

**Use Case**: Testing NFCLI shell client functionality

## Writing Tests

### Test Structure

Tests follow standard pytest conventions with class-based organization:

```python
import pytest

class TestServiceName:
    def test_specific_functionality(self, nfclient):
        # Arrange
        # Act
        ret = nfclient.run_job("service", "task", workers="any")
        
        # Assert
        assert not ret.errors
        assert "expected_key" in ret.result
```

### Common Testing Patterns

#### Running a Job

All service tests interact with NORFAB through the client's `run_job()` method:

```python
ret = nfclient.run_job(
    service_name,  # service name (e.g., "netbox", "nornir")
    task_name,     # task name
    workers="any", # worker filter
    kwargs={...}   # task-specific parameters
)
```

**Response Structure**:
```python
{
    "worker_name": {
        "errors": [],           # List of error messages
        "result": {...},        # Task result data
        "task_id": "uuid",      # Task identifier
        "status": "done"        # Task status
    }
}
```

#### Assertions

Common assertion patterns in tests:

```python
# Check for no errors
assert not res["errors"]

# Validate response structure
assert all(k in res["result"] for k in ["expected", "keys"])

# Check specific values
assert res["result"]["status"] == "success"
assert len(res["result"]["items"]) > 0
```

## Test Dependencies

The testing framework requires:

- **pytest** - Testing framework and runner
- **pyyaml** - Inventory file parsing
- **pyzmq** - ZeroMQ communication for NorFab
- **All service dependencies** - Nornir, Netbox, Containerlab, etc.

Install test dependencies:

```bash
poetry install  # Install all dependencies including optional ones
```

## Running Tests

### Run All Tests

```bash
pytest tests/
```

### Run Specific Test File

```bash
pytest tests/test_netbox_service.py
```

### Run Specific Test Class

```bash
pytest tests/test_netbox_service.py::TestNetboxWorker
```

### Run Specific Test Method

```bash
pytest tests/test_netbox_service.py::TestNetboxWorker::test_get_devices
```

### Run with Verbose Output

```bash
pytest tests/ -v
```
## Test Inventory

The test inventory is located in `tests/nf_tests_inventory/` and defines:

- **Broker configuration** - ZeroMQ endpoint and shared key
- **Worker topology** - Worker names and assignments
- **Worker configurations** - Service and plugin definitions
- **Service inventories** - Service-specific configuration files

### Inventory Files

- `inventory.yaml` - Main inventory file
- `nornir/` - Nornir service configurations
- `nf_containerlab/` - Containerlab test environments

## Test Setup and Teardown

### Automatic Cleanup

All fixtures use class-level scope with automatic teardown:

1. **Setup Phase**: 
   - Create NorFab instance
   - Load inventory
   - Start broker
   - Start workers
   - Wait for initialization

2. **Test Phase**: 
   - Run individual test methods
   - Reuse same NorFab instance across tests

3. **Teardown Phase**: 
   - Destroy NorFab instance
   - Clean up worker connections
   - Release resources

## Best Practices

### 1. Use Appropriate Fixtures

Choose the right fixture for your test type:
- `nfclient` - General service testing
- `nfclient_dict_inventory` - Custom topology testing
- `picle_shell` - CLI client testing

### 2. Wait for Worker Readiness

Always allow time for workers to initialize:

```python
@pytest.fixture(scope="class")
def nfclient():
    nf = NorFab(...)
    nf.start()
    time.sleep(3)  # Critical for worker initialization
    yield nf.make_client()
    nf.destroy()
```

### 3. Validate Response Structure

Always check for errors and expected keys:

```python
assert not res["errors"]
assert all(k in res["result"] for k in expected_keys)
```

### 4. Use Descriptive Test Names

Test method names should clearly indicate what is being tested:

```python
def test_create_device_with_valid_data(self, nfclient):
    """Test creating a device with valid Netbox data"""
    pass

def test_handle_invalid_device_data(self, nfclient):
    """Test error handling for invalid device data"""
    pass
```

### 5. Clean Up Test Data

Always clean up created resources to prevent test interference:

```python
def test_create_and_cleanup(self, nfclient):
    # Create test data
    create_result = nfclient.run_job(...)
    
    try:
        # Test operations
        assert create_result["success"]
    finally:
        # Always cleanup
        cleanup_result = nfclient.run_job(...)
        assert not cleanup_result["errors"]
```

### 6. Mock External Dependencies

For tests requiring external services (Netbox, Containerlab):

```python
import unittest.mock

@unittest.mock.patch('external_service.api')
def test_with_mocked_service(self, mock_api, nfclient):
    mock_api.return_value = {"status": "ok"}
    # Test with mocked service
    pass
```

## Continuous Integration

The testing framework supports CI/CD pipelines:

```bash
# Run tests with coverage report
pytest tests/ --cov=norfab --cov-report=html

# Run tests with JUnit XML output
pytest tests/ --junit-xml=test-results.xml

# Run tests with specific markers
pytest tests/ -m "not integration"
```

## Troubleshooting

### Worker Startup Timeout

If workers fail to start within the 3-second wait:

```python
time.sleep(5)  # Increase wait time
```

### Import Errors

Ensure all dependencies are installed:

```bash
poetry install  # Install all optional dependencies
```

### Port Conflicts

Multiple test runs may conflict on ZeroMQ ports. Clear stale processes:

```bash
lsof -i :5555  # Find process using port 5555
kill -9 <PID>  # Kill process
```

### Worker Connection Issues

Check worker status using the MMI service:

```python
status = nfclient.get("mmi.service.broker", "show_workers")
```

## Related Documentation

- [NORFAB Getting Started](../norfab_getting_started.md)
- [NORFAB Architecture](../reference_architecture_norfab.md)
- [Services and Workers Documentation](../services_overview.md)
- [Service Plugin Development](../customization/service_plugin_overview.md)
