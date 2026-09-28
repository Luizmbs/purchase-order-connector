from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.cache_service import CacheService
from adapters.persistence.client_repository import ClientRepository
from api.dependencies import require_admin
from api.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from infrastructure.database import get_redis, get_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin — clientes"])

_CACHE_KEY = "clients:all"
_CACHE_TTL = 300


@router.get("/clients", response_model=list[ClientResponse])
async def list_clients(
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    cache = CacheService(redis)
    cached = await cache.get(_CACHE_KEY)
    if cached:
        import json
        return json.loads(cached)

    repo = ClientRepository(session)
    clients = await repo.find_all()
    result = [ClientResponse.model_validate(c, from_attributes=True) for c in clients]

    import json
    await cache.set(_CACHE_KEY, json.dumps([r.model_dump(mode="json") for r in result]), _CACHE_TTL)

    return result


@router.post("/clients", response_model=ClientResponse, status_code=201)
async def create_client(
    body: ClientCreate,
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    repo = ClientRepository(session)
    existing = await repo.find_by_id(body.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Cliente '{body.id}' já existe")

    client = await repo.create(body.id, body.name, body.format_type)

    cache = CacheService(redis)
    await cache.delete(_CACHE_KEY)

    return ClientResponse.model_validate(client, from_attributes=True)


@router.patch("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    body: ClientUpdate,
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    repo = ClientRepository(session)
    data = body.model_dump(exclude_none=True)
    client = await repo.update(client_id, data)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Cliente '{client_id}' não encontrado")

    cache = CacheService(redis)
    await cache.delete(_CACHE_KEY)

    return ClientResponse.model_validate(client, from_attributes=True)
