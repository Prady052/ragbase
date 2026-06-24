# ADR-002: Use Qdrant as the Vector Store

**Status:** Accepted
**Date:** 2025-06
**Related:** PRD.md, system-design.md §5

## Context

ragbase needs to store document chunk embeddings and perform fast similarity search at query time, filtered by `user_id` to enforce data isolation between users. The store must run fully locally (no managed cloud dependency, per the privacy-first requirement) and needs to support metadata filtering alongside vector search, since each chunk carries `document_id`, `page_number`, and `source_filename` payload.

## Decision

Use **Qdrant** as the dedicated vector database, run as a local Docker container.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **Pinecone** | Managed cloud-only service. Violates the core privacy-first requirement — document embeddings (which can reconstruct sensitive text) would leave local infrastructure. Also introduces a recurring cost, which conflicts with the project's zero-cost local constraint. |
| **Weaviate** | Capable and open-source, but heavier to self-host (more moving parts, GraphQL-first API) for a project of this scale. Qdrant's REST/gRPC API and Python client are simpler to integrate directly into FastAPI services. |
| **pgvector (PostgreSQL extension)** | Attractive since PostgreSQL is already in the stack — would reduce one container. However, pgvector's HNSW indexing and filtering performance lag behind purpose-built vector engines at scale, and mixing transactional relational queries with high-volume vector search on the same database risks resource contention. Kept as a noted alternative if the stack ever needs to shrink. |
| **Qdrant** (chosen) | Open-source, self-hostable via a single Docker container, native payload-based filtering (used for the `user_id` isolation filter), HNSW indexing out of the box, and a clean Python SDK (`qdrant-client`). |

## Consequences

**Positive:**
- Runs entirely locally in Docker — no data ever leaves the machine, satisfying the privacy-first requirement.
- Payload filtering (`user_id`, `document_id`) is native to the query API — no need for a second filtering pass in application code.
- HNSW indexing gives good recall/speed tradeoff without manual tuning for the dataset sizes this project targets.
- Free and open-source — no per-query or per-vector cost, consistent with the zero-budget local deployment goal.

**Negative / Tradeoffs:**
- One more service to run and operate (health checks, container memory limits) compared to using an extension on an existing database.
- Qdrant's clustering/replication features (relevant at large scale) are unused here — acceptable since ragbase targets single-machine local deployment, not distributed scale.
- If the project ever needed to consolidate infrastructure, migrating from Qdrant to pgvector would require re-embedding or exporting/reimporting all vectors.
