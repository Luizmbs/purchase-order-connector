import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user
from api.schemas.conference import (
    ConferenceListResponse,
    ConferenceRequest,
    ConferenceResponse,
    ConferenceSummary,
    DivergenceResponse,
    build_pagination,
)
from domain.models.conference import Conference, ConferenceResult
from domain.models.invoice import Invoice, InvoiceItem
from domain.ports.outbound.conference_repository import ConferenceFilters
from domain.services.conference_service import ConferenceService
from infrastructure.container import get_conference_service

_VALID_RESULTS = {r.value for r in ConferenceResult}

router = APIRouter(prefix="/api/v1", tags=["conferências"])


@router.post("/conferences", response_model=ConferenceResponse, status_code=201)
async def check_invoice(
    body: ConferenceRequest,
    _=Depends(get_current_user),
    service: ConferenceService = Depends(get_conference_service),
):
    invoice = Invoice(
        client_id=body.client_id,
        po_number=body.po_number,
        invoice_number=body.invoice_number,
        vendor_tax_id=body.vendor_tax_id,
        items=[
            InvoiceItem(
                material=item.material,
                quantity=item.quantity,
                total_value=item.total_value,
            )
            for item in body.items
        ],
    )

    conference = await service.check_invoice(invoice)

    return ConferenceResponse(
        conference_id=conference.id,
        result=conference.result.value,
        divergences=[
            DivergenceResponse(**dataclasses.asdict(d))
            for d in conference.divergences
        ],
    )


def _to_summary(c: Conference) -> ConferenceSummary:
    return ConferenceSummary(
        id=c.id,
        client_id=c.client_id,
        po_number=c.po_number,
        invoice_number=c.invoice_number,
        vendor_tax_id=c.vendor_tax_id,
        result=c.result.value,
        checked_at=c.checked_at,
        divergences_count=len(c.divergences),
        divergence_types=list({d.type.value for d in c.divergences}),
    )


@router.get("/conferences", response_model=ConferenceListResponse)
async def list_conferences(
    client_id: str | None = Query(None),
    result: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _=Depends(get_current_user),
    service: ConferenceService = Depends(get_conference_service),
):
    if result and result not in _VALID_RESULTS:
        raise HTTPException(
            status_code=422,
            detail="Resultado inválido. Valores aceitos: approved, rejected",
        )

    filters = ConferenceFilters(
        client_id=client_id,
        result=ConferenceResult(result) if result else None,
    )

    conferences, total = await service.list_conferences(filters, page, page_size)

    return ConferenceListResponse(
        data=[_to_summary(c) for c in conferences],
        pagination=build_pagination(total, page, page_size),
    )
