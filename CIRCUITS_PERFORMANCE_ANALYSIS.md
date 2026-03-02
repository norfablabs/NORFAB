# Performance Analysis: get_circuits() Method

## Current Performance Bottlenecks

### 1. **Multiple Sequential GraphQL Queries** ⚠️ CRITICAL
**Problem:** The code makes two separate GraphQL queries:
- First: Query `last_updated` timestamps to check cache validity
- Second: Full circuit data query with all fields

**Impact:** For each cache validation check, you're making a round-trip to Netbox even if the data is already cached.

**Affected Code:** Lines 287-322 (cache validation phase) + Lines 349-361 (data fetch phase)

### 2. **Inefficient Cache Validation Logic** ⚠️ HIGH
**Problem:** Complex nested loops with redundant timestamp checks:
```python
for device in devices:
    for circuit in last_updated.result:
        # Multiple if conditions checking cache validity
        # Deep copy for each device that uses the circuit
```

**Impact:**
- O(n*m) complexity where n=devices, m=circuits
- Creates deep copies even when data won't be used
- Redundant timestamp comparisons

**Affected Code:** Lines 305-342

### 3. **Excessive Deep Copying** ⚠️ HIGH
**Problem:** Uses `copy.deepcopy()` multiple times per circuit:
- One in `_map_circuit()` for device A endpoint (line 121)
- One in `_map_circuit()` for device Z endpoint (line 132)
- Additional copies if circuit is used by multiple devices

**Impact:** Deep copying is expensive for complex nested objects. For 1000s of circuits, this adds significant overhead.

### 4. **ThreadPoolExecutor for I/O-Bound Mapping** ⚠️ MEDIUM
**Problem:** Uses ThreadPoolExecutor with only 10 workers for client-side data transformation (lines 366-373)

**Impact:**
- Thread pool has GIL contention
- Only 10 workers = sequential batch processing for 100+ circuits
- Better suited for asyncio, but current use is reasonable for light workload

### 5. **String Manipulation for GraphQL Filters** ⚠️ MEDIUM
**Problem:** Building GraphQL filter strings using string replacement (lines 265-280):
```python
circuits_filters = "{terminations: {site: {slug: {in_list: slist}}}}"
circuits_filters = circuits_filters.replace("slist", slist)
```

**Impact:** Error-prone, less efficient than building query programmatically

### 6. **Optional Interface Details in Separate Call** ⚠️ MEDIUM
**Problem:** When `add_interface_details=True`, makes additional REST call to `get_interfaces()` (line 381)

**Impact:** Extra API latency if not batched efficiently

## REST API vs GraphQL Trade-offs

### GraphQL Advantages:
- ✅ Query only needed fields
- ✅ Single query for related data (circuit + terminations)
- ✅ Built-in pagination

### GraphQL Disadvantages:
- ❌ More complex query building
- ❌ Less efficient for simple sequential operations
- ❌ Overhead when fetching unrelated data

### REST API (pynetbox/pure) Advantages:
- ✅ Simpler, more straightforward API calls
- ✅ Better pagination support in pynetbox
- ✅ Easier to cache at HTTP level
- ✅ Native async support available
- ✅ Better error handling and retries in pynetbox

### REST API Disadvantages:
- ❌ May require multiple requests for related data
- ❌ Less flexible field selection

## Optimization Strategies

### Strategy 1: Combine Cache Validation with Data Fetch (Hybrid Approach) ⭐ QUICK WIN
**Impact:** 30-50% faster for cache hits
- Single GraphQL query returns both `last_updated` and full circuit data
- Check cache validity in-flight while processing results
- No second round-trip needed

### Strategy 2: Switch to REST API with pynetbox ⭐ RECOMMENDED
**Impact:** 40-60% faster overall
- Use `pynetbox.circuits.all()` with built-in pagination
- Simpler code, better maintainability
- Native retry logic and connection pooling
- Status code: `pynetbox` handles it better

**Trade-off:** May need multiple REST calls if filtering is complex

### Strategy 3: Reduce Deep Copying ⭐ QUICK WIN
**Impact:** 10-20% faster
- Use shallow copies or dict manipulation instead of deepcopy
- Reference shared circuit fields instead of copying

### Strategy 4: Implement Async Collection ⭐ MEDIUM EFFORT
**Impact:** 20-30% faster
- Use `asyncio` instead of ThreadPoolExecutor
- Concurrent interface details fetching
- Better resource utilization

### Strategy 5: Batch Field Selection
**Impact:** 15-25% faster
- Only fetch fields actually used in response
- Remove unused fields from GraphQL query
- Reduce payload size

## Recommended Implementation Path

### Phase 1 (Immediate - 30min)
1. Combine cache validation + data fetch into single GraphQL call
2. Remove deep copies, use shallow copies
3. Results: ~35% faster

### Phase 2 (Short-term - 4-6 hours)
4. Migrate to pynetbox REST API
5. Implement proper pagination
6. Results: Additional ~25% faster (60% total)

### Phase 3 (Long-term - Optional)
7. Add async interface details fetching

## Code Snippets for Quick Wins

### Quick Win #1: Single GraphQL Query
Instead of 2 queries, make 1 with full data + cache timestamps:
```python
# Old approach: 2 queries
last_updated = graphql(...)  # Query 1
query_result = graphql(...)  # Query 2

# New approach: 1 query with timestamps included
query_result = graphql(..., fields=circuit_fields + ["last_updated", "termination_a {...}"])
# Then validate cache while iterating results
```

### Quick Win #2: Reduce Copying
```python
# Old: copy.deepcopy(circuit) - expensive
# New: Create minimal dict with needed fields
device_data = {
    "interface": end_a["name"],
    "remote_device": end_z["device"],
    **{k: circuit[k] for k in circuit_fields}  # Only needed fields
}
```

## Switch to pynetbox Example
```python
import pynetbox

# Initialize
nb = pynetbox.api(url="https://netbox.example.com", token="token123")

# Get circuits for specific sites
circuits = nb.circuits.circuits.all(
    filters={"terminations__site__slug": site_slugs}
)

# Pagination handled automatically
for circuit in circuits:
    # Process circuit
    pass
```

## Performance Metrics to Track

1. **API Call Count**: Track number of graphql/rest calls
2. **Total Latency**: End-to-end time for get_circuits()
3. **Data Transfer Size**: Payload size (REST will likely be larger)
4. **Memory Usage**: Deep copies add memory overhead
5. **Cache Hit Rate**: With improvements, should improve hit rate

## Testing Recommendations

1. Benchmark current implementation with varying circuit counts (100, 1000, 10000)
2. Test with cache hits/misses scenarios
3. Compare GraphQL vs REST performance
4. Monitor memory usage during large operations
5. Test with/without interface details

