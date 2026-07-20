import json
import redis.asyncio as io_redis
from app.core.config import settings

class NotificationService:
    @staticmethod
    async def publish_status(
        user_id: str,
        document_id: str,
        filename: str,
        status: str,
        error_message: str | None = None,
        file_type: str | None = None,
        file_size_bytes: int | None = None
    ) -> None:
        """Asynchronously publish document status details to Redis Pub/Sub."""
        try:
            r = await io_redis.from_url(settings.redis_url)
            channel = f"document_status:{user_id}"
            payload = {
                "id": document_id,
                "filename": filename,
                "status": status,
                "error_message": error_message,
                "file_type": file_type,
                "file_size_bytes": file_size_bytes
            }
            await r.publish(channel, json.dumps(payload))
            await r.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to publish status update: {e}")
