# ADR 0001: Authentication Strategy for Public API

## Status

Proposed

## Context

The current project scope explicitly states that no authentication is required. That is acceptable for local demos and early development, but a public deployment still needs a clear path to protect write operations, prevent abuse, and support future multi-client integrations.

The API currently exposes:

- Read endpoints (`GET` list/detail/search)
- Mutation endpoints (`POST`, `PATCH`, `DELETE`) for categories and products

Without authentication, anyone with network access can mutate catalog data.

## Decision

Adopt a staged authentication model:

1. Keep read-only endpoints public for demo usability.
2. Protect all mutation endpoints with API keys in the near term.
3. Design the auth layer so it can evolve to OAuth2/JWT without endpoint contract churn.

Near-term mechanism:

- Header: `Authorization: Bearer <api_key>`
- Validation against configured hashed keys (environment-based secret source)
- Role mapping by key scope:
  - `reader`: read-only access
  - `editor`: create/update
  - `admin`: create/update/delete and future privileged operations

## Consequences

### Positive

- Minimal implementation complexity and operational overhead
- Stronger protection for write paths in public environments
- Backward-compatible transition path: can start in optional mode and enforce per environment
- Clear migration path to identity-provider-backed OAuth2 for third-party clients

### Negative / Trade-offs

- API keys are less user-centric than OAuth2 (no user identity, coarse revocation model)
- Key rotation and distribution require operational discipline
- Per-key scopes are simpler than claim-based authorization

## Alternatives Considered

### 1) Keep no-auth in all environments

Rejected for public deployment because it leaves mutation endpoints unprotected.

### 2) OAuth2/JWT immediately

Deferred. It provides stronger identity semantics but adds setup complexity (IdP, token flow, client registration) that is not necessary for the current service maturity.

### 3) Basic Auth

Rejected. It is weaker operationally than scoped API keys and not a good long-term base for service-to-service integrations.

## Rollout Plan

1. Add an auth dependency/middleware at the API router level.
2. Start with feature flag:
   - `AUTH_ENABLED=false` for local demos
   - `AUTH_ENABLED=true` for deployed/public environments
3. Apply enforcement only to mutation routes first.
4. Add 401/403 response documentation in OpenAPI.
5. Add tests for:
   - missing token (401)
   - invalid token (401)
   - insufficient scope (403)
   - valid scoped access (200/201/204)

## Revisit Triggers

Re-evaluate this decision when any of the following occur:

- External consumers need user-level identity and delegated access
- Fine-grained tenant or user authorization is required
- Compliance requires centralized identity and auditable login flows
