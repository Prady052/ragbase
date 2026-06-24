# ADR-005: Use PostgreSQL for Relational Data

**Status:** Accepted
**Date:** 2025-06
**Related:** system-design.md §4

## Context

ragbase needs a relational store for structured, relationship-heavy data: users, refresh tokens, document metadata, conversations, and messages. These entities have clear foreign-key relationships (a document belongs to a user; a message belongs to a conversation) and benefit from transactional guarantees — for example, a document's status update and chunk-count update should commit atomically. The store also needs to support a flexible field (`sources` on a message, storing an array of citation objects) without requiring a separate table for a relatively simple structure.

## Decision

Use **PostgreSQL** as the relational database, accessed via SQLAlchemy's async ORM with the `asyncpg` driver.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **MongoDB** | Schema flexibility is appealing, but ragbase's data is inherently relational (users → documents → conversations → messages, all with clear foreign keys). Modeling these relationships in a document store means either denormalizing data (duplication, harder consistency) or manually managing references without the referential integrity a relational database provides for free. |
| **SQLite** | Sufficient for a single-user local tool and zero setup, but lacks robust concurrent write support — a concern once the Celery worker and FastAPI process write to the same database simultaneously during ingestion. Also lacks native support for some types used in the schema (e.g., `JSONB` with indexing, `ENUM` types). |
| **PostgreSQL** (chosen) | Strong relational integrity via foreign keys, native `JSONB` support for the semi-structured `sources` field on messages, native `ENUM` types for fields like document status and user role, and solid concurrent write handling for the API + worker writing simultaneously. |

## Consequences

**Positive:**
- Foreign key constraints enforce referential integrity automatically (e.g., a message cannot reference a non-existent conversation).
- `JSONB` on the `sources` column gives schema flexibility for citation data without needing a separate `citations` table for what is fundamentally a small, denormalizable array.
- Native `ENUM` types (`document.status`, `user.role`) catch invalid values at the database layer, not just in application code.
- Mature tooling — Alembic for migrations, broad driver support (`asyncpg`) for async FastAPI integration.

**Negative / Tradeoffs:**
- Requires a schema migration discipline (every change goes through Alembic) — slightly slower iteration speed early on compared to a schemaless store.
- One more stateful service to run locally compared to SQLite's zero-process embedded model.
- `JSONB` fields (like `sources`) sacrifice some queryability compared to a fully normalized schema — acceptable here since citation data is always read as a whole, never queried by individual citation fields.
