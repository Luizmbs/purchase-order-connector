from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.user_repository import UserRepository
from api.dependencies import get_current_user, require_admin
from api.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate, build_pagination
from infrastructure.database import get_session
from infrastructure.security import UserPayload, hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin — usuários"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    repo = UserRepository(session)
    offset = (page - 1) * page_size
    users, total = await repo.find_all(offset, page_size)
    return UserListResponse(
        data=[UserResponse.model_validate(u, from_attributes=True) for u in users],
        pagination=build_pagination(total, page, page_size),
    )


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    repo = UserRepository(session)

    if await repo.find_by_username(body.username):
        raise HTTPException(status_code=409, detail="Username já está em uso")
    if await repo.find_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email já está em uso")

    user = await repo.create(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    return UserResponse.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    current_user: UserPayload = Depends(get_current_user),
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if str(user_id) == current_user.user_id:
        if body.active is False:
            raise HTTPException(status_code=422, detail="Admin não pode se auto-desativar")
        if body.role == "operator":
            raise HTTPException(status_code=422, detail="Admin não pode rebaixar a própria role")

    repo = UserRepository(session)
    data = body.model_dump(exclude_none=True)
    user = await repo.update(user_id, data)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Usuário '{user_id}' não encontrado")

    return UserResponse.model_validate(user, from_attributes=True)
