# ADR - Simplify NorFab ZeroMQ CURVE Trust and Peer Admission

## Status

Proposed.

Date: 2026-08-09.

This ADR is a design proposal only. It does not change code.

This ADR replaces the previous contents of this file. It deliberately keeps
ZeroMQ and does not propose NATS, HTTP, TLS wrapping, a central AAA service, or
custom payload encryption. The separate
[`adr_norfab_aaa_security_architecture.md`](adr_norfab_aaa_security_architecture.md)
is not modified or required by this decision.

## Decision summary

NorFab will continue to use its existing ZeroMQ ROUTER/DEALER transport and
native CURVE security.

The design has two small trust mechanisms:

1. **Clients and workers trust the broker public key from the same inventory
   entry that supplies the broker endpoint.** The key is public and should no
   longer be called a `shared_key`. No second signing key, bootstrap server, or
   certificate file distribution mechanism is introduced.
2. **The broker admits clients and workers through PyZMQ's native ZAP
   authenticator.** In managed mode, `configure_curve_callback()` checks each
   peer's CURVE public key against a small broker-local registry. Optional
   `Authenticator.allow()` or `deny()` rules apply source-IP policy before the
   CURVE key check.

Unknown peer keys are recorded as pending and denied. A locally provisioned
administrator, or an already admitted client with the `approve_peers` flag,
can approve the key through a small broker management command. The peer then
retries and is accepted. A worker never sends its private key anywhere.

The authenticated CURVE key, exposed by ZeroMQ as the ZAP `User-Id`, is the
connection identity. A self-selected ZeroMQ routing identity or claimed worker
name is not an authenticated identity.

## Why this is the simplest secure boundary

There are two directions of trust and they are not symmetrical:

- A client or worker must know the broker's permanent public key before the
  CURVE handshake starts.
- The broker receives the connecting peer's permanent public key during the
  CURVE/ZAP handshake and can decide whether to accept it.

CurveZMQ explicitly requires clients to know the server public key before
connecting. ZeroMQ does not define secure server-key discovery, a wildcard
"trust any server key" client option, or trust-on-first-use storage. A broker
cannot send its key over a CURVE connection that has not yet been established,
because that key is needed to establish the connection.

Consequently, a signed bootstrap response does not remove initial key
distribution: every client would still need the signing public key. That is
the same deployment work as distributing the broker CURVE public key, with an
extra protocol and extra code. The authoritative inventory already distributes
the endpoint, so coupling the public key to that endpoint is the smallest
honest solution.

## Current NorFab behavior

The reviewed code already contains most of the required primitives:

- `broker.py` creates a CURVE server and starts `ThreadAuthenticator`, but sets
  `allow_any = True` and configures `CURVE_ALLOW_ANY`. The broker therefore
  encrypts connections but does not recognize or restrict client/worker keys.
- `client.py` and `worker.py` generate and keep their own CURVE key pairs, then
  set `curve_serverkey` from a local copy of `broker.key` before connecting.
- `security.py` copies the broker public key from a colocated broker directory
  or converts `inventory.broker.shared_key` back into a certificate file.
- `NorFabClientAuthProvider.callback()` exists in `security.py`, but currently
  returns `True` for every key and is not connected to
  `configure_curve_callback()`.
- The broker receives multipart messages as copied `bytes`. It therefore does
  not currently read the accepted connection's CURVE `User-Id` metadata.
- The ROUTER socket has `ROUTER_HANDOVER` enabled while clients and workers
  choose their own routing identities. Without binding that routing identity
  to the authenticated CURVE key, another admitted peer could claim the same
  name and take over the route.

The current design also uses the term `shared_key` for the broker public key.
It is not a shared secret. Only `broker.key_secret` is secret.

## Relevant native ZeroMQ and PyZMQ behavior

### CURVE server trust

A CURVE client must set `ZMQ_CURVE_SERVERKEY` before connecting. The server
public key is used to authenticate the broker and protect the handshake. There
is no secure native first-contact mode that accepts an unknown server key and
then reports it to the application.

`CURVE_ALLOW_ANY` is a **server-side client-admission** option. It means the
server accepts any peer CURVE key. It does not make a client trust an arbitrary
broker key.

### ZAP admission callback

PyZMQ provides two useful CURVE admission choices:

- `configure_curve(location=CURVE_ALLOW_ANY)` accepts every peer key.
- `configure_curve_callback(domain, provider)` calls
  `provider.callback(domain, key)` with the peer's Z85-encoded public key and
  accepts the connection only when the callback returns true.

The callback is enough for dynamic admission. It can look up a key in a local
database and can record an unknown key as pending before returning false. Unlike
the certificate-directory form of `configure_curve()`, callback-backed changes
do not require certificates to be copied into a directory and the authenticator
to be reconfigured after every change.

On successful CURVE authentication, PyZMQ's default `curve_user_id()` returns
the peer public key in Z85 form. PyZMQ makes that ZAP `User-Id` available on
received `Frame` objects when using `recv_multipart(copy=False)`.

### IP filtering

`Authenticator.allow(*addresses)` is an allowlist: a connection from any other
source address is rejected. For CURVE, an allowed address must still pass the
CURVE key callback. `deny()` is the inverse and cannot be combined with
`allow()`.

In the pinned PyZMQ 27.1.0 implementation these are exact string comparisons of
the source IP supplied by ZAP; they are not CIDR matching. In particular,
`allow("0.0.0.0")` is not an "allow all" wildcard.

For subnets and CIDR rules, use the operating-system or container firewall. Do
not build a second Python network-policy engine. Although libzmq has
`ZMQ_TCP_ACCEPT_FILTER` with CIDR syntax, that option is deprecated in favor of
ZAP IP allow/block policy. IP policy is defense in depth, not a replacement for
CURVE key admission, and NAT or proxies may hide the original source address.

## Decision details

### 1. Keep the existing transport

Retain:

- PyZMQ and libzmq;
- the current ROUTER/DEALER socket pattern;
- the NFP message format and broker mediation role;
- native CURVE encryption and authentication;
- locally generated, persistent key pairs for the broker, clients, and workers.

Do not add TLS around ZeroMQ or encrypt message payloads a second time. Native
CURVE already provides confidentiality, integrity, broker authentication, and
per-connection session keys.

### 2. Replace `shared_key` with an explicit broker descriptor

The resolved inventory should keep the endpoint and its CURVE public key
together:

```yaml
broker:
  endpoint: "tcp://10.20.0.10:5555"
  curve_public_key: "<40-character-Z85-public-key>"
  zmq_auth: true
```

The public key may be present in source-controlled inventory where that is
appropriate; it is trust-sensitive configuration but it is not secret. The
broker private key must never be placed in inventory.

For a colocated broker started by the same `NorFab` process, the resolved
in-memory inventory may be populated directly from the broker public-key file.
Remote clients and workers use the inventory value directly. There is no need
to manufacture and copy a `broker.key` certificate file merely because the
PyZMQ socket option accepts the key bytes directly.

Operational discovery is intentionally small:

- A broker command prints its public key, a SHA-256 fingerprint, and a ready-to-
  paste inventory fragment.
- Configuration validation couples each endpoint to exactly one public key and
  fails closed if the key is absent or malformed while `zmq_auth` is enabled.
- If multiple brokers are supported later, inventory contains a list of
  `{endpoint, curve_public_key}` descriptors. A key is never accepted for a
  different endpoint merely because it appears elsewhere in the inventory.

This is configuration-based discovery, not an unauthenticated network key
discovery protocol.

### 3. Keep peer private keys local

Each client and worker generates its own CURVE key pair on first start and
reuses it across restarts:

- the secret key stays on that node with restrictive file permissions;
- only the public key is presented by CURVE and stored by the broker;
- deleting or rotating the local key creates a new identity that must be
  admitted again;
- cloning a data directory also clones the identity and must be treated as a
  credential-copy operation.

No inventory entry needs to contain every worker or client private key. No
shared client secret is introduced.

### 4. Provide two explicit broker admission modes

#### Managed mode - recommended default

The broker configures one ZAP domain, for example `norfab`, and wires
`NorFabClientAuthProvider` to:

```python
auth.configure_curve_callback(
    domain="norfab",
    credentials_provider=provider,
)
```

The provider checks a broker-local admission registry. Only records with
`status = allowed` are accepted. Revoked, pending, and unknown keys are denied.

The registry should be a small SQLite database in the broker data directory,
using Python's built-in `sqlite3`. This is not a service or a new infrastructure
dependency. It provides atomic updates and works on Windows, Linux, and macOS.
The authenticator thread must use its own SQLite connection or a deliberately
thread-safe registry wrapper.

A minimal record is:

```text
curve_public_key   primary key, Z85 text
status             pending | allowed | revoked
kind               client | worker | unassigned
name               optional expected NorFab name
approve_peers      boolean, normally client-only
created_at
approved_at
approved_by_key
last_seen_at
```

The callback receives only `domain` and `key`. It must not pretend it also knows
the peer's claimed NorFab name, service, or source IP. PyZMQ applies configured
IP rules separately; the broker validates names and roles after the CURVE
handshake.

#### Network mode - explicit low-assurance option

For a small trusted lab, the broker may use `CURVE_ALLOW_ANY` together with an
exact source-IP allowlist. Any node that can reach the broker from an allowed
address and possesses any valid CURVE key can connect.

This mode provides encrypted transport and authenticates the broker to peers,
but it does **not** establish a known client or worker identity. It must be named
and documented as network-trust mode, not client-authenticated mode. Managed
mode should be used when peers can submit tasks or when names/roles matter.

### 5. Optional source-IP policy remains independent

Inventory can define either exact allowed IPs or exact denied IPs:

```yaml
broker:
  endpoint: "tcp://10.20.0.10:5555"
  curve_public_key: "<broker-public-key>"
  admission:
    mode: managed
    allow_ips:
      - "10.20.0.21"
      - "10.20.0.22"
```

Semantics:

- non-empty `allow_ips` calls `auth.allow(*allow_ips)`;
- non-empty `deny_ips` calls `auth.deny(*deny_ips)`;
- configuring both is an error;
- configuring neither means no ZAP IP restriction;
- CIDR is rejected by inventory validation and delegated to the host firewall;
- CURVE key admission is still required in managed mode after an IP is allowed.

This makes IP filtering visible and testable without confusing it with
cryptographic identity.

### 6. On-demand enrollment uses deny, approve, retry

The enrollment flow uses the existing broker and the native ZAP callback:

1. A new client or worker generates its key pair locally.
2. It obtains the broker endpoint and public key from inventory.
3. It attempts a normal CURVE connection.
4. The callback does not find the peer key, inserts or refreshes one bounded
   `pending` record, and returns false. ZAP rejects the connection.
5. An operator sees the pending key and fingerprint using a local broker CLI,
   or an already admitted client lists it through a broker management command.
6. A locally bootstrapped administrator or an admitted client whose registry
   record has `approve_peers = true` approves the key and assigns its kind and,
   optionally, expected name.
7. The new peer's normal reconnect loop retries. The callback now returns true,
   and CURVE establishes the connection.

The very first approving client is provisioned locally on the broker. This is
the minimal trust root; subsequent enrollment can be remote and on demand.

Pending entries must be deduplicated by public key, capped, expired, and rate-
limited enough that unauthenticated connection attempts cannot grow the local
database without bound. Approval and revocation events are audited with public-
key fingerprints, never secret keys.

The management operations should be deliberately small:

```text
peer.list_pending
peer.approve(key, kind, expected_name=None)
peer.revoke(key)
peer.list_allowed
```

This is broker-local admission control, not general-purpose AAA. Workers cannot
approve peers by default. Approval authority is bound to the approver's CURVE
key, not its self-declared routing name.

### 7. Bind NorFab identities to the accepted CURVE key

After successful ZAP authentication, the broker must receive message frames
with `copy=False` and read the connection's `User-Id`. With PyZMQ's default
mapping, this is the peer's Z85 CURVE public key.

For every registration and management message, the broker should:

1. obtain the authenticated CURVE key from `User-Id`;
2. find the allowed registry record for that key;
3. check the record's `kind` against the NFP role (`CLIENT` or `WORKER`);
4. if `name` is pinned, check the claimed NorFab name against it;
5. authorize admission-management commands only when `approve_peers` is true.

The ZeroMQ routing identity remains an address used to route replies. It is not
proof of identity. With `ROUTER_HANDOVER`, a routing name may be taken over only
by a connection authenticated with the same allowed CURVE key. A different key
claiming an active name must be rejected, even if both keys are otherwise
allowed.

This binding is essential. Without it, the callback controls which keys may
connect but application code could still trust a spoofed client or worker name.

### 8. Revocation and runtime changes

The callback naturally applies changes to the next connection attempt. To make
revocation effective for an already connected peer, the broker also maintains
an in-memory view of allowed keys and refuses application messages from a key
after it is revoked. It may discard the peer's route and wait for the underlying
connection to close.

Registry writes update that in-memory view immediately. A broker restart
rebuilds it from SQLite. No certificate directory reload and no central service
are required.

### 9. Broker-key rotation

The first trusted broker key still comes from inventory. Rotation has two
simple paths:

- **Baseline:** update the broker public key in inventory as part of a planned
  broker key rotation and restart/reconnect rollout.
- **Optional same-channel rollover:** while connected through the currently
  trusted CURVE channel, clients and workers may request the broker's `next`
  public key through a management message and cache it. Because the response is
  protected by the already authenticated current key, no separate signature
  key is needed. On activation, the peer creates a new socket using the cached
  next key. New or offline peers still receive the current key from inventory.

The optional rollover is useful for future automation but is not required for
the first implementation. ZeroMQ sockets use one server key for a connection;
the client cannot change `curve_serverkey` on an established connection.

## Security properties

The proposed managed mode provides:

- encryption and integrity from native CurveZMQ;
- broker authentication from the inventory-pinned broker public key;
- proof that an admitted peer possesses the private key corresponding to an
  allowed public key;
- optional exact source-IP filtering before key admission;
- application identity bound to the authenticated key rather than routing
  identity;
- local, immediate approval and revocation without a new network service;
- private keys that never need to be distributed.

It does not provide human login, OIDC, MFA, organization-wide RBAC, or a central
audit system. Those are intentionally outside this ADR. A human using an
approved client inherits that client's local key authority; protecting that
client host remains important.

## Failure behavior

- Missing or malformed broker public key with `zmq_auth: true`: fail startup or
  connection setup; do not silently fall back to NULL security.
- Broker key mismatch: CURVE handshake fails; display endpoint and expected key
  fingerprint without exposing private material.
- Unknown, pending, or revoked peer key in managed mode: ZAP rejects it.
- Allowed key from a source excluded by IP policy: ZAP rejects it before the
  callback result can grant access.
- Registry unavailable or callback error: fail closed and reject the peer.
- Duplicate claimed name from a different authenticated key: reject the new
  registration and keep the existing route.
- `zmq_auth: false`: clearly report that transport encryption and CURVE peer
  admission are both disabled. This should remain an explicit development-only
  choice.

## Considered alternatives

### Signed broker-key bootstrap over ZeroMQ

Rejected. A NULL and a CURVE security mechanism cannot be upgraded inside the
same ZMTP connection, and CURVE cannot start without the server key. A separate
bootstrap socket or connection would be unauthenticated unless every peer were
preloaded with a signature-verification key. Distributing that verifier is the
same workload as distributing the broker public key.

### Trust on first use

Rejected as the default. It can cache the first key observed, but the first
connection is vulnerable to interception and ZeroMQ/PyZMQ does not implement
TOFU storage as a built-in feature. It may be considered later as an explicitly
unsafe local-development convenience.

### `CURVE_ALLOW_ANY` everywhere

Retained only as the explicit network mode. It encrypts traffic and lets peers
authenticate the broker, but it does not tell the broker which client or worker
is connecting.

### Public client-certificate directory

Supported by PyZMQ but not selected. `configure_curve(location=directory)` is
simple for a static allowlist, yet public certificates must be created/copied
and `configure_curve()` called again after additions or removals. The callback
and local SQLite registry better fit on-demand approval with less file handling.

### Custom ZAP implementation

Rejected initially. PyZMQ's native `ThreadAuthenticator`, exact IP rules, and
CURVE callback are sufficient. Subclassing or replacing ZAP would add protocol
and threading risk without solving the broker's initial key trust problem.

### TLS wrapping or application payload encryption

Rejected. It duplicates native CURVE confidentiality and introduces framing,
certificate, or key-management complexity while retaining the same ZeroMQ
application protocol.

### NATS, HTTP, or another transport

Rejected by scope. The broker and existing ZeroMQ message transport remain.

### Central AAA, OIDC, and MFA

Rejected by scope for this refactoring. They solve broader human and
organization policy problems, not the immediate native CURVE bootstrap and
peer-admission problem. This ADR must remain independently implementable.

## Suggested implementation sequence

No code is changed by this ADR. If accepted, implement in small stages:

1. Rename the resolved inventory field from `shared_key` to
   `curve_public_key`, accept the old name temporarily with a deprecation
   warning, and set `curve_serverkey` directly from the inventory value.
2. Add broker key/fingerprint display and strict inventory validation. Preserve
   the current colocated auto-configuration behavior without copying a public
   certificate file where possible.
3. Implement the broker-local registry and make
   `NorFabClientAuthProvider.callback()` return true only for allowed keys.
4. Wire the provider to `configure_curve_callback()` and add optional exact
   `allow_ips` or `deny_ips` configuration.
5. Receive broker frames with `copy=False`, bind ZAP `User-Id` to the registry
   record, and protect routing identity handover.
6. Add local list/approve/revoke commands, then allow already admitted clients
   with `approve_peers` to invoke the same broker operations.
7. Add runtime revocation, audit events, limits on pending records, and the
   optional current-to-next broker-key rollover only if operationally useful.

## Acceptance criteria

The refactoring is complete when tests demonstrate that:

1. Existing NFP client, worker, and broker message flows still use ZeroMQ.
2. CURVE traffic remains encrypted and a wrong broker public key cannot connect.
3. No broker or peer private key is placed in inventory or transferred to
   another node.
4. In managed mode an unknown key is recorded as pending and denied.
5. Approving that key allows its next connection without restarting the broker
   or reloading a certificate directory.
6. Revoking a key blocks both new connections and application messages from an
   existing connection.
7. Exact IP allow/deny policy and CURVE key policy are both enforced.
8. `allow("0.0.0.0")` is never treated as a wildcard.
9. A peer cannot gain client/worker privileges or take over a routing name by
   changing only its self-declared ZeroMQ identity.
10. Only an allowed client key with `approve_peers` can remotely approve or
    revoke peers; a worker or unprivileged client cannot.
11. Broker key/fingerprint mismatch errors are actionable and fail closed.
12. Windows, Linux, and macOS use the same PyZMQ plus standard-library SQLite
    design.

## References

- [PyZMQ authentication API](https://pyzmq.readthedocs.io/en/latest/api/zmq.auth.html)
- [PyZMQ Frame and `User-Id` metadata](https://pyzmq.readthedocs.io/en/latest/api/zmq.html#zmq.Frame)
- [ZeroMQ Message Transport Protocol, RFC 23](https://rfc.zeromq.org/spec/23/)
- [CurveZMQ protocol, RFC 26](https://rfc.zeromq.org/spec/26/)
- [ZeroMQ Authentication Protocol, RFC 27](https://rfc.zeromq.org/spec/27/)
- [libzmq socket security and IP-filter options](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html)
- [Pinned PyZMQ 27.1.0 authenticator implementation](https://github.com/zeromq/pyzmq/blob/v27.1.0/zmq/auth/base.py)
