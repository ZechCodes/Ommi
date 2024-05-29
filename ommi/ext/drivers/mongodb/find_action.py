from typing import Sequence, Type

from ommi.drivers.count_actions import CountAction
from ommi.drivers.delete_actions import DeleteAction
from ommi.drivers.driver_types import TModel, TConn
from ommi.drivers.fetch_actions import FetchAction
from ommi.drivers.find_actions import FindAction
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.count_action import MongoDBCountAction
from ommi.ext.drivers.mongodb.delete_action import MongoDBDeleteAction
from ommi.ext.drivers.mongodb.fetch_action import MongoDBFetchAction
from ommi.ext.drivers.mongodb.set_fields_action import MongoDBSetFieldsAction
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode

Predicate = ASTGroupNode | Type[OmmiModel] | bool


class MongoDBFindAction(FindAction[MongoDBConnection, OmmiModel]):
    _count_action = MongoDBCountAction
    _delete_action = MongoDBDeleteAction
    _fetch_action = MongoDBFetchAction
    _set_fields_action = MongoDBSetFieldsAction

    def __init__(self, connection: MongoDBConnection, predicates: Sequence[Predicate], database):
        super().__init__(connection, predicates)
        self._db = database

    @property
    def count(self) -> CountAction[TConn, TModel]:
        return self._count_action(self._connection, self._predicates, self._db)

    @property
    def delete(self) -> DeleteAction[TConn, TModel]:
        return self._delete_action(self._connection, self._predicates, self._db)

    @property
    def fetch(self) -> FetchAction[TConn, TModel]:
        return self._fetch_action(self._connection, self._predicates, self._db)

    @property
    def set(self) -> SetFieldsAction[TConn, TModel]:
        return self._set_fields_action(self._connection, self._predicates, self._db)
