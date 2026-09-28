import math
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


def build_pagination(total: int, page: int, page_size: int) -> PaginationMeta:
    total_pages = max(1, math.ceil(total / page_size))
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


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
