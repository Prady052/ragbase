import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, DocumentStatus, FileType


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue_upload(self, user_id: uuid.UUID, file: UploadFile) -> Document:
        upload_dir = Path(settings.upload_dir) / str(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(file.filename or "").suffix.lower()
        file_type = FileType.pdf if suffix == ".pdf" else FileType.docx
        file_path = upload_dir / (file.filename or "upload")

        content = await file.read()
        file_path.write_bytes(content)

        document = Document(
            user_id=user_id,
            filename=file.filename or file_path.name,
            file_path=str(file_path),
            file_type=file_type,
            file_size_bytes=len(content),
            status=DocumentStatus.pending,
        )
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)

        # Publish upload pending event
        from app.services.notification_service import NotificationService
        await NotificationService.publish_status(
            user_id=str(user_id),
            document_id=str(document.id),
            filename=document.filename,
            status=document.status.value,
            file_type=document.file_type.value,
            file_size_bytes=document.file_size_bytes
        )

        # Enqueue async ingestion pipeline
        from app.workers.tasks import process_document  # local import avoids circular deps
        process_document.delay(str(document.id))

        return document

    async def list_documents(self, user_id: uuid.UUID) -> list[Document]:
        result = await self.db.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document(self, document_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def delete_document(self, document_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        document = await self.get_document(document_id, user_id)
        if document is None:
            return False

        # Remove disk file
        Path(document.file_path).unlink(missing_ok=True)

        # Remove Qdrant vectors for this document
        try:
            from app.services.vector_service import VectorService
            VectorService().delete_by_document(document_id)
        except Exception:
            pass  # Best-effort; don't block the DB delete

        await self.db.delete(document)
        await self.db.commit()

        # Publish deletion event
        from app.services.notification_service import NotificationService
        await NotificationService.publish_status(
            user_id=str(user_id),
            document_id=str(document_id),
            filename=document.filename,
            status="deleted"
        )

        return True

