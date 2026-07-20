import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentStatusResponse
from app.services.ingestion_service import IngestionService

router = APIRouter()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IngestionService(db)
    document = await service.enqueue_upload(current_user.id, file)
    return document


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IngestionService(db)
    return await service.list_documents(current_user.id)


@router.get("/stream")
async def stream_document_statuses(
    current_user: User = Depends(get_current_user)
):
    async def event_generator():
        import redis.asyncio as io_redis
        import asyncio
        import json
        from app.core.config import settings

        r = await io_redis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        channel = f"document_status:{current_user.id}"
        await pubsub.subscribe(channel)
        
        try:
            # Yield an initial connection event
            yield f"event: ping\ndata: {json.dumps({'message': 'connected'})}\n\n"
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                if message:
                    data = message["data"].decode("utf-8")
                    yield f"event: document_status\ndata: {data}\n\n"
                else:
                    # Keep-alive ping
                    yield f"event: ping\ndata: {json.dumps({'message': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IngestionService(db)
    document = await service.get_document(document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IngestionService(db)
    document = await service.get_document(document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IngestionService(db)
    deleted = await service.delete_document(document_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return None
