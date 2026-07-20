import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

COLLECTION_NAME = "document_chunks"
VECTOR_SIZE = 768  # nomic-embed-text output dimension


class VectorService:
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._ensure_collection_exists()

    def _ensure_collection_exists(self) -> None:
        """Create the Qdrant collection if it doesn't already exist."""
        try:
            collections = self.client.get_collections().collections
            existing = {c.name for c in collections}
            if COLLECTION_NAME not in existing:
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=qmodels.VectorParams(
                        size=VECTOR_SIZE,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
        except Exception as exc:
            # Log but don't crash — the upsert will fail with a clearer error if it truly doesn't exist
            import logging
            logging.getLogger(__name__).warning(f"Could not verify Qdrant collection: {exc}")

    def upsert_chunks(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        chunks: list[dict],
        vectors: list[list[float]],
    ) -> None:
        points = [
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "document_id": str(document_id),
                    "user_id": str(user_id),
                    "chunk_index": chunk["chunk_index"],
                    "page_number": chunk.get("page_number", 0),
                    "text": chunk["text"],
                    "source_filename": chunk["source_filename"],
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    def search(self, user_id: uuid.UUID, query_vector: list[float], top_k: int | None = None) -> list[dict]:
        k = top_k or settings.top_k_retrieval
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=k,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="user_id",
                        match=qmodels.MatchValue(value=str(user_id)),
                    )
                ]
            ),
        )
        return [hit.payload for hit in results.points if hit.payload]

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
        )
