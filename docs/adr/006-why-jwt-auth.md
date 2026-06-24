# ADR-006: Use JWT-Based Authentication Instead of Server-Side Sessions

**Status:** Accepted
**Date:** 2025-06
**Related:** PRD.md §5.1; system-design.md §4.2, §10.1

## Context

ragbase needs to authenticate users across every API call, including the streaming SSE chat endpoint. The auth mechanism needs to work cleanly with a stateless FastAPI backend (no sticky sessions required) and support the access/refresh token pattern so that short-lived credentials limit the blast radius of a leaked token, while a longer-lived refresh token avoids forcing the user to re-login every 15 minutes.

## Decision

Use **JWT (JSON Web Tokens)** for authentication: a short-lived access token (15 minutes) sent as a Bearer header, paired with a longer-lived refresh token (7 days) stored as an httpOnly cookie and tracked server-side in the `refresh_tokens` table.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **Server-side sessions (session ID + server-side store)** | Requires a session store (would mean using Redis or PostgreSQL for session state) and ties the API server to stateful session lookups on every request. Works fine for a single-server deployment but adds a lookup hop on every authenticated request that JWTs avoid via self-contained signature verification. |
| **Long-lived single JWT, no refresh token** | Simpler to implement, but a single long-lived token that leaks (e.g., via XSS or logs) remains valid for its full lifetime with no way to limit ongoing exposure short of token revocation infrastructure, which defeats the simplicity benefit anyway. |
| **Access + refresh token JWT pattern** (chosen) | Access tokens are short-lived (15 min), limiting the exposure window if one is compromised. Refresh tokens are longer-lived but revocable — the `refresh_tokens` table allows immediate invalidation on logout, which a stateless-only JWT design cannot do. |

## Consequences

**Positive:**
- Access token verification is fast and stateless — signature check only, no database round-trip needed for every request.
- Short access-token lifetime limits how long a leaked token remains usable.
- Refresh tokens are revocable via the database table, giving a real logout mechanism — closing the usual "JWTs can't be revoked" gap.
- httpOnly cookie storage for the refresh token prevents it from being read by JavaScript, reducing XSS exposure for the longer-lived credential.

**Negative / Tradeoffs:**
- More moving parts than a single session token: access token issuance, refresh token rotation, and revocation tracking all need to be implemented and tested correctly.
- The refresh token table introduces a database dependency back into the auth flow (only for refresh, not for every request) — a partial return to statefulness, accepted as the cost of supporting real revocation.
- Clients (the React frontend) must implement silent token refresh logic — added frontend complexity compared to a cookie-only session model.
