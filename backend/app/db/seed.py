import asyncio
from app.db.session import async_session_factory
from app.models.user import User
from app.services.auth_service import AuthService
from sqlalchemy import select

async def seed_user():
    async with async_session_factory() as db:
        auth_service = AuthService(db)
        # Check if default user exists
        result = await db.execute(select(User).where(User.email == "test@ragbase.dev"))
        user = result.scalar_one_or_none()
        if not user:
            print("Seeding default test user...")
            await auth_service.register("test@ragbase.dev", "password123", "Test User")
            print("Default test user seeded successfully.")
        else:
            print("Default test user already exists.")

if __name__ == "__main__":
    asyncio.run(seed_user())
