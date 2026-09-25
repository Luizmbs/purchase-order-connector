from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adapters.persistence.sqlalchemy_models import ConferenceDivergenceModel, ConferenceModel
from domain.models.conference import Conference, ConferenceDivergence, ConferenceResult, DivergenceType
from domain.ports.outbound.conference_repository import ConferenceFilters, ConferenceRepository


class PostgresConferenceRepository(ConferenceRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, conference: Conference) -> None:
        async with self._session.begin():
            orm = ConferenceModel(
                id=conference.id,
                purchase_order_id=conference.purchase_order_id,
                client_id=conference.client_id,
                po_number=conference.po_number,
                invoice_number=conference.invoice_number,
                vendor_tax_id=conference.vendor_tax_id,
                result=conference.result.value,
                checked_at=conference.checked_at,
            )
            self._session.add(orm)
            await self._session.flush()

            self._session.add_all([
                ConferenceDivergenceModel(
                    conference_id=conference.id,
                    type=d.type.value,
                    item_line=d.item_line,
                    material=d.material,
                    expected=d.expected,
                    received=d.received,
                    detail=d.detail,
                )
                for d in conference.divergences
            ])

    async def find_many(
        self, filters: ConferenceFilters, offset: int, limit: int
    ) -> tuple[list[Conference], int]:
        base = select(ConferenceModel)

        if filters.client_id:
            base = base.where(ConferenceModel.client_id == filters.client_id)
        if filters.result:
            base = base.where(ConferenceModel.result == filters.result.value)

        total_result = await self._session.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        query = (
            base.options(selectinload(ConferenceModel.divergences))
            .order_by(ConferenceModel.checked_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(query)
        rows = result.scalars().all()

        return [self._to_domain(row) for row in rows], total

    def _to_domain(self, orm: ConferenceModel) -> Conference:
        return Conference(
            id=orm.id,
            purchase_order_id=orm.purchase_order_id,
            client_id=orm.client_id,
            po_number=orm.po_number,
            invoice_number=orm.invoice_number,
            vendor_tax_id=orm.vendor_tax_id,
            result=ConferenceResult(orm.result),
            checked_at=orm.checked_at,
            divergences=[self._div_to_domain(d) for d in orm.divergences],
        )

    def _div_to_domain(self, orm: ConferenceDivergenceModel) -> ConferenceDivergence:
        return ConferenceDivergence(
            type=DivergenceType(orm.type),
            item_line=orm.item_line,
            material=orm.material,
            expected=orm.expected,
            received=orm.received,
            detail=orm.detail,
        )
