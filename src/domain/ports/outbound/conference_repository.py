from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.models.conference import Conference, ConferenceResult


@dataclass
class ConferenceFilters:
    client_id: str | None = None
    result: ConferenceResult | None = None


class ConferenceRepository(ABC):
    @abstractmethod
    async def save(self, conference: Conference) -> None: ...

    @abstractmethod
    async def find_many(
        self, filters: ConferenceFilters, offset: int, limit: int
    ) -> tuple[list[Conference], int]: ...
