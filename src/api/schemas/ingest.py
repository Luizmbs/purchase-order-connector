from pydantic import BaseModel


class FieldChangeResponse(BaseModel):
    field: str
    before: str
    after: str


class OrderUpdateResponse(BaseModel):
    po_number: str
    client_id: str
    changes: list[FieldChangeResponse]


class IngestionResponse(BaseModel):
    ingested: int
    updated: int
    errors: list[dict]
    warnings: list[str]
    updates: list[OrderUpdateResponse]
