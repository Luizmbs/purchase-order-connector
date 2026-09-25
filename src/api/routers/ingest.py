from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

import adapters.clients  # noqa: F401 — garante registro dos adapters
from adapters.clients.base import ClientAdapter, InputFormat
from adapters.clients.registry import ClientAdapterRegistry
from api.dependencies import get_current_user
from api.schemas.ingest import IngestionResponse
from domain.services.ingestion_service import IngestionService
from infrastructure.container import get_ingestion_service

router = APIRouter(prefix="/api/v1", tags=["ingestão"])


async def _read_field(field: Any) -> str:
    if hasattr(field, "read"):
        return (await field.read()).decode("utf-8")
    return field


async def _extract_raw_data(adapter: ClientAdapter, request: Request) -> Any:
    if adapter.input_format == InputFormat.MULTIPART:
        form = await request.form()
        return {
            "cabecalho": await _read_field(form["cabecalho"]),
            "itens": await _read_field(form["itens"]),
        }
    return await request.json()


@router.post("/ingest/{client_id}", response_model=IngestionResponse)
async def ingest(
    client_id: str,
    request: Request,
    current_user=Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    try:
        adapter = ClientAdapterRegistry.get(client_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Cliente '{client_id}' não encontrado")

    raw_data = await _extract_raw_data(adapter, request)

    try:
        result = await service.ingest(adapter, raw_data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return IngestionResponse(
        ingested=result.ingested,
        updated=result.updated,
        errors=result.errors,
    )
