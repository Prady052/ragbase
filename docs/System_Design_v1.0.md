# ragbase

### System Design Document

*Version 1.0 | June 2025*

|                   |                                                                  |
|-------------------|------------------------------------------------------------------|
| **Field**         | **Details**                                                      |
| **Project**       | ragbase — Enterprise RAG Platform                                |
| **Document Type** | System Design Document (SDD)                                     |
| **Version**       | 1.0 — Initial                                                    |
| **Scope**         | Full system architecture, data models, API contracts, data flows |
| **Related Docs**  | PRD v1.0, ADR-001 through ADR-006                                |

# 1. System Overview

ragbase is a self-hosted, privacy-preserving Retrieval-Augmented Generation (RAG) platform. It enables users to upload document collections (PDF, DOCX) and query them in natural language. All processing — embedding generation, vector search, and LLM inference — happens locally with no external API calls.

The system is orchestrated via Docker Compose across six containers: a FastAPI backend, a Celery worker, PostgreSQL, Qdrant, Redis, and Ollama. Architecture style is covered in detail in Section 2.

# 2. Architecture Style: Modular Monolith

ragbase is a **modular monolith**, not a microservices architecture. This distinction matters and is stated explicitly to avoid ambiguity.

| Question | Answer |
|---|---|
| Is business logic split into independently deployable services? | No — all application logic lives in one FastAPI codebase |
| Does each "service" own its own database? | No — PostgreSQL is shared by the API and the Celery worker |
| Do internal components talk over network APIs (REST/gRPC)? | No — internal modules call each other as Python functions |
| Can one component fail without affecting others? | Partially — the Celery worker can crash without killing the API, but they still share code and data models |
| Is there independent scaling per business capability? | No — the only independently scalable units are infrastructure stores (Qdrant, Redis, Postgres, Ollama), not business logic |

**What is actually separated:** infrastructure-level concerns. PostgreSQL, Qdrant, Redis, and Ollama are dedicated, swappable stores reachable over the network — this gives clean separation of *data and compute concerns*, not *business logic*. The Celery worker is a separate process for async execution, but it imports and shares the same application codebase as the API.


## 2.1. Migration Path: Evolutionary Architecture

The modular monolith is treated as the current stage of an intentionally evolvable architecture, not a permanent ceiling. The internal `services/` layer (`auth_service`, `ingestion_service`, `embedding_service`, `vector_service`, `rag_service`, `memory_service`) was deliberately structured so that each module has a single responsibility and minimal cross-module coupling. This means each one is a **microservice extraction candidate**, not just an internal package.

The intended migration path follows demand, not a fixed schedule. A module is extracted into its own service only when a concrete signal justifies it — not preemptively. Likely triggers, in order of probability:

| Trigger | Likely first extraction |
|---|---|
| Embedding/LLM inference becomes a GPU bottleneck under concurrent load | `embedding_service` → standalone inference service, independently scaled on GPU-backed infra |
| Ingestion volume grows and starts competing with query latency for resources | `ingestion_service` + Celery worker → dedicated ingestion service with its own queue |
| Multiple client applications need to query the same knowledge base | `rag_service` → standalone retrieval API, decoupled from the main backend |
| Authentication needs to be shared across multiple products | `auth_service` → centralized identity service (e.g., OAuth2 provider) |

Each extraction follows the same discipline: the module's existing internal interface becomes its external API contract, its data ownership is clarified (does it need its own database, or can it remain a client of the shared PostgreSQL instance), and it is deployed independently behind the same API gateway boundary the frontend already talks to — so the migration is invisible to clients of the system.

This approach avoids two common failure modes: building microservices upfront before real scaling pressure exists (over-engineering, premature distributed-systems complexity), and never revisiting the architecture as the system grows (under-engineering, eventual monolith collapse). The architecture is expected to change — deliberately, incrementally, and only in response to evidence.

# 3. C4 Architecture Diagrams

## 3.1. Level 1 — System Context

Shows how ragbase sits in relation to users and external systems. At this level there are no external systems — by design.

|                    |                  |                                                                 |
|--------------------|------------------|-----------------------------------------------------------------|
| **Actor / System** | **Type**         | **Interaction**                                                 |
| End User           | Human            | Uploads documents, asks questions, views answers via browser    |
| Admin User         | Human            | Manages users, views all documents, system configuration        |
| ragbase Platform   | Software System  | Ingests, indexes, retrieves, and answers queries from documents |
| External APIs      | None — by design | Zero external calls. All inference and storage is local.        |

## 3.2. Level 2 — Container Diagram

The system is composed of six containers, each running as a Docker service:

|                 |                         |          |                                                         |
|-----------------|-------------------------|----------|---------------------------------------------------------|
| **Container**   | **Technology**          | **Port** | **Responsibility**                                      |
| React Frontend  | React + Vite + Tailwind | 5173     | Browser UI — chat, document manager, auth               |
| FastAPI Backend | Python 3.12 + FastAPI   | 8000     | REST API, auth, SSE streaming, orchestration            |
| Celery Worker   | Python + Celery         | internal | Async document parsing, chunking, embedding             |
| PostgreSQL      | PostgreSQL 16           | 5432     | Users, documents, chunks metadata, conversations        |
| Qdrant          | Qdrant v1.9             | 6333     | Vector embeddings and similarity search                 |
| Redis           | Redis 7                 | 6379     | Celery broker + result backend, conversation cache      |
| Ollama          | Ollama + CUDA           | 11434    | Local LLM (llama3.2:3b) + embeddings (nomic-embed-text) |

## 3.3. Level 3 — Component Diagram (FastAPI Backend)

The backend is organized into the following internal components:

|                   |                           |                                                                |
|-------------------|---------------------------|----------------------------------------------------------------|
| **Component**     | **Module Path**           | **Responsibility**                                             |
| Auth Router       | app/api/auth.py           | Register, login, token refresh, logout                         |
| Documents Router  | app/api/documents.py      | Upload, list, delete, status endpoints                         |
| Chat Router       | app/api/chat.py           | Query endpoint, SSE streaming, conversation list               |
| Auth Service      | app/services/auth.py      | JWT creation, validation, password hashing                     |
| Ingestion Service | app/services/ingestion.py | Document parsing, chunking strategy                            |
| Embedding Service | app/services/embedding.py | Calls Ollama embed endpoint, batches requests                  |
| Vector Service    | app/services/vector.py    | Qdrant upsert, search, delete operations                       |
| RAG Service       | app/services/rag.py       | Retrieval chain: embed query, search, build prompt, stream LLM |
| Memory Service    | app/services/memory.py    | Read/write conversation turns from Redis and PostgreSQL        |
| Celery Tasks      | app/workers/tasks.py      | process_document task: parse → chunk → embed → upsert          |

# 4. Data Flow Diagrams

## 4.1. Document Ingestion Flow

This flow is triggered when a user uploads a document. The API returns immediately; all heavy processing is async.

|          |                      |                                                                                       |
|----------|----------------------|---------------------------------------------------------------------------------------|
| **Step** | **Actor**            | **Action**                                                                            |
| **1**    | User → Frontend      | User selects a PDF or DOCX file and clicks Upload                                     |
| **2**    | Frontend → FastAPI   | POST /api/documents/upload with multipart/form-data and JWT header                    |
| **3**    | FastAPI              | Validates JWT, checks MIME type and file size, saves file to /uploads/{user_id}/      |
| **4**    | FastAPI → PostgreSQL | Inserts document record with status=PENDING, returns document_id to client            |
| **5**    | FastAPI → Redis      | Enqueues process_document Celery task with document_id                                |
| **6**    | Celery Worker        | Picks up task, updates document status to PROCESSING in PostgreSQL                    |
| **7**    | Worker → File        | Reads file from disk. Uses pypdf2 for PDF or python-docx for DOCX to extract raw text |
| **8**    | Worker               | Splits text using RecursiveCharacterTextSplitter (chunk=512, overlap=64 tokens)       |
| **9**    | Worker → Ollama      | Sends chunks in batches to Ollama /api/embeddings (nomic-embed-text model)            |
| **10**   | Worker → Qdrant      | Upserts vectors with payload: {document_id, chunk_index, page_number, text, source}   |
| **11**   | Worker → PostgreSQL  | Updates document status to READY, stores chunk_count and page_count                   |
| **12**   | Frontend polls       | GET /api/documents/{id}/status every 3 seconds until READY or FAILED                  |

## 4.2. Query & Answer Flow (RAG Pipeline)

This flow handles a user question and produces a streamed, cited answer.

|          |                      |                                                                                                              |
|----------|----------------------|--------------------------------------------------------------------------------------------------------------|
| **Step** | **Actor**            | **Action**                                                                                                   |
| **1**    | User → Frontend      | User types a question and presses Send                                                                       |
| **2**    | Frontend → FastAPI   | POST /api/chat/query with {session_id, question} and JWT header. Opens SSE connection.                       |
| **3**    | FastAPI → Memory     | Fetches last 10 conversation turns from Redis (or PostgreSQL if cache miss)                                  |
| **4**    | FastAPI → Ollama     | Embeds the user question using nomic-embed-text — produces a 768-dim vector                                  |
| **5**    | FastAPI → Qdrant     | Searches top-5 nearest vectors filtered by user_id. Returns chunks with payloads.                            |
| **6**    | FastAPI              | Reranks retrieved chunks by relevance score. Builds context string with source attribution.                  |
| **7**    | FastAPI              | Constructs structured prompt: system instructions + retrieved context + conversation history + user question |
| **8**    | FastAPI → Ollama     | Sends prompt to llama3.2:3b with stream=true. Receives token stream.                                         |
| **9**    | FastAPI → Frontend   | Forwards each token as an SSE event: data: {token}. Frontend renders progressively.                          |
| **10**   | FastAPI → Frontend   | On stream end, sends final SSE event with source citations array                                             |
| **11**   | FastAPI → PostgreSQL | Persists full turn {question, answer, sources, timestamp} to conversations table                             |
| **12**   | FastAPI → Redis      | Updates session cache with new turn. TTL reset to 24 hours.                                                  |

# 5. Database Schema (PostgreSQL)

All relational data lives in PostgreSQL. Migrations managed via Alembic. Never modify schema directly — always create a migration file.

## 5.1. users

|                 |              |                               |                               |
|-----------------|--------------|-------------------------------|-------------------------------|
| **Column**      | **Type**     | **Constraints**               | **Notes**                     |
| id              | UUID         | PK, default gen_random_uuid() | Primary key                   |
| email           | VARCHAR(255) | UNIQUE, NOT NULL              | Login identifier              |
| hashed_password | TEXT         | NOT NULL                      | bcrypt hash, cost=12          |
| full_name       | VARCHAR(255) | NOT NULL                      | Display name                  |
| role            | ENUM         | NOT NULL, default 'user'      | 'admin' or 'user'             |
| is_active       | BOOLEAN      | default TRUE                  | Soft disable without deleting |
| created_at      | TIMESTAMPTZ  | default NOW()                 | Account creation time         |
| updated_at      | TIMESTAMPTZ  | auto-update                   | Last profile update           |

## 5.2. refresh_tokens

|            |             |                  |                               |
|------------|-------------|------------------|-------------------------------|
| **Column** | **Type**    | **Constraints**  | **Notes**                     |
| id         | UUID        | PK               |                               |
| user_id    | UUID        | FK → users.id    | Owner of token                |
| token_hash | TEXT        | UNIQUE, NOT NULL | SHA-256 hash of the raw token |
| expires_at | TIMESTAMPTZ | NOT NULL         | 7-day TTL                     |
| revoked    | BOOLEAN     | default FALSE    | Revoked on logout or rotation |
| created_at | TIMESTAMPTZ | default NOW()    |                               |

## 5.3. documents

|                 |              |                             |                                       |
|-----------------|--------------|-----------------------------|---------------------------------------|
| **Column**      | **Type**     | **Constraints**             | **Notes**                             |
| id              | UUID         | PK                          |                                       |
| user_id         | UUID         | FK → users.id               | Owner                                 |
| filename        | VARCHAR(500) | NOT NULL                    | Original uploaded filename            |
| file_path       | TEXT         | NOT NULL                    | Absolute path on disk                 |
| file_type       | ENUM         | NOT NULL                    | 'pdf' or 'docx'                       |
| file_size_bytes | BIGINT       | NOT NULL                    | Used for display and quota checks     |
| status          | ENUM         | NOT NULL, default 'pending' | pending → processing → ready → failed |
| page_count      | INTEGER      | nullable                    | Set after parsing                     |
| chunk_count     | INTEGER      | nullable                    | Set after embedding                   |
| error_message   | TEXT         | nullable                    | Set on FAILED status                  |
| created_at      | TIMESTAMPTZ  | default NOW()               |                                       |

## 5.4. conversations

|            |              |                 |                                    |
|------------|--------------|-----------------|------------------------------------|
| **Column** | **Type**     | **Constraints** | **Notes**                          |
| id         | UUID         | PK              | Also used as Redis session key     |
| user_id    | UUID         | FK → users.id   | Owner                              |
| title      | VARCHAR(500) | nullable        | Auto-generated from first question |
| created_at | TIMESTAMPTZ  | default NOW()   |                                    |
| updated_at | TIMESTAMPTZ  | auto-update     | Used to sort conversation list     |

## 5.5. messages

|                 |             |                       |                                                         |
|-----------------|-------------|-----------------------|---------------------------------------------------------|
| **Column**      | **Type**    | **Constraints**       | **Notes**                                               |
| id              | UUID        | PK                    |                                                         |
| conversation_id | UUID        | FK → conversations.id | Parent conversation                                     |
| role            | ENUM        | NOT NULL              | 'user' or 'assistant'                                   |
| content         | TEXT        | NOT NULL              | Full message text                                       |
| sources         | JSONB       | nullable              | Array of {filename, chunk_index, page} — assistant only |
| created_at      | TIMESTAMPTZ | default NOW()         | Message ordering                                        |

# 6. Qdrant Vector Store Schema

## 6.1. Collection: document_chunks

|           |              |                                                        |
|-----------|--------------|--------------------------------------------------------|
| **Field** | **Type**     | **Notes**                                              |
| id        | UUID string  | Unique point ID — format: {document_id}\_{chunk_index} |
| vector    | float\[768\] | nomic-embed-text output dimension is 768               |

## 6.2. Payload (per point)

|                 |               |                                                                |
|-----------------|---------------|----------------------------------------------------------------|
| **Payload Key** | **Type**      | **Notes**                                                      |
| document_id     | string (UUID) | Links back to PostgreSQL documents table                       |
| user_id         | string (UUID) | Used for filtering — users only search their own documents     |
| chunk_index     | integer       | Position of chunk within document (0-indexed)                  |
| page_number     | integer       | Source page for citation display                               |
| text            | string        | Raw chunk text — returned with search results to build context |
| source_filename | string        | Original filename for citation display in UI                   |

## 6.3. Search Configuration

- Distance metric: Cosine similarity

- Default top-k: 5 (configurable per query)

- Filter: user_id must match requesting user — prevents cross-user data leakage

- Index type: HNSW (Qdrant default) — optimal for recall/speed tradeoff at this scale

# 7. API Contract

All endpoints are prefixed with /api/v1. All protected endpoints require Authorization: Bearer \<access_token\> header.

## 7.1. Auth Endpoints

|            |                |               |                                      |
|------------|----------------|---------------|--------------------------------------|
| **Method** | **Path**       | **Auth**      | **Description**                      |
| **POST**   | /auth/register | None          | Create new user account              |
| **POST**   | /auth/login    | None          | Returns access_token + refresh_token |
| **POST**   | /auth/refresh  | Refresh token | Returns new access_token             |
| **POST**   | /auth/logout   | Bearer        | Revokes refresh token                |
| **GET**    | /auth/me       | Bearer        | Returns current user profile         |

## 7.2. Document Endpoints

|            |                        |          |                                                                           |
|------------|------------------------|----------|---------------------------------------------------------------------------|
| **Method** | **Path**               | **Auth** | **Description**                                                           |
| **POST**   | /documents/upload      | Bearer   | Upload PDF or DOCX. Returns document_id immediately. Processing is async. |
| **GET**    | /documents             | Bearer   | List all documents for current user with status                           |
| **GET**    | /documents/{id}        | Bearer   | Get single document metadata                                              |
| **GET**    | /documents/{id}/status | Bearer   | Poll ingestion status: PENDING / PROCESSING / READY / FAILED              |
| **DELETE** | /documents/{id}        | Bearer   | Delete document: removes file, PostgreSQL record, and all Qdrant vectors  |

## 7.3. Chat Endpoints

|            |                          |          |                                                                             |
|------------|--------------------------|----------|-----------------------------------------------------------------------------|
| **Method** | **Path**                 | **Auth** | **Description**                                                             |
| **POST**   | /chat/conversations      | Bearer   | Create a new conversation session. Returns session_id.                      |
| **GET**    | /chat/conversations      | Bearer   | List all conversations for current user, sorted by updated_at desc          |
| **GET**    | /chat/conversations/{id} | Bearer   | Get full message history for a conversation                                 |
| **POST**   | /chat/query              | Bearer   | Submit a question. Returns SSE stream of tokens, followed by sources event. |
| **DELETE** | /chat/conversations/{id} | Bearer   | Delete conversation and all its messages                                    |

## 7.4. SSE Stream Format

The /chat/query endpoint returns a text/event-stream response. Events:

> event: token
>
> data: {"token": "The"}
>
> event: token
>
> data: {"token": " answer"}
>
> event: sources
>
> data: {"sources": \[{"filename": "policy.pdf", "page": 4, "chunk_index": 12}\]}
>
> event: done
>
> data: {}

# 8. LLM Prompt Template

The structured prompt sent to the local LLM for every query:

> SYSTEM:
>
> You are a precise document assistant. Answer the user's question using ONLY
>
> the provided context. If the answer is not in the context, say so explicitly.
>
> Always cite the source document and page number for each claim.
>
> Do not make up information. Be concise and factual.
>
> CONTEXT:
>
> \[Source: policy.pdf, Page 4\]
>
> ...chunk text here...
>
> \[Source: contract.pdf, Page 12\]
>
> ...chunk text here...
>
> CONVERSATION HISTORY:
>
> User: previous question
>
> Assistant: previous answer
>
> USER QUESTION:
>
> {question}

# 9. Environment Variables

All secrets and configuration live in a .env file. Never committed to git. A .env.example with placeholder values is committed instead.

|                             |                       |                                                      |
|-----------------------------|-----------------------|------------------------------------------------------|
| **Variable**                | **Example Value**     | **Notes**                                            |
| POSTGRES_USER               | ragbase               | PostgreSQL username                                  |
| POSTGRES_PASSWORD           | changeme              | Use strong password in prod                          |
| POSTGRES_DB                 | ragbase_db            | Database name                                        |
| DATABASE_URL                | postgresql://...      | Full SQLAlchemy connection string                    |
| SECRET_KEY                  | random-64-char-hex    | JWT signing key — generate with openssl rand -hex 32 |
| ACCESS_TOKEN_EXPIRE_MINUTES | 15                    | Access token TTL                                     |
| REFRESH_TOKEN_EXPIRE_DAYS   | 7                     | Refresh token TTL                                    |
| REDIS_URL                   | redis://redis:6379/0  | Celery broker and cache                              |
| QDRANT_HOST                 | qdrant                | Docker service name                                  |
| QDRANT_PORT                 | 6333                  | Qdrant REST port                                     |
| OLLAMA_BASE_URL             | http://ollama:11434   | Ollama service URL                                   |
| EMBED_MODEL                 | nomic-embed-text      | Embedding model name in Ollama                       |
| LLM_MODEL                   | llama3.2:3b           | LLM model name in Ollama                             |
| MAX_UPLOAD_SIZE_MB          | 50                    | File upload size limit                               |
| CHUNK_SIZE                  | 512                   | Tokens per chunk                                     |
| CHUNK_OVERLAP               | 64                    | Token overlap between chunks                         |
| TOP_K_RETRIEVAL             | 5                     | Number of chunks retrieved per query                 |
| CORS_ORIGINS                | http://localhost:5173 | Allowed frontend origins                             |

# 10. Inter-Service Communication

|               |            |                                                                               |
|---------------|------------|-------------------------------------------------------------------------------|
| **From**      | **To**     | **Protocol & Notes**                                                          |
| Frontend      | FastAPI    | HTTP REST + SSE over port 8000. CORS enforced.                                |
| FastAPI       | PostgreSQL | SQLAlchemy async via asyncpg driver. Connection pool size 10.                 |
| FastAPI       | Redis      | redis-py async client. Used for session cache reads and Celery task dispatch. |
| FastAPI       | Qdrant     | qdrant-client Python SDK over HTTP port 6333.                                 |
| FastAPI       | Ollama     | HTTP to port 11434. OpenAI-compatible API (/api/embed, /api/chat).            |
| Celery Worker | Redis      | Broker and result backend. Worker polls task queue continuously.              |
| Celery Worker | PostgreSQL | Updates document status, stores chunk metadata.                               |
| Celery Worker | Qdrant     | Batch upserts of vectors after embedding.                                     |
| Celery Worker | Ollama     | Batch embedding calls during ingestion.                                       |

# 11. Security Design

## 11.1. Authentication Flow

- User logs in → receives short-lived access token (15 min) + long-lived refresh token (7 days)

- Access token sent as Authorization: Bearer header on every API call

- Refresh token stored in httpOnly cookie — not accessible to JavaScript

- On access token expiry, client silently calls /auth/refresh to get a new one

- On logout, refresh token is revoked in database

## 11.2. Data Isolation

- Every Qdrant search includes a user_id filter — users cannot retrieve other users' document chunks

- Document file paths are scoped to /uploads/{user_id}/ — no path traversal possible

- All database queries use parameterized statements via SQLAlchemy ORM

## 11.3. Input Validation

- File upload: MIME type validated server-side (not just extension)

- File size hard-capped at MAX_UPLOAD_SIZE_MB

- All request bodies validated via Pydantic models before any processing

- UUID parameters validated by type system — no string injection