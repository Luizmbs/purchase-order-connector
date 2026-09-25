from abc import ABC, abstractmethod
from enum import Enum

from domain.models.purchase_order import PurchaseOrder


class InputFormat(Enum):
    JSON = "json"
    MULTIPART = "multipart"


class ClientAdapter(ABC):
    input_format: InputFormat = InputFormat.JSON

    @abstractmethod
    def parse(self, raw_data: any) -> list[PurchaseOrder]:
        """
        Recebe dados brutos no formato do cliente e retorna PurchaseOrders normalizados.
        Lança ValueError para dados inválidos ou malformados.
        """
        ...
