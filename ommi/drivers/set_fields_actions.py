from typing import Generic, Sequence, Any, TypeAlias, Type
from abc import ABC, abstractmethod

from ommi.drivers.database_results import AsyncResultWrapper
from ommi.drivers.driver_types import TConn, TModel
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class SetFieldsAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn, predicates: Sequence[Predicate]):
        self._connection = connection
        self._predicates = predicates

    def __call__(self, **kwargs: Any) -> AsyncResultWrapper[bool]:
        return self.set_fields(**kwargs)

    @abstractmethod
    def set_fields(self, **kwargs: Any) -> AsyncResultWrapper[bool]:
        ...
