from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from api.dependencies import get_current_user
from api.schemas.purchase_order import (
    PurchaseOrderDetail,
    PurchaseOrderListResponse,
    PurchaseOrderSummary,
    build_pagination,
)
from domain.models.purchase_order import OrderStatus, PurchaseOrder
from domain.ports.outbound.purchase_order_repository import OrderFilters
from domain.services.purchase_order_service import PurchaseOrderService
from infrastructure.container import get_purchase_order_service

router = APIRouter(prefix="/api/v1", tags=["pedidos"])

_VALID_STATUSES = {s.value for s in OrderStatus}


def _to_summary(order: PurchaseOrder) -> PurchaseOrderSummary:
    return PurchaseOrderSummary(
        id=order.id,
        client_id=order.client_id,
        po_number=order.po_number,
        created_at=order.created_at,
        status=order.status.value,
        currency=order.currency,
        vendor_tax_id=order.vendor_tax_id,
        vendor_name=order.vendor_name,
        loaded_at=order.loaded_at,
        items_count=len(order.items),
        has_pending=order.has_pending_items,
    )


@router.get("/purchase-orders", response_model=PurchaseOrderListResponse)
async def list_purchase_orders(
    client_id: str | None = Query(None),
    vendor_tax_id: str | None = Query(None),
    status: str | None = Query(None),
    has_pending: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Status inválido. Valores aceitos: open, closed, blocked",
        )

    filters = OrderFilters(
        client_id=client_id,
        vendor_tax_id=vendor_tax_id,
        status=OrderStatus(status) if status else None,
        has_pending=has_pending,
    )

    orders, total = await service.list_orders(filters, page, page_size)

    return PurchaseOrderListResponse(
        data=[_to_summary(o) for o in orders],
        pagination=build_pagination(total, page, page_size),
    )


@router.get(
    "/purchase-orders/{client_id}/{po_number}",
    response_model=PurchaseOrderDetail,
)
async def get_purchase_order(
    client_id: str = Path(...),
    po_number: str = Path(...),
    response: Response = None,
    _=Depends(get_current_user),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    order, from_cache = await service.get_order(client_id, po_number)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pedido '{po_number}' não encontrado para o cliente '{client_id}'",
        )
    response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
    return PurchaseOrderDetail.model_validate(order)
