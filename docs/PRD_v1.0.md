# Enterprise RAG Platform

### Product Requirements Document

*Version 1.0 | June 2025*
*Status: Draft*

|                  |                                                                   |
|------------------|-------------------------------------------------------------------|
| **Field**        | **Details**                                                       |
| **Project Name** | Enterprise RAG Platform                                           |
| **Author**       | Engineering Team                                                  |
| **Version**      | 1.0 — Initial Draft                                               |
| **Stack**        | FastAPI · PostgreSQL · Qdrant · Redis · Celery · Ollama · React   |
| **Deployment**   | Local-first · Docker Compose · Privacy-preserving (no cloud APIs) |

# 1. Executive Summary

Organizations accumulate thousands of internal documents — policy manuals, legal contracts, research reports, HR handbooks — but have no efficient way to extract answers from them. Employees waste hours manually searching through PDFs and DOCX files, often failing to find what they need or missing critical information buried across hundreds of pages.

The Enterprise RAG Platform is a privacy-first, locally-deployable document intelligence system. It allows organizations to upload their internal documents and query them in natural language, receiving accurate, cited answers backed by their own knowledge base — without sending any data to external cloud services.

The system is built on Retrieval-Augmented Generation (RAG), combining vector similarity search with a locally-running large language model to produce contextually accurate responses. It supports multi-turn conversation memory, role-based access control, and asynchronous document ingestion pipelines.

# 2. Problem Statement

## 2.1. The Core Problem

Enterprise knowledge is trapped in documents. A legal team may have 500 vendor contracts. An HR department maintains dozens of policy versions. A research team accumulates hundreds of papers. The only way to extract specific information from these is to manually open, read, and search — a process that is slow, error-prone, and does not scale.

Existing solutions fall into two categories, both with critical flaws:

- Cloud-based AI tools (ChatGPT Enterprise, Microsoft Copilot) require uploading sensitive documents to third-party servers — unacceptable for regulated industries such as legal, healthcare, and finance.

- Traditional keyword search misses semantic relationships. Searching for 'termination clause' does not surface a document that says 'contract may be dissolved upon 30 days notice.'

## 2.2. Who Suffers From This

|                  |                                                      |                                                                           |
|------------------|------------------------------------------------------|---------------------------------------------------------------------------|
| **User Segment** | **Pain Point**                                       | **Example**                                                               |
| Legal teams      | Manual contract review across hundreds of files      | "What indemnity clauses exist across all 200 vendor contracts?"           |
| HR departments   | Policy lookup across multiple handbook versions      | "What is the leave policy for contract employees per the 2024 handbook?"  |
| Research teams   | Synthesizing findings across large paper collections | "Summarize all findings related to NLP benchmarks across these 50 papers" |
| IT / DevOps      | Finding specific config or policy in internal docs   | "What are the rate limits defined in our internal API governance docs?"   |

## 2.3. Why Existing Solutions Fail

- Cloud AI tools: data privacy risk, per-query cost at scale, internet dependency

- CTRL+F / keyword search: no semantic understanding, no cross-document synthesis

- Full-text search (Elasticsearch): better recall but no natural language answers, no citations

- Manual reading: does not scale beyond a few documents, inconsistent, slow

# 3. Proposed Solution

## 3.1. What We Are Building

A self-hosted, privacy-preserving RAG platform where users can upload PDF and DOCX documents, ask questions in natural language, and receive accurate answers sourced directly from those documents — with citations, conversation history, and access control.

Every component runs locally. No document or query ever leaves the user's infrastructure. The system uses open-source LLMs via Ollama, Qdrant for vector storage, PostgreSQL for relational data, and React for the user interface.

## 3.2. How It Works (High Level)

- User uploads a PDF or DOCX file through the React UI

- The file is sent to FastAPI, stored, and queued for async processing via Celery

- A worker parses the document, splits it into semantic chunks, and generates vector embeddings using a local model (nomic-embed-text via Ollama)

- Embeddings are stored in Qdrant along with chunk metadata (source file, page number, chunk index)

- When the user asks a question, it is embedded and matched against the vector store using hybrid search (dense + BM25 rerank)

- The top retrieved chunks are assembled into a context window and passed to the local LLM (llama3.2:3b via Ollama) with a structured prompt

- The LLM generates a streamed response; the answer is returned to the UI with source citations

- Conversation turns are persisted in PostgreSQL and cached in Redis for fast multi-turn context

## 3.3. Key Differentiators

|                    |                                             |                                  |
|--------------------|---------------------------------------------|----------------------------------|
| **Feature**        | **Our Platform**                            | **Cloud Alternatives**           |
| Data privacy       | 100% local, no external calls               | Data sent to third-party servers |
| Cost               | Zero per-query cost after setup             | Pay per token / per query        |
| Customization      | Full control over chunking, models, prompts | Limited, vendor-locked           |
| Offline capability | Fully offline after setup                   | Requires internet                |
| Source citations   | Built-in, per-chunk attribution             | Often absent or unreliable       |

# 4. Goals & Success Metrics

## 4.1. Primary Goals

- Enable natural language querying of any collection of PDF/DOCX documents

- Maintain full data privacy — zero external API calls in the query path

- Support multi-turn conversations with persistent memory

- Provide source citations for every answer

- Enforce user authentication and role-based access control

## 4.2. Success Metrics

|                     |                                            |                               |
|---------------------|--------------------------------------------|-------------------------------|
| **Metric**          | **Target**                                 | **Measurement**               |
| Query response time | \< 8 seconds end-to-end (local LLM)        | P95 latency in logs           |
| Ingestion time      | \< 60 seconds for a 50-page PDF            | Celery task duration          |
| Retrieval accuracy  | \> 80% answer grounded in retrieved chunks | Manual evaluation on test set |
| System uptime       | \> 99% during active sessions              | Docker health checks          |
| Concurrent users    | 5 simultaneous users on local hardware     | Load test with k6             |

## 4.3. Non-Goals (Out of Scope)

- Real-time web search or internet-sourced content

- Support for audio, video, or image-only documents

- Multi-language support (English only in v1)

- Mobile native applications

- Document editing or annotation

# 5. Functional Requirements

## 5.1. Authentication & Authorization

- Users must register and log in with email + password

- JWT access tokens (15-minute expiry) with refresh token rotation

- Two roles: Admin (full access) and User (own documents only)

- All API endpoints protected; unauthenticated requests return 401

- Password hashing with bcrypt

## 5.2. Document Ingestion

- Upload endpoint accepts PDF and DOCX files up to 50MB

- Async processing — upload returns immediately, processing happens in background

- Document status tracked: PENDING → PROCESSING → READY → FAILED

- Text extraction: pypdf2 for PDF, python-docx for DOCX

- Chunking: recursive character splitting, chunk size 512 tokens, 64-token overlap

- Each chunk stored with metadata: document_id, chunk_index, page_number, source_filename

- Embeddings generated via nomic-embed-text (Ollama), stored in Qdrant

## 5.3. Query & Retrieval

- User submits a natural language query through the chat UI

- Query embedded with the same model as documents (nomic-embed-text)

- Qdrant performs top-k similarity search (k=5 default, configurable)

- Retrieved chunks assembled into context window with source metadata

- Structured prompt sent to local LLM (llama3.2:3b via Ollama)

- Response streamed back to UI via Server-Sent Events (SSE)

- Each answer includes cited source document and chunk reference

## 5.4. Conversation Memory

- Each conversation has a unique session ID

- Last 10 turns stored in Redis for fast in-context retrieval

- Full conversation history persisted in PostgreSQL

- Users can start new conversations or resume existing ones

- Conversation list visible in sidebar with timestamps

## 5.5. Document Management

- Users can view all uploaded documents with status indicators

- Delete a document (removes file, DB record, and Qdrant vectors)

- View document metadata: filename, upload time, page count, chunk count, status

# 6. Technical Architecture

## 6.1. System Components

|               |                  |                                                                     |
|---------------|------------------|---------------------------------------------------------------------|
| **Component** | **Technology**   | **Responsibility**                                                  |
| API Server    | FastAPI (Python) | REST endpoints, auth, request routing, SSE streaming                |
| Relational DB | PostgreSQL       | Users, documents metadata, conversation history, tokens             |
| Vector Store  | Qdrant           | Document chunk embeddings and similarity search                     |
| Cache / Queue | Redis            | Celery task queue, conversation memory hot cache                    |
| Async Worker  | Celery           | Document parsing, chunking, embedding pipeline                      |
| LLM Runtime   | Ollama           | Local LLM inference (llama3.2:3b) and embeddings (nomic-embed-text) |
| Frontend      | React + Tailwind | Chat UI, document management, auth flows                            |
| Orchestration | Docker Compose   | Local multi-service orchestration                                   |

## 6.2. Repository Structure

```
ragbase/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py            # register, login, refresh, logout
│   │   │   │   ├── documents.py       # upload, list, status, delete
│   │   │   │   └── chat.py            # query, SSE stream, conversations
│   │   │   └── deps.py                # shared FastAPI dependencies
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic Settings, .env loader
│   │   │   ├── security.py            # JWT, password hashing
│   │   │   └── logging.py             # structured JSON logger setup
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── conversation.py
│   │   │   └── message.py
│   │   ├── schemas/                   # Pydantic request/response models
│   │   │   ├── auth.py
│   │   │   ├── document.py
│   │   │   └── chat.py
│   │   ├── services/                  # business logic — the real engine
│   │   │   ├── auth_service.py
│   │   │   ├── ingestion_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── vector_service.py
│   │   │   ├── rag_service.py
│   │   │   └── memory_service.py
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   └── tasks.py               # process_document task
│   │   ├── db/
│   │   │   ├── session.py             # async engine + session factory
│   │   │   └── base.py                # declarative base
│   │   └── main.py                    # FastAPI app entrypoint
│   ├── alembic/                       # DB migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py                # pytest fixtures
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   └── pyproject.toml                 # ruff, black, pytest config
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/                  # ChatWindow, MessageBubble, SourceCard
│   │   │   ├── documents/             # UploadDropzone, DocList, StatusBadge
│   │   │   └── ui/                    # shared buttons, inputs (shadcn-based)
│   │   ├── pages/
│   │   │   ├── Login.tsx, Register.tsx
│   │   │   ├── Chat.tsx
│   │   │   └── Documents.tsx
│   │   ├── hooks/                     # useAuth, useSSE, useDocuments
│   │   ├── api/                       # axios client, endpoint wrappers
│   │   ├── context/                   # AuthContext
│   │   └── App.tsx
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
│
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── ollama/Modelfile               # custom model config if needed
│
├── docs/
│   ├── PRD.md
│   ├── system-design.md
│   └── adr/
│       ├── 001-why-fastapi.md
│       ├── 002-why-qdrant.md
│       └── 003-why-local-llm.md
│
├── .github/workflows/ci.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## 6.3. Hardware Requirements (Local)

|               |                               |                                           |
|---------------|-------------------------------|-------------------------------------------|
| **Component** | **Minimum**                   | **Recommended (this project)**            |
| RAM           | 8 GB                          | 16 GB                                     |
| GPU VRAM      | None (CPU fallback)           | 4 GB — NVIDIA RTX 3050 Ti                 |
| Storage       | 20 GB free                    | 50 GB+ for large document collections     |
| LLM Model     | llama3.2:3b Q4 (~2.2 GB VRAM) | llama3.2:3b — fits comfortably in 3050 Ti |

# 7. Non-Functional Requirements

## 7.1. Performance

- API response (non-LLM): \< 200ms P95

- First LLM token (TTFT): \< 3 seconds on local GPU

- Full response: \< 8 seconds for average query

- Ingestion pipeline: \< 60 seconds for a 50-page document

## 7.2. Security

- No secrets in source code — all via environment variables

- JWT tokens signed with RS256 or HS256 with rotation

- SQL injection prevention via SQLAlchemy ORM only (no raw queries)

- File upload validation: MIME type, size limit, virus scan stub

- CORS restricted to known frontend origin

- Passwords hashed with bcrypt (cost factor 12)

## 7.3. Reliability

- Failed ingestion tasks retried up to 3 times with exponential backoff

- Database migrations managed via Alembic (never raw schema changes)

- Health check endpoints for all services (/health)

- Graceful shutdown handling in all containers

## 7.4. Observability

- Structured JSON logs in all services (loguru for Python)

- Request ID propagated across all service calls

- Prometheus metrics endpoint on FastAPI (/metrics)

- Grafana dashboard for: request rate, latency, error rate, queue depth

# 8. Development Milestones

|           |              |                                                                 |
|-----------|--------------|-----------------------------------------------------------------|
| **Phase** | **Timeline** | **Deliverable**                                                 |
| 1         | Week 1       | PRD, system design doc, ADRs, repo setup                        |
| 2         | Week 2       | Docker Compose stack running, CI/CD pipeline, dev environment   |
| 3         | Weeks 3–4    | Auth service, user management, JWT, RBAC                        |
| 4         | Weeks 5–6    | Ingestion pipeline, Celery workers, Qdrant integration          |
| 5         | Weeks 7–8    | RAG engine, LLM integration, SSE streaming, conversation memory |
| 6         | Weeks 9–10   | React frontend — chat UI, document manager, auth pages          |
| 7         | Weeks 11–12  | Testing, observability, security hardening, documentation       |

# 9. Risks & Mitigations

|                                              |                             |                                                                           |
|----------------------------------------------|-----------------------------|---------------------------------------------------------------------------|
| **Risk**                                     | **Likelihood**              | **Mitigation**                                                            |
| LLM quality insufficient for complex queries | Medium                      | Use prompt engineering, increase retrieval context, swap model if needed  |
| GPU VRAM insufficient for model              | Low (3050 Ti fits 3b model) | Use smaller quantized model or CPU offload via Ollama                     |
| Chunking strategy produces poor retrieval    | Medium                      | Build evaluation harness with test Q&A pairs; tune chunk size and overlap |
| PDF parsing fails on scanned documents       | Medium                      | Add OCR fallback with pytesseract for image-based PDFs                    |
| Scope creep during development               | High                        | Strict sprint planning; features added only after v1 is complete          |

# 10. Glossary

|               |                                                                                                                                                       |
|---------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Term**      | **Definition**                                                                                                                                        |
| **RAG**       | Retrieval-Augmented Generation — a technique that retrieves relevant document chunks and feeds them as context to an LLM to generate grounded answers |
| **Embedding** | A dense vector representation of text that encodes semantic meaning; similar texts produce similar vectors                                            |
| **Qdrant**    | An open-source vector database optimized for storing and searching high-dimensional embeddings                                                        |
| **Ollama**    | A local LLM runtime that serves open-source models (Llama, Mistral, etc.) via an OpenAI-compatible API                                                |
| **Chunking**  | The process of splitting a long document into smaller text segments that fit within the model's context window                                        |
| **RBAC**      | Role-Based Access Control — permissions assigned by user role rather than per-user                                                                    |
| **SSE**       | Server-Sent Events — HTTP protocol for streaming data from server to client in real-time (used for LLM token streaming)                               |
| **Celery**    | A distributed task queue for Python; used here to run ingestion jobs asynchronously without blocking the API                                          |
