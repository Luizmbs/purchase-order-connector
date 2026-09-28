from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.sqlalchemy_models import UserModel


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_all(self, offset: int, limit: int) -> tuple[list[UserModel], int]:
        total_result = await self._session.execute(select(func.count()).select_from(UserModel))
        total = total_result.scalar_one()

        result = await self._session.execute(
            select(UserModel).order_by(UserModel.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def find_by_id(self, user_id: UUID) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_by_username(self, username: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none()

    async def find_by_email(self, email: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    async def create(self, username: str, email: str, hashed_password: str, role: str) -> UserModel:
        orm = UserModel(username=username, email=email, hashed_password=hashed_password, role=role)
        self._session.add(orm)
        await self._session.commit()
        await self._session.refresh(orm)
        return orm

    async def update(self, user_id: UUID, data: dict) -> UserModel | None:
        orm = await self.find_by_id(user_id)
        if orm is None:
            return None
        for key, value in data.items():
            setattr(orm, key, value)
        await self._session.commit()
        await self._session.refresh(orm)
        return orm
