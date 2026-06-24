# ADR-001: Use FastAPI as the Backend Framework

**Status:** Accepted
**Date:** 2025-06
**Related:** PRD.md, system-design.md §6.1

## Context

ragbase needs a Python backend that can handle standard REST endpoints (auth, document upload, document listing) as well as a streaming endpoint for LLM token output (Server-Sent Events). The framework choice affects developer velocity, runtime performance, and how naturally async I/O-bound work (database calls, Qdrant search, Ollama inference) fits into the codebase.

## Decision

Use **FastAPI** as the backend web framework.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **Django** | Built around sync ORM and a "batteries included" philosophy (admin panel, templating) that ragbase doesn't need. Async support exists but feels bolted on rather than native. Heavier than required for an API-only service. |
| **Flask** | Minimal and flexible, but async support requires extensions (e.g., `asgiref`) and isn't first-class. No built-in request/response validation — would need to hand-roll what Pydantic gives FastAPI for free. |
| **FastAPI** (chosen) | Native `async def` route support, built-in Pydantic validation for request/response schemas, automatic OpenAPI docs, and first-class support for streaming responses (needed for SSE token streaming from the LLM). |

## Consequences

**Positive:**
- Async-native — database calls (via `asyncpg`), Qdrant searches, and Ollama HTTP calls can all run non-blocking, which matters because RAG queries involve multiple sequential I/O hops (embed → search → generate).
- Pydantic schemas double as both validation and documentation — `schemas/` directory stays the single source of truth for API contracts.
- Auto-generated OpenAPI docs (`/docs`) are useful during development and as a reference for the frontend team (even a team of one).
- SSE streaming for token-by-token LLM output is straightforward with `StreamingResponse`.

**Negative / Tradeoffs:**
- Smaller ecosystem than Django for things ragbase doesn't currently need (admin panel, built-in auth scaffolding) — auth had to be hand-built (see `services/auth_service.py`).
- Async-everywhere discipline must be maintained — a single blocking call (e.g., a sync DB driver or sync file I/O) in an async route can stall the event loop and silently degrade performance under load.
