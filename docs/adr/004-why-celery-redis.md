# ADR-004: Use Celery with Redis for Async Document Ingestion

**Status:** Accepted
**Date:** 2025-06
**Related:** PRD.md §5.2; system-design.md §3.1, §9

## Context

Document ingestion (parsing a PDF/DOCX, chunking, generating embeddings for every chunk, upserting into Qdrant) takes anywhere from several seconds to over a minute for larger files. This work cannot run inline in the HTTP request — doing so would block the FastAPI event loop and force the user to wait with an open connection for the entire pipeline to finish. The upload endpoint needs to return immediately while the actual processing happens in the background, with status tracked so the frontend can poll for completion.

## Decision

Use **Celery** as the task queue, with **Redis** as both the message broker and result backend.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **FastAPI `BackgroundTasks`** | Built into FastAPI with zero extra infrastructure, but tasks run in the same process as the API server and are lost if the server restarts mid-task. No retry mechanism, no task status persistence, no visibility into queue depth. Acceptable for trivial fire-and-forget work, not for a multi-step pipeline that can fail partway through. |
| **RQ (Redis Queue)** | Simpler than Celery and also Redis-backed, but has fewer built-in features for retries with exponential backoff and task chaining — both of which matter for a pipeline with multiple failure-prone steps (parsing, embedding, upserting). |
| **Celery + RabbitMQ** | RabbitMQ is a more feature-complete message broker than Redis for complex routing, but it's a heavier service to self-host for this project's needs. Redis already exists in the stack as a cache, so reusing it as a broker avoids adding a fifth infrastructure container. |
| **Celery + Redis** (chosen) | Mature, battle-tested task queue with built-in retry/backoff, task status tracking, and a broker (Redis) that's already part of the stack for conversation-memory caching — no additional service required. |

## Consequences

**Positive:**
- Upload endpoint returns near-instantly; processing happens fully out-of-band.
- Built-in retry with exponential backoff (configured for up to 3 attempts) handles transient failures — e.g., a momentary Qdrant connection blip during upsert — without manual retry logic.
- Task status is queryable, enabling the frontend's polling-based status indicator (`PENDING → PROCESSING → READY → FAILED`).
- Redis is dual-purposed as both the Celery broker and the conversation-memory cache, keeping total container count lower than introducing a separate broker.

**Negative / Tradeoffs:**
- Celery has a non-trivial learning curve and its own failure modes (e.g., worker not picking up tasks if misconfigured, "zombie" tasks on ungraceful shutdowns) that require care to debug.
- Using Redis as both broker and cache means a Redis outage affects two concerns simultaneously (task dispatch and conversation memory) rather than failing independently.
- Adds an additional long-running process (the worker) that must be kept alive and monitored alongside the API server.
