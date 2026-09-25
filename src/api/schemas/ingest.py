from pydantic import BaseModel


class IngestionResponse(BaseModel):
    ingested: int
    updated: int
    errors: list[dict]
