from adapters.clients.base import ClientAdapter


class ClientAdapterRegistry:
    _registry: dict[str, type[ClientAdapter]] = {}

    @classmethod
    def register(cls, client_id: str, adapter_cls: type[ClientAdapter]) -> None:
        cls._registry[client_id] = adapter_cls

    @classmethod
    def get(cls, client_id: str) -> ClientAdapter:
        if client_id not in cls._registry:
            raise ValueError(f"Adapter não registrado para o cliente '{client_id}'")
        return cls._registry[client_id]()

    @classmethod
    def registered_clients(cls) -> list[str]:
        return list(cls._registry.keys())
