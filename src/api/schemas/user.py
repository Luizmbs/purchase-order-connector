from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from api.schemas.purchase_order import PaginationMeta, build_pagination


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(default="operator", pattern=r"^(admin|operator)$")


class UserUpdate(BaseModel):
    active: bool | None = None
    role: str | None = Field(None, pattern=r"^(admin|operator)$")


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: str
    active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    data: list[UserResponse]
    pagination: PaginationMeta
