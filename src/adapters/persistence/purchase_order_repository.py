import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adapters.persistence.cache_service import CacheService
from adapters.persistence.sqlalchemy_models import PurchaseOrderItemModel, PurchaseOrderModel
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem
from domain.ports.outbound.purchase_order_repository import OrderFilters, PurchaseOrderRepository

log = structlog.get_logger()

_PO_TTL = 600  # 10 minutos


def _cache_key(client_id: str, po_number: str) -> str:
    return f"po:{client_id}:{po_number}"


def _serialize(order: PurchaseOrder) -> str:
    def default(obj):
        if isinstance(obj, (UUID, Decimal, date, datetime)):
            return str(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    data = {
        "id": str(order.id),
        "client_id": order.client_id,
        "po_number": order.po_number,
        "created_at": str(order.created_at) if order.created_at else None,
        "status": order.status.value,
        "currency": order.currency,
        "vendor_tax_id": order.vendor_tax_id,
        "vendor_name": order.vendor_name,
        "loaded_at": order.loaded_at.isoformat(),
        "items": [
            {
                "id": str(i.id),
                "purchase_order_id": str(i.purchase_order_id),
                "line": i.line,
                "material": i.material,
                "description": i.description,
                "uom": i.uom,
                "quantity_ordered": str(i.quantity_ordered),
                "quantity_received": str(i.quantity_received),
                "unit_price": str(i.unit_price),
                "item_created_at": str(i.item_created_at) if i.item_created_at else None,
            }
            for i in order.items
        ],
    }
    return json.dumps(data)


def _deserialize(raw: str) -> PurchaseOrder:
    data = json.loads(raw)
    return PurchaseOrder(
        id=UUID(data["id"]),
        client_id=data["client_id"],
        po_number=data["po_number"],
        created_at=date.fromisoformat(data["created_at"]) if data["created_at"] else None,
        status=OrderStatus(data["status"]),
        currency=data["currency"],
        vendor_tax_id=data["vendor_tax_id"],
        vendor_name=data["vendor_name"],
        loaded_at=datetime.fromisoformat(data["loaded_at"]),
        items=[
            PurchaseOrderItem(
                id=UUID(i["id"]),
                purchase_order_id=UUID(i["purchase_order_id"]),
                line=i["line"],
                material=i["material"],
                description=i["description"],
                uom=i["uom"],
                quantity_ordered=Decimal(i["quantity_ordered"]),
                quantity_received=Decimal(i["quantity_received"]),
                unit_price=Decimal(i["unit_price"]),
                item_created_at=date.fromisoformat(i["item_created_at"]) if i["item_created_at"] else None,
            )
            for i in data["items"]
        ],
    )


class PostgresPurchaseOrderRepository(PurchaseOrderRepository):
    def __init__(self, session: AsyncSession, cache: CacheService | None = None):
        self._session = session
        self._cache = cache

    async def find_many(
        self, filters: OrderFilters, offset: int, limit: int
    ) -> tuple[list[PurchaseOrder], int]:
        base = select(PurchaseOrderModel)

        if filters.client_id:
            base = base.where(PurchaseOrderModel.client_id == filters.client_id)
        if filters.vendor_tax_id:
            base = base.where(PurchaseOrderModel.vendor_tax_id == filters.vendor_tax_id)
        if filters.status:
            base = base.where(PurchaseOrderModel.status == filters.status.value)
        if filters.has_pending:
            pending_exists = exists().where(
                PurchaseOrderItemModel.purchase_order_id == PurchaseOrderModel.id,
                PurchaseOrderItemModel.quantity_ordered - PurchaseOrderItemModel.quantity_received > 0,
            )
            base = base.where(pending_exists)

        total_result = await self._session.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        query = (
            base.options(selectinload(PurchaseOrderModel.items))
            .order_by(PurchaseOrderModel.loaded_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(query)
        rows = result.scalars().all()

        return [self._to_domain(row) for row in rows], total

    async def find_by_client_and_number(
        self, client_id: str, po_number: str
    ) -> PurchaseOrder | None:
        if self._cache:
            key = _cache_key(client_id, po_number)
            cached = await self._cache.get(key)
            if cached:
                log.info("cache.hit", key=key)
                return _deserialize(cached)
            log.info("cache.miss", key=key)

        result = await self._session.execute(
            select(PurchaseOrderModel)
            .where(
                PurchaseOrderModel.client_id == client_id,
                PurchaseOrderModel.po_number == po_number,
            )
            .options(selectinload(PurchaseOrderModel.items))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        order = self._to_domain(row)

        if self._cache:
            await self._cache.set(key, _serialize(order), _PO_TTL)

        return order

    async def upsert(self, order: PurchaseOrder) -> None:
        async with self._session.begin():
            result = await self._session.execute(
                select(PurchaseOrderModel).where(
                    PurchaseOrderModel.client_id == order.client_id,
                    PurchaseOrderModel.po_number == order.po_number,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.status = order.status.value
                existing.vendor_tax_id = order.vendor_tax_id
                existing.vendor_name = order.vendor_name
                existing.currency = order.currency
                existing.loaded_at = datetime.now(UTC)
                await self._session.execute(
                    delete(PurchaseOrderItemModel).where(
                        PurchaseOrderItemModel.purchase_order_id == existing.id
                    )
                )
                order_id = existing.id
            else:
                orm_order = PurchaseOrderModel(
                    id=order.id,
                    client_id=order.client_id,
                    po_number=order.po_number,
                    created_at=order.created_at,
                    status=order.status.value,
                    currency=order.currency,
                    vendor_tax_id=order.vendor_tax_id,
                    vendor_name=order.vendor_name,
                    loaded_at=order.loaded_at,
                )
                self._session.add(orm_order)
                await self._session.flush()
                order_id = orm_order.id

            self._session.add_all([
                PurchaseOrderItemModel(
                    id=item.id,
                    purchase_order_id=order_id,
                    line=item.line,
                    material=item.material,
                    description=item.description,
                    uom=item.uom,
                    quantity_ordered=item.quantity_ordered,
                    quantity_received=item.quantity_received,
                    unit_price=item.unit_price,
                    item_created_at=item.item_created_at,
                )
                for item in order.items
            ])

        if self._cache:
            await self._cache.delete(_cache_key(order.client_id, order.po_number))

    def _to_domain(self, orm: PurchaseOrderModel) -> PurchaseOrder:
        return PurchaseOrder(
            id=orm.id,
            client_id=orm.client_id,
            po_number=orm.po_number,
            created_at=orm.created_at,
            status=OrderStatus(orm.status),
            currency=orm.currency,
            vendor_tax_id=orm.vendor_tax_id,
            vendor_name=orm.vendor_name,
            loaded_at=orm.loaded_at,
            items=[self._item_to_domain(i) for i in orm.items],
        )

    def _item_to_domain(self, orm: PurchaseOrderItemModel) -> PurchaseOrderItem:
        return PurchaseOrderItem(
            id=orm.id,
            purchase_order_id=orm.purchase_order_id,
            line=orm.line,
            material=orm.material,
            description=orm.description,
            uom=orm.uom,
            quantity_ordered=orm.quantity_ordered,
            quantity_received=orm.quantity_received,
            unit_price=orm.unit_price,
            item_created_at=orm.item_created_at,
        )
