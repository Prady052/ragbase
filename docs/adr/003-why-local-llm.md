# ADR-003: Use Ollama with Local Open-Source Models Instead of Cloud LLM APIs

**Status:** Accepted
**Date:** 2025-06
**Related:** PRD.md §2.3, §3.2; system-design.md §7

## Context

ragbase's central value proposition is privacy: documents and queries must never leave the user's machine. This directly constrains the choice of LLM and embedding provider. Additionally, the project has a zero-budget constraint — any per-token API cost is unacceptable for a portfolio project meant to run indefinitely without ongoing spend. The target development hardware includes a consumer GPU (NVIDIA RTX 3050 Ti, 4GB VRAM), which further constrains model size.

## Decision

Use **Ollama** as the local LLM runtime, serving **llama3.2:3b** (quantized) for generation and **nomic-embed-text** for embeddings.

## Alternatives Considered

| Option | Why not chosen |
|---|---|
| **OpenAI API (GPT-4o / GPT-4o-mini)** | Best-in-class quality, but every query and every document chunk would be transmitted to a third-party server — directly violates the privacy-first requirement. Also introduces per-token cost, which conflicts with the zero-budget goal. |
| **Anthropic Claude API** | Same fundamental issue as OpenAI — cloud-hosted, data leaves the machine, recurring cost. Excellent for non-privacy-sensitive use cases, but disqualified here on the same grounds. |
| **Self-hosted larger model (e.g., Llama 3 70B) via vLLM** | Would need far more VRAM than the available 4GB GPU provides; effectively unrunnable on the target hardware without expensive cloud GPU rental, which reintroduces both cost and a network dependency. |
| **Ollama + llama3.2:3b** (chosen) | Runs fully offline, fits comfortably in 4GB VRAM at Q4 quantization (~2.2GB), zero per-query cost, and exposes an OpenAI-compatible API that keeps the FastAPI integration code simple. |

## Consequences

**Positive:**
- Zero external network calls in the inference path — directly fulfills the core privacy guarantee that differentiates ragbase from cloud RAG tools.
- Zero marginal cost per query, indefinitely — sustainable for a personal/portfolio project with no funding.
- Fully offline-capable after initial model pull — works without internet access.
- Ollama's API shape closely mirrors OpenAI's chat completion format, minimizing integration friction and making a future provider swap (if ever needed) low-effort.

**Negative / Tradeoffs:**
- Response quality is measurably below GPT-4-class models, particularly on complex multi-hop reasoning across retrieved chunks. Mitigated by tighter prompt engineering and a more conservative retrieval strategy (smaller, higher-precision context windows).
- Inference latency is slower than a cloud API on dedicated server-grade GPUs — acceptable for a local single-user tool, would not meet typical enterprise multi-user SLAs without hardware upgrades.
- Locked to models that fit in 4GB VRAM, limiting context window size and reasoning capability compared to larger hosted models.
