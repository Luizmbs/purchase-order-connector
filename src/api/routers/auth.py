from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.auth_repository import AuthRepository
from api.schemas.auth import LoginRequest, LoginResponse, LogoutRequest, RefreshRequest, RefreshResponse
from infrastructure.config import settings
from infrastructure.database import get_session
from infrastructure.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    repo = AuthRepository(session)
    user = await repo.find_user_by_username(body.username)

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    if not user.active:
        raise HTTPException(status_code=403, detail="Usuário inativo")

    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    await repo.save_refresh_token(user.id, token_hash, expires_at)

    return LoginResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    repo = AuthRepository(session)
    token_hash = hash_refresh_token(body.refresh_token)
    stored = await repo.find_refresh_token(token_hash)

    if not stored:
        raise HTTPException(status_code=401, detail="Token inválido")
    if stored.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Token revogado")
    if stored.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Token expirado")

    user = await repo.find_user_by_id(stored.user_id)

    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return RefreshResponse(access_token=access_token)


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_session),
):
    repo = AuthRepository(session)
    await repo.revoke_refresh_token(hash_refresh_token(body.refresh_token))
