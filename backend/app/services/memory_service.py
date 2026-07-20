import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(self, user_id: uuid.UUID) -> Conversation:
        conversation = Conversation(user_id=user_id)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def list_conversations(self, user_id: uuid.UUID) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_messages(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Message] | None:
        conversation = await self._get_conversation(conversation_id, user_id)
        if conversation is None:
            return None
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def append_turn(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        answer: str,
        sources: list[dict] | None = None,
    ) -> None:
        conversation = await self._get_conversation(conversation_id, user_id)
        if conversation is None:
            return

        self.db.add_all(
            [
                Message(conversation_id=conversation_id, role=MessageRole.user, content=question),
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.assistant,
                    content=answer,
                    sources=sources,
                ),
            ]
        )
        await self.db.commit()

    async def delete_conversation(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        conversation = await self._get_conversation(conversation_id, user_id)
        if conversation is None:
            return False
        await self.db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        await self.db.delete(conversation)
        await self.db.commit()
        return True

    async def _get_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
