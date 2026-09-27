import dataclasses

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user
from api.schemas.conference import (
    ConferenceRequest,
    ConferenceResponse,
    DivergenceResponse,
)
from domain.models.invoice import Invoice, InvoiceItem
from domain.services.conference_service import ConferenceService
from infrastructure.container import get_conference_service

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
