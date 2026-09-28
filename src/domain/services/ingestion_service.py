import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from adapters.clients.base import ClientAdapter
from adapters.persistence.cache_service import CacheService
from domain.models.purchase_order import PurchaseOrder
from domain.ports.outbound.purchase_order_repository import PurchaseOrderRepository

log = structlog.get_logger()


@dataclass
class FieldChange:
    field: str
    before: str
    after: str


@dataclass
class OrderUpdate:
    po_number: str
    client_id: str
    changes: list[FieldChange] = field(default_factory=list)


def _diff_orders(existing: PurchaseOrder, new_order: PurchaseOrder) -> list[FieldChange]:
    changes: list[FieldChange] = []

    if existing.status != new_order.status:
        changes.append(FieldChange("status", existing.status.value, new_order.status.value))
    if existing.vendor_tax_id != new_order.vendor_tax_id:
        changes.append(FieldChange("vendor_tax_id", existing.vendor_tax_id, new_order.vendor_tax_id))
    if existing.vendor_name != new_order.vendor_name:
        changes.append(FieldChange("vendor_name", str(existing.vendor_name), str(new_order.vendor_name)))
    if existing.currency != new_order.currency:
        changes.append(FieldChange("currency", existing.currency, new_order.currency))

    existing_by_line = {item.line: item for item in existing.items}
    new_by_line = {item.line: item for item in new_order.items}

    for line, new_item in new_by_line.items():
        if line not in existing_by_line:
            changes.append(FieldChange(
                f"item.linha_{line}",
                "ausente",
                f"adicionado (material={new_item.material})",
            ))
        else:
            old = existing_by_line[line]
            if old.quantity_ordered != new_item.quantity_ordered:
                changes.append(FieldChange(
                    f"item.linha_{line}.quantity_ordered",
                    str(old.quantity_ordered),
                    str(new_item.quantity_ordered),
                ))
            if old.quantity_received != new_item.quantity_received:
                changes.append(FieldChange(
                    f"item.linha_{line}.quantity_received",
                    str(old.quantity_received),
                    str(new_item.quantity_received),
                ))
            if old.unit_price != new_item.unit_price:
                changes.append(FieldChange(
                    f"item.linha_{line}.unit_price",
                    str(old.unit_price),
                    str(new_item.unit_price),
                ))

    for line, old_item in existing_by_line.items():
        if line not in new_by_line:
            changes.append(FieldChange(
                f"item.linha_{line}",
                f"material={old_item.material}",
                "removido",
            ))

    return changes


class IngestionResult:
    def __init__(
        self,
        ingested: int,
        updated: int,
        errors: list[dict],
        warnings: list[str],
        updates: list[OrderUpdate],
    ):
        self.ingested = ingested
        self.updated = updated
        self.errors = errors
        self.warnings = warnings
        self.updates = updates


class IngestionService:
    def __init__(self, order_repo: PurchaseOrderRepository, cache: CacheService):
        self._repo = order_repo
        self._cache = cache

    async def ingest(self, adapter: ClientAdapter, raw_data) -> IngestionResult:
        parse_result = adapter.parse(raw_data)

        client_id = getattr(adapter, "CLIENT_ID", None) or (
            parse_result.orders[0].client_id if parse_result.orders else "unknown"
        )

        log.info(
            "ingest.start",
            client_id=client_id,
            orders_count=len(parse_result.orders),
        )

        for warning in parse_result.warnings:
            log.warning("ingest.parse_warning", client_id=client_id, detail=warning)

        ingested = 0
        updated = 0
        errors = []
        order_updates: list[OrderUpdate] = []

        for order in parse_result.orders:
            try:
                existing, _ = await self._repo.find_by_client_and_number(
                    order.client_id, order.po_number
                )
                await self._repo.upsert(order)
                if existing:
                    updated += 1
                    changes = _diff_orders(existing, order)
                    order_updates.append(OrderUpdate(
                        po_number=order.po_number,
                        client_id=order.client_id,
                        changes=changes,
                    ))
                    log.info(
                        "ingest.order_updated",
                        client_id=order.client_id,
                        po_number=order.po_number,
                        changes_count=len(changes),
                    )
                else:
                    ingested += 1
                    log.info(
                        "ingest.order_created",
                        client_id=order.client_id,
                        po_number=order.po_number,
                    )
            except Exception as e:
                errors.append({"po_number": order.po_number, "error": str(e)})
                log.error(
                    "ingest.order_error",
                    client_id=order.client_id,
                    po_number=order.po_number,
                    error=str(e),
                )

        # Resolve itens órfãos (pedido não veio no payload mas pode existir no banco)
        for po_number, orphan_items in parse_result.orphan_items.items():
            try:
                existing, _ = await self._repo.find_by_client_and_number(client_id, po_number)
                if existing is None:
                    warning = (
                        f"Itens do pedido '{po_number}' descartados: "
                        f"pedido não encontrado no banco nem no payload"
                    )
                    parse_result.warnings.append(warning)
                    log.warning("ingest.orphan_discarded", client_id=client_id, po_number=po_number)
                else:
                    # Mescla por linha: preserva itens existentes, adiciona/sobrescreve pelos órfãos
                    merged_by_line = {item.line: item for item in existing.items}
                    for item in orphan_items:
                        merged_by_line[item.line] = dataclasses.replace(
                            item, purchase_order_id=existing.id
                        )
                    updated_order = dataclasses.replace(
                        existing,
                        items=list(merged_by_line.values()),
                        loaded_at=datetime.now(timezone.utc),
                    )
                    changes = _diff_orders(existing, updated_order)
                    await self._repo.upsert(updated_order)
                    updated += 1
                    order_updates.append(OrderUpdate(
                        po_number=po_number,
                        client_id=client_id,
                        changes=changes,
                    ))
                    log.info(
                        "ingest.order_updated",
                        client_id=client_id,
                        po_number=po_number,
                        changes_count=len(changes),
                    )
            except Exception as e:
                errors.append({"po_number": po_number, "error": str(e)})
                log.error("ingest.order_error", client_id=client_id, po_number=po_number, error=str(e))

        if parse_result.orders or parse_result.orphan_items:
            await self._cache.delete_pattern(f"po:{client_id}:*")

        log.info(
            "ingest.completed",
            client_id=client_id,
            ingested=ingested,
            updated=updated,
            errors=len(errors),
            warnings=len(parse_result.warnings),
        )

        return IngestionResult(
            ingested=ingested,
            updated=updated,
            errors=errors,
            warnings=parse_result.warnings,
            updates=order_updates,
        )
