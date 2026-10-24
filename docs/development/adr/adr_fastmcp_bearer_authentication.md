# ADR - FastMCP Bearer Authentication

## Overview

FastMCP exposes NorFab service tasks over the MCP streamable HTTP transport.
By default this endpoint remains unauthenticated for backwards compatibility.
When the FastMCP worker inventory sets `authentication_enabled: true`, the MCP
endpoint requires an `Authorization: Bearer <token>` header.

The MCP Python SDK supports this by passing a `TokenVerifier` implementation and
`AuthSettings` to `FastMCP(...)`. The verifier validates the bearer token and
returns an `AccessToken` object when the token is accepted.

Reference:
https://py.sdk.modelcontextprotocol.io/authorization/

---

## Decision

FastMCP authentication uses the same local diskcache-backed token store pattern
as the FastAPI worker:

- Tokens are stored as `bearer_token::<token>` keys.
- Token data includes `token`, `username`, and `created`.
- Optional expiry is handled by diskcache.
- Token management tasks are available through the NorFab client and hidden
  from MCP with `mcp=False`.

The FastMCP worker adds a `DiskcacheBearerTokenVerifier` that checks the worker
cache and returns an MCP `AccessToken` for valid tokens. Invalid, missing, or
expired tokens are rejected by the MCP SDK bearer auth middleware.

---

## Inventory

Authentication is optional and controlled by a top-level FastMCP inventory flag:

```yaml
service: fastmcp
host: "127.0.0.1"
port: 8001

authentication_enabled: true
auth_bearer:
  token_ttl: 86400
  issuer_url: "http://127.0.0.1:8001"
  resource_server_url: "http://127.0.0.1:8001"
  required_scopes: []
```

`issuer_url` and `resource_server_url` default to the worker URL. If the bind
host is `0.0.0.0`, the default public URL uses `127.0.0.1`.

`required_scopes` is optional. When it is configured, locally stored tokens are
assigned the same scopes unless `auth_bearer.token_scopes` is set explicitly.

---

## Token Lifecycle

Store a token before enabling or using authentication:

```python
nfclient.run_job(
    "fastmcp",
    "bearer_token_store",
    kwargs={"username": "automation", "token": "secret-token", "expire": 86400},
)
```

Connect MCP clients with the bearer header:

```http
Authorization: Bearer secret-token
```

Delete or inspect tokens with:

- `bearer_token_store`
- `bearer_token_delete`
- `bearer_token_list`
- `bearer_token_check`

These tasks are intentionally not exposed as MCP tools to avoid managing MCP
credentials through the protected MCP protocol itself.

---

## Consequences

- Existing FastMCP deployments continue to work because authentication defaults
  to disabled.
- Token storage stays local to the FastMCP worker instance, matching the current
  FastAPI worker approach.
- A future shared bearer-token helper can reduce duplication between FastAPI and
  FastMCP workers, but this change keeps the implementation local and low-risk.
