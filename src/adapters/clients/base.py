from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from domain.models.purchase_order import PurchaseOrder, PurchaseOrderItem


class InputFormat(Enum):
    JSON = "json"
    MULTIPART = "multipart"


@dataclass
class ParseResult:
    orders: list[PurchaseOrder]
    warnings: list[str] = field(default_factory=list)
    # Itens cujo pedido não veio no payload atual (ex: Delta com duas queries defasadas).
    # O service resolve: se o pedido existe no banco, atualiza; senão, descarta com warning.
    orphan_items: dict[str, list[PurchaseOrderItem]] = field(default_factory=dict)


class ClientAdapter(ABC):
    input_format: InputFormat = InputFormat.JSON

    @abstractmethod
    def parse(self, raw_data: any) -> ParseResult:
        """
        Recebe dados brutos no formato do cliente e retorna ParseResult com
        pedidos normalizados e avisos não bloqueantes (ex: itens órfãos descartados).
        Lança ValueError para dados inválidos ou malformados.
        """
        ...
