from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.sqlalchemy_models import ClientModel


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_all(self) -> list[ClientModel]:
        result = await self._session.execute(select(ClientModel).order_by(ClientModel.id))
        return list(result.scalars().all())

    async def find_by_id(self, client_id: str) -> ClientModel | None:
        result = await self._session.execute(
            select(ClientModel).where(ClientModel.id == client_id)
        )
        return result.scalar_one_or_none()

    async def create(self, client_id: str, name: str, format_type: str) -> ClientModel:
        orm = ClientModel(id=client_id, name=name, format_type=format_type)
        self._session.add(orm)
        await self._session.commit()
        await self._session.refresh(orm)
        return orm

    async def update(self, client_id: str, data: dict) -> ClientModel | None:
        result = await self._session.execute(
            select(ClientModel).where(ClientModel.id == client_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(orm, key, value)
        await self._session.commit()
        await self._session.refresh(orm)
        return orm
