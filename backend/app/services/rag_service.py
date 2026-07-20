import json
import uuid
from collections.abc import AsyncGenerator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.memory_service import MemoryService
from app.services.vector_service import VectorService

SYSTEM_PROMPT = (
    "You are a precise document assistant. Answer using ONLY the provided context. "
    "If the answer is not in the context, say so explicitly. Cite source and page."
)


class RAGService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding = EmbeddingService()
        self.vector = VectorService()
        self.memory = MemoryService(db)

    def _build_context(self, chunks: list[dict]) -> str:
        parts = []
        for chunk in chunks:
            parts.append(
                f"[Source: {chunk['source_filename']}, Page {chunk.get('page_number', '?')}]\n{chunk['text']}"
            )
        return "\n\n".join(parts)

    async def stream_answer(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        question: str,
    ) -> AsyncGenerator[str, None]:
        query_vector = await self.embedding.embed_query(question)
        chunks = self.vector.search(user_id, query_vector)
        context = self._build_context(chunks)

        prompt = f"SYSTEM:\n{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}\n\nUSER QUESTION:\n{question}"

        # Accumulate the full answer so we can persist it to the DB after streaming
        full_answer: list[str] = []

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        full_answer.append(token)
                        yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

        sources = [
            {
                "filename": c["source_filename"],
                "page": c.get("page_number", 0),
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ]
        yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
        yield "event: done\ndata: {}\n\n"

        # Persist the complete turn (with aggregated answer) to PostgreSQL
        await self.memory.append_turn(
            conversation_id,
            user_id,
            question,
            "".join(full_answer),
            sources,
        )
