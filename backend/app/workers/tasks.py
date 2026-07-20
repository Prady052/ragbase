import asyncio
import logging
import uuid
from pathlib import Path

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.document import Document, DocumentStatus, FileType
from app.models.user import User  # Required for SQLAlchemy ForeignKey resolution
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process_document_async(document_id_str: str) -> None:
    """Async implementation of the document ingestion pipeline."""
    # Create a local engine for this asyncio event loop
    # Celery forks + asyncio.run() create new event loops, which breaks global asyncpg connection pools.
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    doc_uuid = uuid.UUID(document_id_str)

    try:
        async with async_session_factory() as db:
            # 1. Fetch the document record
            result = await db.execute(select(Document).where(Document.id == doc_uuid))
            document = result.scalar_one_or_none()
            if not document:
                logger.error(f"Document {document_id_str} not found in database.")
                return

            # 2. Update status to processing
            document.status = DocumentStatus.processing
            await db.commit()
            await db.refresh(document)

            from app.services.notification_service import NotificationService
            await NotificationService.publish_status(
                user_id=str(document.user_id),
                document_id=str(document.id),
                filename=document.filename,
                status=document.status.value,
                file_type=document.file_type.value,
                file_size_bytes=document.file_size_bytes
            )

            try:
                file_path = Path(document.file_path)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found on disk: {file_path}")

                chunks_data: list[dict] = []

                # 3. Parse text and build chunks with page attribution
                if document.file_type == FileType.pdf:
                    reader = PdfReader(str(file_path))
                    document.page_count = len(reader.pages)

                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=512,
                        chunk_overlap=64,
                    )

                    chunk_idx = 0
                    for page_num, page in enumerate(reader.pages, start=1):
                        text = page.extract_text() or ""
                        if not text.strip():
                            continue
                        for chunk_text in splitter.split_text(text):
                            chunks_data.append(
                                {
                                    "chunk_index": chunk_idx,
                                    "page_number": page_num,
                                    "text": chunk_text,
                                    "source_filename": document.filename,
                                }
                            )
                            chunk_idx += 1

                elif document.file_type == FileType.docx:
                    doc = DocxDocument(str(file_path))
                    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                    combined_text = "\n".join(paragraphs)

                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=512,
                        chunk_overlap=64,
                    )

                    document.page_count = 1  # DOCX pages aren't addressable; use 1
                    for idx, chunk_text in enumerate(splitter.split_text(combined_text)):
                        chunks_data.append(
                            {
                                "chunk_index": idx,
                                "page_number": 1,
                                "text": chunk_text,
                                "source_filename": document.filename,
                            }
                        )
                else:
                    raise ValueError(f"Unsupported file type: {document.file_type}")

                if not chunks_data:
                    raise ValueError("No extractable text content found in document.")

                # 4. Generate embeddings via Ollama
                embedding_service = EmbeddingService()
                texts = [c["text"] for c in chunks_data]
                vectors = await embedding_service.embed_texts(texts)

                # 5. Upsert vectors into Qdrant
                vector_service = VectorService()
                vector_service.upsert_chunks(
                    document_id=document.id,
                    user_id=document.user_id,
                    chunks=chunks_data,
                    vectors=vectors,
                )

                # 6. Mark document as ready
                document.chunk_count = len(chunks_data)
                document.status = DocumentStatus.ready
                await db.commit()

                from app.services.notification_service import NotificationService
                await NotificationService.publish_status(
                    user_id=str(document.user_id),
                    document_id=str(document.id),
                    filename=document.filename,
                    status=document.status.value,
                    file_type=document.file_type.value,
                    file_size_bytes=document.file_size_bytes
                )
                logger.info(
                    f"Document {document_id_str} ingested successfully. "
                    f"chunks={len(chunks_data)}, pages={document.page_count}"
                )

            except Exception as exc:
                logger.exception(f"Error processing document {document_id_str}: {exc}")
                document.status = DocumentStatus.failed
                document.error_message = str(exc)
                await db.commit()

                from app.services.notification_service import NotificationService
                await NotificationService.publish_status(
                    user_id=str(document.user_id),
                    document_id=str(document.id),
                    filename=document.filename,
                    status=document.status.value,
                    error_message=str(exc),
                    file_type=document.file_type.value,
                    file_size_bytes=document.file_size_bytes
                )
    finally:
        await engine.dispose()


@celery_app.task(name="process_document", bind=True, max_retries=3, default_retry_delay=10)
def process_document(self, document_id: str) -> None:
    """Celery task: parse → chunk → embed → upsert a document into Qdrant."""
    try:
        asyncio.run(_process_document_async(document_id))
    except Exception as exc:
        logger.exception(f"Celery task failed for document {document_id}: {exc}")
        raise self.retry(exc=exc)
