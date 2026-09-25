import structlog

from adapters.clients.base import ClientAdapter
from adapters.persistence.cache_service import CacheService
from domain.ports.outbound.purchase_order_repository import PurchaseOrderRepository

log = structlog.get_logger()


class IngestionResult:
    def __init__(self, ingested: int, updated: int, errors: list[dict]):
        self.ingested = ingested
        self.updated = updated
        self.errors = errors


class IngestionService:
    def __init__(self, order_repo: PurchaseOrderRepository, cache: CacheService):
        self._repo = order_repo
        self._cache = cache

    async def ingest(self, adapter: ClientAdapter, raw_data) -> IngestionResult:
        orders = adapter.parse(raw_data)

        ingested = 0
        updated = 0
        errors = []
        client_id = None

        for order in orders:
            client_id = order.client_id
            try:
                existing = await self._repo.find_by_client_and_number(
                    order.client_id, order.po_number
                )
                await self._repo.upsert(order)
                if existing:
                    updated += 1
                else:
                    ingested += 1
            except Exception as e:
                errors.append({"po_number": order.po_number, "error": str(e)})
                log.error("ingest.item_error", po_number=order.po_number, error=str(e))

        if client_id:
            await self._cache.delete_pattern(f"po:{client_id}:*")

        log.info(
            "ingest.completed",
            client_id=client_id or "unknown",
            ingested=ingested,
            updated=updated,
            errors=len(errors),
        )

        return IngestionResult(ingested=ingested, updated=updated, errors=errors)
