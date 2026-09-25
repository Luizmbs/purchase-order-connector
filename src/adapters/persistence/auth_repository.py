from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.sqlalchemy_models import RefreshTokenModel, UserModel


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_user_by_id(self, user_id: UUID) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_user_by_username(self, username: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none()

    async def save_refresh_token(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> None:
        self._session.add(
            RefreshTokenModel(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        )
        await self._session.commit()

    async def find_refresh_token(self, token_hash: str) -> RefreshTokenModel | None:
        result = await self._session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_hash: str) -> None:
        result = await self._session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        token = result.scalar_one_or_none()
        if token:
            token.revoked_at = datetime.now(UTC)
            await self._session.commit()
