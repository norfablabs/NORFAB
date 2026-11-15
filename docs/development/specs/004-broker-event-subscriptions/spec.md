# Feature Specification: Broker Event Subscriptions

**Feature Branch**: Not created. Feature selection is independent of the current branch.

**Created**: 2026-11-15

**Status**: Draft

**Acceptance Status**: Proposed, pending maintainer review.

**Implementation Status**: Not implemented.

**Input**: Specify a simple generic broker subscription mechanism that lets clients select broker-published events using filters. Worker discovery is the first use case. Reuse existing worker registration and `show_workers` membership snapshots.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive Selected Worker Events (Priority: P1)

As a NorFab client author, I can subscribe to worker lifecycle events for selected services so my application reacts to membership changes without repeatedly requesting the complete worker list.

**Why this priority**: Receiving relevant changes is the main capability and supports later event-driven gateway discovery.

**Independent Test**: Through the public client interface, subscribe to lifecycle events for one service, start and stop workers from that service and another service, and inspect received notifications.

**Acceptance Scenarios**:

1. **Given** a successful subscription for registration events from Netbox, **When** a Netbox worker registers, **Then** the subscriber receives its subscription identifier, event name, worker name, and service name.
2. **Given** that subscription, **When** a worker from another service registers or a Netbox worker is removed, **Then** neither event is delivered to that subscription.
3. **Given** a subscription for removal events, **When** a matching worker disconnects or is removed after heartbeat expiry, **Then** the subscriber receives a removal notification with the corresponding reason.
4. **Given** two clients with matching subscriptions, **When** a matching lifecycle transition occurs, **Then** both receive independent notifications.
5. **Given** multiple selected event names and filter fields, **When** an event is published, **Then** it matches any selected event name and every specified filter field. A list of allowed field values matches any listed value.
6. **Given** malformed selection criteria, an unsupported event name, or an unsupported filter field, **When** a client subscribes, **Then** the request fails clearly and creates no subscription.

### User Story 2 - Control Subscription Lifetime And Ownership (Priority: P1)

As a client author, I can renew or cancel my subscriptions so notifications stop when no longer needed and disconnected consumers do not leave permanent subscriptions behind.

**Why this priority**: Explicit ownership and bounded lifetime are necessary for a usable subscription service.

**Independent Test**: Create a subscription with a short lease, renew it, cancel it, and verify that a second client cannot manage it.

**Acceptance Scenarios**:

1. **Given** an active subscription, **When** its owner renews before expiry, **Then** the identifier and selection criteria remain unchanged and the acknowledged lease restarts from successful renewal.
2. **Given** a subscription with no renewal, **When** its lease expires, **Then** no further events are selected for that subscription.
3. **Given** an active subscription, **When** its owner cancels it, **Then** no subsequent events are selected. Notifications already in transit may still arrive.
4. **Given** another client's subscription identifier, **When** a client attempts renewal or cancellation, **Then** the operation fails without changing that subscription.
5. **Given** an expired or unknown identifier, **When** a client requests renewal or cancellation, **Then** it receives a clear not-found result and may create a new subscription.
6. **Given** an invalid lease or exhausted subscription capacity, **When** a client subscribes, **Then** the request fails clearly without creating partial state.

### User Story 3 - Recover From Missed Changes (Priority: P2)

As a discovery consumer author, I can combine subscriptions with the existing worker snapshot so startup, disconnects, and broker restarts do not make notifications my only source of membership information.

**Why this priority**: Best-effort notifications cannot establish current membership or recover changes that occurred while disconnected.

**Independent Test**: Subscribe, request the existing worker snapshot, interrupt the connection, change membership, then reconnect, resubscribe, and request the snapshot again.

**Acceptance Scenarios**:

1. **Given** workers already running, **When** a consumer subscribes, **Then** no historical events are replayed and the existing `show_workers` operation remains available to establish current membership.
2. **Given** a subscription acknowledged before a snapshot request, **When** membership changes while that snapshot is obtained, **Then** matching notifications remain available for the consumer to trigger another refresh.
3. **Given** a broker restart, **When** a consumer creates a new subscription and obtains a new snapshot, **Then** it can reconstruct current membership without relying on the old subscription or missed events.
4. **Given** duplicate notifications or notifications for an already changed worker, **When** a consumer requests a snapshot, **Then** the snapshot remains the authority for current membership.

### User Story 4 - Keep Normal Jobs Independent (Priority: P2)

As a NorFab operator, I can use subscriptions alongside existing jobs without slow consumers delaying job dispatch or causing lifecycle notices to appear as job progress.

**Why this priority**: Notifications must preserve established client and broker behavior.

**Independent Test**: Run a normal public-client job while a subscriber stops consuming notifications and another client continues consuming them.

**Acceptance Scenarios**:

1. **Given** a client with an active subscription and job, **When** it receives lifecycle notifications, **Then** those notifications are available separately from job results and job events.
2. **Given** an overloaded subscriber, **When** its pending notification capacity is reached, **Then** notification loss is observable through a warning or delivery status and normal jobs and other subscribers continue progressing.
3. **Given** a client that has never subscribed, **When** workers register and leave, **Then** that client receives no unsolicited lifecycle notifications and its existing operations remain unchanged.

### Edge Cases

- A repeated registration with no membership transition must not create another registration event.
- A worker restart under the same name produces removal and registration events when the broker observes those transitions. An unobserved restart does not imply a guaranteed event.
- A removal notification describes the worker before its membership information is discarded.
- A missing event field cannot satisfy a filter on that field. An omitted filter imposes no field restriction.
- Empty event lists, empty allowed-value lists, nested filter expressions, and mixed wildcard/event selections are rejected.
- An event matching two subscriptions owned by the same client produces a notification for each subscription.
- Renewal at or after expiry cannot revive an expired subscription.
- Broker restart clears subscriptions. No durable event history or subscription recovery is implied.
- A registration event establishes broker membership, not successful initialization of all worker dependencies or immediate task availability.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Clients MUST be able to create a subscription, renew its lease, and cancel it through the public NorFab client interface. Successful creation MUST return an identifier and the effective lease duration.
- **FR-002**: Subscriptions MUST select one or more exact event names, or the single wildcard `*` for all supported public broker events. Event names and filter values MUST be case-sensitive. Wildcards within names or values are unsupported.
- **FR-003**: Filters MUST support exact text matching against documented event fields. One value or a non-empty list of values is allowed per field. Values within a field combine with OR, fields combine with AND, and omitted filters match all selected events.
- **FR-004**: The initial public events MUST be `worker.registered` and `worker.removed`. Both MUST expose `worker` and `service` fields usable as filters. Removal notifications MUST also identify explicit disconnect or heartbeat expiry as the reason when those caused removal.
- **FR-005**: Each matching subscription MUST receive its own notification containing its subscription identifier, event name, and event data. Notifications MUST describe observed broker lifecycle transitions and MUST NOT contain task arguments, results, credentials, or private job messages.
- **FR-006**: Subscription ownership MUST derive from the requesting client's established connection identity. Clients MUST NOT choose another delivery identity or manage another client's subscriptions. Existing connection authentication and access restrictions remain applicable.
- **FR-007**: The default lease MUST be 120 seconds. Requested leases MUST be whole seconds from 1 through 3600. Renewal MUST preserve the original lease duration and criteria. Expired subscriptions MUST stop matching and release their resources.
- **FR-008**: Delivery MUST be best effort, with no historical replay, acknowledgement requirement, persistence, or exactly-once guarantee. Consumers MUST be able to continue using the existing `show_workers` snapshot for recovery. Existing worker registration and snapshot arguments and results MUST remain unchanged.
- **FR-009**: Client notification consumption MUST be separate from job results and progress events. Notification handlers or slow consumers MUST NOT block broker dispatch or client receipt of normal job responses.
- **FR-010**: Pending notification storage and subscription counts MUST be bounded. Capacity exhaustion MUST be observable and MUST NOT cause unbounded resource growth or stop other clients' normal work. Effective limits and loss behavior MUST be documented during implementation planning.
- **FR-011**: Invalid selections, unsupported names or fields, invalid leases, ownership violations, and expired or unknown identifiers MUST produce clear failures without partial subscription changes. Cancellation acknowledgement excludes notices already in transit.
- **FR-012**: Broker restart MUST clear all subscriptions. Clients MUST be able to establish replacement subscriptions after connection recovery. Recovery guidance MUST describe subscribing before obtaining a membership snapshot and periodically reconciling that snapshot.
- **FR-013**: Only clients with active matching subscriptions MUST receive notifications. Existing clients and workers MUST continue normal operation without subscribing or changing their registration behavior.
- **FR-014**: Subscription behavior MUST apply uniformly to supported public broker events. Adding an event type MUST NOT require a new filtering language or event-specific subscription operations. Only explicit public broker events are eligible for selection.

### Key Entities *(include if feature involves data)*

- **Subscription**: A client's selection of event names and field values, with an identifier, owner, effective lease, and expiry.
- **Broker Event**: A supported public occurrence with a name and documented event fields. Initially represents a worker registration or removal.
- **Notification**: A delivery of one broker event to one matching subscription, carrying the subscription identifier.
- **Membership Snapshot**: The current worker membership returned by existing `show_workers`, used independently of event delivery.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a connected local integration environment without induced overload, each matching worker lifecycle transition is available to every active matching subscriber within two seconds of broker observation across 20 consecutive transitions.
- **SC-002**: Filter acceptance scenarios deliver zero nonmatching notifications. Every supported selection combination produces the expected matching notifications.
- **SC-003**: After cancellation or expiry, zero events published afterward are selected for the subscription. All cross-client management attempts fail without modifying the owner's subscription.
- **SC-004**: After an induced disconnect or broker restart, a consumer can reconstruct the complete current membership through a new subscription and snapshot, without manual worker restarts or historical event replay.
- **SC-005**: During notification overload, a separate client's normal job completes within its configured timeout, a healthy subscriber continues receiving events, and notification loss or capacity rejection is observable.

## Assumptions

- This feature delivers generic broker subscriptions and initial worker lifecycle events. Full FastAPI endpoint and MCP tool/prompt reconciliation, client-facing MCP change notifications, and gateway automation are follow-up work.
- The existing NorFab connection and worker snapshot are reused. No separate listener, external messaging service, or second membership registry is required.
- All clients permitted to inspect worker membership may subscribe to the same public membership information. Private job traffic is outside scope.
- Consumers renew before lease expiry and establish new subscriptions after reconnect. Transparent automatic renewal or recovery is not required in this first delivery.
- Consumers tolerate duplicate or stale notifications and reconcile snapshots periodically. No delivery ordering guarantee or revision mechanism is required.
- The 120-second lease and two-second healthy-delivery target are proposed defaults for review, not measurements of existing behavior.
- Broker publication is authoritative. Worker-defined arbitrary event publication, filter expressions, durable history, full task metadata registration, and heterogeneous-worker task routing are outside scope.
