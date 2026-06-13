# ADR - Norfab AAA and End-to-End Security Architecture

## Status

Proposed.

Date: 2026-06-14.

This ADR is an architecture proposal. It does not authorize replacing the
current protocol in one change. The migration must be staged and preserve an
explicit compatibility mode until NFP v2 is ready.

## Decision summary

Norfab will separate human authentication from ZeroMQ transport security:

1. Keep ZeroMQ CURVE as the encrypted data-plane transport.
2. Add an HTTPS control plane for broker discovery, OIDC login, key enrollment,
   approvals, revocation, and administration.
3. Use an external OpenID Connect identity provider for human authentication.
   Okta can be used directly. LDAP and Active Directory should normally be
   connected through an identity broker such as Keycloak rather than queried
   directly by the Norfab broker.
4. Require MFA at the identity provider. The Norfab broker consumes validated
   `acr`, `amr`, and `auth_time` claims and can require fresh step-up
   authentication for sensitive operations.
5. Replace `CURVE_ALLOW_ANY` on the operational data plane with a registry-backed
   custom ZAP authenticator.
6. Bind each short-lived Norfab session to the authenticated CURVE client key.
7. Identify users by the immutable OIDC `(iss, sub)` pair. A username is a
   display attribute, not the security identifier.
8. Add a broker-issued principal context to NFP v2 messages sent to workers.
   Clients must never be trusted to assert their own username, roles, or MFA
   state.
9. Make the broker the primary policy enforcement point. Use default-deny RBAC
   initially, behind an authorization provider interface. Add an OPA provider
   for centralized or more conditional policy.
10. Add structured, append-only audit events at the broker and execution events
    at workers.
11. Treat client-to-worker payload encryption, where the broker cannot decrypt
    job content, as a separate NFP v2 phase using standardized hybrid
    encryption. It must not be confused with the current hop-by-hop CURVE
    encryption.

The recommended target architecture is therefore:

```text
                  HTTPS + X.509
  Client  <---------------------------->  Norfab control API
     |          discovery, OIDC login,      |
     |          enrollment, approvals       |
     |                                      |
     | CURVE + key-bound session            | OIDC / OAuth
     v                                      v
  ZeroMQ data socket  <---- Broker ---->  Okta / Keycloak / other IdP
                              |
                              | CURVE + workload identity
                              v
                           Workers
                              |
                              v
                    Audit store / SIEM / OTel
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
- Provide a path to client-to-worker encrypted payloads when the broker is not
  permitted to read job arguments or results.
- Preserve a practical migration path from NFP v1.

## Non-goals

- Norfab will not become a general-purpose password database or MFA server.
- A username supplied by a client will not be treated as authenticated.
- The ZeroMQ routing identity will not be treated as a human identity.
- The first AAA release will not hide routing metadata from the broker.
- The first AAA release will not encrypt all SQLite databases at the field
  level. Data-at-rest protection is a separate requirement.
- RBAC will not be implemented independently in every worker.
- Direct LDAP username/password bind will not be the preferred human login
  mechanism.

## Threat model

The initial AAA design protects against:

- Network eavesdropping and message modification.
- Clients impersonating other users by changing a username or routing identity.
- Unknown CURVE keys accessing the operational data plane.
- Stolen Norfab session tokens used without the bound CURVE private key.
- Unauthorized access to services, tasks, workers, and management operations.
- Replay of expired or previously consumed authentication operations.
- Accidental disclosure of credentials in logs and audit records.
- Continued access after key or session revocation, subject to bounded cache and
  disconnect delays.

The optional payload encryption phase additionally protects job payloads from
an honest-but-curious broker.

It does not, by itself, protect against:

- A compromised client or worker host.
- A compromised identity provider.
- A broker that controls both worker key discovery and the signing authority
  used to certify those keys.
- Traffic analysis based on endpoints, message size, timing, service, task, or
  worker selection.
- Secrets intentionally returned by a task and then logged by application code.

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

The broker, or a companion `norfab-authd` service, exposes an HTTPS control
endpoint with an X.509 certificate issued by a public or enterprise CA trusted
by clients.

An authenticated discovery document is available at a well-known path such as:

```text
https://broker.example.com/.well-known/norfab
```

Example:

```json
{
  "version": 1,
  "broker_id": "brisbane-prod-1",
  "nfp_endpoints": ["tcp://broker.example.com:5555"],
  "curve_keys": [
    {
      "kid": "curve-2026-06",
      "public_key": "Z85_ENCODED_KEY",
      "not_before": "2026-06-01T00:00:00Z",
      "not_after": "2026-09-01T00:00:00Z",
      "status": "current"
    }
  ],
  "oidc_issuers": [
    {
      "issuer": "https://example.okta.com/oauth2/default",
      "audience": "api://norfab"
    }
  ],
  "control_api": "https://broker.example.com/api/v1",
  "expires_at": "2026-06-14T12:00:00Z"
}
```

The client validates HTTPS through its CA trust store, caches the descriptor for
a bounded time, and then configures `curve_serverkey` with the discovered key.
Broker key rotation uses an overlap period with current and next keys.

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

An OIDC token must never be sent to a broker before the broker endpoint has been
authenticated by one of these methods.

## Authentication control plane

### Human login flow

CLI and desktop clients should use one of:

- OAuth 2.0 Device Authorization Grant for terminals and remote shells.
- Authorization Code with PKCE when a local browser callback is practical.

The identity provider performs password, passkey, WebAuthn, OTP, push, or other
MFA. Norfab does not collect the user's password or OTP.

The control API validates an access token, not an arbitrary username and
password. Validation includes:

- HTTPS issuer discovery from an allowlisted issuer.
- Signature against cached and rotated JWKS keys, or token introspection for an
  opaque token.
- Exact issuer match.
- Expected audience.
- Expiry and not-before time.
- Required scope.
- Subject presence.
- Authorized client ID where applicable.
- Allowed algorithms configured by the broker, never selected freely from the
  token header.

ID tokens are intended for the OIDC client. The broker resource server should
normally consume an access token minted for the Norfab audience.

After validation, the control API creates a short-lived Norfab session:

```json
{
  "session_id": "random-opaque-identifier",
  "principal_id": "oidc:https://id.example.com#abc",
  "curve_key_fingerprint": "sha256:...",
  "auth_time": "2026-06-14T01:23:45Z",
  "acr": "urn:example:aal2",
  "amr": ["pwd", "otp"],
  "expires_at": "2026-06-14T01:38:45Z"
}
```

The client receives a random opaque session token. The broker stores only a
hash of that token. On the data plane the token is accepted only when:

- It is active and unexpired.
- It is presented over a CURVE connection using the bound key.
- The principal and key are still active.
- The request is not a replay where one-time semantics apply.

Opaque sessions are preferred for the first implementation because immediate
revocation and server-side policy updates are simpler. A signed session token
can be considered for a broker cluster, but it still needs revocation and key
binding.

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

If the session lacks sufficient assurance, the broker returns a distinct
`STEP_UP_REQUIRED` response. The client obtains a new OIDC authorization with
the requested `acr_values` or reauthentication requirement and exchanges it
for a refreshed Norfab session.

Policies should prefer `acr` assurance classes over hard-coding individual
authentication methods. `amr` remains useful for audit detail.

### Key enrollment

The key registry is separate from the user directory:

```text
principals
  principal_id, type, issuer, subject, username, enabled, created_at

credentials
  credential_id, principal_id, curve_public_key, fingerprint, status,
  created_at, approved_at, approved_by, expires_at, last_seen_at

sessions
  token_hash, principal_id, credential_id, auth_time, acr, amr,
  created_at, expires_at, revoked_at
```

Enrollment sequence:

1. The client validates the HTTPS control endpoint.
2. The client authenticates to the configured OIDC provider.
3. The client generates or loads its local CURVE key pair.
4. The client submits the public key and access token to `/enroll`.
5. The broker validates the token and enrollment policy.
6. The credential becomes `active` automatically or `pending` for approval.
7. The client receives the broker discovery descriptor and credential status.
8. The data-plane ZAP authenticator accepts only active, unexpired keys.

Auto-enrollment policy can require an issuer, audience, group, device posture,
or minimum authentication assurance. A successful IdP login alone does not have
to imply access to every Norfab deployment.

Manual approval records the approving principal and reason. Revocation must
invalidate new ZAP handshakes, active Norfab sessions, and existing routing
connections as quickly as the transport permits.

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

## ZAP and CURVE changes

The operational data socket must stop using:

```python
self.auth.allow_any = True
self.auth.configure_curve(location=zmq.auth.CURVE_ALLOW_ANY)
```

Use a custom ZAP authenticator backed by the credential registry. It must:

- Reject unknown, pending, revoked, or expired keys.
- Return a stable ZAP `User-Id` derived from the credential or principal.
- Keep the public key fingerprint available for session binding.
- Reload changes without restarting the broker.
- Rate-limit repeated failures.
- Emit authentication audit events.

PyZMQ provides `configure_curve_callback()` for database-backed key validation
and `curve_user_id()` for mapping an accepted public key to a user ID. A custom
authenticator may be needed to return all required metadata and to support
efficient revocation.

Before implementation, create a small compatibility spike proving that the
broker can retrieve the ZAP `User-Id` from received ROUTER message metadata
using the pinned PyZMQ and libzmq versions. If this is not reliable, keep an
explicit connection registry populated by a custom ZAP handler.

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
  session_token,
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
  "payload_encryption": "none",
  "trace_id": "..."
}
```

The client does not send authoritative roles, username, `acr`, or `amr`.

The broker must redact `session_token` and payload data from logs.

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
  "session_id": "8d9f...",
  "credential_id": "curve-key-17",
  "auth_time": "2026-06-14T01:23:45Z",
  "acr": "urn:example:aal2",
  "amr": ["pwd", "otp"],
  "decision_id": "authz-01J...",
  "policy_version": "sha256:...",
  "trace_id": "..."
}
```

The context should be signed by a broker signing key when it is stored,
forwarded across broker boundaries, or used as evidence outside the live CURVE
connection. The CURVE broker-to-worker connection already protects it in
transit, but a signature gives durable provenance.

Workers must store at least:

- `principal_id`
- `username`
- `principal_type`
- `session_id`
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
broker/credentials:approve
broker/policy:update
worker/run_shell_cmd:execute
```

Role bindings can map:

- OIDC subjects to roles.
- Trusted IdP groups to local roles.
- Workload subjects to narrow service permissions.

IdP groups are inputs to role mapping, not automatically Norfab administrator
roles. Local policy controls the mapping.

### Policy implementation

Define an internal `AuthorizationProvider` interface before selecting a single
policy engine:

```python
class AuthorizationProvider:
    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        ...
```

Recommended providers:

- `LocalRbacAuthorizationProvider`: built-in, versioned YAML policy for
  standalone deployments and tests.
- `OpaAuthorizationProvider`: recommended for centralized enterprise policy,
  conditional rules, policy-as-code tests, and cross-service consistency.

PyCasbin is a reasonable embedded alternative for deployments that need role
hierarchy and adapters without running OPA. It should not become a hard core
dependency until its policy model and operational behavior are evaluated
against Norfab's service/task/worker requirements.

All providers must default to deny on errors, timeouts, missing policy, and
unknown resources. A narrowly scoped, cached last-known-good policy can be
allowed during a policy service outage if the deployment explicitly enables
that behavior.

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
- Session created, expired, and revoked.
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
session_id
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

- Passwords, OTP values, WebAuthn assertions, access tokens, refresh tokens, or
  Norfab session tokens.
- Full job payloads by default.
- Secret interactive input.
- Private keys.

### Storage and export

The first implementation can append to a broker SQLite audit database with WAL
enabled and strict file permissions. Production deployments should support an
external durable store and export to a SIEM or log platform.

Use structured JSON events and OpenTelemetry-compatible trace and correlation
identifiers. Audit records should be separate from ordinary debug logs.

A hash chain and periodic external checkpoint can make tampering detectable:

```text
event_hash = SHA-256(canonical_event || previous_event_hash)
```

This does not replace operating-system permissions, append-only storage, backup,
retention, or an external protected audit sink.

If the remote sink is unavailable, the broker should spool locally. Policy may
require privileged operations to fail closed when no durable audit path exists.

## Encryption layers

### Layer 1: authenticated transport encryption

CURVE remains suitable for the ZeroMQ data plane when:

- The broker key is obtained through authenticated discovery.
- Client and worker keys are registered and checked by ZAP.
- Keys are rotated and revocable.
- Private key files have strict permissions.
- Sessions are bound to the accepted CURVE key.

This protects:

```text
client <-> broker
worker <-> broker
```

It does not protect job payloads from the broker.

### Layer 2: client-to-worker payload encryption

If the broker must not read arguments, results, events, streams, or interactive
input, add application-layer envelope encryption above CURVE.

This is a protocol change because the broker currently selects workers after
receiving one plaintext payload. The proposed flow is:

1. Client sends an authorized `RESOLVE` request containing visible service,
   task, target selector, and request metadata.
2. Broker selects workers and returns a short-lived assignment token plus each
   worker's certified encryption public key.
3. Client generates a random content-encryption key.
4. Client encrypts the payload once with an AEAD.
5. Client wraps the content key separately to every selected worker using HPKE.
6. Client submits the encrypted envelope with the broker assignment token.
7. Broker validates the visible metadata and assignment, then routes ciphertext.
8. Workers decrypt and encrypt responses to a client response key.

Example envelope:

```json
{
  "version": 1,
  "suite": "HPKE-X25519-HKDF-SHA256-CHACHA20POLY1305",
  "assignment_id": "assign-01J...",
  "aad_hash": "sha256:...",
  "recipients": [
    {
      "worker_id": "nornir-worker-1",
      "kid": "worker-key-7",
      "encapsulated_key": "base64..."
    }
  ],
  "nonce": "base64...",
  "ciphertext": "base64..."
}
```

The visible metadata must be authenticated as AEAD additional data. It includes
the command, service, task, request UUID, assignment, selected workers, content
type, deadline, and protocol version.

For `workers="any"`, worker selection must happen before encryption. For
`workers="all"`, one content key can be wrapped independently for each worker.

HPKE is preferred as the design standard. Implementation must use a maintained,
reviewed library and published test vectors. PyNaCl `Box` can support a simpler
prototype, but `SealedBox` alone does not prove the sender's identity. Do not
create a custom collection of raw X25519, HKDF, nonce, and AEAD operations
without a complete protocol review.

The payload-encryption design must define:

- Sender authentication.
- Worker key certification and rotation.
- Replay protection.
- Multi-recipient behavior.
- Large payload and stream framing.
- Bidirectional job keys.
- Cancellation and interactive input.
- Algorithm negotiation and downgrade prevention.
- Key erasure and retention.
- How workers validate broker authorization context.

### Authorization consequence of encrypted payloads

The broker cannot authorize fields it cannot read.

Task, service, worker target, and any policy-relevant attributes must therefore
remain visible in authenticated metadata. Sensitive arguments stay encrypted.
If policy depends on an argument, the protocol must expose a specifically
declared, non-secret projection of that argument or defer that check to the
worker.

Accounting can store metadata and ciphertext hashes, but not plaintext details.

### Encryption at rest

Transport and payload encryption do not protect:

- Worker job SQLite databases.
- Client job SQLite databases.
- Broker audit databases.
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
| ZeroMQ transport | Existing `pyzmq` CURVE | Keep, but replace allow-any with registry-backed ZAP |
| HTTPS control API | FastAPI/Starlette plus Uvicorn | Already familiar in the repository; run as a separate component or carefully isolated broker service |
| OAuth/OIDC client flow | Authlib plus `httpx` | Device Authorization and Authorization Code with PKCE |
| JWT/JWKS validation | `joserfc` plus `httpx` | Pin allowed algorithms and validate issuer, audience, time, and required claims |
| Opaque token validation | OAuth token introspection over `httpx` | Cache only within token lifetime and revocation requirements |
| X.509 and signing | `cryptography` | Discovery signing, broker context signing, and certificate validation |
| Local policy | Pydantic models plus versioned YAML | Small, auditable standalone baseline |
| Enterprise policy | Open Policy Agent | Broker is PEP; OPA is PDP |
| Embedded RBAC alternative | PyCasbin | Evaluate before making it a hard dependency |
| Human MFA | Okta, Keycloak, or another OIDC IdP | Norfab consumes assurance claims; it does not implement MFA |
| LDAP/AD | Keycloak user federation or existing enterprise IdP | Avoid direct password collection in Norfab |
| Payload encryption | Reviewed HPKE implementation | Prototype only after protocol and threat-model review |
| Simple crypto prototype | PyNaCl | `Box` authenticates peers; `SealedBox` does not authenticate sender |
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
- It still needs OIDC sessions and RBAC.
- It does not provide client-to-worker payload encryption.

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

- Stop logging complete multipart messages, session credentials, and payloads.
- Add redaction helpers and security-focused log tests.
- Document private key file permission requirements.
- Add broker key fingerprints to status output.
- Add an optional static client-key allowlist before full enrollment exists.
- Add security configuration validation that warns loudly about
  `CURVE_ALLOW_ANY`.

### Phase 1 - Security domain models

- Add Pydantic models for principals, credentials, sessions, issuers,
  authorization requests, decisions, and audit events.
- Add a broker security database with migrations.
- Add unit tests for expiry, revocation, role mapping, and default deny.
- Define stable reason codes and avoid exposing sensitive validation detail to
  unauthenticated clients.

### Phase 2 - HTTPS discovery and enrollment

- Add the well-known discovery document.
- Add OIDC issuer configuration and JWKS caching.
- Implement Device Authorization in `nfcli`.
- Add enrollment, approval, list, rotate, and revoke APIs.
- Add worker one-time enrollment.
- Test broker CURVE key rotation with overlapping keys.

### Phase 3 - Registry-backed ZAP

- Replace `CURVE_ALLOW_ANY` on the secure data socket.
- Map accepted CURVE keys to stable ZAP user IDs.
- Bind sessions to key fingerprints.
- Revoke active sessions when credentials are revoked.
- Add rate limits and authentication audit events.

### Phase 4 - NFP v2 identity context

- Add `NFPC02`, `NFPB02`, and `NFPW02`.
- Add the session security frame and broker-issued principal context.
- Store principal and decision fields in worker job databases.
- Expose read-only actor context on `Job`.
- Add downgrade and malformed-context tests.

### Phase 5 - RBAC and accounting

- Implement default-deny local RBAC.
- Enforce policy before MMI, inventory, dispatch, and worker registration.
- Add task permission declarations for dangerous built-in tasks.
- Add append-only audit events and export.
- Add OPA provider and policy contract tests.

### Phase 6 - MFA step-up and assurance policy

- Map issuer-specific `acr` and `amr` values to configured Norfab assurance
  levels.
- Add fresh-authentication requirements.
- Add `STEP_UP_REQUIRED` protocol responses.
- Test Okta and a Keycloak-to-LDAP deployment.

### Phase 7 - Optional client-to-worker payload encryption

- Write a dedicated cryptographic protocol specification.
- Complete an external security review.
- Implement `RESOLVE`, worker encryption-key discovery, assignments, HPKE
  envelopes, response keys, streams, and rotation.
- Keep the feature opt-in until interoperability, failure, replay, and recovery
  tests are complete.

## Required tests

- Unknown, pending, revoked, and expired CURVE keys are rejected.
- An approved key cannot claim another principal by changing routing identity.
- A stolen session token fails when used with a different CURVE key.
- Tokens with wrong issuer, audience, signature, algorithm, time, or scope fail.
- Username changes do not change the principal or permissions.
- Group-to-role changes take effect within the configured cache limit.
- Every command path is default-deny without a matching policy.
- MMI and inventory services are authorized, not bypassed.
- Worker `READY` cannot register an unauthorized name or service.
- Sensitive tasks require the expected permission and assurance.
- Revocation stops new requests and terminates or expires existing sessions.
- Audit events exist for allow, deny, login failure, approval, revocation, and
  execution outcome.
- Tokens, passwords, private keys, and secret payloads never appear in logs.
- Broker key rotation works without disabling broker authentication.
- NFP v2 cannot silently downgrade to unauthenticated NFP v1.
- Payload encryption test vectors cover tampering, wrong recipient, replay,
  worker rotation, multi-recipient jobs, streaming, and cancellation.

## Consequences

Positive:

- Human credentials and MFA remain with a specialized identity provider.
- Okta and LDAP-backed identities converge on one OIDC contract.
- The broker gains a trustworthy actor identity and enforceable RBAC.
- Key enrollment can be automatic or manually approved.
- Broker CURVE keys can rotate without copying a new key to every client by
  hand.
- Workers receive a durable principal and authorization decision for accounting.
- The architecture supports standalone and enterprise policy backends.
- True payload privacy from the broker remains possible without discarding
  ZeroMQ.

Negative:

- An HTTPS control-plane endpoint and CA trust must be operated.
- AAA introduces databases, migrations, session expiry, revocation, and policy
  lifecycle concerns.
- Existing clients and workers need an NFP v2 migration.
- Secure token validation requires careful caching, rotation, timeout, and
  algorithm configuration.
- Payload encryption substantially complicates worker selection, streaming,
  retries, interactive input, and audit visibility.
- Highly available brokers require shared or replicated security state.

## Open questions

- Will the HTTPS control API run inside the broker process or as a separate
  `norfab-authd` component?
- Which CA model is expected for standalone installations?
- Which OIDC providers must be in the first interoperability test matrix?
- Is Okta Device Authorization available under the expected tenant policies?
- Will LDAP deployments use Keycloak, an existing enterprise IdP, or an optional
  direct compatibility provider?
- What are the initial roles, protected tasks, and environment boundaries?
- How quickly must role changes and revocations take effect?
- Is the broker trusted to read job payloads, or is broker-blind encryption a
  mandatory launch requirement?
- What audit retention, privacy, and external export requirements apply?
- Does broker HA require a shared session database from the first release?
- Can the pinned PyZMQ/libzmq combination expose ZAP `User-Id` metadata on
  ROUTER messages as required?
- How are worker encryption keys certified if the payload encryption threat
  model includes a malicious broker?

## References

- [CurveZMQ specification](https://rfc.zeromq.org/spec/26/)
- [ZeroMQ Authentication Protocol](https://rfc.zeromq.org/spec/27/)
- [PyZMQ authentication API](https://pyzmq.readthedocs.io/en/latest/api/zmq.auth.html)
- [ZMTP GSSAPI draft](https://rfc.zeromq.org/spec/38/)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth 2.0 Device Authorization Grant, RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628)
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://datatracker.ietf.org/doc/html/rfc9700)
- [Authentication Method Reference Values, RFC 8176](https://datatracker.ietf.org/doc/html/rfc8176)
- [Okta Device Authorization Grant](https://developer.okta.com/docs/guides/device-authorization-grant/main/)
- [Keycloak Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/)
- [Authlib OAuth 2 client documentation](https://docs.authlib.org/en/latest/client/oauth2.html)
- [joserfc JWT documentation](https://jose.authlib.org/en/guide/jwt/)
- [Open Policy Agent documentation](https://www.openpolicyagent.org/docs)
- [Apache Casbin RBAC documentation](https://casbin.apache.org/docs/rbac/)
- [Hybrid Public Key Encryption, RFC 9180](https://datatracker.ietf.org/doc/html/rfc9180)
- [PyNaCl public-key encryption](https://pynacl.readthedocs.io/en/latest/public/)
