from datetime import datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    id: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    format_type: str


class ClientUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


class ClientResponse(BaseModel):
    id: str
    name: str
    format_type: str
    active: bool
    created_at: datetime
