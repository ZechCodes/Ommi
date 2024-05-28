from typing import Generic, Sequence, Type, TypeAlias
from abc import ABC, abstractmethod

from ommi.drivers.driver_types import TConn, TModel

from ommi.drivers.database_results import AsyncResultWrapper
import ommi.query_ast

Predicate: TypeAlias = "ommi.query_ast.ASTGroupNode | Type[TModel] | bool"


class DeleteAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn, predicates: Sequence[Predicate]):
        self._connection = connection
        self._predicates = predicates

    def __call__(self) -> AsyncResultWrapper[bool]:
        return self.delete()

    @abstractmethod
    def delete(self) -> AsyncResultWrapper[bool]:
        ...
