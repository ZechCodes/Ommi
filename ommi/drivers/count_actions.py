from abc import ABC, abstractmethod
from typing import Generic, Sequence, Type, TypeAlias

from ommi.drivers.driver_types import TConn, TModel

from ommi.drivers.database_results import AsyncResultWrapper
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class CountAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn, predicates: Sequence[Predicate]):
        self._connection = connection
        self._predicates = predicates

    def __call__(self) -> AsyncResultWrapper[int]:
        return self.count()

    @abstractmethod
    def count(self) -> AsyncResultWrapper[int]:
        ...
