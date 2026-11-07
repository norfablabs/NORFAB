# Feature Specification: NorFab State Service (NSS)

**Feature Branch**: No feature branch created.

**Created**: 2026-11-07

**Status**: Draft. Specification acceptance pending. Implementation: not implemented.

**Input**: Derive confirmed behavior from the [original ADR](../../adr/adr_service_owned_configuration_graph.md), preserving that file and keeping its proposals separate.

**Service**: NorFab State Service (NSS), registered as `nss`, with worker class `NssWorker` and example instance name `nss-worker-1`. NSS holds graph data. Device configuration, network-service associations, and reconciliation are broader planned use cases, not a restriction on the data it can represent. Initial implementation covers the graph baseline, sync_from, and generic CRUD only. A network service instance represented in the graph is distinct from the NorFab NSS worker service.

**Design artifacts**: [Implementation plan](plan.md), [research](research.md), [data model](data-model.md), [task contracts](contracts/nss-tasks.md), and [validation guide](quickstart.md). These describe proposed implementation, not delivered functionality. The structural mapping decisions below supersede the earlier flattening/name-key design. The plan, data model, contracts, quickstart, and tasks are aligned to these decisions. All remain proposed and unimplemented.

## Initial Implementation Scope

The initial implementation is limited to the baseline NSS worker and persistent graph storage, `sync_from` for supplied XML, and generic node/relationship CRUD. CRUD supports arbitrary graph data through contextual traversal, rather than device-specific tasks such as `delete_device`.

The plan and contracts target this milestone only. Network service definitions, ownership/dependency behavior, drift detection, reconciliation plans/application, sync to devices, and device transport integration are deferred. Their requirements below remain the broader feature definition, not initial acceptance obligations. Do not implement their tables, task modules, tests, or client commands in this milestone. Dedicated NFCLI/NFWeb interfaces are also deferred. Standard worker inventory/version tasks and existing job routing/discovery are part of the baseline.

Initial acceptance covers worker lifecycle/persistence, generic node and relationship CRUD, and XML merge/replacement with namespace, unchanged-value, presence, preserved-container, and unordered-collection semantics. No static entity-key mappings or inferred semantic keys are required. See [initial task contracts](contracts/nss-tasks.md) and [validation guide](quickstart.md). Implementation has not started.

## Clarifications

### Session 2026-11-07

- Q: Should the first release retain a complete history of desired configuration, service definitions, ownership, dependencies, and deletions? -> A: Keep current state only. History, rollback, and time travel are later additions. Account for their future addition in the initial design where practical, without implementing them in the first release.
- Q: When a service update overrides a value required by another service, should the affected service be marked inconsistent? -> A: Accept the update and mark services with contradicted requirements inconsistent. Do not automatically reapply their values.
- Q: Which device and protocol scope should the first release support? -> A: NETCONF and OpenConfig are later device-integration validation targets, outside the initial graph-only milestone. Graph-service ingestion uses pluggable format support independent of transport, platform, model, and schema. The first iteration supports arbitrary XML, with JSON support added later.
- Q: How should XML configuration be represented in the graph? -> A: Convert XML to a dictionary using xmltodict, then translate the dictionary tree into a graph tree rooted at the supplied device name. Preserve dictionary containers and parent-child relationships. This supersedes the earlier flattened device-to-entity-to-leaf design. Separate node identities and stored full-path identifiers are not required.
- Q: How should ingestion determine which child values identify repeated entries in arbitrary XML? -> A: Do not require semantic entity keys for structural ingestion. Field/tag names label nodes, arrays contain separate entry nodes, and name remains ordinary source data. Static mappings and name-based entity matching are not part of initial ingestion.
- Q: When importing configuration for an existing device, should omitted configuration be removed from the graph or left unchanged? -> A: Merge by default, preserving omitted configuration. Support explicit whole-device replacement that removes omitted configuration.
- Q: What should happen if desired state or device configuration changes after a reconciliation plan is generated but before it is applied? -> A: Assume this cannot happen for now. Initial operation requires both sides to remain unchanged between plan generation and application. Stale-plan handling is deferred.
- Q: If applying a device reconciliation plan fails after some changes have succeeded, what should the first release do? -> A: Stop on failure. Report completed, failed, and unattempted operations, and require a new comparison and plan. Do not automatically retry or roll back.
- Q: When a service owns a parent node, should that ownership also cover its descendant configuration nodes? -> A: No. Link the service directly to each node it owns. Ownership does not implicitly extend to children or other descendants. The service-to-node relationship can carry properties indicating the type of ownership.
- Q: After applying a device plan successfully, should the system automatically read the device again and verify it matches desired state? -> A: No. Assume successful operations mean configuration matches. Do not automatically read back or compare after application.
- Q: Should the first release support only owns and depends_on as service-to-node relationship types? -> A: Yes. Owns identifies configuration the service manages, eligible for removal only when no surviving service needs it. Depends_on identifies configuration the service needs but does not own. Both apply only to directly linked nodes.
- Q: How should imports handle repeated XML entries whose name child is missing or duplicated under the same parent? -> A: Represent repeated entries as separate nodes in a collection, including unnamed entries and duplicates. Representation does not require unique entity names. Stable semantic matching across changed collections is a separate future concern.
- Q: Should XML namespaces distinguish nodes whose tags have the same local name? -> A: Use namespace URI plus local tag name as the node type. Different prefixes for the same namespace URI identify the same type. Equal local names in different namespace URIs remain distinct.
- Q: Should the first release preserve leaf values as supplied, without inferring numbers, booleans, or defaults from a schema? -> A: Preserve leaf values as supplied, without type conversion or inference. Distinguish an empty element from an absent element. Do not add defaults.

- Q: Should changing only the order of named sibling entities count as configuration drift? -> A: No. Object fields are selected within their parent context. Arrays are unordered collections of separate entries; duplicate multiplicity is preserved. Reordering alone is not a structural difference.

- Q: Should NSS preserve dictionary containers as graph nodes or flatten wrappers? -> A: Preserve dictionary containers as graph nodes. This supersedes the earlier flattening choice after reviewing the real device XML/JSON samples. Flattened views may be considered later; they do not define stored structure.

- Q: How should CRUD operations select entries in a collection when those entries have no unique names? -> A: Select by field/value filters without static key mappings or public node IDs. Individual updates and deletes require exactly one match and fail without mutation on zero or multiple matches. Identical duplicates can be managed by replacing the collection.

- Q: Should node updates leave omitted fields unchanged and treat an explicitly supplied null value as clearing the leaf value? -> A: Yes. Omitted fields remain unchanged. Explicit value=null sets a present null value. Supplied property keys merge into existing properties without type conversion.

- Q: Should creating a named root require only its name, with no parent or child-node payload? -> A: Yes. Create a root using create_node(root="example", parent=null, node=null). Creating an existing root returns an error without changes. Child creation requires an existing parent selector and a node payload.

- Q: When an XML element changes from one occurrence to several, should its stored field change from an object to a collection? -> A: Yes. Preserve the shape produced by xmltodict. One occurrence is an object or scalar; repeated occurrences form a collection. A supplied shape change replaces that field's subtree and removes incident links to removed nodes, without inferring entity keys.

- Q: Should collection-entry filters support exact matches on nested fields, with all supplied conditions required to match? -> A: Support exact equality on direct fields only, with all supplied conditions required to match. Nested-field filters and broader query operators are outside initial scope.

- Q: How should CRUD select scalar collection entries? -> A: Allow exact, type-preserving selection by the entry value, with exactly one match required for individual mutations.

## Structural Representation and Sample Findings

The captures at `tests/nf_tests_inventory/ceos-spine-1.config.xml` and `tests/nf_tests_inventory/ceos-spine-1.config.json` are review references. They include NorFab result envelopes around configuration data. They are not both raw XML/JSON device payloads: the .xml file contains a Python dictionary representation whose get_config value is XML. Do not evaluate or ingest that representation as XML. Extract the actual configuration payload in test/example preparation without adding device collection to NSS.

The samples contain entities keyed in their source models by name, index, ip, interface-id, and compound fields. Some singleton config objects also contain name. Therefore neither a name field nor repetition reliably identifies an entity boundary without model knowledge. The JSON also contains XML-derived leaf objects with #text and attributes.

Use a structural representation instead:

| Source structure | Stored graph representation |
| --- | --- |
| Named root | Root node using the caller-supplied name. |
| Object field | Named object/container node with direct links to its fields. Preserve containers such as interfaces, config, ipv4, and ipv6. |
| Array field | Named collection node with a separate child node for every entry. Object entries may share a type/name and need no semantic name. |
| Scalar field or array entry | Leaf/entry node holding the original scalar value. |
| Explicit null or empty XML element | Present node with null value, distinct from a missing field. |
| XML text with attributes | Leaf value and separate attribute metadata when the object contains only text/attributes. Preserve attributes on container nodes when children are present. |

For example, repeated interfaces are stored as device -> interfaces object -> interface collection -> interface entry -> config object -> mtu leaf. A singleton interface follows the object shape produced by xmltodict instead of inventing a collection. The interface entry also links to its ordinary name leaf. Node labels need not be unique among collection entries. Private database storage handles distinguish records, but they are not domain identities, full-path keys, or inferred source-model identifiers.

During merge, supplied object fields of the same shape are merged recursively and omitted object fields remain. A supplied change of field shape replaces only that field subtree, as defined in FR-029. A supplied array replaces that collection's entries as a whole; an omitted array remains unchanged. Explicit root replacement removes all omitted fields. Replacing a collection does not promise stable entry-node associations across syncs; incident generic links to replaced entries are removed according to normal graph-deletion rules, while links between surviving nodes remain.

A structural diff is possible without entity mappings: compare object field names, scalar types/values, and arrays as unordered collections with duplicate counts. A changed array object may be reported as a removed entry plus an added entry. Reporting an entity-specific update such as Ethernet1 MTU changed requires additional matching knowledge and is deferred. No diff task is added to the initial implementation milestone. Caller-supplied CRUD filters are exact direct-field selection conditions, not inferred semantic entity keys or a promise of stable identity across syncs.

Initial sync_from input remains XML converted through xmltodict inside NssWorker methods. The JSON file demonstrates the internal structural model and is not authorization to add a public JSON input format in this milestone. Preserve namespace distinctions, XML attributes, text values, and dictionary-level structure; lexical XML and mixed-content ordering fidelity are not promised.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish and compare desired configuration (Priority: P1)

An operator imports device configuration as desired state and identifies later drift without changing either side.

**Why this priority**: A trusted baseline is needed before deciding what to change.

**Independent Test**: Import configuration, change a device value, and compare. Inspect both states afterward.

**Acceptance Scenarios**:

1. **Given** supported device configuration, **When** it is imported, **Then** configuration items and relationships become the device's desired state.
2. **Given** drift from desired state, **When** comparison runs, **Then** it identifies differences without importing observations or modifying the device.
3. **Given** matching configurations, **When** comparison runs, **Then** no corrective operations are needed.
4. **Given** XML supplied directly rather than collected through NETCONF, **When** it is ingested, **Then** graph representation does not require a platform, model, or schema. The supplied device name roots the graph. Preserve the interfaces object, the interface collection when repeated, separate entries, config containers, and MTU leaves without requiring entity-key mappings. A singleton interface follows the source object shape.
5. **Given** an existing device tree, **When** configuration is imported without selecting replacement, **Then** supplied object fields are added or updated, omitted object fields remain unchanged, and each supplied collection replaces its complete set of entries.
6. **Given** an existing device tree, **When** whole-device replacement is explicitly selected, **Then** supplied configuration becomes desired state and omitted configuration is removed. Service-impact reporting under FR-008 and FR-012 belongs to the deferred ownership milestone.
7. **Given** tags with equal local names but different namespace URIs, **When** XML is ingested, **Then** their node types remain distinct. Reimporting with different prefixes for the same namespace URIs MUST preserve equivalent normalized types and values; stable collection-entry links are not required.
8. **Given** leaves containing `001` and `true`, an empty element, and an absent element, **When** XML is ingested, **Then** the leaf values remain strings `001` and `true`, the empty element is represented as present, the absent element is not created by ingestion, and no inferred defaults are added. Merge still preserves pre-existing omitted nodes under FR-018.
9. **Given** equivalent configuration with sibling elements supplied in a different order, **When** it is imported or compared, **Then** object fields remain distinguishable and collection entries retain their types, values, and duplicate counts. Reordering alone is not a structural difference; persistent entry links across collection replacement are not guaranteed.
10. **Given** a field stored as an object, **When** supplied XML represents that field as repeated occurrences, **Then** merge replaces that field with a collection, removes links incident to removed nodes, and preserves unrelated fields and roots. The same replacement rule applies when the field changes back to an object, scalar, or null.

### User Story 2 - Review and apply reconciliation (Priority: P1)

An operator reviews whole-device corrective changes and explicitly applies them in either direction.

**Why this priority**: Review separates understanding drift from authorizing changes.

**Independent Test**: Generate and explicitly apply each direction in separate scenarios with differing desired and device configuration.

**Acceptance Scenarios**:

1. **Given** drift, **When** a plan is generated, **Then** it contains corrective operations, affected services, and the device observations used to calculate it, without changing either side.
2. **Given** a sync to device plan, **When** explicitly applied successfully, **Then** the device matches desired state across the supported whole-device scope.
3. **Given** a sync from device plan, **When** explicitly applied successfully, **Then** device configuration replaces saved desired state without changing the device.
4. **Given** a device reconciliation plan with multiple operations, **When** an operation fails, **Then** application stops without attempting later operations, reports completed, failed, and unattempted operations, and requires a new comparison and plan without automatic retries or rollback. Desired state remains unchanged.
5. **Given** every device operation reports success, **When** application finishes, **Then** the result reports success and treats configuration as matching desired state without automatic read-back or comparison. This result is based on operation responses, not independent verification.

### User Story 3 - Declare services and track shared items (Priority: P2)

A service designer creates parameterized network service instances and tracks the configuration they own or depend on.

**Why this priority**: Associations explain the service impact of configuration changes.

**Independent Test**: Create two instances sharing an item, update it sequentially, and reimport configuration. Inspect retained intent and associations.

**Acceptance Scenarios**:

1. **Given** a parameterized definition, **When** an instance is created, **Then** its declared paths, values, and relationships are created and its definition, parameters, ownership, and dependencies are retained.
   Service-to-node relationship types are limited to `owns` and `depends_on`. Each relationship retains its own type. A dependency does not confer ownership or extend to descendants.
2. **Given** A requires MTU 9000 and B later writes 1500 to the same item, **When** B's update is accepted, **Then** the value becomes 1500 without a conflict error, regardless of service creation order, and A is marked inconsistent without automatically reapplying its value. A later update can set 9000 again.
3. **Given** service associations, **When** configuration is reimported, **Then** ownership and dependency links remain attached to semantically corresponding configuration nodes, and evidence of disappeared items permits affected services to be reported. This deferred story requires a future entity-matching policy; structural collection replacement alone does not provide it.
4. **Given** an import contradicts a service's requirements, **When** import completes, **Then** it succeeds, marks affected services inconsistent, preserves definitions and parameters, and does not regenerate configuration or rewrite intent.

### User Story 4 - Remove services safely (Priority: P2)

An operator removes a network service while preserving configuration still needed by other services and unrelated imported configuration.

**Why this priority**: Removal must respect shared use and avoid unexpected restoration of old values.

**Independent Test**: Remove an overriding instance sharing an item, then separately remove an instance whose owned item has no surviving users or dependencies.

**Acceptance Scenarios**:

1. **Given** A needs an item currently set to 1500 by B, **When** B is removed, **Then** the item remains at 1500 without restoring A's earlier value.
2. **Given** a service-owned item with no surviving service use or dependency, **When** its owner is removed, **Then** that configuration is removed from desired state.
3. **Given** unrelated unowned imported configuration, **When** a service is removed, **Then** that configuration remains.
4. **Given** removal changes desired state, **When** removal completes, **Then** device changes still require separate plan review and explicit application.
5. **Given** a service linked as owner of a parent node, **When** ownership is evaluated, **Then** only explicitly linked nodes are owned. Children and further descendants are not implicitly owned. When the service is removed, unowned descendants and nodes needed by surviving services remain, together with the parents required to contain them.

### User Story 5 - Manage arbitrary graph data (Priority: P1, initial milestone)

An NSS client creates, reads, updates, and deletes nodes and typed relationships under named roots, independently of XML ingestion or device transport.

**Why this priority**: Generic graph operations provide the baseline storage capability needed by the initial NSS implementation and `sync_from`.

**Independent Test**: Through the public NorFab client, create a non-device root and child nodes, read and update them, manage a relationship with properties, and delete only the test-owned data.

**Acceptance Scenarios**:

1. **Given** a named root, **When** a client creates and reads nodes through contextual selectors, **Then** the graph retains node types, names, values, and properties without exposing storage IDs.
2. **Given** an existing node, **When** its value or properties are updated, **Then** supplied fields change and omitted fields remain unchanged without renaming or reparenting the node. Explicit `value=null` leaves the node present with a null value. Supplied property keys merge into existing properties and omitted keys remain unchanged, without type conversion.
3. **Given** two nodes, **When** a typed relationship is created, read, updated, and deleted, **Then** its properties are retained independently and deletion preserves both endpoints.
4. **Given** a parent with children, **When** deletion is requested without cascade, **Then** it fails without mutation. Explicit cascade removes its containment subtree and incident relationships while preserving nodes connected only by generic relationships.
5. **Given** collection entries with direct child fields, **When** a caller supplies field/value filters, **Then** only entries satisfying every direct-field equality condition match, without type conversion. Missing fields do not match null, XML text/attribute leaves compare by their leaf value, and nested-field filters are rejected.
6. **Given** filters that match zero or multiple entries, **When** an individual entry update or deletion is requested, **Then** the request fails without mutation. Reads can return all matches; identical duplicates can be managed by explicit collection replacement.
7. **Given** a scalar collection, **When** entries are selected by their own value, **Then** exact type-preserving equality determines matches, including explicit null. Individual mutation fails unchanged for zero or multiple matches.
8. **Given** no root with the supplied name, **When** create_node is called with that name and parent=null and node=null, **Then** the named root is created. Repeating the call fails without changing the root. Child creation requires a payload and exactly one existing parent.

### Edge Cases

- Shared ownership and dependency-only use both prevent deletion of items needed by surviving services.
- Parent ownership does not imply descendant ownership. Removing an owner MUST preserve unowned descendants, nodes still needed by other services, and the ancestors required to contain surviving nodes.
- Imports can remove items or contradict intent while definitions and association evidence must remain available.
- Default merge preserves omitted object fields but replaces each supplied collection in full. Explicit root replacement removes omitted fields. Future sync from device reconciliation uses replacement as defined in Story 2.3.
- Sequential override order differs from service creation order. Concurrent ordering remains undecided.
- Leaf values remain as supplied without type conversion, inference, or added defaults. Empty elements are present nodes, distinct from absent fields. Arrays are unordered collections, and duplicate entries retain their multiplicity.
- Repeated entries may lack names or share identical content. They remain distinct stored entries without static entity-key mappings. No list index or content-derived key is a stable semantic identity.
- Array replacement can remove generic relationships attached to old entry nodes. Future stable service associations require a separate matching policy and are not guaranteed by structural ingestion.
- Partial observations, concurrent writes, and interrupted application still need decisions. Initial operation assumes neither desired state nor device configuration changes between planning and application. Stale-plan detection and handling are deferred. Device application stops on failure and reports operation outcomes without automatic retries or rollback. No all-or-nothing application guarantee is implied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Represent device configuration as linked items and network services as distinct associated entities (Stories 1.1, 3.1).
- **FR-002**: Imported or service-generated configuration MUST be desired state. Comparison MUST read device observations without importing them or maintaining a separate persistent observed-state graph (Story 1.1-1.3).
- **FR-003**: Support whole-device reconciliation in both directions: enforce desired state on devices or replace desired state with device configuration (Story 2.2-2.3).
- **FR-004**: Plan generation MUST expose corrective operations, affected services, and supporting observations without modifying either side (Story 2.1).
- **FR-005**: Plan application MUST require a separate explicit action (Story 2.2-2.3, Story 4.4).
- **FR-006**: Support parameterized service declarations of paths, values, and relationships, retaining definitions and instance parameters (Story 3.1).
- **FR-007**: Multiple services MUST be able to own or depend on the same item. Initial service-to-node relationship types MUST be limited to `owns` and `depends_on`, recorded independently on each relationship. `owns` identifies configuration managed by a service and eligible for removal under FR-010. `depends_on` identifies configuration needed but not owned by the service. Both types MUST apply only to the directly linked node, without inheritance to descendants (Story 3.1, Story 4.1).
- **FR-008**: Associations MUST remain attached to semantically corresponding configuration nodes across imports, with disappearance evidence sufficient to report affected services. This is a deferred ownership requirement: stable entity matching must be designed separately before ownership is implemented. Initial structural collection replacement does not provide stable entry associations.
- **FR-009**: Newer sequential updates MUST override earlier values without conflict errors, independently of service creation order (Story 3.2).
- **FR-010**: Service removal MUST delete owned configuration only when no surviving service uses or depends on it. Retained items MUST keep current values without restoring earlier owners' values (Story 4.1-4.2).
- **FR-011**: Removal MUST preserve unrelated unowned imported configuration. Device changes MUST follow separate planning and application (Story 4.3-4.4).
- **FR-012**: Conflicting imports MUST succeed and mark affected services inconsistent, preserving definitions and parameters without regenerating configuration or rewriting intent (Story 3.4).
- **FR-013**: The first release MUST maintain current desired state only. Historical state retention, revision/time queries, and rollback are outside first-release scope. Evidence of disappeared items required by FR-008 MUST still be retained.
- **FR-014**: An accepted service update that contradicts another service's requirements MUST mark the affected service inconsistent without rejecting the update or automatically reapplying the affected service's values (Story 3.2).
- **FR-015**: Initial device-integration validation MUST use NETCONF and start with OpenConfig. These choices MUST NOT restrict graph-service ingestion by transport, platform, model, or schema. RESTCONF and gNMI device integration are deferred.
- **FR-016**: Graph-service ingestion MUST be transport-, platform-, model-, and schema-independent. XML format handling MUST accept well-formed XML through its dictionary representation without static entity-key mappings. Preserve dictionary-level containers, values, XML attribute metadata, and repeated-entry multiplicity. JSON input remains deferred; lexical XML and mixed-content order fidelity are outside scope.
- **FR-017**: XML ingestion MUST use xmltodict within NssWorker methods and translate its dictionary representation into a graph rooted at the supplied device name. Preserve object containers and collections as nodes, with separate nodes for collection entries and leaves. Field/tag names label nodes; name is ordinary data rather than a required entity key. Do not flatten stored containers, require static mappings, infer semantic keys, or use full-path node identities (Story 1.4).

- **FR-018**: sync_from MUST merge supplied object fields recursively by default, preserving omitted object fields. A supplied collection MUST replace all entries of that collection; an omitted collection MUST remain unchanged. Explicit root replacement MUST remove omitted fields. Collection replacement need not retain entry nodes or their incident generic relationships. Service intent/association behavior is deferred under FR-008 and FR-012 (Story 1.5-1.6).
- **FR-019**: Device reconciliation application MUST stop on the first operation failure and report completed, failed, and unattempted operations. It MUST NOT automatically retry or roll back. Further reconciliation MUST require a new comparison and plan. Device-write failure MUST NOT change desired state (Story 2.4).
- **FR-020**: A service MUST link directly to each configuration node it owns. Ownership MUST NOT implicitly extend to children or other descendants. Removal MUST evaluate ownership and surviving use per node, preserving unowned descendants, nodes still owned, used, or depended on by surviving services, and the ancestors needed to contain surviving nodes (Story 4.5).
- **FR-021**: When all device operations report success, application MUST report success and assume configuration matches desired state. It MUST NOT automatically read back or compare device configuration. Results MUST distinguish operation-reported success from independently verified agreement. Operators MAY request a separate comparison (Story 2.5).
- **FR-022**: XML node types MUST be determined by namespace URI and local tag name, independently of namespace prefixes. Equal local names in different namespace URIs MUST remain distinct. Prefix-only changes MUST NOT alter normalized field types or values (Story 1.7). Stable service associations across replaced collections remain deferred under FR-008.
- **FR-023**: Ingestion MUST preserve leaf values as supplied, without type conversion or inference and without adding schema defaults. XML text values such as `001` and `true` MUST remain unchanged. Empty elements MUST be represented as present nodes, distinct from absent elements. Omitted elements MUST NOT be synthesized from defaults. Merge preservation of omitted existing nodes remains governed by FR-018 (Story 1.8).

- **FR-024**: Element order MUST NOT affect structural comparison. Object fields are named within their parent context. Arrays MUST preserve separate entries and duplicate multiplicity without requiring unique names. Reordering alone MUST NOT be a structural difference. Positional indexes MUST NOT be treated as stable semantic identities (Story 1.9).

- **FR-025 (initial milestone)**: NSS MUST expose generic node and relationship create/read/update/delete methods for arbitrary graph data, alongside supplied-XML `sync_from`. Relationships MUST support a type and properties. Selection MUST use parent context and traversal without public storage IDs. Deletion MUST require explicit cascade for containment subtrees and MUST NOT delete endpoints merely connected by non-containment relationships.

- **FR-026 (initial milestone)**: Collection-entry selection MUST support field/value filters supplied by the caller, without predefined entity keys or public storage IDs. Reads MAY return multiple matching entries. An individual entry update or deletion MUST resolve exactly one match; zero or multiple matches MUST return a clear error without mutation. Identical duplicates can be changed by explicitly replacing the containing collection.

- **FR-027 (initial milestone)**: Node updates MUST distinguish omitted fields from explicitly supplied values. Omitted values and properties MUST remain unchanged. Explicit `value=null` MUST set a present null value without deleting the node. Supplied property keys MUST merge into existing properties, preserving omitted keys. Supplied values MUST NOT undergo type conversion or inference (Story 5.2).

- **FR-028 (initial milestone)**: Explicit root creation MUST require only a nonempty root name, with `parent=null` and `node=null`. Creating an existing root MUST fail without mutation. Child creation MUST require a node payload and a selector resolving to exactly one existing parent; an empty parent selector identifies the root. The supplied root name MUST NOT be inferred from a child payload.

- **FR-029 (initial milestone)**: XML ingestion MUST preserve object, scalar, null, and collection shapes produced by xmltodict without schema or collection hints. During merge, a supplied change between these shapes MUST replace only that field's subtree and remove incident generic relationships to removed nodes. Unrelated fields and roots MUST remain unchanged. Singleton XML occurrences MUST NOT be inferred to be collections merely because multiple occurrences may appear later.

- **FR-030 (initial milestone)**: Collection-entry filters MUST compare direct child fields using exact, type-preserving equality. All supplied conditions MUST match (AND semantics). A missing field MUST differ from a present null field. Nested-field filtering, OR expressions, ranges, and regular expressions are outside initial scope. XML leaves represented as text plus attributes MUST expose their leaf value for direct-field equality without treating attribute metadata as nested filter syntax.

- **FR-031 (initial milestone)**: Scalar collection entries MUST be selectable by exact, type-preserving equality against their own value, including explicit null. Individual mutations MUST require exactly one match and fail unchanged on zero or multiple matches. Object-entry direct-field filters and scalar-entry value filters MUST be distinct selector forms.

### Key Entities *(include if feature involves data)*


- **Root/Device**: A caller-named graph root. Device data is one use case; initial containment preserves its source object/collection hierarchy.
- **Graph item**: An object/container, collection, collection entry, or leaf node linked beneath its parent. Containers preserve fields, collection entries may share labels, and leaves hold unchanged values. Private storage handles are not public semantic identities.
- **Node type and field name**: Namespace URI plus local XML tag determines XML type independently of prefixes. Dictionary field names label child nodes. Collection entries need no unique semantic names; their fields, including name when present, remain data.
- **Network service definition**: A parameterized declaration of configuration and relationships. Distinct from a NorFab worker service.
- **Network service instance**: Retained definition, parameters, ownership, dependencies, and consistency status.
- **Ownership association**: A direct link from a service to an owned configuration node, with relationship properties indicating the type of ownership. It applies only to that node, without inheritance to descendants, and informs removal eligibility.
- **Dependency association**: A direct `depends_on` relationship recording a service's need for a configuration node without ownership or inheritance to descendants.
- **Reconciliation plan**: Direction, corrective operations, affected services, and supporting observations.
- **Disappearance evidence**: Information connecting missing items to affected services after import.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All ten broader Story 1 scenarios pass, with zero desired-state or device changes during comparison.
- **SC-002**: Both reconciliation directions can be reviewed and explicitly applied. Every generated plan identifies operations, affected services, and supporting observations.
- **SC-003**: All four service association scenarios pass, including sequential overrides, stable associations, disappearance reporting, and import inconsistency without lost intent.
- **SC-004**: All five removal scenarios pass with zero deletions of still-needed shared items or unowned descendants and zero automatic restorations of earlier values. Parent ownership confers zero implicit ownership of descendants.
- **SC-005**: After successful reconciliation and before further changes, repeat whole-device comparison reports zero differences within supported scope.
- **SC-006**: Initial NETCONF acceptance scenarios pass with OpenConfig configuration. A separate XML configuration using a different model is also ingested with its structure and relationships preserved, without platform- or model-specific ingestion rules.
- **SC-007**: In the application-failure scenario, zero later operations are attempted after failure, every planned operation has a reported outcome, desired state remains unchanged, and no automatic retry or rollback occurs.
- **SC-008**: When every operation reports success, application reports success with zero automatic read-back or comparison requests. SC-005 is validated through a separately requested comparison, not an automatic application step.

### Initial Milestone Outcomes

- **SC-009**: Public-client node/relationship CRUD scenarios in Story 5 pass, preserving unchanged fields, explicit cascade boundaries, and relationship endpoints. Field/value filters select entries without static keys. Individual entry updates/deletes with zero or multiple matches make zero changes and return a clear error.
- **SC-010**: sync_from represents the extracted sample configuration without static mappings, preserving containers, scalar values, attributes, null presence, collection counts, and duplicate multiplicity. Input rejection must not depend merely on an entity lacking a name field.
- **SC-011**: Focused merge tests prove omitted object fields survive, supplied collections replace completely, omitted collections survive, shape changes replace only the supplied field, and explicit root replacement removes omitted fields without modifying unrelated roots.

SC-001 through SC-008 include broader deferred feature outcomes. They are not a claim that initial implementation includes diff, NETCONF, service ownership, or reconciliation. Structural diff feasibility is recorded above, with implementation deferred.

## Assumptions

- This specification includes confirmed ADR behavior and decisions recorded in Clarifications. Other ADR proposals remain unaccepted. It does not claim implementation, benchmarks, or operational readiness.
- Acceptance scenarios assume complete readable configuration, supported capabilities, and sequential updates. For later reconciliation delivery, desired state and device configuration MUST remain unchanged between plan generation and application. Stale-plan detection and handling are outside initial scope. Other failure behavior still needs clarification.
- Operators have authorized device access. Authentication and changes to existing public client interfaces are outside this specification.
- Corrective changes suffice. Configuration export and byte-for-byte reproduction are outside scope.
- Later device integration uses NETCONF, with validation starting with OpenConfig; it is not part of initial delivery. Graph-service ingestion is transport-independent and supports any well-formed XML through pluggable format support. It does not require a platform, model, or supplied schema. JSON ingestion and RESTCONF/gNMI device integration are later additions.
- The preserved ADR retains architecture choices and technical constraints for planning, including the selected storage technology.
- Initial design MUST consider future history, rollback, and time travel where practical. Planning must record how the current-state graph tree and service relationships can accommodate that later addition, or identify migration needs, without adding historical storage or rollback behavior to the first release.

## Open Decisions and Deferred Scope

These inherited decisions are not accepted requirements. They must be resolved or explicitly deferred before implementation planning is finalized.

- **Q20 - History (resolved for first release)**: Current state only. History, rollback, and time travel are deferred additions. Their scope, retention, provenance, and timestamp semantics remain future decisions. Initial design considers later extension where practical.
- **Q21 - Override status (resolved)**: Accept overrides and mark services with contradicted requirements inconsistent. Do not automatically reapply their values.
- **Initial CRUD decisions (resolved)**: FR-026 through FR-030 define exact direct-field AND filters, exactly-one-match individual mutations, omitted-versus-null patch semantics, name-only root creation with duplicate rejection, and replacement on source-shape changes. These decisions are reflected in the revised contracts and tasks.
- **Scalar collection selection (resolved)**: Select scalar entries by exact, type-preserving equality against their own value. Individual mutations still require exactly one match; identical duplicates are managed through whole-collection replacement.
- **Model (structural baseline resolved)**: Preserve objects, containers, collections, entries, and leaves without mappings or inferred entity identities. Arrays are unordered and supplied arrays replace their entries during merge. Static key inference, semantic entity matching, stable service links across collection changes, and graph diff APIs are deferred. Collection-entry CRUD uses caller-supplied field/value filters. Individual updates/deletes require exactly one match; ambiguous identical duplicates are managed by explicit collection replacement. Do not expose private IDs or use list positions as semantic keys.
- **Lifecycle (deferred)**: Later service-to-node relationship types are `owns` and `depends_on`, recorded independently per relationship and applying only to the directly linked node. Removal preserves unowned descendants, surviving service use, and required containing ancestors. Cleanup after the final dependency disappears and update scope remain open.
- **Reconciliation safety**: Stale-plan detection and handling are explicitly deferred under the initial assumption that neither side changes between planning and application. Device application stops on failure, reports operation outcomes, and requires a new comparison and plan without automatic retries or rollback. Successful operation responses are assumed to mean configuration matches, without automatic verification. Separate operator-requested comparison remains available. Collection completeness, unreadable configuration, concurrent ordering/writes, and interruption or crash recovery remain open.
- **Delivery**: Initial delivery is supplied-XML sync_from plus baseline generic graph CRUD. NETCONF/OpenConfig device integration is deferred. Service declaration syntax, device operation representation, and reconciliation recovery remain future decisions. The initial plan already proposes single-worker database ownership and dependency versions; those technical choices require revalidation when planning is updated.

The original ADR remains the source for architecture rationale and supporting references. No performance target or history guarantee is inferred from it.
