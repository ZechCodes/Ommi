from typing import Generic, Type, Sequence, TypeAlias

from ommi.drivers.count_actions import CountAction
from ommi.drivers.delete_actions import DeleteAction
from ommi.drivers.driver_types import TConn, TModel
from ommi.drivers.fetch_actions import FetchAction
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class FindAction(Generic[TConn, TModel]):
    _count_action: Type[CountAction[TConn, TModel]]
    _delete_action: Type[DeleteAction[TConn, TModel]]
    _fetch_action: Type[FetchAction[TConn, TModel]]
    _set_fields_action: Type[SetFieldsAction[TConn, TModel]]

    def __init__(
        self,
        connection: TConn,
        predicates: Sequence[Predicate],
    ):
        self._connection = connection
        self._predicates = predicates

    @property
    def count(self) -> CountAction[TConn, TModel]:
        return self._count_action(self._connection, self._predicates)

    @property
    def delete(self) -> DeleteAction[TConn, TModel]:
        return self._delete_action(self._connection, self._predicates)

    @property
    def fetch(self) -> FetchAction[TConn, TModel]:
        return self._fetch_action(self._connection, self._predicates)

    @property
    def set(self) -> SetFieldsAction[TConn, TModel]:
        return self._set_fields_action(self._connection, self._predicates)
