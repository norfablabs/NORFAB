# ADR - Norfab AAA and Encrypted Transport Architecture

## Status

Proposed.

Date: 2026-06-14.

This ADR is an architecture proposal. It does not authorize replacing the
current protocol in one change. The migration must be staged and preserve an
explicit compatibility mode until NFP v2 is ready.

## Decision summary

Norfab will separate durable AAA state from ZeroMQ traffic mediation:

1. Keep ZeroMQ CURVE as the encrypted data-plane transport.
2. Add a dedicated, independently deployable `norfab-aaa` service for broker
   discovery, OIDC login, token exchange, key enrollment, approvals, policy,
   revocation, and accounting ingestion.
3. Use an external OpenID Connect identity provider for human authentication.
   Okta can be used directly. LDAP and Active Directory should normally be
   connected through an identity broker such as Keycloak rather than queried
   directly by the Norfab broker.
4. Require MFA at the identity provider. The AAA service validates `acr`, `amr`,
   and `auth_time` and can require fresh step-up authentication for sensitive
   operations.
5. Exchange external access tokens for short-lived, signed Norfab access
   credentials bound to a client CURVE public-key fingerprint.
6. Let brokers validate Norfab credentials locally with cached AAA public keys
   and signed policy material. Brokers must not own the principal, credential,
   session, role, policy, or audit databases.
7. Identify users by the immutable OIDC `(iss, sub)` pair. A username is a
   display attribute, not the security identifier.
8. Add a broker-issued principal context to NFP v2 messages sent to workers.
   Clients must never be trusted to assert their own username, roles, or MFA
   state.
9. Make the broker a policy enforcement point, while the AAA service owns policy
   and acts as the policy decision authority. Brokers may evaluate signed policy
   bundles locally or call the AAA service for decisions that require current
   external state.
10. Send structured authentication, authorization, routing, and execution events
    to the dedicated accounting service. Brokers may keep only a bounded
    temporary spool.
11. Define the encryption requirement as authenticated encryption on every
    network hop: client to broker and broker to worker. The broker is a trusted
    decryption and re-encryption point. Broker-blind application encryption is
    not required by this ADR.

The recommended target architecture is therefore:

```text
                         OIDC / OAuth
  Client  <------------------------------------------>  Identity provider
     |
     | HTTPS: discovery, token exchange, enrollment
     v
  +---------------- active-active norfab-aaa ----------------+
  | authentication | policy | credentials | accounting input |
  +----------------------+------------------------------------+
                         | signed keys, credentials, policy
                         | and revocation updates
                         v
  Client === CURVE ===> Broker === CURVE ===> Worker pool
                        (soft state)           (active-active)
                            |
                            +---- structured audit events ---->
```

## Context

Norfab currently uses ZeroMQ CURVE between clients and the broker and between
workers and the broker. The broker creates a permanent CURVE key pair, and each
client or worker creates its own key pair.

The current implementation has several important properties:

- `norfab/core/security.py` creates local CURVE certificates and can copy or
  inject the broker public key.
- `norfab/core/client.py` and `norfab/core/worker.py` require the broker CURVE
  public key before connecting.
- `norfab/core/broker.py` starts `ThreadAuthenticator`, sets `allow_any = True`,
  and configures `CURVE_ALLOW_ANY`.
- Client and worker routing identities are application-selected strings.
- The broker forwards the client routing address to workers. Workers store it as
  `client_address`.
- NFP does not carry a broker-verified human or workload principal.
- The broker can read all request and result payloads because CURVE terminates at
  the broker on both hops.
- The broker owns in-memory worker and service registries used for liveness and
  routing. This is necessary soft state, but it should not become durable AAA or
  job state.
- Several debug log statements include complete multipart messages or request
  data. Authentication tokens and secrets must not pass through these log
  statements.

`CURVE_ALLOW_ANY` is not equivalent to client authentication. It encrypts the
connection and authenticates the broker to a client that already has the
correct broker key, but the broker accepts any client CURVE key.

The CURVE specification also requires the client to know the server's permanent
public key before connecting. There is no cryptographic mechanism that can
authenticate an unknown broker without some other trust anchor. The requirement
can be improved from "manually copy this exact broker key" to "trust this CA,
Kerberos realm, or signed discovery authority", but trust cannot be removed.

## Goals

- Authenticate human users through modern external identity providers.
- Support Okta, LDAP-backed identities, Active Directory, and other OIDC
  providers without provider-specific logic in the NFP data protocol.
- Support phishing-resistant authentication and MFA when the identity provider
  offers it.
- Support non-interactive automation and service accounts without pretending
  that they are human users.
- Authenticate and authorize workers as workloads.
- Allow manual approval, automatic approval, revocation, expiration, and
  rotation of client and worker keys.
- Enforce RBAC before the broker dispatches a request.
- Support task-level and worker-level permissions.
- Propagate a trustworthy actor identity to workers.
- Produce useful accounting records for authentication, authorization, job
  execution, administrative changes, and denied operations.
- Encrypt every network hop.
- Keep the broker free of durable principal, credential, session, policy, and
  accounting databases.
- Support active-active worker pools and broker failover without requiring
  durable job state in the broker.
- Preserve a practical migration path from NFP v1.

## Non-goals

- Norfab will not become a general-purpose password database or MFA server.
- A username supplied by a client will not be treated as authenticated.
- The ZeroMQ routing identity will not be treated as a human identity.
- The first AAA release will not hide routing metadata from the broker.
- Job payloads will not be hidden from the broker. The broker is a trusted
  decryption and re-encryption point.
- The first AAA release will not encrypt all SQLite databases at the field
  level. Data-at-rest protection is a separate requirement.
- RBAC will not be implemented independently in every worker.
- Direct LDAP username/password bind will not be the preferred human login
  mechanism.

## Threat model

The initial AAA design protects against:

- Network eavesdropping and message modification.
- Clients impersonating other users by changing a username or routing identity.
- Unknown CURVE keys executing operational NFP commands.
- Stolen Norfab access credentials used without the bound CURVE private key.
- Unauthorized access to services, tasks, workers, and management operations.
- Replay of expired or previously consumed authentication operations.
- Accidental disclosure of credentials in logs and audit records.
- Continued access after key or access-credential revocation, subject to bounded
  cache and disconnect delays.

It does not, by itself, protect against:

- A compromised client or worker host.
- A compromised identity provider.
- A compromised broker, because the broker is explicitly trusted to decrypt
  mediated traffic.
- A compromised AAA signing key or AAA durable store.
- Traffic analysis based on endpoints, message size, timing, service, task, or
  worker selection.
- Secrets intentionally returned by a task and then logged by application code.

## State ownership and availability

### Broker state boundary

The broker should be operationally stateless, not literally stateless.

The following soft state is inherent to a ZeroMQ ROUTER broker and remains in
memory:

- Open client and worker connections.
- ZeroMQ routing identities.
- Worker heartbeats and liveness deadlines.
- The currently connected worker set for each service.
- Bounded token, policy, key, and authorization caches.
- In-flight routing correlation needed to forward a response.

This state may be discarded when a broker restarts. It must not be the system of
record.

The broker must not own durable:

- Users or workload principals.
- CURVE credential approvals.
- OIDC refresh tokens.
- Norfab access credential records.
- Roles, role bindings, or policy source.
- Audit history.
- Job request, result, or retry state.

Durable job state remains at clients and workers. Durable AAA and accounting
state belongs to `norfab-aaa` and its backing services.

### Dedicated AAA service

`norfab-aaa` is a security control-plane service, not an ordinary worker reached
only through the protected NFP data plane. Making it depend exclusively on the
broker would create a bootstrap cycle: the broker would need AAA to authorize
the service that provides AAA.

The service exposes an authenticated HTTPS API and may also expose a Norfab
worker adapter for administration after the core security path is established.
It owns:

- Identity-provider integration and token validation.
- Token exchange and Norfab access credential issuance.
- Principal and workload credential enrollment.
- Manual and automatic approvals.
- Role mappings and authorization policy.
- Credential, principal, and policy revocation.
- Broker discovery metadata and AAA public signing keys.
- Accounting event ingestion and export.

The service should run as multiple active-active instances behind a load
balancer. Replicas share a durable database and signing-key service or KMS.
Requests must be idempotent, and every administrative mutation must use an
immutable event or version number so replicas and brokers can reject stale
updates.

### Broker and AAA interaction

Normal data-plane routing must not require a synchronous AAA network call for
every message. The preferred fast path is:

1. AAA issues a short-lived signed credential bound to the client CURVE key.
2. The broker validates the signature and claims locally.
3. The broker evaluates a signed, versioned policy bundle locally.
4. The broker emits an accounting event asynchronously.

The broker may call AAA synchronously for:

- High-risk authorization requiring immediately current external state.
- Token introspection when policy requires immediate revocation.
- Refreshing a missing or expired signed policy or revocation bundle.

Clients perform token exchange, step-up completion, enrollment, and
administrative changes directly against AAA.

Short token lifetimes and signed revocation or policy updates bound the period
during which a disconnected broker can use cached information.

### Active-active worker pools

Each worker replica has a unique workload identity and credential while sharing
a service name. For example:

```text
service: nornir
workers:
  - workload:worker:nornir-1
  - workload:worker:nornir-2
  - workload:worker:nornir-3
```

All healthy replicas may accept work concurrently.

- `workers="any"` means dispatch once to one healthy, authorized replica.
- `workers="all"` means intentional fan-out and may execute the task multiple
  times. It is not the default resilience mechanism.
- Explicit worker lists target the named workload identities.

Resilient retries require an idempotency contract. `request_uuid` is the natural
idempotency key. A single worker can reject or return the stored result for a
duplicate job UUID from its local job database. Deduplication across different
worker replicas requires a shared service-level idempotency store or an
idempotent target operation.

Broker failover therefore provides at-least-once rather than exactly-once
delivery after an ambiguous failure. Tasks with side effects must declare their
retry behavior. The broker must not persist a retry ledger.

Workers should eventually support connections to more than one broker instance.
This allows a client that reconnects through another broker to reach the same
worker-held job state. Broker discovery must list multiple broker endpoints, and
clients must retry with the same request UUID after an ambiguous failure.

Sharing one CURVE private key among broker replicas simplifies load balancing
but increases key exposure. Unique broker keys and endpoint-specific discovery
are preferred. A shared broker key should require KMS-backed distribution,
rotation, and an explicit acceptance of the larger blast radius.

## Identity model

### Human principals

The stable principal identifier must be derived from the OIDC issuer and subject:

```text
principal_id = "oidc:" + issuer + "#" + subject
```

For example:

```text
oidc:https://example.okta.com/oauth2/default#00u123abc
```

OIDC only guarantees the `(iss, sub)` pair as a stable unique identifier.
`preferred_username`, email address, and display name can change and can be
reassigned. They are useful accounting attributes but must not be policy keys.

Suggested principal fields:

```json
{
  "principal_id": "oidc:https://id.example.com/realms/norfab#f4c2...",
  "principal_type": "human",
  "issuer": "https://id.example.com/realms/norfab",
  "subject": "f4c2...",
  "username": "alice",
  "display_name": "Alice Example",
  "groups": ["network-operators"],
  "enabled": true
}
```

### Workload principals

Workers, CI jobs, API gateways, and unattended automation are workloads, not
human usernames.

Examples:

```text
workload:worker:nornir-worker-1
workload:client:nightly-compliance
workload:gateway:fastapi-1
```

Workloads may authenticate with:

- An OAuth client-credentials access token accepted by the control plane.
- A one-time enrollment token followed by an approved CURVE key.
- An enterprise workload identity system such as SPIFFE/SPIRE in a later
  integration.
- Kerberos/GSSAPI in deployments that are already centered on Active Directory.

Every workload key must have an owner, purpose, expiry or review date, and
revocation path.

### Break-glass principals

An optional local administrator may exist for recovery when the identity
provider is unavailable. It must be:

- Disabled by default.
- Stored with a modern password hash such as Argon2id.
- Protected by a second factor or hardware-backed credential where practical.
- Restricted to local or explicitly configured management networks.
- Fully audited.
- Unable to silently impersonate another user.

## Trust bootstrap and broker discovery

### Security constraint

CURVE cannot securely connect a client to a broker whose key is completely
unknown and unauthenticated. The trust must be anchored somewhere.

### Chosen bootstrap

The `norfab-aaa` service exposes an HTTPS control endpoint with an X.509
certificate issued by a public or enterprise CA trusted by clients.

An authenticated discovery document is available at a well-known path such as:

```text
https://aaa.example.com/.well-known/norfab
```

Example:

```json
{
  "version": 1,
  "fabric_id": "brisbane-prod",
  "brokers": [
    {
      "broker_id": "brisbane-prod-1",
      "endpoint": "tcp://broker-1.example.com:5555",
      "curve_key": {
        "kid": "broker-1-curve-2026-06",
        "public_key": "Z85_ENCODED_KEY_1",
        "not_before": "2026-06-01T00:00:00Z",
        "not_after": "2026-09-01T00:00:00Z"
      }
    },
    {
      "broker_id": "brisbane-prod-2",
      "endpoint": "tcp://broker-2.example.com:5555",
      "curve_key": {
        "kid": "broker-2-curve-2026-06",
        "public_key": "Z85_ENCODED_KEY_2",
        "not_before": "2026-06-01T00:00:00Z",
        "not_after": "2026-09-01T00:00:00Z"
      }
    }
  ],
  "oidc_issuers": [
    {
      "issuer": "https://example.okta.com/oauth2/default",
      "audience": "api://norfab"
    }
  ],
  "aaa_api": "https://aaa.example.com/api/v1",
  "aaa_jwks_uri": "https://aaa.example.com/.well-known/jwks.json",
  "expires_at": "2026-06-14T12:00:00Z"
}
```

The client validates HTTPS through its CA trust store, caches the signed
descriptor for a bounded time, chooses a broker endpoint, and configures
`curve_serverkey` with that broker's key. Broker key rotation uses an overlap
period with current and next keys.

This removes per-client distribution of the exact broker CURVE key. It does not
remove the requirement to trust the HTTPS CA.

### Other valid bootstrap choices

- An enterprise configuration-management system can distribute a signed broker
  descriptor.
- Kerberos/GSSAPI can use the Kerberos realm and service principal as the trust
  anchor.
- DNSSEC/DANE could publish a key, but operational support is less common.
- Trust on first use can be offered for development only. A changed key must
  require explicit approval.

An OIDC token is sent only to the authenticated AAA HTTPS endpoint. Brokers
receive a short-lived Norfab credential, not the user's reusable OIDC refresh
token or password.

## Authentication control plane

### Human login flow

CLI and desktop clients should use one of:

- OAuth 2.0 Device Authorization Grant for terminals and remote shells.
- Authorization Code with PKCE when a local browser callback is practical.

The identity provider performs password, passkey, WebAuthn, OTP, push, or other
MFA. Norfab does not collect the user's password or OTP.

The AAA API validates an access token, not an arbitrary username and password.
Validation includes:

- HTTPS issuer discovery from an allowlisted issuer.
- Signature against cached and rotated JWKS keys, or token introspection for an
  opaque token.
- Exact issuer match.
- Expected audience.
- Expiry and not-before time.
- Required scope.
- Subject presence.
- Authorized client ID where applicable.
- Allowed algorithms configured by AAA, never selected freely from the token
  header.

ID tokens are intended for the OIDC client. The AAA service should normally
consume an access token minted for the Norfab audience.

After validation and approval checks, AAA performs a token exchange and issues
a short-lived signed Norfab access credential. The credential is audience
restricted to the intended Norfab fabric and bound to the client's CURVE public
key through a confirmation claim.

```json
{
  "iss": "https://aaa.example.com",
  "sub": "oidc:https://id.example.com#abc",
  "aud": "norfab:brisbane-prod",
  "jti": "01J...",
  "iat": 1781399025,
  "exp": 1781399925,
  "principal_id": "oidc:https://id.example.com#abc",
  "principal_type": "human",
  "username": "alice",
  "scope": "norfab:connect nornir:execute",
  "roles": ["network-operator"],
  "cnf": {
    "norfab_curve_key_sha256": "base64url..."
  },
  "auth_time": "2026-06-14T01:23:45Z",
  "acr": "urn:example:aal2",
  "amr": ["pwd", "otp"],
  "policy_version": "sha256:..."
}
```

The exact confirmation-claim profile must be specified and tested. It should
follow the proof-of-possession semantics of RFC 7800 while defining an
unambiguous representation of the ZeroMQ CURVE public key.

The broker stores no durable session record. On the data plane the credential
is accepted only when:

- Its signature, issuer, audience, time, and required claims are valid.
- It is presented over a CURVE connection using the bound key.
- Its policy version is accepted by the broker.
- It is not present in the broker's bounded revocation cache.
- The request is not a replay where one-time semantics apply.

The broker may cache the validation result until the credential expires. This
cache is disposable soft state.

Revocation is handled by short credential lifetimes plus signed revocation
updates. Operations requiring immediate revocation semantics use AAA
introspection or a fresh authorization decision.

### MFA and step-up

MFA policy belongs at the identity provider. Norfab records the resulting
assurance information.

Authorization rules may require:

- A minimum `acr` value.
- An `amr` value indicating MFA or hardware-key use.
- An `auth_time` no older than a configured duration.

Examples of operations that may require fresh step-up authentication:

- Running shell commands.
- Sending network configuration.
- Changing AAA policy.
- Approving a worker.
- Reading stored secrets.
- Disabling audit export.

If the credential lacks sufficient assurance, the broker returns a distinct
`STEP_UP_REQUIRED` response. The client obtains a new OIDC authorization with
the requested `acr_values` or reauthentication requirement and exchanges it
for a new Norfab access credential.

Policies should prefer `acr` assurance classes over hard-coding individual
authentication methods. `amr` remains useful for audit detail.

### Key enrollment

The AAA credential registry is separate from the user directory:

```text
principals
  principal_id, type, issuer, subject, username, enabled, created_at

credentials
  credential_id, principal_id, curve_public_key, fingerprint, status,
  created_at, approved_at, approved_by, expires_at, last_seen_at

credential_events
  event_id, credential_id, action, actor_id, reason, version, created_at
```

Enrollment sequence:

1. The client validates the AAA HTTPS endpoint.
2. The client authenticates to the configured OIDC provider.
3. The client generates or loads its local CURVE key pair.
4. The client submits the public key and access token to `/enroll`.
5. AAA validates the token and enrollment policy.
6. The credential becomes `active` automatically or `pending` for approval.
7. The client receives the broker discovery descriptor and credential status.
8. AAA exchanges a valid external token for a key-bound Norfab credential.
9. A broker validates that credential and its key binding before accepting any
   application command.

Auto-enrollment policy can require an issuer, audience, group, device posture,
or minimum authentication assurance. A successful IdP login alone does not have
to imply access to every Norfab deployment.

Manual approval records the approving principal and reason. Revocation prevents
AAA from issuing new credentials and is distributed to brokers. Existing
credentials remain valid only within the configured short expiry or until a
broker receives the revocation update.

### Worker enrollment

Workers use a separate enrollment policy and principal type. A worker must be
authorized to:

- Register a specific worker name or name pattern.
- Register a specific service.
- Receive jobs for that service.
- Publish events and results.

A worker must not be able to claim an arbitrary service merely by changing its
`READY` frame.

Recommended worker bootstrap options:

1. One-time, short-lived enrollment token created by an administrator.
2. OAuth client credentials for managed service accounts.
3. A workload identity provider in larger deployments.

AAA issues each worker a short-lived signed workload credential bound to that
worker's CURVE key. The credential lists the worker names and services it may
register. Every active-active replica has its own credential and identity.

## ZAP and CURVE changes

The current configuration:

```python
self.auth.allow_any = True
self.auth.configure_curve(location=zmq.auth.CURVE_ALLOW_ANY)
```

provides encrypted transport but does not authenticate a Norfab principal. In
the stateless-broker design, ZAP and NFP authentication have distinct jobs:

- ZAP establishes CURVE encryption and exposes the connecting key fingerprint.
- The signed Norfab credential authenticates and authorizes the principal.

Use a custom ZAP authenticator that:

- Returns a stable `User-Id` derived from the CURVE public-key fingerprint.
- Makes that fingerprint available for credential binding.
- Rate-limit repeated failures.
- Optionally rejects fingerprints in a signed in-memory revocation set.
- Emits transport-authentication audit events.

The ZAP handler does not need a durable credential database and does not need to
call AAA for every handshake. A connection authenticated only by CURVE is
quarantined: the broker rejects `POST`, `GET`, `PUT`, `MMI`, `READY`, and other
application commands until a valid key-bound Norfab credential is present.

An optional stricter mode can distribute a signed active-key snapshot from AAA
to each broker and reject unknown keys during ZAP. The snapshot is disposable
broker cache, not broker-owned state.

PyZMQ provides `configure_curve_callback()` and `curve_user_id()` for custom key
handling. A custom authenticator may be needed to return all required metadata.

Before implementation, create a small compatibility spike proving that the
broker can retrieve the ZAP `User-Id` from received ROUTER message metadata
using the pinned PyZMQ and libzmq versions. If this is not reliable, keep an
ephemeral connection-to-key map populated by a custom ZAP handler.

## NFP v2 security header

### Principle

The username added to NFP must be part of a broker-issued principal context. It
must never be accepted directly from a client as proof of identity.

The immutable principal ID is authoritative. `username` is included for readable
logs and user interfaces.

### Client-to-broker message

One possible NFP v2 request envelope is:

```text
[
  empty,
  NFPC02,
  command,
  access_credential,
  service,
  workers,
  request_uuid,
  request_metadata,
  payload
]
```

`request_metadata` is a versioned JSON object:

```json
{
  "version": 1,
  "task": "cli",
  "created_at": "2026-06-14T01:25:00Z",
  "content_type": "application/json",
  "trace_id": "..."
}
```

The client presents the signed AAA credential but cannot add or override
authoritative roles, username, `acr`, or `amr` outside that credential.

The broker must redact `access_credential` and payload data from logs.

### Worker-to-broker message

Workers use the same credential pattern. A v2 registration message may be:

```text
[
  empty,
  NFPW02,
  READY,
  workload_credential,
  service,
  worker_metadata
]
```

The broker validates that:

- The credential is issued to a workload principal.
- Its confirmation claim matches the worker CURVE key.
- Its audience includes the fabric.
- Its permissions allow the claimed worker name and service.
- The credential, principal, and key are not revoked.

Subsequent worker messages either carry the credential or refer to an
authenticated connection context cached until credential expiry. The latter is
soft state and is rebuilt after reconnect.

### Broker-to-worker message

The broker adds an identity and authorization context:

```text
[
  empty,
  NFPB02,
  command,
  client_routing_id,
  principal_context,
  request_uuid,
  payload
]
```

This shape can reuse the currently empty application frame between
`client_routing_id` and `request_uuid`, which reduces migration impact. NFP v2
must still version and validate the frame explicitly.

Example `principal_context`:

```json
{
  "version": 1,
  "principal_id": "oidc:https://id.example.com#abc",
  "principal_type": "human",
  "username": "alice",
  "access_jti": "01J...",
  "credential_id": "curve-key-17",
  "auth_time": "2026-06-14T01:23:45Z",
  "acr": "urn:example:aal2",
  "amr": ["pwd", "otp"],
  "decision_id": "authz-01J...",
  "policy_version": "sha256:...",
  "trace_id": "..."
}
```

The CURVE broker-to-worker connection authenticates and protects the context in
transit. If the context is used as durable evidence outside that connection, it
should include the AAA credential `jti`, policy version, decision ID, and broker
ID. An optional detached broker signature can provide durable provenance without
requiring a broker database.

Workers must store at least:

- `principal_id`
- `username`
- `principal_type`
- `access_jti`
- `decision_id`
- `client_address`
- `request_uuid`
- `task`

The `Job` object should expose a read-only principal context to tasks.

### Version negotiation

- NFP v1 remains available only in an explicit compatibility mode.
- A secure deployment defaults to rejecting unauthenticated NFP v1 clients.
- NFP v2 clients and workers advertise supported security capabilities.
- The broker must never silently downgrade an authenticated NFP v2 request to
  unauthenticated v1 behavior.

## Authorization

### Enforcement points

The broker is the primary policy enforcement point because it sees the actor,
requested service, worker target, command, task, and routing decision.
`norfab-aaa` is the policy administration and decision authority.

Workers perform defense-in-depth checks:

- Confirm the context came from the broker.
- Confirm the task matches the authorized resource.
- Reject missing or expired context in secure mode.
- Apply task-local safety constraints that cannot be evaluated by the broker.

### Policy input

The normalized authorization request should resemble:

```json
{
  "subject": {
    "id": "oidc:https://id.example.com#abc",
    "type": "human",
    "groups": ["network-operators"],
    "acr": "urn:example:aal2",
    "auth_age_seconds": 42
  },
  "action": {
    "command": "POST",
    "service": "nornir",
    "task": "cfg"
  },
  "resource": {
    "workers": ["nornir-worker-1"],
    "environment": "production"
  },
  "context": {
    "source_ip": "192.0.2.10",
    "time": "2026-06-14T01:25:00Z",
    "request_uuid": "..."
  }
}
```

The decision should include more than a Boolean:

```json
{
  "allow": true,
  "decision_id": "authz-01J...",
  "matched_policy": "network-operator-config",
  "policy_version": "sha256:...",
  "allowed_workers": ["nornir-worker-1"],
  "obligations": {
    "audit_payload_hash": true,
    "require_fresh_auth_seconds": 300
  }
}
```

### RBAC model

Initial roles may include:

- `norfab-viewer`
- `norfab-operator`
- `norfab-network-configurator`
- `norfab-worker-operator`
- `norfab-security-admin`
- `norfab-auditor`

Permissions should use explicit resources and actions:

```text
nornir/cli:execute
nornir/cfg:execute
netbox/get_devices:execute
broker/workers:read
aaa/credentials:approve
aaa/policy:update
worker/run_shell_cmd:execute
```

Role bindings can map:

- OIDC subjects to roles.
- Trusted IdP groups to local roles.
- Workload subjects to narrow service permissions.

IdP groups are inputs to role mapping, not automatically Norfab administrator
roles. AAA policy controls the mapping.

### Policy implementation

Define an internal `AuthorizationProvider` interface before selecting a single
policy engine:

```python
class AuthorizationProvider:
    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        ...
```

Recommended evaluation modes:

- `SignedBundleAuthorizationProvider`: broker evaluates a versioned policy
  bundle signed and distributed by AAA. This is the normal low-latency path.
- `RemoteAaaAuthorizationProvider`: broker asks AAA for decisions that require
  immediately current external state.
- `OpaAuthorizationProvider`: AAA uses Open Policy Agent for centralized
  enterprise policy, conditional rules, and policy-as-code tests.
- `LocalDevelopmentAuthorizationProvider`: local YAML for tests and isolated
  development only. It is not the production system of record.

PyCasbin is a reasonable embedded alternative for deployments that need role
hierarchy and adapters without running OPA. It should not become a hard core
dependency until its policy model and operational behavior are evaluated
against Norfab's service/task/worker requirements.

All providers must default to deny on errors, timeouts, invalid signatures,
missing policy, and unknown resources. A narrowly scoped, cached
last-known-good signed policy can be allowed during an AAA service outage if the
deployment explicitly enables that behavior.

### Task declarations

The existing `Task` metadata can later declare authorization requirements:

```python
@Task(
    authorization={
        "permission": "nornir/cfg:execute",
        "assurance": "aal2",
        "fresh_auth_seconds": 300,
    }
)
def cfg(...):
    ...
```

The broker should discover this metadata with task schemas. Policy remains
authoritative, while declarations provide safe defaults and make dangerous
tasks easier to identify.

## Accounting and audit

### Required events

Authentication:

- Login started, succeeded, failed, refreshed, and logged out.
- Key enrollment requested, approved, rejected, rotated, expired, and revoked.
- Norfab access credential issued, expired, and revoked.
- Step-up requested and completed.

Authorization:

- Allowed and denied decisions.
- Policy version and matched rule.
- Requested service, task, worker selector, and final workers.

Execution:

- Job submitted, dispatched, accepted, started, completed, failed, cancelled,
  and timed out.
- Worker registered, disconnected, expired, and changed service.
- Interactive input requested and answered, without recording secret input.

Administration:

- Principal, role, binding, policy, issuer, key, audit, and security
  configuration changes.

### Event fields

Each event should include:

```text
event_id
event_type
timestamp_utc
broker_id
principal_id
username
principal_type
access_jti
credential_id
source_ip
request_uuid
trace_id
service
task
requested_workers
selected_workers
decision_id
policy_version
outcome
reason_code
duration
payload_hash
previous_event_hash
```

Do not record:

- Passwords, OTP values, WebAuthn assertions, external access tokens, refresh
  tokens, or complete Norfab access credentials.
- Full job payloads by default.
- Secret interactive input.
- Private keys.

### Storage and export

The broker must not be the durable audit store. Brokers and workers emit events
to the active-active AAA accounting endpoint or to a durable event transport
consumed by that endpoint. The accounting service stores and exports them to a
SIEM or log platform.

Use structured JSON events and OpenTelemetry-compatible trace and correlation
identifiers. Audit records should be separate from ordinary debug logs.

A hash chain and periodic external checkpoint can make tampering detectable:

```text
event_hash = SHA-256(canonical_event || previous_event_hash)
```

This does not replace operating-system permissions, append-only storage, backup,
retention, or an external protected audit sink.

The broker may keep a bounded memory queue or local spool during a short
accounting outage. This is delivery buffering, not the audit system of record.
Policy may require privileged operations to fail closed when no durable audit
path exists.

## Encrypted transport

### Required trust model

The encryption requirement is continuous encryption in transit across the
mediated path:

```text
client == CURVE encrypted ==> broker == CURVE encrypted ==> worker
```

The broker terminates the client CURVE connection, decrypts the NFP message,
performs authentication, authorization, accounting, and routing, then sends the
message over a separately encrypted CURVE connection to the worker.

This is hop-by-hop authenticated encryption with a trusted broker. It is often
described operationally as encrypted client-to-worker communication because no
network segment carries plaintext. It is not cryptographic end-to-end
encryption in the narrower sense where only the client and worker can decrypt.

This ADR does not require broker-blind payload encryption or an additional
application encryption layer.

### CURVE requirements

CURVE remains suitable for the ZeroMQ data plane when:

- Every client-to-broker and worker-to-broker connection enables CURVE.
- The broker public key is obtained through authenticated AAA discovery.
- Client and worker access credentials are bound to their CURVE keys.
- Broker, client, and worker keys are rotated and revocable.
- Private key files have strict permissions.
- The broker refuses application commands without a valid AAA credential.
- Plain ZeroMQ endpoints are disabled in secure mode.

An L4 load balancer, TCP proxy, router, firewall, or other middle component sees
only CURVE ciphertext. It must not terminate the ZeroMQ security mechanism.

If a TLS proxy or service mesh terminates encryption before the broker, that
proxy becomes part of the trusted computing base. CURVE should normally remain
enabled through the proxy so TLS is an additional layer rather than the only
data-plane protection.

The HTTPS link between clients and `norfab-aaa` uses TLS and X.509. Connections
from brokers and workers to AAA also use TLS, with mTLS recommended for service
identity.

### Encryption at rest

Encrypted transport does not protect:

- Worker job SQLite databases.
- Client job SQLite databases.
- AAA databases and accounting stores.
- Inventory files.
- Crash dumps.
- Debug logs.

Use operating-system disk encryption as the baseline. For higher assurance, use
envelope-encrypted fields with keys from an external KMS or HSM and prefer
secret references over embedding secrets in job payloads.

## Library and component recommendations

These choices should be pinned and reviewed when implementation begins.

| Need | Recommended option | Notes |
| --- | --- | --- |
| ZeroMQ transport | Existing `pyzmq` CURVE | Keep CURVE on both data-plane hops; use custom ZAP to expose key fingerprints |
| Dedicated AAA API | FastAPI/Starlette plus Uvicorn | Run as an independent active-active service, not inside the broker |
| OAuth/OIDC client flow | Authlib plus `httpx` | Device Authorization and Authorization Code with PKCE |
| JWT/JWKS validation | `joserfc` plus `httpx` | Pin allowed algorithms and validate issuer, audience, time, and required claims |
| Token exchange | OAuth 2.0 Token Exchange profile | AAA exchanges IdP tokens for short-lived key-bound Norfab credentials |
| X.509 and signing | `cryptography` | Discovery signing, AAA credential signing, and certificate validation |
| AAA durable state | PostgreSQL or equivalent HA database | Principals, credentials, approvals, role bindings, policy metadata, and audit |
| Policy distribution | Signed versioned bundles | Brokers evaluate locally without durable policy state |
| Enterprise policy | Open Policy Agent | AAA is policy authority; brokers are PEPs |
| Embedded RBAC alternative | PyCasbin | Evaluate before making it a hard dependency |
| Human MFA | Okta, Keycloak, or another OIDC IdP | Norfab consumes assurance claims; it does not implement MFA |
| LDAP/AD | Keycloak user federation or existing enterprise IdP | Avoid direct password collection in Norfab |
| Accounting transport | Durable event stream or active-active HTTPS ingestion | Broker keeps only a bounded delivery buffer |
| Audit correlation | OpenTelemetry conventions | Keep security audit storage separate from diagnostic logs |

## Alternatives considered

### Continue CURVE with a static copied broker key

Advantages:

- Smallest implementation change.
- Strong encrypted transport when the copied key is correct.

Disadvantages:

- Manual key distribution and rotation.
- No human login, MFA, RBAC, or useful accounting identity.
- Current allow-any configuration does not authorize clients.

Decision: retain only as an explicit compatibility mode.

### Use ZeroMQ PLAIN with username and password

Advantages:

- ZAP can map a username to a user ID.
- Easy to understand.

Disadvantages:

- The PLAIN mechanism sends username/password credentials without providing
  transport encryption.
- It would require a separate secure tunnel.
- It encourages Norfab to collect reusable passwords.
- MFA, passkeys, federation, step-up, and token revocation become custom work.

Decision: rejected for the target architecture.

### Authenticate directly against LDAP

Advantages:

- Fewer external components in a simple LDAP deployment.

Disadvantages:

- Norfab handles user passwords.
- MFA and passkeys are difficult or provider-specific.
- LDAP group semantics leak into the protocol.
- Account-risk policy, browser login, recovery, and federation must be rebuilt.

Decision: support only through an optional compatibility authentication
provider. Prefer OIDC through an identity broker that federates LDAP.

### ZeroMQ GSSAPI/Kerberos

Advantages:

- Mutual authentication and confidentiality.
- No copied CURVE server key.
- Natural fit for some Active Directory environments.

Disadvantages:

- The ZMTP GSSAPI specification is still marked draft.
- Deployment and cross-platform packaging are more complex.
- It does not solve Okta, general OIDC, passkeys, or Norfab RBAC by itself.
- Kerberos service-principal and realm operations become mandatory.

Decision: valid optional enterprise transport, not the default.

### TLS proxy around ZeroMQ

Examples include stunnel, Envoy, HAProxy, or a service mesh.

Advantages:

- Standard X.509 PKI and certificate rotation.
- Can provide mTLS.

Disadvantages:

- Extra deployment component and failure mode.
- The broker may see only the proxy connection unless identity is propagated
  securely.
- It still needs key-bound Norfab credentials and RBAC.
- Termination at the proxy makes the proxy part of the trusted computing base.

Decision: supported deployment option, especially where enterprise PKI and
service mesh are already present. It does not replace the AAA protocol.

### Replace ZeroMQ with gRPC, HTTP/2, QUIC, or NNG TLS

Advantages:

- Standard TLS and mature authentication middleware.
- Easier integration with gateways and service meshes.

Disadvantages:

- Large rewrite of routing, streaming, keepalives, worker registration, and job
  behavior.
- High compatibility and migration cost.

Decision: not selected for the AAA project. Revisit only as a separate transport
ADR.

### Trust on first use

Advantages:

- Very easy first connection.

Disadvantages:

- The first connection can be intercepted.
- Rotation and disaster recovery are awkward.

Decision: development mode only.

## Migration plan

### Phase 0 - Immediate hardening

- Stop logging complete multipart messages, access credentials, and payloads.
- Add redaction helpers and security-focused log tests.
- Document private key file permission requirements.
- Add broker key fingerprints to status output.
- Add an optional static client-key allowlist before full enrollment exists.
- Add security configuration validation that warns loudly about
  `CURVE_ALLOW_ANY`.

### Phase 1 - Dedicated AAA service foundation

- Add Pydantic models for principals, credentials, access claims, issuers,
  authorization requests, decisions, and audit events.
- Add the independent `norfab-aaa` service and durable database migrations.
- Keep broker security storage limited to in-memory caches.
- Add unit tests for expiry, revocation, role mapping, and default deny.
- Define stable reason codes and avoid exposing sensitive validation detail to
  unauthenticated clients.

### Phase 2 - Active-active discovery, enrollment, and token exchange

- Add the well-known discovery document.
- Add OIDC issuer configuration and JWKS caching.
- Implement Device Authorization in `nfcli`.
- Add enrollment, approval, list, rotate, and revoke APIs.
- Issue short-lived signed Norfab credentials bound to CURVE keys.
- Run multiple AAA replicas against shared durable state and signing keys.
- Add worker one-time enrollment.
- Test broker CURVE key rotation with overlapping keys.

### Phase 3 - Key-aware ZAP and NFP authentication gate

- Map CURVE keys to stable fingerprint-based ZAP user IDs.
- Reject all application commands without a valid signed Norfab credential.
- Bind credentials to the current connection key fingerprint.
- Add optional signed active-key and revocation snapshots.
- Add rate limits and authentication audit events.

### Phase 4 - NFP v2 identity context

- Add `NFPC02`, `NFPB02`, and `NFPW02`.
- Add the access-credential frame and broker-issued principal context.
- Store principal and decision fields in worker job databases.
- Expose read-only actor context on `Job`.
- Add downgrade and malformed-context tests.

### Phase 5 - Distributed policy and accounting

- Implement default-deny AAA policy and signed policy bundles.
- Enforce policy before MMI, inventory, dispatch, and worker registration.
- Add task permission declarations for dangerous built-in tasks.
- Add active-active accounting ingestion and durable export.
- Add broker delivery buffers, OPA provider, and policy contract tests.

### Phase 6 - MFA step-up and assurance policy

- Map issuer-specific `acr` and `amr` values to configured Norfab assurance
  levels.
- Add fresh-authentication requirements.
- Add `STEP_UP_REQUIRED` protocol responses.
- Test Okta and a Keycloak-to-LDAP deployment.

### Phase 7 - Active-active workers and broker failover

- Give every worker replica a unique workload identity.
- Test `any`, `all`, and explicit worker selection semantics.
- Add duplicate request UUID handling and task idempotency declarations.
- Support workers connected to multiple broker instances.
- Test broker restart and client failover without a broker-owned job database.

## Required tests

- A CURVE connection without a valid AAA credential cannot execute any command.
- Strict ZAP mode rejects unknown, pending, revoked, and expired CURVE keys.
- An approved key cannot claim another principal by changing routing identity.
- A stolen access credential fails when used with a different CURVE key.
- Tokens with wrong issuer, audience, signature, algorithm, time, or scope fail.
- Username changes do not change the principal or permissions.
- Group-to-role changes take effect within the configured cache limit.
- Every command path is default-deny without a matching policy.
- MMI and inventory services are authorized, not bypassed.
- Worker `READY` cannot register an unauthorized name or service.
- Sensitive tasks require the expected permission and assurance.
- Revocation stops new credential issuance and reaches brokers within the
  configured bound.
- Audit events exist for allow, deny, login failure, approval, revocation, and
  execution outcome.
- Tokens, passwords, private keys, and secret payloads never appear in logs.
- Broker key rotation works without disabling broker authentication.
- NFP v2 cannot silently downgrade to unauthenticated NFP v1.
- Both client-to-broker and broker-to-worker links reject plain transport in
  secure mode.
- Loss of one AAA replica does not interrupt token exchange or administration.
- Broker restart does not lose durable AAA, accounting, or job state.
- `workers="any"` executes once on one healthy replica.
- `workers="all"` intentionally executes on every selected healthy replica.
- Idempotent tasks or shared service-level deduplication prevent unintended
  repeated side effects for duplicate request UUIDs across worker replicas.

## Consequences

Positive:

- Human credentials and MFA remain with a specialized identity provider.
- Okta and LDAP-backed identities converge on one OIDC contract.
- The broker gains a trustworthy actor identity and enforceable RBAC.
- Key enrollment can be automatic or manually approved.
- Broker CURVE keys can rotate without copying a new key to every client by
  hand.
- Workers receive a durable principal and authorization decision for accounting.
- Brokers do not require a durable security or audit database.
- Active-active AAA and worker pools remove individual service instances as
  single points of failure.
- All mediated traffic remains encrypted on every network segment.

Negative:

- An active-active HTTPS AAA service, CA trust, shared database, and signing-key
  lifecycle must be operated.
- Existing clients and workers need an NFP v2 migration.
- Secure token validation requires careful caching, rotation, timeout, and
  algorithm configuration.
- Short-lived credentials reduce but do not eliminate revocation delay.
- Broker failover still loses live ZeroMQ connections and in-flight soft state;
  clients and workers must reconnect and retry idempotently.
- Active-active worker retries require clear task idempotency semantics.

## Open questions

- Which CA model is expected for standalone installations?
- Which OIDC providers must be in the first interoperability test matrix?
- Is Okta Device Authorization available under the expected tenant policies?
- Will LDAP deployments use Keycloak, an existing enterprise IdP, or an optional
  direct compatibility provider?
- What are the initial roles, protected tasks, and environment boundaries?
- How quickly must role changes and revocations take effect?
- What audit retention, privacy, and external export requirements apply?
- What durable database, event transport, and KMS will back active-active AAA?
- What access-credential lifetime balances failover, revocation, and login load?
- Which operations require synchronous AAA decisions instead of signed bundles?
- Should production use permissive fingerprint-only ZAP plus NFP authentication,
  or require signed active-key snapshots at ZAP?
- How will workers connect to multiple brokers without duplicate dispatch?
- Are broker endpoints individually discovered, or placed behind an L4 load
  balancer with a shared broker CURVE key?
- Can the pinned PyZMQ/libzmq combination expose ZAP `User-Id` metadata on
  ROUTER messages as required?

## References

- [CurveZMQ specification](https://rfc.zeromq.org/spec/26/)
- [ZeroMQ Authentication Protocol](https://rfc.zeromq.org/spec/27/)
- [PyZMQ authentication API](https://pyzmq.readthedocs.io/en/latest/api/zmq.auth.html)
- [ZMTP GSSAPI draft](https://rfc.zeromq.org/spec/38/)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth 2.0 Device Authorization Grant, RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628)
- [OAuth 2.0 Token Exchange, RFC 8693](https://datatracker.ietf.org/doc/html/rfc8693)
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://datatracker.ietf.org/doc/html/rfc9700)
- [Proof-of-Possession Key Semantics for JWTs, RFC 7800](https://datatracker.ietf.org/doc/html/rfc7800)
- [JWT Profile for OAuth 2.0 Access Tokens, RFC 9068](https://datatracker.ietf.org/doc/html/rfc9068)
- [Authentication Method Reference Values, RFC 8176](https://datatracker.ietf.org/doc/html/rfc8176)
- [Okta Device Authorization Grant](https://developer.okta.com/docs/guides/device-authorization-grant/main/)
- [Keycloak Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/)
- [Authlib OAuth 2 client documentation](https://docs.authlib.org/en/latest/client/oauth2.html)
- [joserfc JWT documentation](https://jose.authlib.org/en/guide/jwt/)
- [Open Policy Agent documentation](https://www.openpolicyagent.org/docs)
- [Apache Casbin RBAC documentation](https://casbin.apache.org/docs/rbac/)
