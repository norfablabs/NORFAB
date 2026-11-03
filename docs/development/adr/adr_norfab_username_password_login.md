# ADR - NorFab Username and Password Application Login

## Status

Proposed. This records the application login proposal from the 3 November 2026
core review. It does not describe implemented functionality or authorize a
protocol migration.

This is a local-account alternative to the proposed
[AAA and encrypted transport architecture](adr_norfab_aaa_security_architecture.md),
which uses an external OIDC identity provider and a separate AAA service.
That proposal explicitly keeps passwords and durable identity state outside
the broker. This proposal instead places local account/session ownership at
the broker. Neither proposal supersedes the other; select the deployment
model before implementing authentication.

The proposed [CURVE peer admission design](adr_norfab_transport_authentication_simplification.md)
addresses machine trust and can complement application login. Admitting a
peer key does not authenticate the human using that peer.

## Date

2026-11-03.

## Context

NorFab encrypts NFP traffic with CURVE when enabled, but the broker currently
accepts any peer key. Client-selected routing identities and worker headers
do not establish an authenticated user or machine role. Existing FastAPI
bearer checks protect the HTTP boundary but do not authenticate direct NFP
requests or establish job ownership across entry points.

Application login needs an authenticated principal carried through dispatch,
worker execution, child jobs, result retrieval, and audit events. Related
defects remain tracked in [the bug hunt](../bug_hunt.md), findings 55 and 79.

Terms used here:

- **Principal:** An immutable identity for a user or service account. A username
  is a readable account attribute; a routing address is a delivery identifier.
- **Session:** A revocable, expiring grant issued after successful login.
- **Machine credential:** A credential authorizing a worker or gateway to act
  in its assigned role, separate from a human user's password.

## Proposed decision

Keep CURVE encryption and broker-key verification. Add application-level
login, logout, and session validation over encrypted transport. Require
encryption for password login; define an explicit development policy for
deployments using `zmq_auth=False` before implementation.

### Accounts and sessions

Store users and password hashes in a restricted broker-side authentication
store, outside exported inventory and task arguments. Prefer Argon2id with
parameters calibrated for deployment hardware. Never persist passwords in
client job history or include credentials in events, inventory responses, or
raw-frame logs. Redact authentication envelopes before enabling login.

Issue opaque, high-entropy, short-lived session tokens. Store token hashes
with principal, expiry, revocation state, and client binding. Validate the
session on every request. Specify reconnect, logout, password-change,
disabled-account, and broker-restart behavior. Session renewal must not
silently resubmit non-idempotent work.

Use generic authentication failures and rate limiting. Perform password
verification in a bounded executor outside the broker routing loop so login
load cannot block heartbeats and dispatch. Reject oversized or malformed
requests before hashing. Record security events without credentials.

### Protocol and authorization

Add a versioned authenticated envelope in `norfab/core/NFP.py`. Keep identity
metadata separate from task kwargs, preserving public task arguments and
existing `run_job` call patterns. Add credentials/session configuration at
client construction or through an explicit login interface.

The broker validates sessions and supplies trusted principal metadata to
workers. Persist job ownership in the job model and client/worker databases.
Enforce service, task, worker, and ownership permissions before routing,
including GET, PUT, STREAM, MMI, and inventory requests. Workers must enforce
ownership using broker-authenticated metadata. When authentication is enabled,
reject legacy unauthenticated frames; define the upgrade policy explicitly.

Restrict user administration, shell execution, broad filesystem access,
token administration, unrestricted job listing, logs, and sensitive inventory
to authorized principals. A shared initial user role grants broad power;
job isolation still requires explicit ownership checks.

### Workers and gateways

Provision machine credentials for worker registration and worker-created
NFPClient connections. Bind worker credentials to allowed names/services;
do not exempt clients merely because they claim to be internal. Define how
child jobs inherit the initiating principal and how scheduled/system jobs
receive a service principal.

HTTP and NFWeb gateways must propagate verified user identity through a
trusted mechanism rather than assigning every user the gateway account.
Untrusted clients cannot supply their own authoritative principal or roles.

## Alternatives considered

- **External OIDC and dedicated AAA:** The existing AAA proposal supports
  federation and identity-provider MFA without NorFab collecting passwords.
  Prefer that architecture where centralized identity is required; it adds
  deployment components compared with local accounts.
- **CURVE peer admission alone:** Establishes approved machine connections,
  but does not provide human login or per-user job ownership.
- **ZeroMQ PLAIN username/password:** Selects a different socket security
  mechanism and provides no confidentiality itself. Adding PLAIN options to
  the current CURVE socket is not an encrypted application login design.

## Consequences

Local accounts avoid requiring an external identity provider, but NorFab
must own password verification, account provisioning/recovery, session
revocation, and protection of the authentication store. Password hashing
adds bounded CPU/memory cost. Durable broker-owned identity state requires
an explicit backup and multi-broker consistency strategy.

This is a cross-cutting protocol and ownership change. A CLI password prompt
alone does not protect direct NFP clients, worker registration, or HTTP users.
The existing task interfaces should remain stable while authenticated
envelopes introduce a deliberate compatibility boundary.

## Implementation and validation

First fix boundary crashes and escaping file deletion. Then agree the
principal/session envelope and compatibility policy, implement broker login
and machine-role separation, persist/enforce ownership, and integrate CLI,
HTTP, and NFWeb entry points. Run recovery and load checks before rollout.

Acceptance coverage must include:

- Unknown, incorrect, and disabled accounts; expiry, revocation, logout,
  reconnect, password changes, and broker restart.
- Unauthenticated POST/GET/PUT/STREAM/MMI/inventory; identity takeover;
  client-to-worker role spoofing; cross-user reads and input; privileged tasks.
- Secret redaction; login flooding while heartbeats continue; child jobs and
  gateway identity propagation; interrupted jobs and duplicate UUID handling.
- Legacy clients when authentication is enabled, and explicit behavior when
  encrypted transport is disabled.

Open decisions include local accounts versus external AAA, account bootstrap
and recovery, session lifetime/client binding, initial roles, authentication
store location and multi-broker behavior, and the protocol upgrade policy.

## References

- [ZeroMQ socket security selection](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html)
- [ZeroMQ PLAIN confidentiality limitations](https://libzmq.readthedocs.io/en/latest/zmq_plain.html)
- [PyZMQ CURVE security](https://pyzmq.readthedocs.io/en/latest/howto/curve.html)
- [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
