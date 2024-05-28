from abc import ABC, abstractmethod
from typing import Generic, Iterable

from ommi.drivers.driver_types import TConn, TModel
from ommi.drivers.database_results import AsyncResultWrapper


class AddAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn):
        self._connection = connection

    def __call__(self, *items: TModel) -> AsyncResultWrapper[Iterable[TModel]]:
        return self.items(*items)

    @abstractmethod
    def items(self, *items: TModel) -> AsyncResultWrapper[Iterable[TModel]]:
        ...
