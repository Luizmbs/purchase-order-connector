import base64
import json
from datetime import datetime
from uuid import UUID


def encode_cursor(ts: datetime, id: UUID) -> str:
    payload = {"t": ts.isoformat(), "id": str(id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(payload["t"]), UUID(payload["id"])
