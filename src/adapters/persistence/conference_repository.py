from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adapters.persistence.sqlalchemy_models import ConferenceDivergenceModel, ConferenceModel
from domain.models.conference import Conference, ConferenceDivergence, ConferenceResult, DivergenceType
from domain.ports.outbound.conference_repository import ConferenceFilters, ConferenceRepository
from infrastructure.cursor import decode_cursor, encode_cursor


class PostgresConferenceRepository(ConferenceRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, conference: Conference) -> None:
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

        await self._session.commit()

    async def find_many(
        self, filters: ConferenceFilters, cursor: str | None, limit: int
    ) -> tuple[list[Conference], str | None]:
        query = select(ConferenceModel)

        if filters.client_id:
            query = query.where(ConferenceModel.client_id == filters.client_id)
        if filters.result:
            query = query.where(ConferenceModel.result == filters.result.value)

        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            # Keyset: registros mais antigos que o cursor (ordem DESC)
            query = query.where(
                or_(
                    ConferenceModel.checked_at < cursor_ts,
                    and_(
                        ConferenceModel.checked_at == cursor_ts,
                        ConferenceModel.id < cursor_id,
                    ),
                )
            )

        # Busca limit+1 para saber se existe próxima página sem COUNT(*)
        query = (
            query.options(selectinload(ConferenceModel.divergences))
            .order_by(ConferenceModel.checked_at.desc(), ConferenceModel.id.desc())
            .limit(limit + 1)
        )
        result = await self._session.execute(query)
        rows = list(result.scalars().all())

        has_next = len(rows) > limit
        if has_next:
            rows = rows[:limit]

        next_cursor = encode_cursor(rows[-1].checked_at, rows[-1].id) if has_next else None
        return [self._to_domain(row) for row in rows], next_cursor

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
